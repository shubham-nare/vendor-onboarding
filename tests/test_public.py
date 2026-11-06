"""The public side: top bar, How it works, Contact us, the thank-you page, language, and the bot check."""

import asyncio
import os

import pytest

from tests.flags import flags_on

_features = flags_on("payables", "unsolicited")   # the top bar's "Register for future work" and "Submit a bill" links


@pytest.fixture(scope="module")
def pub(tmp_path_factory):
    db = tmp_path_factory.mktemp("pub") / "t.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import httpx

    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    from onboarding.main import app
    from onboarding.seeding import seed
    out: dict = {}

    async def go():
        await seed(reset=True, dispose=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            for p in ("/", "/tour", "/contact", "/thanks?for=bill&ref=VOB-0004", "/thanks?ref=<script>x"):
                out[p] = await c.get(p)
            r = await c.post("/lang", data={"to": "hi", "next": "/tour"})
            out["lang"] = (r.status_code, r.headers.get("location"), r.cookies.get("lang"))
            c.cookies.set("lang", "hi")
            out["home_hi"] = (await c.get("/")).text
            out["tour_hi"] = (await c.get("/tour")).text
            c.cookies.set("lang", "en")
            out["contact_bad"] = (await c.post("/contact", data={"name": "A", "email": "nope", "body": "hello there friends"})).text
            r = await c.post("/contact", data={"name": "Asha Kulkarni", "company": "Tejas Industrial", "email": "asha@tejas.example.com",
                                               "topic": "A bill or payment", "body": "When will invoice TIS-0042 be paid?"})
            out["contact_ok"] = (r.status_code, r.headers.get("location"))
            from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD
            await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})
            out["outbox"] = (await c.get("/api/v1/outbox")).text
            # signing up twice (a double click): the second one just logs in; a wrong password still gets the message
            c.cookies.clear()
            twice = {"company_name": "Twice Co", "contact_name": "T", "email": "twice@twice.example.com", "password": "Str0ng!pass"}
            out["reg1"] = (await c.post("/vendor/register", data=twice)).status_code
            c.cookies.clear()
            out["reg2"] = (await c.post("/vendor/register", data=twice)).status_code
            c.cookies.clear()
            out["reg3"] = (await c.post("/vendor/register", data=twice | {"password": "Other!pass9"})).text
            # the bot check, switched on (demo mode uses Cloudflare's test keys; no token is sent, so no network call)
            os.environ["CAPTCHA"] = "true"
            os.environ["TURNSTILE_SITE_KEY"], os.environ["TURNSTILE_SECRET_KEY"] = "0x-site-test", "0x-secret-test"
            cfg.get_settings.cache_clear()
            try:
                c.cookies.clear()
                out["reg_page"] = (await c.get("/vendor/register")).text
                reg = {"company_name": "Bot Co", "contact_name": "Bot", "email": "bot@bot.example.com", "password": "Str0ng!pass"}
                out["reg_no_token"] = (await c.post("/vendor/register", data=reg)).text
                out["reg_honeypot"] = (await c.post("/vendor/register", data=reg | {"website": "http://spam.example.com"})).text
                out["login_no_token"] = (await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})).status_code
            finally:
                os.environ["CAPTCHA"] = "false"
                os.environ.pop("TURNSTILE_SITE_KEY", None), os.environ.pop("TURNSTILE_SECRET_KEY", None)
                cfg.get_settings.cache_clear()
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


def test_public_pages_have_the_top_bar(pub):
    for p in ("/", "/tour", "/contact", "/thanks?for=bill&ref=VOB-0004"):
        page = pub[p].text
        assert pub[p].status_code == 200, p
        assert "Parakh" in page and "View demo" in page and "Contact us" in page and 'action="/lang"' in page, p
        assert "Register for future work" in page and "Submit a bill" in page, p


def test_the_thank_you_page(pub):
    page = pub["/thanks?for=bill&ref=VOB-0004"].text
    assert "Thank you for submitting your bill." in page and "VOB-0004" in page and "suppliers@parakh.tech" in page
    assert "<script>x" not in pub["/thanks?ref=<script>x"].text                 # the reference is cleaned


def test_language_switch(pub):
    assert pub["lang"][0] == 303 and pub["lang"][1] == "/tour" and pub["lang"][2] == "hi"
    assert "डेमो देखें" in pub["home_hi"] and "संपर्क करें" in pub["home_hi"] and 'lang="hi"' in pub["home_hi"]
    assert "देखें यह कैसे काम करता है" in pub["tour_hi"]


def test_contact_form_reaches_the_team(pub):
    assert "valid email" in pub["contact_bad"]
    assert pub["contact_ok"] == (303, "/thanks?for=contact")
    assert '"inbox"' in pub["outbox"] and "TIS-0042" in pub["outbox"]


def test_bot_check_on_sign_up_and_log_in(pub):
    assert "cf-turnstile" in pub["reg_page"] and 'name="website"' in pub["reg_page"]
    assert "not a robot" in pub["reg_no_token"]
    assert "Something went wrong" in pub["reg_honeypot"]
    assert pub["login_no_token"] == 200                                          # back on the log-in page, not logged in


def test_home_has_the_employee_log_in_and_the_ropeway(pub):
    page = pub["/"].text
    assert 'id="home-login"' in page and 'action="/company/login"' in page and 'name="password"' in page
    assert "I work at Parakh" in page and "Nare" not in page
    assert 'id="cables"' in page and "rope-tip" in page


def test_every_language_covers_the_same_phrases():
    from onboarding import i18n
    assert set(i18n.LANGS) == {"en", "hi", "mr", "te", "zh"}
    used = set(i18n.MR)                                       # the phrases the pages use today
    for code in ("mr", "te", "zh"):
        assert set(i18n.TABLES[code]) == used, code
        assert i18n.translate("View demo", code) != "View demo"
    assert i18n.translate("View demo", "zh") == "查看演示" and i18n.translate("Not a phrase", "te") == "Not a phrase"


def test_signing_up_twice_logs_in(pub):
    assert pub["reg1"] == 303 and pub["reg2"] == 303
    assert "already exists" in pub["reg3"]


def test_chrome_devtools_probe_is_quiet():
    from fastapi.testclient import TestClient

    from onboarding.main import app
    assert TestClient(app).get("/.well-known/appspecific/com.chrome.devtools.json").status_code == 204
