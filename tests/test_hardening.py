"""Phase-3 security hardening: the demo parameter, the person switcher's signed cookie, API docs, request size caps,
required secrets, demo logins, the guarded database reset, and a startup that survives an empty database."""

import asyncio
import os

import httpx
import pytest
from sqlalchemy import func, select

FAKE_PG = "postgresql://vendor_user:s3cret-pw@ep-demo-123.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"


def _use_db(path) -> None:
    import onboarding.config as cfg
    import onboarding.db as dbm
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{path.as_posix()}"
    cfg.get_settings.cache_clear()
    dbm._engine = None


async def _dispose():
    import onboarding.db as dbm
    if dbm._engine is not None:
        await dbm._engine.dispose()
    dbm._engine = None


@pytest.fixture
def db(tmp_path):
    """A fresh seeded SQLite database for one test."""
    from onboarding.seeding import seed
    _use_db(tmp_path / "h.db")
    asyncio.run(seed(reset=True, dispose=True))
    yield
    os.environ.pop("DATABASE_URL", None)


def _client():
    from onboarding.main import app
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _count_runs() -> int:
    from onboarding.models import Run
    from onboarding.pipeline import sessions
    async with sessions()() as s:
        return (await s.execute(select(func.count(Run.id)))).scalar()


async def _invite_token() -> str:
    from onboarding.models import Invite
    from onboarding.pipeline import sessions
    async with sessions()() as s:
        return (await s.execute(select(Invite.token).where(Invite.scenario_key == "happy_nilgiri"))).scalars().first()


# --- S1: the demo parameter never replaces the vendor login ----------------------------------------------------
@pytest.mark.parametrize("demo_tools", [False, True])
def test_demo_parameter_never_skips_the_vendor_login(db, monkeypatch, demo_tools):
    from onboarding.config import get_settings
    from onboarding.demo_data import SCENARIOS
    monkeypatch.setattr(get_settings(), "demo_tools", demo_tools)
    nilgiri = SCENARIOS["happy_nilgiri"]["form"]

    async def go():
        token = await _invite_token()
        before = await _count_runs()
        async with _client() as c:
            pages = {p: await c.get(p) for p in ("/apply?demo=happy_nilgiri", "/bill?demo=bill_kesari", f"/apply/{token}?demo=happy_nilgiri",
                                                 "/apply?demo=x", "/bill?demo=x")}
            posts = {p: await c.post(p, data={**{k: str(v) for k, v in nilgiri.items() if not isinstance(v, bool)}, "demo": "happy_nilgiri"})
                     for p in ("/apply", "/bill", f"/apply/{token}")}
        return pages, posts, before, await _count_runs()

    pages, posts, before, after = asyncio.run(go())
    for p, r in {**pages, **posts}.items():
        assert r.status_code == 303 and r.headers["location"].startswith("/vendor/"), p     # to log in or register
        assert nilgiri["pan"] not in r.text and nilgiri["bank_account"] not in r.text, p
    assert after == before                                                                   # no anonymous run


def test_demo_prefill_needs_demo_mode_and_a_known_scenario(db, monkeypatch):
    from onboarding import web
    from onboarding.config import get_settings
    assert web.demo_key("happy_nilgiri") == "happy_nilgiri" and web.demo_key("x") == ""
    monkeypatch.setattr(get_settings(), "demo_tools", False)
    assert web.demo_key("happy_nilgiri") == ""

    async def go():
        from onboarding.seeding import DEMO_PASSWORD, DEMO_VENDOR
        async with _client() as c:
            await c.post("/vendor/login", data={"email": DEMO_VENDOR["email"], "password": DEMO_PASSWORD})
            return await c.get("/apply?demo=happy_nilgiri")
    r = asyncio.run(go())
    from onboarding.demo_data import SCENARIOS
    assert r.status_code == 200 and SCENARIOS["happy_nilgiri"]["form"]["pan"] not in r.text


# --- S5: no API docs in any mode --------------------------------------------------------------------------------
def test_api_docs_are_off_even_in_demo_mode(db):
    async def go():
        async with _client() as c:
            return [(await c.get(p)).status_code for p in ("/docs", "/redoc", "/openapi.json")]
    assert asyncio.run(go()) == [404, 404, 404]


# --- S6: the person switcher -------------------------------------------------------------------------------------
def test_actor_cookie_is_signed_and_bound_to_the_login_and_audit_keeps_both_people(db):
    from starlette.requests import Request

    from onboarding import auth
    from onboarding.models import Employee, HumanAction, Run
    from onboarding.pipeline import sessions
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD

    async def me(c):
        return (await c.get("/api/v1/session")).json()["actor"]["name"]

    async def go():
        out = {}
        async with _client() as c:
            await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})   # Arjun, id 3
            out["no cookie"] = await me(c)
            c.cookies.set("actor", "4")                                       # an unsigned cookie (the old format)
            out["unsigned"] = await me(c)
            c.cookies.set("actor", auth.make_actor(4, 1))                     # signed, but for another login
            out["other login"] = await me(c)
            c.cookies.delete("actor")
            await c.post("/api/v1/session/actor", json={"employee_id": 4})    # the switcher itself
            out["switched"] = await me(c)
            cookie = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
        req = Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})
        out["ids"] = auth.actor_ids(req)
        async with sessions()() as s:   # the record run_action writes (hand-off: comment=auth.audit_comment(request, comment))
            run = Run(application_id=1, form={})
            from onboarding.models import Application
            s.add(Application(id=1, ref="VOB-T1", legal_name="T"))
            s.add(run)
            await s.flush()
            staff_id, actor_id = out["ids"]
            s.add(HumanAction(run_id=run.id, employee_id=actor_id, action="review_approve", comment=auth.audit_comment(req, "Looks fine")))
            await s.commit()
            ha = (await s.execute(select(HumanAction))).scalars().one()
            out["audit"] = ((await s.get(Employee, ha.employee_id)).name, ha.comment)
            out["plain"] = auth.audit_comment(Request({"type": "http", "headers": []}), "Looks fine")
        return out

    out = asyncio.run(go())
    assert out["no cookie"] == out["unsigned"] == out["other login"] == "Arjun Mehta"   # never "the maker" by default, never forged
    assert out["switched"] == "Kavita Rao" and out["ids"] == (3, 4)
    who, comment = out["audit"]
    assert who == "Kavita Rao" and comment.startswith("Looks fine") and "logged-in employee #3" in comment   # both people
    assert out["plain"] == "Looks fine"                                                                    # no switcher: unchanged


# --- S8: request and upload size caps ---------------------------------------------------------------------------
def test_oversized_bodies_and_files_get_413(db, monkeypatch):
    from onboarding.config import get_settings

    async def go():
        async with _client() as c:
            big_file = await c.post("/apply", data={"legal_name": "X"}, files={"pan_card": ("p.pdf", b"%PDF-1.4" + b"0" * (10 * 1024 * 1024 + 10), "application/pdf")})
            read = await c.post("/apply/read", data={"slot": "pan_card"}, files={"file": ("p.pdf", b"%PDF-1.4" + b"0" * (10 * 1024 * 1024 + 10), "application/pdf")})
            monkeypatch.setattr(get_settings(), "max_request_bytes", 1024 * 1024)
            declared = await c.post("/apply", content=b"x" * (2 * 1024 * 1024), headers={"content-type": "application/octet-stream"})

            async def chunks():
                for _ in range(3):
                    yield b"y" * (512 * 1024)
            streamed = await c.post("/apply", content=chunks(), headers={"content-type": "application/x-www-form-urlencoded"})
            return big_file, read, declared, streamed
    big_file, read, declared, streamed = asyncio.run(go())
    assert big_file.status_code == 413 and "larger than 10 MB" in big_file.text
    assert read.status_code == 413 and read.json()["ok"] is False
    assert declared.status_code == 413 and streamed.status_code == 413


# --- S3/S4: required secrets and demo logins --------------------------------------------------------------------
def test_secrets_are_required_off_a_developer_machine():
    from onboarding.config import Settings, missing_secrets, require_secrets
    assert missing_secrets(Settings(database_url="sqlite+aiosqlite:///x.db", demo_tools=True, session_secret="")) == []   # local demo only
    for s in (Settings(database_url=FAKE_PG, demo_tools=True, session_secret=""),            # the deployed demo
              Settings(database_url="sqlite+aiosqlite:///x.db", demo_tools=False, session_secret=""),
              Settings(database_url=FAKE_PG, demo_tools=True, session_secret="short")):
        with pytest.raises(RuntimeError) as e:
            require_secrets(s)
        assert "SESSION_SECRET" in str(e.value) and "s3cret-pw" not in str(e.value)
    require_secrets(Settings(database_url=FAKE_PG, demo_tools=True, session_secret="x" * 32))


def test_startup_refuses_without_session_secret_on_a_remote_database(monkeypatch):
    """Fake Postgres URL, demo mode, no secret: the app refuses before touching the database."""
    import onboarding.db as dbm
    from onboarding import main
    from onboarding.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "database_url", FAKE_PG)
    monkeypatch.setattr(s, "demo_tools", True)
    monkeypatch.setattr(s, "session_secret", "")
    monkeypatch.setattr(dbm, "_engine", None)

    async def go():
        async with main.lifespan(main.app):
            pass
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        asyncio.run(go())
    assert dbm._engine is None                                   # never connected
    assert main.demo_remote_warning() == ("Demo tools ON against a remote database (ep-demo-123.ap-southeast-1.aws.neon.tech): "
                                          "fine for the fictional-data demo, never for real vendor data.")


def test_demo_logins_only_with_demo_password_and_the_public_one_is_retired(db, monkeypatch):
    from onboarding.config import get_settings
    from onboarding.models import StaffLogin
    from onboarding.pipeline import sessions
    from onboarding.seeding import DEMO_COMPANY_EMAIL, ensure_demo_logins, seed

    async def login(pw):
        async with _client() as c:
            return (await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": pw})).status_code

    async def logins():
        async with sessions()() as s:
            return (await s.execute(select(func.count(StaffLogin.id)))).scalar()

    async def go():
        out = {"seeded": await login("demo_pass")}                   # conftest: DEMO_PASSWORD=demo_pass
        monkeypatch.setattr(get_settings(), "demo_tools", False)      # production mode: the public password stops working
        async with sessions()() as s:
            await ensure_demo_logins(s)
            await s.commit()
        out["retired"] = await login("demo_pass")
        monkeypatch.setattr(get_settings(), "demo_tools", True)
        monkeypatch.setattr(get_settings(), "demo_password", "Another-Demo-Pw1")
        async with sessions()() as s:
            await ensure_demo_logins(s)
            await s.commit()
        out["new password"], out["old password"] = await login("Another-Demo-Pw1"), await login("demo_pass")
        monkeypatch.setattr(get_settings(), "demo_password", "")
        await seed(reset=True, dispose=False)
        out["no password, logins"] = await logins()
        await _dispose()
        return out
    out = asyncio.run(go())
    assert out["seeded"] == 303 and out["retired"] == 200 and out["new password"] == 303 and out["old password"] == 200
    assert out["no password, logins"] == 0


# --- the database reset and scripts -------------------------------------------------------------------------------
def test_reset_from_the_command_line_needs_production_and_the_typed_host(monkeypatch, capsys):
    from onboarding.config import get_settings
    from onboarding.seeding import RemoteDatabaseRefused, confirm_target, refuse_remote_reset, seed
    monkeypatch.setattr(get_settings(), "database_url", FAKE_PG)
    with pytest.raises(RemoteDatabaseRefused):
        asyncio.run(seed(reset=True))                        # refused before any connection
    refuse_remote_reset(allow_remote=True)                    # the in-app reset (after its passcode) is allowed
    with pytest.raises(SystemExit):
        confirm_target(["seed.py", "--reset"], ask=lambda _: "")
    with pytest.raises(SystemExit):
        confirm_target(["seed.py", "--reset", "--production"], ask=lambda _: "ep-demo-123")
    assert confirm_target(["seed.py", "--reset", "--production"], ask=lambda _: "ep-demo-123.ap-southeast-1.aws.neon.tech") is True
    printed = capsys.readouterr().out
    assert "ep-demo-123.ap-southeast-1.aws.neon.tech" in printed and "s3cret-pw" not in printed and "vendor_user" not in printed


# --- startup on an empty database ---------------------------------------------------------------------------------
def test_startup_on_an_empty_database_runs_every_step(tmp_path):
    from onboarding import main
    _use_db(tmp_path / "empty.db")
    try:
        assert asyncio.run(_steps(main)) == []
    finally:
        os.environ.pop("DATABASE_URL", None)


async def _steps(main):
    try:
        return await main.startup_steps()
    finally:
        await _dispose()
