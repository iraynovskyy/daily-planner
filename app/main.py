from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import services
from app.db import engine
from app.routes import api, health, pages


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Schema is managed by Alembic (`alembic upgrade head`); here we only seed defaults.
    with Session(engine) as session:
        services.seed_default_habits(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Daily Planner", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(api.router)
    app.include_router(health.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
