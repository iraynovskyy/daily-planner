import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session

from app import auth, services
from app.db import get_session
from app.models import User
from app.templating import templates

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[int, Depends(auth.require_user)]


def _client_ip(request: Request) -> str:
    # Behind Nginx, uvicorn's --proxy-headers puts the real client address here.
    return request.client.host if request.client else "unknown"


def _login_page(
    request: Request,
    session: Session,
    *,
    error: str | None = None,
    username: str = "",
    next_url: str = "/",
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": error,
            "username": username,
            "next": next_url,
            "no_users": not auth.has_users(session),
        },
        status_code=status_code,
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: SessionDep, next: str = "/") -> Response:
    if auth.current_user_id(request) is not None:
        return RedirectResponse(auth.safe_next(next), status_code=303)
    return _login_page(request, session, next_url=auth.safe_next(next))


@router.post("/login")
def login(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form(max_length=50)],
    password: Annotated[str, Form(max_length=200)],
    next: Annotated[str, Form()] = "/",
) -> Response:
    ip, next_url = _client_ip(request), auth.safe_next(next)
    if wait := auth.login_limiter.retry_after(ip, username):
        return _login_page(
            request,
            session,
            username=username,
            next_url=next_url,
            status_code=429,
            error=f"Too many failed attempts. Try again in {wait // 60 + 1} min.",
        )
    user = auth.authenticate(session, username, password)
    if user is None:
        auth.login_limiter.failed(ip, username)
        # Same message for unknown user and wrong password: don't reveal which usernames exist.
        return _login_page(
            request,
            session,
            username=username,
            next_url=next_url,
            status_code=401,
            error="Wrong username or password.",
        )
    auth.login_limiter.succeeded(ip, username)
    request.session.clear()  # fresh session on login (no session fixation)
    request.session["user_id"] = user.id
    return RedirectResponse(next_url, status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- account & invites --------------------------------------------------------------------------


def _account_page(
    request: Request,
    session: Session,
    user: int,
    *,
    invite_token: str | None = None,
    password_error: str | None = None,
    password_changed: bool = False,
    status_code: int = 200,
) -> Response:
    path = request.app.url_path_for("join_form", token=invite_token) if invite_token else None
    return templates.TemplateResponse(
        request,
        "account.html",
        {
            "user": session.get(User, user),
            "invites": auth.pending_invites(session, user),
            "invite_path": path,
            "invite_url": str(request.base_url).rstrip("/") + path if path else None,
            "invite_days": auth.INVITE_DAYS,
            "password_error": password_error,
            "password_changed": password_changed,
            "min_password": auth.MIN_PASSWORD_LENGTH,
        },
        status_code=status_code,
    )


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, session: SessionDep, user: UserDep) -> Response:
    return _account_page(request, session, user)


@router.post("/account/invites", response_class=HTMLResponse)
def create_invite(request: Request, session: SessionDep, user: UserDep) -> Response:
    """Shows the new link once: only its hash is stored, so it can't be displayed again."""
    return _account_page(request, session, user, invite_token=auth.create_invite(session, user))


@router.post("/account/invites/{invite_id}/revoke")
def revoke_invite(invite_id: int, session: SessionDep, user: UserDep) -> RedirectResponse:
    if not auth.revoke_invite(session, user, invite_id):
        raise HTTPException(404, "Invite not found")
    return RedirectResponse("/account", status_code=303)


def _join_page(
    request: Request,
    session: Session,
    token: str,
    *,
    error: str | None = None,
    username: str = "",
    status_code: int = 200,
) -> Response:
    valid = auth.find_invite(session, token) is not None
    return templates.TemplateResponse(
        request,
        "join.html",
        {
            "token": token,
            "valid": valid,
            "error": error,
            "username": username,
            "min_password": auth.MIN_PASSWORD_LENGTH,
        },
        status_code=status_code if valid else 404,
    )


@router.get("/join/{token}", response_class=HTMLResponse)
def join_form(request: Request, token: str, session: SessionDep) -> Response:
    return _join_page(request, session, token)


@router.post("/join/{token}")
def join(
    request: Request,
    token: str,
    session: SessionDep,
    username: Annotated[str, Form(max_length=50)],
    password: Annotated[str, Form(max_length=200)],
    password_repeat: Annotated[str, Form(max_length=200)],
) -> Response:
    if password != password_repeat:
        error = "Passwords don't match."
    else:
        try:
            user = auth.register(session, token, username, password)
        except ValueError as e:
            error = str(e)
        else:
            request.session.clear()  # log the new user in, in a fresh session
            request.session["user_id"] = user.id
            return RedirectResponse("/", status_code=303)
    return _join_page(request, session, token, error=error, username=username, status_code=400)


@router.post("/account/password", response_class=HTMLResponse)
def change_password(
    request: Request,
    session: SessionDep,
    user: UserDep,
    current_password: Annotated[str, Form(max_length=200)],
    new_password: Annotated[str, Form(max_length=200)],
    new_password_repeat: Annotated[str, Form(max_length=200)],
) -> Response:
    """Needs the current password; wrong guesses count like failed logins (rate limited)."""
    ip, username = _client_ip(request), session.get(User, user).username
    error = None
    if wait := auth.login_limiter.retry_after(ip, username):
        error = f"Too many wrong passwords. Try again in {wait // 60 + 1} min."
    elif new_password != new_password_repeat:
        error = "The new passwords don't match."
    else:
        try:
            auth.change_password(session, user, current_password, new_password)
        except ValueError as e:
            error = str(e)
            if "current password" in error:
                auth.login_limiter.failed(ip, username)
    if error:
        return _account_page(request, session, user, password_error=error, status_code=400)
    auth.login_limiter.succeeded(ip, username)
    request.session.clear()  # fresh session after a credential change
    request.session["user_id"] = user
    return _account_page(request, session, user, password_changed=True)


@router.get("/account/export.csv")
def export_csv(session: SessionDep, user: UserDep) -> Response:
    """All ticked habit-days as a CSV (with a BOM so Excel reads non-English names right)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "category", "habit", "done", "target", "golden"])
    writer.writerows(services.export_rows(session, user))
    name = session.get(User, user).username
    filename = f"daily-planner-{name}-{date.today()}.csv"
    return Response(
        "\ufeff" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
