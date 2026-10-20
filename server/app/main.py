"""FastAPI entry point: wires the REST routers and the WebSocket relay together."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, rooms, snapshots
from app.config import settings
from app.realtime import websocket


def _configure_logging() -> None:
    """Make `app.*` INFO logs (the relay's connect/disconnect/reject lines) visible.

    Uvicorn configures its own loggers (uvicorn, uvicorn.access, uvicorn.error) but
    leaves everyone else's alone; with no handler anywhere in our logger hierarchy, the
    root logger's handler of last resort only prints WARNING and above, so these were
    silently dropped. Guarded so building the app more than once (every test does, via
    `create_app()`) doesn't stack up duplicate handlers.
    """
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(title="Collaborative", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
    app.include_router(snapshots.router, prefix="/api/rooms", tags=["snapshots"])
    app.include_router(websocket.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
