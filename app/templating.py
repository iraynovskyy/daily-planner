import hashlib
from datetime import date
from functools import cache
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app import i18n
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


# --- language (see app/i18n.py): every helper reads the request's language from the context ---


def _lang(ctx) -> str:
    return i18n.lang_of(ctx["request"])


@pass_context
def _gettext(ctx, text: str, /, **values: object) -> str:
    return i18n.gettext(_lang(ctx), text, **values)


@pass_context
def _fmt_date(ctx, d: date, style: str) -> str:
    return i18n.fmt_date(d, style, _lang(ctx))


@pass_context
def _weekday(ctx, d: date, short: bool = False) -> str:
    return i18n.weekday(d, _lang(ctx), short)


@pass_context
def _month_name(ctx, month: int, short: bool = False) -> str:
    return i18n.month_name(month, _lang(ctx), short)


@pass_context
def _js_i18n(ctx) -> dict[str, str]:
    """The Ukrainian of the texts the page scripts show (empty in English)."""
    if _lang(ctx) != "uk":
        return {}
    return {text: i18n.UK[text] for text in i18n.JS_TEXTS if text in i18n.UK}


templates.env.globals.update(
    _=_gettext,
    fmt_date=_fmt_date,
    weekday=_weekday,
    month_name=_month_name,
    js_i18n=_js_i18n,
    page_lang=pass_context(_lang),
    LANGUAGES=i18n.LANGUAGES,
)
