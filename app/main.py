import logging
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import auth
from app.config import settings
from app.routes import api, health, pages
from app.routes import auth as auth_routes

log = logging.getLogger(__name__)


def _secret_key() -> str:
    if settings.secret_key:
        return settings.secret_key
    log.warning("SECRET_KEY is not set: using a random one, so logins end when the app restarts.")
    return secrets.token_urlsafe(32)


async def _not_authenticated(request: Request, _exc: Exception) -> Response:
    if request.headers.get("HX-Request"):
        # HTMX would swap the login page into the grid; tell it to navigate instead.
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    if request.method != "GET":
        return Response("Not logged in.", status_code=401)
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


def create_app() -> FastAPI:
    # Schema is managed by Alembic (`alembic upgrade head`); users get starter data on creation.
    app = FastAPI(title="Daily Planner")
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    # Everything the planner shows or changes requires a login; /login, /join/…, /health and
    # /static don't.
    logged_in = [Depends(auth.require_user)]
    app.include_router(pages.router, dependencies=logged_in)
    app.include_router(api.router, dependencies=logged_in)
    app.include_router(auth_routes.router)
    app.include_router(health.router)
    app.add_exception_handler(auth.NotAuthenticated, _not_authenticated)
    # Signed session cookie: HttpOnly (JS can't read it), SameSite=Lax (not sent on cross-site
    # POSTs), Secure when session_https_only is set.
    app.add_middleware(
        SessionMiddleware,
        secret_key=_secret_key(),
        session_cookie="planner_session",
        max_age=settings.session_max_age_days * 24 * 3600,
        same_site="lax",
        https_only=settings.session_https_only,
    )
    app.add_middleware(auth.CSRFMiddleware)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
