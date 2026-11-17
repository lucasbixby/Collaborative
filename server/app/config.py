"""Server settings, read from COLLAB_* environment variables (see .env.example)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The old placeholder key. It is public, so using it still earns a warning at startup.
KNOWN_WEAK_KEY = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COLLAB_", env_file=".env")

    database_url: str = "sqlite+aiosqlite:///./data/collaborative.db"

    # Where uploaded project files are kept, by content hash.
    asset_dir: Path = Path("./data/assets")

    # Signs login tokens. Empty means: generate one on first start and keep it in secret_key_file.
    secret_key: str = ""
    secret_key_file: Path = Path("./data/secret.key")

    token_ttl_hours: int = 168

    max_operation_bytes: int = 64 * 1024
    max_file_bytes: int = 512 * 1024 * 1024

    # A room snapshot is written once its log has grown this many operations past the last one.
    snapshot_every: int = 500

    # Failed sign-ins or room joins allowed per client and name within the window, then 429.
    auth_attempts: int = 10
    auth_window_seconds: int = 300

    # The built web UI to serve at /. Unset, the server is API-only.
    web_dir: Path | None = None

    # Any origin may call the API: requests are authorized by a Bearer token the caller must
    # already hold, never by cookies, so another site gains nothing by calling it.
    cors_origins: list[str] = ["*"]


settings = Settings()
