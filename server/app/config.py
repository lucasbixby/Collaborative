"""Server settings, read from environment variables (see .env.example)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COLLAB_", env_file=".env")

    # SQLite for development; swap for a Postgres URL later.
    database_url: str = "sqlite+aiosqlite:///./data/collaborative.db"

    # Root folder for the local-disk asset store.
    asset_dir: Path = Path("./data/assets")

    # Used to sign auth tokens. Always override outside local dev.
    secret_key: str = "dev-only-change-me"

    # Reject operations larger than this many bytes.
    max_operation_bytes: int = 64 * 1024

    # Origins allowed to call the REST API (the React dev server by default).
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
