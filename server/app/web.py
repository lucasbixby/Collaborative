"""Serve the built web UI (#22) from the same server, so one image and one port do everything.

`COLLAB_WEB_DIR` points at Vite's output (`web/dist`; `/srv/web` in the Docker image). A file
that exists there is served as is (the hashed JS and CSS under `assets/`, the favicon), and any
other GET is the single-page app's own route (`/rooms/demo`, `/join/<code>`), so it gets
`index.html` and the app's router takes over. Paths under `/api/` and `/ws/` never fall back:
an unknown API route stays a JSON 404 rather than a page of HTML. Routes registered before this
one (`/health`, `/docs`, the routers) win anyway, since Starlette matches in order.
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

_NOT_THE_APP = ("api", "ws")


def add_web_routes(app: FastAPI, web_dir: Path) -> None:
    """Register the catch-all. Call it after every other route."""
    root = web_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        logger.warning("no web UI: %s has no index.html (build it with npm run build)", root)
        return

    @app.get("/{path:path}", include_in_schema=False)
    async def web_ui(path: str) -> FileResponse:
        if path.split("/", 1)[0] in _NOT_THE_APP:
            raise HTTPException(404, "Not Found")
        candidate = (root / path).resolve()
        # resolve() then is_relative_to: "../" can't reach outside the build folder.
        if path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        # Not cached: a new deploy's index.html must point at the new hashed assets.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
