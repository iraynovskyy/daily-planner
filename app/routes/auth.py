from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session

from app import auth
from app.db import get_session
from app.templating import templates

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


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
