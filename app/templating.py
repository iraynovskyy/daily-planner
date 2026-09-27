from datetime import date
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.services import HIGHLIGHTS

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["today_iso"] = lambda: date.today().isoformat()
templates.env.globals["HIGHLIGHTS"] = HIGHLIGHTS
