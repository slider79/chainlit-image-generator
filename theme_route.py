"""Serve Mirage's stylesheet from the app itself.

Chainlit can point `custom_css` at a file under `public/`, but that path is
served with Starlette's FileResponse, which calls `anyio.to_thread.run_sync`
and fails with NoEventLoopError on some Python and anyio combinations (seen on
Python 3.14). The stylesheet is small, so it is simply read once at import and
returned from a normal route, which works on every version.

Importing this module registers the route on Chainlit's FastAPI app.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import Response

from chainlit.server import app as chainlit_app

CSS_PATH = Path(__file__).resolve().parent / "public" / "style.css"
CSS_ROUTE = "/mirage.css"

try:
    _CSS = CSS_PATH.read_text(encoding="utf-8")
except OSError:  # pragma: no cover - only if the file is missing
    _CSS = "/* Mirage stylesheet not found */"


@chainlit_app.get(CSS_ROUTE, include_in_schema=False)
async def mirage_css() -> Response:
    return Response(
        content=_CSS,
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=300"},
    )


def _prioritise_route() -> None:
    """Move the stylesheet route ahead of Chainlit's catch-all.

    Chainlit registers a catch-all route that serves the single-page app for
    any unmatched path, and Starlette matches routes in registration order.
    Since that route already exists by the time this module is imported, a
    newly appended route would never be reached: the request would come back
    as index.html with a text/html content type. Moving it to the front fixes
    that without touching Chainlit's own routing.
    """
    for index, route in enumerate(chainlit_app.routes):
        if getattr(route, "path", None) == CSS_ROUTE:
            chainlit_app.routes.insert(0, chainlit_app.routes.pop(index))
            return


_prioritise_route()
