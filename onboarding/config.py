"""Settings, read from environment variables or the local .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-3.1-flash-lite"
    database_url: str = "sqlite+aiosqlite:///./local.db"
    admin_passcode: str = "change-me"
    db_direct: bool = True     # use Neon's direct endpoint even if DATABASE_URL is the -pooler one (faster; see db.engine_args)
    session_secret: str = ""   # signs vendor login cookies; if empty, derived from the database URL (also secret)
    intel_secret: str = ""     # Vendor Intelligence: keys for identifier HMACs and encryption; if empty, derived like session_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
