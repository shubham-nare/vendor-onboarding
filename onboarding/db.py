"""Database engine. Accepts the URL Neon gives you and adapts it for asyncpg."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from onboarding.config import get_settings


def async_url(url: str) -> str:
    """postgresql://...?sslmode=require  ->  postgresql+asyncpg://...?ssl=require"""
    if url.startswith(("postgres://", "postgresql://")):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query.pop("channel_binding", None)
        if query.pop("sslmode", None) or "ssl" not in query:
            query["ssl"] = "require"
        return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, urlencode(query), ""))
    return url


_engine: AsyncEngine | None = None


def engine_args(url: str) -> tuple[str, dict]:
    """URL + engine kwargs. Neon's pooled endpoint (-pooler) runs PgBouncer in
    transaction mode, so asyncpg's prepared-statement cache must be off and
    statement names must be unique (SQLAlchemy's documented recipe)."""
    url = async_url(url)
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql+asyncpg") and "-pooler." in (urlsplit(url).hostname or ""):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query["prepared_statement_cache_size"] = "0"
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
        kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        }
    return url, kwargs


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url, kwargs = engine_args(get_settings().database_url)
        _engine = create_async_engine(url, **kwargs)
    return _engine


async def ping() -> bool:
    async with engine().connect() as conn:
        await conn.execute(text("select 1"))
    return True
