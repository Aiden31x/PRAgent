from pydantic_settings import BaseSettings, SettingsConfigDict


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
    database_url: str  # e.g. postgresql+asyncpg://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require

    # --- GitHub OAuth ---
    github_client_id: str = ""
    github_client_secret: str = ""

    # --- GitHub PAT (used by MCP server) ---
    github_token: str = ""

    # --- Gemini ---
    gemini_api_key: str = ""

    # --- JWT ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 1 week

    # --- CORS ---
    frontend_url: str = "http://localhost:3000"


settings = Settings()  # type: ignore[call-arg]
