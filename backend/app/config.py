"""Environment variables  ->  one typed, validated Settings object.

pydantic-settings reads real environment variables first, then a local `.env`
file. Nothing secret is hard-coded: in production the app refuses to boot
with the insecure development secret key.
"""
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEV_KEY = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Expense Tracker API"
    environment: str = "development"  # development | testing | production
    debug: bool = False

    # Database. SQLite by default; Render/Heroku-style Postgres URLs are normalised below.
    database_url: str = "sqlite+aiosqlite:///./data/expenses.db"

    # Auth / JWT
    secret_key: str = INSECURE_DEV_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # CORS: comma separated list of browser origins allowed to call this API
    cors_origins: str = "http://localhost:5000,http://127.0.0.1:5000"

    # Uploads
    upload_dir: str = "uploads"
    max_upload_mb: int = 5

    # Third-party API (free, no key needed)
    exchange_api_url: str = "https://open.er-api.com/v6/latest"

    # Caching / rate limiting
    cache_ttl_seconds: int = 30
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    crawler_rate_limit_per_minute: int = 10

    @field_validator("database_url")
    @classmethod
    def normalise_database_url(cls, v: str) -> str:
        # Render gives `postgres://...`; SQLAlchemy async needs the asyncpg driver name.
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def forbid_insecure_key_in_production(self) -> "Settings":
        if self.environment == "production" and self.secret_key == INSECURE_DEV_KEY:
            raise ValueError("SECRET_KEY must be set to a random value in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
