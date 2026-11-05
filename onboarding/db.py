"""Database engine. Accepts the URL Neon gives you and adapts it for asyncpg."""

from __future__ import annotations

import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, DisconnectionError, InterfaceError
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

IDLE_PING_SECONDS = 30  # re-check a pooled connection only if it sat unused this long


def engine_args(url: str, direct: bool = True) -> tuple[str, dict]:
    """URL + engine kwargs for a long-running single-process app.

    Speed matters because every query is a network round trip to Neon:
    - Neon's pooled endpoint (-pooler) runs PgBouncer in transaction mode, which forbids asyncpg's
      prepared-statement cache, so every query costs two round trips. One uvicorn process with its
      own small pool doesn't need PgBouncer, so by default we connect to the direct endpoint (the
      same host without "-pooler") and keep the statement cache: one round trip per query.
    - No ping before every checkout (that was another round trip per request). A connection is
      pinged only if it sat idle long enough for Neon to have suspended (see install_idle_ping).
    Set DB_DIRECT=false to keep the pooled endpoint (e.g. many app instances); then statement names
    must be unique and the cache off (SQLAlchemy's documented recipe)."""
    url = async_url(url)
    if not url.startswith("postgresql+asyncpg"):
        return url, {}
    kwargs: dict = {"pool_size": 8, "max_overflow": 4, "pool_recycle": 1800}
    parts = urlsplit(url)
    host = parts.hostname or ""
    if "-pooler." in host and direct:
        url = urlunsplit((parts.scheme, parts.netloc.replace(host, host.replace("-pooler.", ".", 1)), parts.path, parts.query, ""))
    elif "-pooler." in host:
        query = dict(parse_qsl(parts.query))
        query["prepared_statement_cache_size"] = "0"
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
        kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        }
    return url, kwargs


def install_idle_ping(eng: AsyncEngine, idle_seconds: float = IDLE_PING_SECONDS) -> None:
    """Pessimistic disconnect handling without a ping on every request: Neon suspends an idle
    compute and drops its connections, so a connection that sat unused is checked once before use;
    if it's dead, the pool quietly opens a fresh one (DisconnectionError makes it retry)."""
    @event.listens_for(eng.sync_engine, "checkin")
    def _checkin(dbapi_conn, record):
        record.info["idle_since"] = time.monotonic()

    @event.listens_for(eng.sync_engine, "checkout")
    def _checkout(dbapi_conn, record, proxy):
        since = record.info.get("idle_since")
        if since is not None and time.monotonic() - since > idle_seconds:
            try:
                dbapi_conn.ping()
            except Exception as e:
                raise DisconnectionError() from e


def is_local_url(url: str) -> bool:
    """SQLite, or a database server on this machine."""
    if url.startswith("sqlite"):
        return True
    host = (urlsplit(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def refuse_remote_database_under_tests(url: str) -> None:
    """Tests must never reach a real database (the local .env may hold production's URL). Fail loudly instead."""
    import sys
    if "pytest" in sys.modules and not is_local_url(url):
        raise RuntimeError("Refusing to connect to a non-local database while tests are running. "
                           "Tests must use SQLite (tests/conftest.py sets one for the session).")


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        refuse_remote_database_under_tests(settings.database_url)
        url, kwargs = engine_args(settings.database_url, direct=settings.db_direct)
        _engine = create_async_engine(url, **kwargs)
        if url.startswith("postgresql+asyncpg"):
            install_idle_ping(_engine)
    return _engine


async def ping() -> bool:
    async with engine().connect() as conn:
        await conn.execute(text("select 1"))
    return True


WARM_CONNECTIONS = 4  # the most queries a page sends at once (web._reads), so a page never waits to connect


async def warm_pool(n: int = WARM_CONNECTIONS) -> None:
    """Open a few connections up front and keep them in the pool. Opening one costs several network
    round trips (TCP, TLS, login), seconds on a slow link; a page should find them ready."""
    eng = engine()
    if not eng.url.drivername.startswith("postgresql"):
        return
    conns = []
    try:
        for _ in range(n):  # one at a time: a burst of new connections is what flaky networks refuse
            conns.append(await eng.connect())
            await conns[-1].execute(text("select 1"))
    except Exception:
        pass  # pages open connections themselves if this didn't work
    finally:
        for c in conns:
            await c.close()  # back to the pool, still open


def is_dropped_connection(e: BaseException | None) -> bool:
    """A database connection that died under us (Wi-Fi blip, Neon suspending, a firewall resetting
    sockets), as opposed to a bug. Safe to retry for a page that only reads."""
    if isinstance(e, DBAPIError) and e.connection_invalidated:
        return True
    seen = 0
    while e is not None and seen < 8:  # the socket error is usually a few causes down
        if isinstance(e, (OSError, InterfaceError)) or "connection was closed" in str(e) or type(e).__name__ == "ConnectionDoesNotExistError":
            return True
        e, seen = e.__cause__ or e.__context__, seen + 1
    return False
