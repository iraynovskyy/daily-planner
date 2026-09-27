import hashlib
from datetime import date
from functools import cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.services import HIGHLIGHTS

STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@cache
def static_url(path: str) -> str:
    """URL of a file in static/ with a hash of its content, so browsers fetch it again after a
    deploy changed it instead of reusing a cached old copy (e.g. an old style.css)."""
    digest = hashlib.sha256((STATIC_DIR / path).read_bytes()).hexdigest()[:10]
    return f"/static/{path}?v={digest}"


templates.env.globals["static_url"] = static_url
templates.env.globals["today_iso"] = lambda: date.today().isoformat()
templates.env.globals["HIGHLIGHTS"] = HIGHLIGHTS
