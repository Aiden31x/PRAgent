from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_asyncpg_database_url(url: str) -> str:
    """Make Neon / libpq-style URLs safe for SQLAlchemy + asyncpg.

    - `postgresql://` → `postgresql+asyncpg://` (app uses asyncpg, not psycopg2).
    - Strip `sslmode`, `channel_binding`, and `ssl` from the query string. SQLAlchemy
      forwards query params to ``asyncpg.connect()``; libpq params break TLS setup
      and `ssl=true` is interpreted as an invalid ``sslmode``. TLS is applied in
      :func:`app.database.asyncpg_connect_args` instead.
    """
    parsed = urlparse(url)
    if parsed.scheme == "postgresql":
        parsed = parsed._replace(scheme="postgresql+asyncpg")
        url = urlunparse(parsed)
    if "postgresql+asyncpg" not in url:
        return url
    parsed = urlparse(url)
    if not parsed.query:
        return url
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    drop = {"sslmode", "channel_binding", "ssl"}
    out = [(k, v) for k, v in pairs if k.lower() not in drop]
    new_query = urlencode(out)
    return urlunparse(parsed._replace(query=new_query))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "PRAgent"
    debug: bool = False

    # --- Database (Neon PostgreSQL) ---
    # Paste Neon’s connection string; _normalize_asyncpg_database_url fixes driver + SSL query params.
    database_url: str

    # --- GitHub OAuth ---
    github_client_id: str = ""
    github_client_secret: str = ""

    # --- GitHub PAT (used by MCP server) ---
    github_token: str = ""

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # --- JWT ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 1 week

    # --- Webhooks ---
    webhook_secret: str = "change-me-webhook-secret"
    webhook_url: str = "http://localhost:8000/webhooks/github"

    # --- CORS ---
    frontend_url: str = "http://localhost:3000"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: object) -> object:
        if isinstance(v, str):
            return _normalize_asyncpg_database_url(v)
        return v


settings = Settings()  # type: ignore[call-arg]
