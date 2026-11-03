"""Employee and vendor login, the redirect after login, and that a login never freezes the server.

Root cause of the reported "service stops accepting connections after the employee login": the local server was
being stopped from outside (low system memory) right after the login page was opened, so the submit found no
server. The app-side defect behind the report is fixed here: password checks (scrypt, ~0.2 s CPU) ran on the
event loop and blocked every other request while they ran; they now run on a worker thread."""

import asyncio
import os
import time

import pytest


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    db = tmp_path_factory.mktemp("logindb") / "login.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    from onboarding.seeding import seed
    asyncio.run(seed(reset=True, dispose=False))
    from onboarding.main import app
    yield app
    asyncio.run(dbm.engine().dispose())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None


def _run(coro):
    return asyncio.run(coro)


async def _client(app):
    import httpx
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def test_employee_login_redirects_to_the_dashboard(app_client):
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD

    async def go():
        async with await _client(app_client) as c:
            r = await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL.upper(), "password": DEMO_PASSWORD})
            page = await c.get("/console")
            return r, page
    r, page = _run(go())
    assert r.status_code == 303 and r.headers["location"] == "/console"
    assert page.status_code == 200 and "Arjun" in page.text


def test_login_returns_to_the_page_that_asked_for_it(app_client):
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD

    async def go():
        async with await _client(app_client) as c:
            gate = await c.get("/bills")
            r = await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD, "next": "/bills"})
            evil = await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD, "next": "https://evil.example.com/"})
            return gate, r, evil
    gate, r, evil = _run(go())
    assert gate.status_code == 303 and gate.headers["location"].startswith("/company/login?next=")
    assert r.headers["location"] == "/bills"
    assert evil.headers["location"] == "/console"     # never redirect off-site


def test_wrong_password_and_unknown_email_get_the_same_message(app_client):
    from onboarding.seeding import DEMO_COMPANY_EMAIL

    async def go():
        async with await _client(app_client) as c:
            a = await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": "not-the-password"})
            b = await c.post("/company/login", data={"email": "nobody@nareenterprises.example.com", "password": "whatever-1"})
            return a, b
    a, b = _run(go())
    for r in (a, b):
        import html
        assert r.status_code == 200 and "don't match an employee login" in html.unescape(r.text)


def test_vendor_login(app_client):
    from onboarding.seeding import DEMO_PASSWORD, DEMO_VENDOR

    async def go():
        async with await _client(app_client) as c:
            bad = await c.post("/vendor/login", data={"email": DEMO_VENDOR["email"], "password": "wrong-password"})
            r = await c.post("/vendor/login", data={"email": DEMO_VENDOR["email"], "password": DEMO_PASSWORD})
            home = await c.get("/vendor")
            return bad, r, home
    bad, r, home = _run(go())
    assert bad.status_code == 200 and "/vendor" not in bad.headers.get("location", "")
    assert r.status_code == 303 and r.headers["location"].startswith("/vendor")
    assert home.status_code == 200 and DEMO_VENDOR["company_name"] in home.text


def test_a_slow_password_check_does_not_freeze_other_requests(app_client, monkeypatch):
    from onboarding import auth
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD
    real = auth.verify_password

    def slow(password, stored):   # a blocking check, as scrypt is
        time.sleep(0.8)
        return real(password, stored)
    monkeypatch.setattr(auth, "verify_password", slow)

    async def go():
        async with await _client(app_client) as c:
            async def health():
                t = time.perf_counter()          # timed from when it was due: a blocked loop delays even the wake-up
                await asyncio.sleep(0.1)
                await c.get("/healthz")
                return time.perf_counter() - t - 0.1
            login, waited = await asyncio.gather(c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD}), health())
            return login, waited
    login, waited = _run(go())
    assert login.status_code == 303
    assert waited < 0.4, f"the server froze for {waited:.2f}s during a login"


def test_without_demo_tools_the_console_is_the_logged_in_person(app_client, monkeypatch):
    """Production mode: no person switcher, no demo scenarios or credentials, and the 'actor' cookie is ignored."""
    from onboarding.config import get_settings
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD
    monkeypatch.setattr(get_settings(), "demo_tools", False)

    async def go():
        async with await _client(app_client) as c:
            login_page = (await c.get("/company/login")).text
            public = [(await c.get(p)).text for p in ("/", "/vendor/login", "/vendor/register", "/bill")]
            await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})
            c.cookies.set("actor", "4")                       # trying to act as the Finance controller
            console = (await c.get("/console")).text
            act = await c.post("/act-as", data={"employee_id": "4"})
            demo = await c.get("/demo/happy_nilgiri")
            return login_page, public, console, act, demo
    login_page, public, console, act, demo = _run(go())
    for page in [login_page, *public]:
        assert DEMO_PASSWORD not in page                       # never shipped to the browser, not even in a script
        assert "fictional vendors" not in page and "lookups simulated" not in page and "Demo ·" not in page
    assert "one password for all" not in login_page.lower() and "Fill" not in login_page
    assert "Arjun" in console and "Welcome back, Kavita" not in console
    assert "Switch person" not in console and "Demo ·" not in console and "Try a scenario" not in console
    assert act.status_code == 404 and demo.status_code == 404
