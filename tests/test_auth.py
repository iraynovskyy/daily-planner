import datetime as dt
import re

import pytest
from sqlmodel import select

from app import auth, create_user
from app.models import Category, DailyEntry, Habit, Invite, Note, User
from tests.conftest import PASSWORD, USERNAME


def login(client, username=USERNAME, password=PASSWORD, **data):
    return client.post(
        "/login", data={"username": username, "password": password, **data}, follow_redirects=False
    )


# --- everything is behind the login -------------------------------------------------------------


@pytest.mark.parametrize("url", ["/", "/month/2026-09", "/day/2026-09-27", "/habits", "/account"])
def test_pages_redirect_to_login(anon_client, url):
    r = anon_client.get(url, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")


def test_changes_are_refused_without_login(anon_client, session):
    r = anon_client.post("/entries/1/2026-09-27", data={"count": 1})
    assert r.status_code == 401
    htmx = anon_client.post("/entries/1/2026-09-27", data={"count": 1}, headers={"HX-Request": "1"})
    assert htmx.status_code == 401 and htmx.headers["HX-Redirect"] == "/login"
    assert session.exec(select(DailyEntry)).first() is None  # nothing was saved


@pytest.mark.parametrize("url", ["/login", "/health", "/static/style.css"])
def test_public_urls(anon_client, url):
    assert anon_client.get(url).status_code == 200


# --- logging in and out -------------------------------------------------------------------------


def test_login_then_logout(anon_client):
    r = login(anon_client, next="/habits")
    assert r.status_code == 303 and r.headers["location"] == "/habits"
    assert anon_client.get("/habits").status_code == 200
    assert anon_client.post("/logout", follow_redirects=False).headers["location"] == "/login"
    assert anon_client.get("/habits", follow_redirects=False).status_code == 303


def test_logout_needs_post(client):
    # A GET logout could be triggered by any <img src="/logout"> on another site.
    assert client.get("/logout").status_code == 405


def test_wrong_password_and_unknown_user_look_the_same(anon_client):
    wrong_password = login(anon_client, password="nope nope nope")
    unknown_user = login(anon_client, username="nobody")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert "Wrong username or password." in wrong_password.text
    assert "Wrong username or password." in unknown_user.text


def test_session_cookie_flags(anon_client):
    cookie = login(anon_client).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


@pytest.mark.parametrize(
    "target", ["https://evil.example", "//evil.example", "/\\evil.example", "/\t/evil.example"]
)
def test_no_open_redirect_after_login(anon_client, target):
    location = login(anon_client, next=target).headers["location"]
    assert location == "/"


def test_safe_next():
    assert auth.safe_next("/day/2026-09-27?x=1") == "/day/2026-09-27?x=1"
    assert auth.safe_next(None) == auth.safe_next("") == auth.safe_next("//x.com") == "/"
    assert auth.safe_next("http://x.com/") == auth.safe_next("/\\x.com") == "/"


# --- brute force --------------------------------------------------------------------------------


def test_too_many_failures_block_even_the_right_password(anon_client):
    for _ in range(5):
        assert login(anon_client, password="wrong password!").status_code == 401
    blocked = login(anon_client)
    assert blocked.status_code == 429 and "Too many failed attempts" in blocked.text


def test_rate_limiter_window():
    limiter = auth.LoginRateLimiter(limit=2, window=60)
    limiter.failed("1.2.3.4", "a")
    assert limiter.retry_after("1.2.3.4", "a") == 0
    limiter.failed("1.2.3.4", "a")
    assert 0 < limiter.retry_after("1.2.3.4", "a") <= 61
    assert limiter.retry_after("5.6.7.8", "b") == 0  # other IP, other user: unaffected
    limiter.succeeded("1.2.3.4", "a")
    assert limiter.retry_after("1.2.3.4", "a") == 0


# --- CSRF ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Sec-Fetch-Site": "same-site"}, 403),  # e.g. demo.example.com → planner.example.com
        ({"Sec-Fetch-Site": "same-origin"}, 200),
        ({"Origin": "https://evil.example"}, 403),
        ({"Origin": "null"}, 403),
        ({"Origin": "http://testserver"}, 200),
    ],
)
def test_cross_site_posts_are_blocked(client, headers, status):
    r = client.post("/entries/1/2026-09-27", data={"count": 1}, headers=headers)
    assert r.status_code == status


def test_cross_site_login_is_blocked(anon_client):
    r = anon_client.post(
        "/login",
        data={"username": USERNAME, "password": PASSWORD},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403


# --- users and passwords ------------------------------------------------------------------------


def test_only_an_argon2_hash_is_stored(session):
    user = auth.create_user(session, "someone", "a long enough password")
    assert user.password_hash.startswith("$argon2id$")
    assert "a long enough password" not in user.password_hash
    other = auth.create_user(session, "someone-else", "a long enough password")
    assert other.password_hash != user.password_hash  # random salt per hash


def test_create_user_validation(session):
    with pytest.raises(ValueError, match="at least 12"):
        auth.create_user(session, "shorty", "short")
    auth.create_user(session, "dup", "a long enough password")
    with pytest.raises(ValueError, match="already taken"):
        auth.create_user(session, "dup", "another long password")


def test_create_user_cli(session, engine, monkeypatch, capsys):
    monkeypatch.setattr(create_user, "engine", engine)
    monkeypatch.setattr(create_user.getpass, "getpass", lambda _prompt: "cli password 123")
    create_user.main(["cli-user"])
    assert "Created user: cli-user" in capsys.readouterr().out
    user = session.exec(select(User).where(User.username == "cli-user")).one()
    assert auth.verify_password(user.password_hash, "cli password 123")

    monkeypatch.setattr(create_user.getpass, "getpass", lambda _prompt: "new cli password")
    create_user.main(["cli-user", "--reset"])
    session.refresh(user)
    assert auth.verify_password(user.password_hash, "new cli password")


def test_login_page_explains_how_to_create_the_first_user(client, session):
    for model in (DailyEntry, Habit, Category, Note, User):  # children before parents (FK)
        for row in session.exec(select(model)):
            session.delete(row)
        session.commit()
    client.post("/logout")
    assert "python -m app.create_user" in client.get("/login").text


# --- several users: each sees and changes only their own data -----------------------------------

FRIEND, FRIEND_PASSWORD = "friend", "another long password"


def test_users_only_see_their_own_data(client, session):
    friend = auth.create_user(session, FRIEND, FRIEND_PASSWORD)  # own copy of the example set
    assert friend.id == 2
    client.post("/entries/1/2026-09-27", data={"count": 1})
    client.post("/logout")
    assert login(client, FRIEND, FRIEND_PASSWORD).status_code == 303

    day = client.get("/day/2026-09-27").text
    assert 'id="habit-13"' in day and 'id="habit-1"' not in day
    assert "Overall · 0% done" in day
    notes = client.get("/month/2026-09").text
    assert 'data-note-id="8"' in notes and 'data-note-id="1"' not in notes

    # Someone else's ids behave as if they didn't exist.
    for url, data in [
        ("/entries/1/2026-09-27", {"count": 0}),
        ("/habits/1", {"name": "Mine now", "target_count": 1}),
        ("/habits/1/active", {"active": "false"}),
        ("/habits/1/highlight", {"color": "blue"}),
        ("/habits/1/delete", {}),
        ("/categories/1", {"name": "Mine now"}),
        ("/categories/1/delete", {}),
        ("/categories/4/delete", {"move_to": 1}),
        ("/habits", {"name": "x", "target_count": 1, "category_id": 1}),
        ("/habits/13", {"name": "x", "target_count": 1, "category_id": 1}),
        ("/notes/1", {"text": "Mine now"}),
        ("/notes/1/delete", {}),
    ]:
        assert client.post(url, data=data).status_code == 404, url
    assert client.post("/habits/reorder", data={"ids": [1, 2]}).status_code == 400
    assert client.post("/notes/order", data={"tip": [1, 8]}).status_code == 400

    client.post("/logout")
    login(client)
    day = client.get("/day/2026-09-27").text
    assert 'id="habit-1"' in day and 'id="habit-13"' not in day
    assert 'class="habit-row done" id="habit-1"' in day  # the check survived
    assert "Mine now" not in client.get("/habits").text


# --- invites ------------------------------------------------------------------------------------


def _new_invite(client) -> str:
    r = client.post("/account/invites")
    assert r.status_code == 200
    return re.search(r'value="http://testserver(/join/[\w-]+)"', r.text)[1]


def _join(client, url, username=FRIEND, password=FRIEND_PASSWORD, repeat=None):
    data = {"username": username, "password": password, "password_repeat": repeat or password}
    return client.post(url, data=data, follow_redirects=False)


def test_invite_flow(client, session):
    assert f"Logged in as <strong>{USERNAME}</strong>" in client.get("/account").text
    url = _new_invite(client)
    assert "Revoke" in client.get("/account").text
    client.post("/logout")

    assert 'action="' + url + '"' in client.get(url).text
    assert "Passwords don&#39;t match." in _join(client, url, repeat="something else!!").text
    assert "at least 12" in _join(client, url, password="short", repeat="short").text
    assert "already taken" in _join(client, url, username=USERNAME).text
    r = _join(client, url)  # failed attempts didn't use the invite up
    assert r.status_code == 303 and r.headers["location"] == "/"

    # Logged in straight away, with a fresh example set of their own.
    assert f"Logged in as <strong>{FRIEND}</strong>" in client.get("/account").text
    assert 'id="habit-13"' in client.get("/day/2026-09-27").text
    invite = session.exec(select(Invite)).one()
    assert invite.used_by == 2 and invite.used_at is not None

    client.post("/logout")
    r = client.get(url)
    assert r.status_code == 404 and "invalid, expired or already used" in r.text
    assert _join(client, url, username="third").status_code == 404
    assert login(client, FRIEND, FRIEND_PASSWORD).status_code == 303


def test_expired_and_revoked_invites(client, session):
    url = _new_invite(client)
    invite = session.exec(select(Invite)).one()
    invite.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    session.commit()
    assert client.get(url).status_code == 404
    assert "Revoke" not in client.get("/account").text

    url = _new_invite(client)
    invite_id = session.exec(select(Invite).order_by(Invite.id.desc())).first().id
    assert client.post(f"/account/invites/{invite_id}/revoke").status_code == 200
    assert client.get(url).status_code == 404
    assert client.post(f"/account/invites/{invite_id}/revoke").status_code == 404


def test_invite_tokens_are_stored_hashed(client, session):
    token = _new_invite(client).removeprefix("/join/")
    assert len(token) >= 32
    assert token not in session.exec(select(Invite)).one().token_hash


# --- changing the password ------------------------------------------------------------------------

NEW_PASSWORD = "a brand new password"


def _change(client, current=PASSWORD, new=NEW_PASSWORD, repeat=None):
    data = {"current_password": current, "new_password": new, "new_password_repeat": repeat or new}
    return client.post("/account/password", data=data)


def test_change_password(client):
    assert "Change password" in client.get("/account").text
    r = _change(client, current="not my password!")
    assert (
        r.status_code == 400
        and "current password isn" in r.text
        and '<details class="account-pick" open>' in r.text
    )
    assert "match" in _change(client, repeat="something else entirely").text
    assert "at least 12" in _change(client, new="short", repeat="short").text
    assert "same as the current" in _change(client, new=PASSWORD).text
    r = _change(client)
    assert r.status_code == 200 and "Password changed." in r.text
    client.post("/logout")
    assert login(client).status_code == 401  # the old one no longer works
    assert login(client, password=NEW_PASSWORD).status_code == 303


def test_change_password_is_rate_limited(client):
    for _ in range(5):
        _change(client, current="wrong guess number")
    r = _change(client)  # even the right one, once blocked
    assert r.status_code == 400 and "Too many wrong passwords" in r.text
