from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.db import get_session

router = APIRouter()


@router.get("/health", include_in_schema=False)
def health(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
    """Liveness + database check for Docker / uptime monitors: 200 if the DB answers, else 503."""
    try:
        session.exec(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok"})
