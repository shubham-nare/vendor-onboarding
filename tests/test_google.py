"""'Continue with Google' for suppliers: hidden without keys; with keys, state is checked, a new email gives
its company name once, a known email just logs in. Google itself is faked (no network)."""

import asyncio
import os
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    db = tmp_path_factory.mktemp("google") / "t.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import httpx

    import onboarding.config as cfg
    import onboarding.db as dbm
    from onboarding import google_auth
    cfg.get_settings.cache_clear()
    dbm._engine = None
    from onboarding.main import app
    from onboarding.seeding import seed
    out: dict = {}
    real_exchange = google_auth.exchange

    async def fake_exchange(request, code):
        return {"bad": {"email": "x@example.com", "email_verified": False},
                "new": {"email": "Meera@Sahyadri.example.com", "email_verified": True, "name": "Meera Kulkarni"},
                "known": {"email": "meera@sahyadri.example.com", "email_verified": True, "name": "Meera"}}[code]

    async def go():
        await seed(reset=True, dispose=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            out["off_page"] = (await c.get("/vendor/login")).text
            out["off_start"] = (await c.get("/vendor/google")).headers.get("location")
            os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"] = "cid.apps.googleusercontent.com", "csecret"
            cfg.get_settings.cache_clear()
            google_auth.exchange = fake_exchange
            try:
                out["on_page"] = (await c.get("/vendor/register")).text

                async def begin():
                    r = await c.get("/vendor/google?next=/apply")
                    return r, parse_qs(urlparse(r.headers["location"]).query)["state"][0]

                r, state = await begin()
                out["start"] = r.headers["location"]
                out["wrong_state"] = (await c.get(f"/vendor/google/callback?code=new&state=nope")).text
                r, state = await begin()
                out["cancel"] = (await c.get("/vendor/google/callback?error=access_denied")).text
                r, state = await begin()
                out["unverified"] = (await c.get(f"/vendor/google/callback?code=bad&state={state}")).text
                r, state = await begin()
                r = await c.get(f"/vendor/google/callback?code=new&state={state}")
                out["new_redirect"] = r.headers.get("location")
                out["finish_page"] = (await c.get(r.headers["location"])).text
                r = await c.post("/vendor/google/finish", data={"company_name": "Sahyadri Tools", "contact_name": "Meera Kulkarni", "next": "/apply"})
                out["finished"] = (r.status_code, r.headers.get("location"))
                out["after"] = (await c.get("/vendor")).status_code
                c.cookies.clear()
                # the Google-only account can't be logged into with a password
                out["pw"] = (await c.post("/vendor/login", data={"email": "meera@sahyadri.example.com", "password": "google"})).text
                r, state = await begin()
                r = await c.get(f"/vendor/google/callback?code=known&state={state}")
                out["known"] = (r.status_code, r.headers.get("location"))
            finally:
                google_auth.exchange = real_exchange
                os.environ["GOOGLE_CLIENT_ID"] = os.environ["GOOGLE_CLIENT_SECRET"] = ""
                cfg.get_settings.cache_clear()
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


def test_hidden_without_keys(flow):
    assert "Continue with Google" not in flow["off_page"]
    assert flow["off_start"] == "/vendor/login"


def test_start_goes_to_google(flow):
    assert "Continue with Google" in flow["on_page"]
    q = parse_qs(urlparse(flow["start"]).query)
    assert flow["start"].startswith("https://accounts.google.com/") and q["client_id"] == ["cid.apps.googleusercontent.com"]
    assert q["redirect_uri"] == ["http://t/vendor/google/callback"] and "email" in q["scope"][0]


def test_bad_returns_are_refused(flow):
    assert "expired" in flow["wrong_state"]
    assert "cancelled" in flow["cancel"]
    assert "isn&#39;t verified" in flow["unverified"] or "isn't verified" in flow["unverified"]


def test_new_supplier_gives_company_name_once(flow):
    assert flow["new_redirect"].startswith("/vendor/google/finish")
    assert "meera@sahyadri.example.com" in flow["finish_page"] and "Meera Kulkarni" in flow["finish_page"]
    assert flow["finished"] == (303, "/apply") and flow["after"] == 200
    assert "don&#39;t match" in flow["pw"] or "don't match" in flow["pw"]


def test_known_email_just_logs_in(flow):
    assert flow["known"] == (303, "/apply")
