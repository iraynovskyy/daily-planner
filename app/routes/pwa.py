"""Web app manifest: lets phones install the planner on the home screen ("Add to Home Screen").

Public, because browsers fetch it without the session cookie. The app opens on today's
checklist; a long press on its icon offers shortcuts to Today and the year page.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

ICONS = "/static/icons"


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": "Daily Planner",
            "short_name": "Planner",
            "description": "Tick off habits, see the month and the year at a glance.",
            "id": "/",
            "start_url": "/today",
            "scope": "/",
            "display": "standalone",
            "background_color": "#13171f",
            "theme_color": "#13171f",
            "icons": [
                {"src": f"{ICONS}/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": f"{ICONS}/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {
                    "src": f"{ICONS}/icon-maskable-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
            "shortcuts": [
                {"name": "Today", "short_name": "Today", "url": "/today"},
                {"name": "Year at a glance", "short_name": "Year", "url": "/year"},
            ],
        },
        media_type="application/manifest+json",
    )
