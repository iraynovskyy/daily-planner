"""Login: password hashing, invites, the current-user dependency, login rate limiting and CSRF
protection."""

import datetime as dt
import hashlib
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request
from sqlmodel import Session, col, select
from starlette.types import ASGIApp, Receive, Scope, Send

from app import services
from app.config import BASE_DIR
from app.models import Invite, User

MIN_PASSWORD_LENGTH = 12

# argon2id with the library's defaults (OWASP-recommended). Each hash embeds its own random salt.
_hasher = PasswordHasher()
# Verified when the username doesn't exist, so a wrong username takes as long as a wrong password
# and response times don't reveal which usernames exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError, InvalidHashError:
        return False


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        verify_password(_DUMMY_HASH, password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    if _hasher.check_needs_rehash(user.password_hash):  # hashing parameters got stronger
        user.password_hash = hash_password(password)
        session.add(user)
        session.commit()
    return user


def create_user(
    session: Session, username: str, password: str, seed_file: Path | None = None
) -> User:
    """New login with its own starter categories, habits and notes (see services.seed_user)."""
    username = username.strip()
    if not username:
        raise ValueError("Username must not be empty.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if session.exec(select(User).where(User.username == username)).first():
        raise ValueError("That username is already taken.")
    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    services.seed_user(session, user.id, seed_file)  # commits the user and the seed together
    session.refresh(user)
    return user


def set_password(session: Session, username: str, password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise ValueError(f"No user {username!r}.")
    user.password_hash = hash_password(password)
    session.add(user)
    session.commit()


def change_password(session: Session, user_id: int, current: str, new: str) -> None:
    """New password for a logged-in user who knows the current one. ValueError if not."""
    user = session.get(User, user_id)
    if user is None or not verify_password(user.password_hash, current):
        raise ValueError("The current password isn't right.")
    if len(new) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"The new password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if new == current:
        raise ValueError("The new password is the same as the current one.")
    user.password_hash = hash_password(new)
    session.add(user)
    session.commit()


def has_users(session: Session) -> bool:
    return session.exec(select(User.id)).first() is not None


# --- invites ------------------------------------------------------------------------------------

INVITE_DAYS = 7
# Friends who join by invite start from the neutral example set, never the owner's local seed.
INVITE_SEED = BASE_DIR / "seed.example.toml"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(value: dt.datetime) -> dt.datetime:
    # SQLite hands datetimes back without a timezone; they are stored in UTC.
    return value if value.tzinfo else value.replace(tzinfo=dt.UTC)


def create_invite(session: Session, user_id: int) -> str:
    """New one-time sign-up token (valid INVITE_DAYS). Returned once; only its hash is kept."""
    token = secrets.token_urlsafe(24)
    now = dt.datetime.now(dt.UTC)
    session.add(
        Invite(
            token_hash=_token_hash(token),
            created_by=user_id,
            created_at=now,
            expires_at=now + dt.timedelta(days=INVITE_DAYS),
        )
    )
    session.commit()
    return token


def find_invite(session: Session, token: str) -> Invite | None:
    """The invite for this token if it is still usable (not used, not expired)."""
    invite = session.exec(select(Invite).where(Invite.token_hash == _token_hash(token))).first()
    if invite is None or invite.used_at is not None:
        return None
    return invite if _utc(invite.expires_at) > dt.datetime.now(dt.UTC) else None


def pending_invites(session: Session, user_id: int) -> list[Invite]:
    """Unused, unexpired invites this user created, newest first."""
    stmt = (
        select(Invite)
        .where(Invite.created_by == user_id, col(Invite.used_at).is_(None))
        .order_by(col(Invite.id).desc())
    )
    now = dt.datetime.now(dt.UTC)
    return [i for i in session.exec(stmt) if _utc(i.expires_at) > now]


def revoke_invite(session: Session, user_id: int, invite_id: int) -> bool:
    invite = session.get(Invite, invite_id)
    if invite is None or invite.created_by != user_id or invite.used_at is not None:
        return False
    session.delete(invite)
    session.commit()
    return True


def register(session: Session, token: str, username: str, password: str) -> User:
    """Uses up an invite and creates the user in one transaction. ValueError if either fails."""
    invite = find_invite(session, token)
    if invite is None:
        raise ValueError("This invite link is invalid, expired or already used.")
    invite.used_at = dt.datetime.now(dt.UTC)
    try:
        user = create_user(session, username, password, INVITE_SEED)
    except ValueError:
        session.rollback()
        raise
    invite.used_by = user.id
    session.commit()
    return user


# --- current user -------------------------------------------------------------------------------


class NotAuthenticated(Exception):
    """Raised by `require_user`; turned into a redirect to /login by the app's exception handler."""


def current_user_id(request: Request) -> int | None:
    return request.session.get("user_id")


def require_user(request: Request) -> int:
    """Router dependency: lets the request through only with a logged-in session."""
    user_id = current_user_id(request)
    if user_id is None:
        raise NotAuthenticated
    return user_id


def safe_next(url: str | None) -> str:
    """Where to go after login: only same-site paths, never another host ("open redirect")."""
    # Browsers read "\" as "/", so "/\evil.com" means "//evil.com"; control characters can be
    # stripped by browsers too. Reject both along with anything that has a host.
    if (
        not url
        or not url.startswith("/")
        or url.startswith("//")
        or "\\" in url
        or any(ord(c) < 0x20 for c in url)
        or urlsplit(url).netloc
    ):
        return "/"
    return url


# --- login rate limiting ------------------------------------------------------------------------


class LoginRateLimiter:
    """Allows `limit` failed logins per `window` seconds, per client IP and per username.

    In memory, so it resets on restart and isn't shared between processes; enough for one
    app instance behind one proxy.
    """

    def __init__(self, limit: int = 5, window: float = 15 * 60) -> None:
        self.limit = limit
        self.window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str, now: float) -> deque[float]:
        failures = self._failures[key]
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        return failures

    def retry_after(self, ip: str, username: str) -> int:
        """Seconds until another attempt is allowed; 0 if allowed now."""
        now = time.monotonic()
        waits = [
            self.window - (now - failures[0])
            for key in (f"ip:{ip}", f"user:{username.lower()}")
            if len(failures := self._recent(key, now)) >= self.limit
        ]
        return int(max(waits, default=0)) + (1 if waits else 0)

    def failed(self, ip: str, username: str) -> None:
        now = time.monotonic()
        for key in (f"ip:{ip}", f"user:{username.lower()}"):
            self._recent(key, now).append(now)

    def succeeded(self, ip: str, username: str) -> None:
        self._failures.pop(f"ip:{ip}", None)
        self._failures.pop(f"user:{username.lower()}", None)

    def reset(self) -> None:
        self._failures.clear()


login_limiter = LoginRateLimiter()


# --- CSRF ---------------------------------------------------------------------------------------


class CSRFMiddleware:
    """Rejects state-changing requests (POST, PUT, …) that a browser sent from another site.

    Browsers label every request with `Sec-Fetch-Site` (same-origin / same-site / cross-site /
    none) and send `Origin` on POSTs; neither can be set by a page's JavaScript. Together with
    SameSite=Lax session cookies this blocks CSRF without per-form tokens, so plain forms, HTMX
    and fetch() calls are all covered. Requests with neither header (curl, tests) aren't from a
    browser, so they can't carry a victim's cookies by accident and are let through.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in self.SAFE_METHODS or self._allowed(scope):
            await self.app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"Cross-site request blocked."})

    @staticmethod
    def _allowed(scope: Scope) -> bool:
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site is not None:
            return fetch_site in ("same-origin", "none")  # "none": typed URL / bookmark
        origin = headers.get("origin")
        if origin is None:
            return True
        # Older browsers: compare Origin with Host. "null" (sandboxed pages) never matches.
        return urlsplit(origin).netloc == headers.get("host")
