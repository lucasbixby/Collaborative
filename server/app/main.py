"""FastAPI entry point: wires the REST routers and the WebSocket relay together."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, rooms, snapshots
from app.config import settings
from app.realtime import websocket


def create_app() -> FastAPI:
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
