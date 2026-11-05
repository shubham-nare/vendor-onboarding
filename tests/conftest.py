"""Tests exercise the development tools (person switcher, demo scenarios), so they're on here.

Production guard: the local .env may hold the production DATABASE_URL. Every test session therefore runs on a
throwaway SQLite file set here, before anything from onboarding is imported; after each test module the URL is
put back (modules that build their own database pop it when they finish). onboarding.db also refuses to connect
to any non-local database while pytest is loaded, and pytest_configure aborts the session if the effective URL is
not local, before any query.
"""
import os
import tempfile

import pytest

SESSION_DB_URL = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(prefix="vob-tests-"), "session.db").replace(os.sep, "/")
os.environ["DATABASE_URL"] = SESSION_DB_URL
os.environ["ADMIN_PASSCODE"] = "test-reset-passcode-1"  # the same everywhere, whatever the local .env says
os.environ["SESSION_SECRET"] = "test-session-secret-not-for-production"
os.environ["DEMO_PASSWORD"] = "demo_pass"               # the seeded demo logins' password in tests
os.environ["GEMINI_API_KEY"] = ""                       # no live AI calls: saved readings only
os.environ["TRUSTED_PROXY_HOPS"] = "1"

os.environ.setdefault("DEMO_TOOLS", "true")
os.environ.setdefault("NEWS_SEARCH", "false")          # no network in tests; the reliability tests fake the sources
os.environ.setdefault("CAPTCHA", "false")               # the bot-check tests turn it on themselves
os.environ.setdefault("RATE_LIMITS", "false")           # tests switch them on in test_security.py
os.environ["OPENSANCTIONS_API_KEY"] = ""
os.environ["GOOGLE_MAPS_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""                     # "Continue with Google" off unless a test turns it on
os.environ["GOOGLE_CLIENT_SECRET"] = ""


def pytest_configure(config):
    """Abort the whole session, before any query, if the database the app would use is not local."""
    import onboarding.config as cfg
    from onboarding.db import is_local_url
    cfg.get_settings.cache_clear()
    url = cfg.get_settings().database_url
    if not is_local_url(url):
        pytest.exit("DATABASE_URL points at a non-local database. Tests only run against SQLite; aborting.", returncode=2)


IFSC_FIXED = {"BANK": "Test Bank", "BRANCH": "Test Branch", "CITY": "Pune", "STATE": "Maharashtra", "ADDRESS": "Test address"}


@pytest.fixture(autouse=True, scope="session")
def _no_live_lookups():
    """No test reaches the network: the live IFSC (Razorpay) and India Post PIN lookups answer from fixed data, for
    the whole session (module fixtures such as the golden scenarios run before function fixtures, so this is
    session-wide). IFSC: the bundled snapshot's record when it has the code, else a fixed branch for a well-formed
    code. PIN: unavailable, so the rules use the offline postal-region check. A test that needs the real functions
    asks for the `live_lookups` fixture."""
    import json

    from onboarding import sources as S

    snap = json.loads(S.SNAPSHOT.read_text(encoding="utf-8"))["records"] if S.SNAPSHOT.exists() else {}

    async def ifsc(code: str, *, timeout: float = 3.0):
        c = (code or "").strip().upper()
        if c in snap:
            return S.SourceResult("Razorpay IFSC directory (live)", "FOUND", True, {k: snap[c].get(k) for k in IFSC_FIXED})
        if len(c) == 11 and c[4] == "0":
            return S.SourceResult("Razorpay IFSC directory (live)", "FOUND", True, dict(IFSC_FIXED))
        return S.SourceResult("Razorpay IFSC directory (live)", "NOT_FOUND", True)

    async def pin(code: str, *, timeout: float = 3.0):
        return S.SourceResult("India Post PIN directory", "ERROR", False, note="network off in tests")

    _REAL_LOOKUPS.update(ifsc_lookup=S.ifsc_lookup, pin_lookup=S.pin_lookup)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(S, "ifsc_lookup", ifsc)
        mp.setattr(S, "pin_lookup", pin)
        yield


_REAL_LOOKUPS: dict = {}


@pytest.fixture
def live_lookups(monkeypatch):
    """Opt out of the stubs for one test: the real IFSC and PIN lookups (they use the network)."""
    for name, fn in _REAL_LOOKUPS.items():
        monkeypatch.setattr("onboarding.sources." + name, fn)


@pytest.fixture(autouse=True, scope="module")
def _back_to_the_session_database():
    """After each module, return to the session's SQLite file (some modules pop DATABASE_URL when they finish,
    which would otherwise let settings fall back to .env)."""
    yield
    import onboarding.config as cfg
    import onboarding.db as dbm
    os.environ["DATABASE_URL"] = SESSION_DB_URL
    cfg.get_settings.cache_clear()
    dbm._engine = None


@pytest.fixture(autouse=True, scope="session")
def _session_database():
    """Tables and demo data in the session's SQLite file, once, so tests that don't build their own database
    (security headers, error pages) still have one to read."""
    import asyncio

    import onboarding.config as cfg
    import onboarding.db as dbm
    from onboarding.seeding import seed
    os.environ["DATABASE_URL"] = SESSION_DB_URL
    cfg.get_settings.cache_clear()
    dbm._engine = None
    asyncio.run(seed(reset=True, dispose=True))
    dbm._engine = None
    yield
