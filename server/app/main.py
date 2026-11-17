"""FastAPI entry point: wires the REST routers and the WebSocket relay together."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, files, rooms, snapshots
from app.auth.ratelimit import RateLimiter
from app.auth.tokens import MIN_KEY_BYTES, signing_key
from app.config import KNOWN_WEAK_KEY, settings
from app.db.session import create_engine, create_session_factory, create_tables
from app.realtime import websocket
from app.realtime.saves import SaveRequests
from app.realtime.tasks import AppTasks
from app.storage.local import LocalAssetStore
from app.sync.state import SnapshotScheduler
from app.sync.validation import OriginRegistry
from app.web import add_web_routes

logger = logging.getLogger(__name__)

REGISTRATIONS_PER_WINDOW = 30


def _configure_logging() -> None:
    """Uvicorn only configures its own loggers, so without a handler here the relay's INFO
    lines are dropped. Guarded, because every test builds an app."""
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)


_WEAK_KEY_WARNING = """
************************************************************************************
  COLLAB_SECRET_KEY is the old placeholder value, which is public: anyone can sign in
  as any user. Unset it (the server then generates and keeps its own key) or set a
  random one of 32+ characters.
************************************************************************************"""


def _check_signing_key() -> None:
    key = signing_key()  # creates the key file on a first start
    if key == KNOWN_WEAK_KEY:
        logger.warning(_WEAK_KEY_WARNING)
    elif len(key.encode()) < MIN_KEY_BYTES:
        logger.warning(
            "COLLAB_SECRET_KEY is under %d bytes, which makes tokens easier to forge",
            MIN_KEY_BYTES,
        )


def create_app(database_url: str | None = None, web_dir: Path | None = None) -> FastAPI:
    """Build the app. The database is only opened at startup, in `lifespan`, so importing this
    module touches no files and each app instance has its own engine."""
    _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _check_signing_key()
        engine = create_engine(database_url or settings.database_url)
        await create_tables(engine)
        state = app.state
        state.sessions = create_session_factory(engine)
        state.tasks = AppTasks()
        state.room_locks = defaultdict(asyncio.Lock)
        state.origins = OriginRegistry()
        state.snapshots = SnapshotScheduler(state.sessions, state.tasks.spawn)
        state.saves = SaveRequests()
        state.assets = LocalAssetStore(settings.asset_dir)
        window = settings.auth_window_seconds
        state.login_limiter = RateLimiter(settings.auth_attempts, window)
        state.join_limiter = RateLimiter(settings.auth_attempts, window)
        state.register_limiter = RateLimiter(REGISTRATIONS_PER_WINDOW, window)
        yield
        # Handlers and their database work first: disposing the engine while a query is still
        # running waits for it forever.
        await state.tasks.shutdown()
        await engine.dispose()

    app = FastAPI(title="Collaborative", version="0.2.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # tokens travel in a header the caller sets, never cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
    app.include_router(files.router, prefix="/api/rooms", tags=["files"])
    app.include_router(snapshots.router, prefix="/api/rooms", tags=["snapshots"])
    app.include_router(websocket.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Last: its catch-all must not shadow anything above.
    if (web_dir or settings.web_dir) is not None:
        add_web_routes(app, web_dir or settings.web_dir)

    return app


app = create_app()
