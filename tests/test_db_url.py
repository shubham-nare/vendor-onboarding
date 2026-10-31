from onboarding.db import async_url


def test_neon_url_is_adapted_for_asyncpg():
    url = "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert async_url(url) == "postgresql+asyncpg://u:p@ep-x.aws.neon.tech/neondb?ssl=require"


def test_sqlite_url_untouched():
    assert async_url("sqlite+aiosqlite:///./local.db") == "sqlite+aiosqlite:///./local.db"


def test_pooler_url_disables_statement_cache():
    from onboarding.db import engine_args

    url, kwargs = engine_args("postgresql://u:p@ep-x-pooler.c-2.aws.neon.tech/neondb?sslmode=require")
    assert "prepared_statement_cache_size=0" in url
    assert kwargs["connect_args"]["statement_cache_size"] == 0


def test_direct_url_keeps_defaults():
    from onboarding.db import engine_args

    _, kwargs = engine_args("postgresql://u:p@ep-x.c-2.aws.neon.tech/neondb?sslmode=require")
    assert "connect_args" not in kwargs
