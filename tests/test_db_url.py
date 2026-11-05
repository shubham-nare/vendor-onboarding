from onboarding.db import async_url


def test_neon_url_is_adapted_for_asyncpg():
    url = "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert async_url(url) == "postgresql+asyncpg://u:p@ep-x.aws.neon.tech/neondb?ssl=require"


def test_sqlite_url_untouched():
    assert async_url("sqlite+aiosqlite:///./local.db") == "sqlite+aiosqlite:///./local.db"


def test_pooler_url_switches_to_direct_endpoint_by_default():
    from onboarding.db import engine_args

    url, kwargs = engine_args("postgresql://u:p@ep-x-pooler.c-2.aws.neon.tech/neondb?sslmode=require")
    assert "@ep-x.c-2.aws.neon.tech/" in url and "-pooler" not in url
    assert "connect_args" not in kwargs and "pool_pre_ping" not in kwargs


def test_pooler_url_disables_statement_cache_when_kept():
    from onboarding.db import engine_args

    url, kwargs = engine_args("postgresql://u:p@ep-x-pooler.c-2.aws.neon.tech/neondb?sslmode=require", direct=False)
    assert "prepared_statement_cache_size=0" in url
    assert kwargs["connect_args"]["statement_cache_size"] == 0


def test_direct_url_keeps_defaults():
    from onboarding.db import engine_args

    _, kwargs = engine_args("postgresql://u:p@ep-x.c-2.aws.neon.tech/neondb?sslmode=require")
    assert "connect_args" not in kwargs


def test_tests_can_never_reach_a_remote_database():
    import pytest as _pytest

    from onboarding.db import is_local_url, refuse_remote_database_under_tests
    assert is_local_url("sqlite+aiosqlite:///x.db") and is_local_url("postgresql://u:p@127.0.0.1/db")
    assert not is_local_url("postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/neondb")
    with _pytest.raises(RuntimeError, match="non-local database"):
        refuse_remote_database_under_tests("postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/neondb")


def test_the_session_runs_on_sqlite():
    import onboarding.config as cfg
    assert cfg.get_settings().database_url.startswith("sqlite")
