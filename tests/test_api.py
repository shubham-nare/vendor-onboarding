"""The JSON API and the browser app: JSON everywhere, logins enforced, the app shell has no inline script."""

import asyncio
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    db = tmp_path_factory.mktemp("api") / "t.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import httpx

    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    from onboarding.main import app
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD, seed
    out: dict = {}

    async def go():
        await seed(reset=True, dispose=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            for p in ("/api/v1/session", "/api/v1/console/home", "/api/v1/console/pending"):
                out["anon " + p] = await c.get(p)
            out["anon /console"] = await c.get("/console")
            await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})
            out["shell"] = await c.get("/console")
            for p in ("/api/v1/session", "/api/v1/console/home", "/api/v1/console/pending"):
                out[p] = await c.get(p)
            priya = next(p for p in out["/api/v1/session"].json()["people"] if p["name"] == "Priya Nair")
            out["act"] = await c.post("/api/v1/session/actor", json={"employee_id": priya["id"]})
            out["home as priya"] = (await c.get("/api/v1/console/home")).json()
            out["act bad"] = await c.post("/api/v1/session/actor", json={"employee_id": "x"})
            out["reset requester"] = await c.post("/api/v1/system/reset", json={"passcode": "change-me"})   # still Priya
            await c.post("/api/v1/session/actor", json={"employee_id": out["/api/v1/session"].json()["actor"]["id"]})   # back to Arjun
            out["reset default"] = await c.post("/api/v1/system/reset", json={"passcode": "change-me"})
            out["system"] = await c.get("/api/v1/system")
            pdf = (ROOT / "fixtures" / "documents" / "happy_nilgiri" / "gst_certificate.pdf").read_bytes()
            out["check ok"] = await c.post("/api/v1/check", files={"file_a": ("gst.pdf", pdf, "application/pdf")})
            out["check html"] = await c.post("/api/v1/check", files={"file_a": ("gst.pdf", b"<html><script>x</script>", "application/pdf")})
            out["help"] = await c.get("/api/v1/help")
            from onboarding import auth
            kept = c.cookies.get(auth.COMPANY_COOKIE)                        # someone copied the cookie before log-out
            out["logout"] = await c.post("/api/v1/session/logout")
            out["after logout"] = await c.get("/api/v1/session")
            c.cookies.set(auth.COMPANY_COOKIE, kept)
            out["copied cookie"] = await c.get("/api/v1/session")
            out["copied cookie page"] = await c.get("/console")
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


def test_every_answer_is_json(api):
    for p in ("/api/v1/session", "/api/v1/console/home", "/api/v1/console/pending", "act", "logout"):
        r = api[p]
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json"), p
        assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff", p


def test_logins_are_enforced(api):
    for p in ("/api/v1/session", "/api/v1/console/home", "/api/v1/console/pending"):
        r = api["anon " + p]
        assert r.status_code == 401 and r.headers["content-type"].startswith("application/json") and "log in" in r.json()["error"]
    assert api["anon /console"].status_code == 303                              # the screen itself still asks you to log in
    assert api["after logout"].status_code == 401
    assert api["copied cookie"].status_code == 401 and api["copied cookie page"].status_code == 303   # log-out really ends it


def test_session_and_home(api):
    me = api["/api/v1/session"].json()
    assert me["actor"]["name"] == "Arjun Mehta" and me["actor"]["role_label"] == "Procurement reviewer"
    assert {"review", "apps"} <= set(me["counts"]) and len(me["people"]) == 4
    home = api["/api/v1/console/home"].json()
    assert [s["label"] for s in home["stars"]] == ["Vendors to approve", "Invoices to approve"] and home["requester"] is False
    assert home["open_invites"] == 6 and home["scenarios"] and isinstance(home["todo"], list)
    assert api["home as priya"]["requester"] is True and api["home as priya"]["actor"]["first_name"] == "Priya"
    assert api["act bad"].status_code == 422 and "employee_id" in api["act bad"].json()["error"]


def test_reset_is_off_with_the_default_passcode(api):
    assert api["reset requester"].status_code == 403 and "Requesters" in api["reset requester"].json()["error"]
    r = api["reset default"]
    assert r.status_code == 403 and "ADMIN_PASSCODE" in r.json()["error"]
    assert any(c["name"].startswith("Database") for c in api["system"].json()["checks"])


def test_checker_and_help(api):
    r = api["check ok"].json()["results"][0]
    assert r["mime"] == "application/pdf" and r["proof"]["level"] and isinstance(r["signals"], list)
    assert api["check html"].status_code == 415 and "PDF, JPG or PNG" in api["check html"].json()["error"]
    assert any(row["information"].startswith("PAN") for row in api["help"].json()["access"])


def test_the_app_shell_has_no_inline_script_and_a_strict_policy(api):
    shell = api["shell"]
    assert shell.status_code == 200 and '<script src="/static/app.js" defer></script>' in shell.text
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", shell.text)            # every script is a file
    csp = shell.headers["content-security-policy"]
    assert "script-src 'self' https://cdn.tailwindcss.com;" in csp and "unsafe-eval" not in csp and "frame-ancestors 'none'" in csp


def test_app_js_is_built_from_the_sources():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_frontend", ROOT / "scripts" / "build_frontend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (ROOT / "onboarding" / "static" / "app.js").read_text(encoding="utf-8") == mod.build(), \
        "onboarding/static/app.js is out of date: run  uv run python scripts/build_frontend.py"
