"""Server settings, read from environment variables (see .env.example)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder secret. It signs login tokens (#16), so anyone who knows it can sign in as
# anyone; the server warns loudly at startup while it's in use.
DEFAULT_SECRET_KEY = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COLLAB_", env_file=".env")

    # SQLite for development; swap for a Postgres URL later.
    database_url: str = "sqlite+aiosqlite:///./data/collaborative.db"

    # Root folder for the local-disk asset store.
    asset_dir: Path = Path("./data/assets")

    # Signs login tokens (HS256). Always override outside local dev.
    secret_key: str = DEFAULT_SECRET_KEY

    # How long a login token stays valid (#16). There's no revocation: signing out only forgets
    # the token on that machine, so keep this short enough to live with.
    token_ttl_hours: int = 168

    # Reject operations larger than this many bytes.
    max_operation_bytes: int = 64 * 1024

    # Write a room snapshot once its log has grown this many operations past the last one (#20).
    snapshot_every: int = 500

    # Origins allowed to call the REST API (the React dev server by default).
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
