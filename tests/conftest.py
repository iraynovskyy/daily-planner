import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import db, main, services
from app.config import BASE_DIR, settings
from app.db import get_session


@pytest.fixture(autouse=True)
def example_seed(monkeypatch):
    # Tests always run against the neutral example data, never a local personal seed.
    monkeypatch.setattr(settings, "seed_file", BASE_DIR / "seed.example.toml")


# In-memory SQLite by default; set TEST_DATABASE_URL (e.g. a Postgres URL) to run against that.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def engine() -> Iterator[Engine]:
    if TEST_DATABASE_URL:
        engine = db.make_engine(TEST_DATABASE_URL)
        SQLModel.metadata.drop_all(engine)  # fresh tables (and id sequences) for every test
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with Session(engine) as s:
        services.seed_default_habits(s)
        yield s


@pytest.fixture
def client(engine, session, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(db, "engine", engine)

    def _session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    main.app.dependency_overrides[get_session] = _session
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
