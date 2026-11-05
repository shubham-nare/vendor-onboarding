"""Settings, read from environment variables or the local .env file."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
MIN_SECRET = 16   # characters: a shorter SESSION_SECRET is a typo, not a secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-3.1-flash-lite"
    database_url: str = "sqlite+aiosqlite:///./local.db"
    db_direct: bool = True     # use Neon's direct endpoint even if DATABASE_URL is the -pooler one (faster; see db.engine_args)
    # --- security ----------------------------------------------------------------------------------------------
    # SESSION_SECRET signs the login and person-switcher cookies. Required whenever the database is not local or
    # DEMO_TOOLS is off: startup refuses without it (require_secrets). Only with a local database in demo mode may it
    # be blank; the key is then random per process (logins end on restart).
    session_secret: str = ""
    admin_passcode: str = ""   # the in-app "Reset demo data"; reset is off while this is blank, short or "change-me"
    demo_password: str = ""    # demo mode only: the password of the seeded demo logins; blank = no demo logins
    intel_secret: str = ""     # Vendor Intelligence keys; blank = SESSION_SECRET
    trusted_proxy_hops: int = 1          # proxies in front of the app that append to X-Forwarded-For (Render: 1)
    max_request_bytes: int = 25 * 1024 * 1024   # the whole request body; each uploaded file is also capped at 10 MB
    # email to vendors (off until set): SMTP server, sender, and an optional single inbox for demos
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""
    mail_redirect_to: str = ""
    # vendor reliability (onboarding/reliability.py): free news search on by default; the two keyed sources stay
    # "not connected" until their keys are set here
    news_search: bool = True
    # bot check on public forms (onboarding/captcha.py): Cloudflare Turnstile keys; demo mode uses Cloudflare's test keys
    captcha: bool = True
    rate_limits: bool = True   # onboarding/security.py; tests switch them off and test them on their own
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    # "Continue with Google" for suppliers (onboarding/google_auth.py): an OAuth client from Google Cloud; hidden when blank
    google_client_id: str = ""
    google_client_secret: str = ""
    opensanctions_api_key: str = ""
    google_maps_api_key: str = ""
    demo_tools: bool = False  # development only: person switcher, demo scenarios, demo logins and sample files in the UI     # Vendor Intelligence: keys for identifier HMACs and encryption; if empty, derived like session_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()


def database_host(url: str) -> str:
    """Where a database URL points, without user, password or query: safe to print or log."""
    if url.startswith("sqlite"):
        return "a local SQLite file"
    return urlsplit(url).hostname or "?"


def local_database(s: Settings | None = None) -> bool:
    from onboarding.db import is_local_url
    return is_local_url((s or get_settings()).database_url)


def dev_keys_allowed(s: Settings | None = None) -> bool:
    """A random per-process cookie key only on a developer's machine: demo mode AND a local database. Anywhere else a
    restart would log everyone out, so a real SESSION_SECRET is required."""
    s = s or get_settings()
    return s.demo_tools and local_database(s)


def missing_secrets(s: Settings | None = None) -> list[str]:
    """The secrets this deployment needs but doesn't have (an empty list means it may start)."""
    s = s or get_settings()
    if dev_keys_allowed(s):
        return []
    return ["SESSION_SECRET"] if len(s.session_secret.strip()) < MIN_SECRET else []


def require_secrets(s: Settings | None = None) -> None:
    """At startup: refuse to run without the secrets, saying which ones and why."""
    s = s or get_settings()
    missing = missing_secrets(s)
    if missing:
        why = "DEMO_TOOLS is off" if not s.demo_tools else f"the database is remote ({database_host(s.database_url)})"
        raise RuntimeError(f"Refusing to start: set {', '.join(missing)} (at least {MIN_SECRET} characters), because {why}. "
                           "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\".")


def reset_passcode(s: Settings | None = None) -> str:
    """The admin passcode if it is a real secret, else '' (reset switched off). There is no default passcode."""
    code = (s or get_settings()).admin_passcode.strip()
    return "" if len(code) < 12 or code.lower() in ("change-me", "changeme") else code
