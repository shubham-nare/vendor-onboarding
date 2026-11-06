"""The lean-phase switches: out-of-scope features are hidden (404, off every menu, no background work) unless their
FEATURE_* flag is on; stage pacing; /readyz; /history; Why cards that lead with the problem; and the five golden
scenarios through the staff scenario launcher with every flag at its default (off)."""

import asyncio
import os
import re

import httpx
import pytest
from sqlalchemy import event


FLAGS = ("payables", "intel", "reliability", "followups", "unsolicited")


def _use_db(path) -> None:
    import onboarding.config as cfg
    import onboarding.db as dbm
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{path.as_posix()}"
    cfg.get_settings.cache_clear()
    dbm._engine = None


@pytest.fixture
def db(tmp_path):
    """A fresh seeded SQLite database for one test, every flag at its default."""
    import onboarding.config as cfg
    import onboarding.db as dbm
    from onboarding.seeding import seed
    _use_db(tmp_path / "f.db")
    asyncio.run(seed(reset=True, dispose=True))
    for n in FLAGS:
        assert getattr(cfg.get_settings(), f"feature_{n}") is False
    yield
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None


def _client():
    from onboarding.main import app
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _staff(c, email=None):
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD
    r = await c.post("/company/login", data={"email": email or DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 303


# --- hidden features: 404 and gone from the menus ---------------------------------------------------------------
HIDDEN = {
    "payables": [("GET", "/invoices"), ("GET", "/bills"), ("GET", "/bill"), ("GET", "/purchase-orders"), ("GET", "/audit"),
                 ("GET", "/api/v1/invoices"), ("GET", "/api/v1/history"), ("POST", "/change-requests/1/decide"), ("GET", "/vendor/bills/new")],
    "intel": [("GET", "/vendors"), ("GET", "/vendors/V-1"), ("GET", "/relationships"), ("GET", "/api/v1/relationships"),
              ("GET", "/api/v1/vendors/V-1"), ("POST", "/runs/1/simulate")],
    "reliability": [("POST", "/runs/1/reliability")],
    "followups": [("POST", "/system/followups"), ("POST", "/api/v1/system/followups")],
    "unsolicited": [("GET", "/apply"), ("POST", "/apply"), ("GET", "/prequalified"), ("GET", "/api/v1/prequalified")],
}


@pytest.mark.parametrize("flag", FLAGS)
def test_a_hidden_feature_answers_404_and_is_in_no_menu(db, flag):
    async def go():
        out = {}
        async with _client() as c:
            await _staff(c)
            for method, path in HIDDEN[flag]:
                r = await c.request(method, path, follow_redirects=False)
                out[(method, path)] = r.status_code
            out["session"] = (await c.get("/api/v1/session")).json()
            out["home"] = (await c.get("/api/v1/console/home")).json()
            out["page"] = (await c.get("/assumptions")).text            # a Jinja page with the staff menu
        return out
    o = asyncio.run(go())
    assert all(o[(m, p)] == 404 for m, p in HIDDEN[flag]), {k: v for k, v in o.items() if isinstance(k, tuple)}
    assert o["session"]["features"][flag] is False and all(v is False for v in o["session"]["features"].values())
    assert "Invoices to approve" not in [s["label"] for s in o["home"]["stars"]] and o["home"]["features"][flag] is False
    assert "/static/app.js" in o["page"]   # the console frame draws its sidebar from session.features (checked in the JS test below)


def test_the_console_menu_is_built_from_the_flags():
    """The browser app drops a screen from its sidebar (and links to it) when the session says the feature is off."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "onboarding" / "static" / "app.js").read_text(encoding="utf-8")
    assert "FEATURE_PATHS" in js and "featureOff(href)" in js and "dropDeadLinks(view)" in js


def test_supplier_pages_do_not_offer_hidden_routes(db):
    async def go():
        from onboarding.seeding import DEMO_PASSWORD, DEMO_VENDOR
        async with _client() as c:
            r = await c.post("/vendor/login", data={"email": DEMO_VENDOR["email"], "password": DEMO_PASSWORD})
            assert r.status_code == 303
            return (await c.get("/vendor")).text, (await c.get("/")).text
    home, landing = asyncio.run(go())
    for page in (home, landing):
        assert 'href="/apply"' not in page and 'href="/bill"' not in page


# --- background work stops with the flags ------------------------------------------------------------------------
def _after_calls(monkeypatch, **env):
    import onboarding.config as cfg
    from onboarding import mailer, reliability, runner
    from onboarding.intel import project
    for n in FLAGS:
        monkeypatch.delenv(f"FEATURE_{n.upper()}", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    cfg.get_settings.cache_clear()
    calls = []

    def rec(name):
        async def f(run_id):
            calls.append(name)
        return f
    monkeypatch.setattr(project, "on_run_completed", rec("intel"))
    monkeypatch.setattr(reliability, "check_run", rec("reliability"))
    monkeypatch.setattr(mailer, "deliver_for_run", rec("mail"))
    asyncio.run(runner._after(1))
    cfg.get_settings.cache_clear()
    return calls


def test_after_a_run_intel_and_reliability_do_not_run_when_off(monkeypatch):
    assert _after_calls(monkeypatch) == ["mail"]


def test_after_a_run_each_flag_turns_its_step_on(monkeypatch):
    assert _after_calls(monkeypatch, FEATURE_INTEL="true") == ["intel", "mail"]
    assert _after_calls(monkeypatch, FEATURE_RELIABILITY="true") == ["mail", "reliability"]


def test_startup_has_no_intel_backfill_followup_loop_or_sample_orders(monkeypatch):
    import onboarding.config as cfg
    from onboarding import followups, main
    from onboarding.intel import project
    called = []

    async def spy(*a, **k):
        called.append("x")
    monkeypatch.setattr(project, "backfill", spy)
    monkeypatch.setattr(followups, "loop", spy)
    monkeypatch.setattr(main, "_purchase_orders", spy)
    monkeypatch.setattr(main, "startup_steps", spy)
    monkeypatch.setattr(main.db, "warm_pool", spy)
    monkeypatch.setattr(cfg, "require_secrets", lambda *a: None)
    monkeypatch.setenv("DEMO_TOOLS", "true")
    for n in FLAGS:
        monkeypatch.delenv(f"FEATURE_{n.upper()}", raising=False)
    cfg.get_settings.cache_clear()

    async def go():
        async with main.lifespan(main.app):
            await asyncio.sleep(0.05)
    asyncio.run(go())
    assert called == ["x", "x"]   # startup_steps and warm_pool only
    cfg.get_settings.cache_clear()


def test_sample_orders_load_only_with_payables(monkeypatch):
    import onboarding.config as cfg
    from onboarding import main
    monkeypatch.setenv("DEMO_TOOLS", "true")
    for n in FLAGS:
        monkeypatch.delenv(f"FEATURE_{n.upper()}", raising=False)
    names = []

    async def fake(*a):
        return None
    monkeypatch.setattr(main, "_create_tables", fake)
    monkeypatch.setattr(main, "_logins", fake)
    monkeypatch.setattr(main, "_sweep", fake)
    monkeypatch.setattr(main, "_purchase_orders", lambda: names.append("po") or fake())
    cfg.get_settings.cache_clear()
    asyncio.run(main.startup_steps())
    assert names == []
    monkeypatch.setenv("FEATURE_PAYABLES", "true")
    cfg.get_settings.cache_clear()
    asyncio.run(main.startup_steps())
    assert names == ["po"]
    cfg.get_settings.cache_clear()


# --- stage pacing, /readyz, /history, System label --------------------------------------------------------------
def test_stage_pace_is_a_setting_read_at_run_time(monkeypatch):
    import onboarding.config as cfg
    from onboarding import runner
    monkeypatch.setattr(runner, "PACE", None)
    monkeypatch.delenv("STAGE_PACE_SECONDS", raising=False)
    cfg.get_settings.cache_clear()
    assert runner._pace() == 0.4
    monkeypatch.setenv("STAGE_PACE_SECONDS", "0.1")
    cfg.get_settings.cache_clear()
    assert runner._pace() == 0.1
    monkeypatch.setattr(runner, "PACE", 0)   # what the tests do: the module attribute overrides
    assert runner._pace() == 0
    cfg.get_settings.cache_clear()


def test_readyz_touches_the_database_once_and_needs_no_login(db, monkeypatch):
    import onboarding.db as dbm
    statements = []

    async def go():
        eng = dbm.engine().sync_engine
        event.listen(eng, "before_cursor_execute", lambda conn, cur, stmt, *a: statements.append(stmt))
        async with _client() as c:
            return await c.get("/readyz")
    r = asyncio.run(go())
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert [s.strip().lower() for s in statements] == ["select 1"]


def test_readyz_is_503_when_the_database_is_down(db, monkeypatch):
    import onboarding.db as dbm

    async def boom():
        raise ConnectionRefusedError("no")
    monkeypatch.setattr(dbm, "ping", boom)

    async def go():
        async with _client() as c:
            return await c.get("/readyz")
    r = asyncio.run(go())
    assert r.status_code == 503 and r.json()["ok"] is False


def test_healthz_does_not_touch_the_database(monkeypatch):
    import onboarding.db as dbm

    def boom():
        raise AssertionError("healthz touched the database")
    monkeypatch.setattr(dbm, "engine", boom)

    async def go():
        async with _client() as c:
            return await c.get("/healthz")
    assert asyncio.run(go()).json() == {"ok": True}


def test_history_redirects_to_the_applications_list():
    async def go():
        async with _client() as c:
            return await c.get("/history", follow_redirects=False)
    r = asyncio.run(go())
    assert r.status_code == 303 and r.headers["location"] == "/applications"


def test_system_health_label_follows_the_database_url():
    from onboarding.config import db_label
    assert db_label("sqlite+aiosqlite:///./local.db") == "Database (SQLite)"
    assert db_label("postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/neondb") == "Database (Neon Postgres)"
    assert db_label("postgresql://u:p@db.internal/app") == "Database (Postgres)"


def test_the_pending_toast_does_not_cover_run_pages_or_phones():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "onboarding"
    css = (root / "static" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"@media \(max-width: 767px\) \{ #pending-note \{ display: none", css)
    assert "path.startsWith('/runs/')" in (root / "static" / "app.js").read_text(encoding="utf-8")
    assert "not path.startswith('/runs/')" in (root / "templates" / "base.html").read_text(encoding="utf-8")


# --- Why cards lead with the problem ----------------------------------------------------------------------------
def test_a_why_card_leads_with_the_problem_not_the_source_reading():
    from onboarding.decision import _card
    from onboarding.rules import FAIL, R
    card = _card(R("R-SRC-GST", "sources", FAIL, "GST registry: active, name is 'KAVERI TRADERS'", "REVIEW",
                   internal="Registry name differs from the applicant."), "PENDING_REVIEW")
    assert card["rule"] == "R-SRC-GST"
    assert "doesn't match" in card["title"] and not card["title"].startswith("GST registry: active")
    assert card["detail"].startswith("GST registry: active, name is 'KAVERI TRADERS'.") and "differs from the applicant" in card["detail"]
    bank = _card(R("R-SRC-BANK", "sources", FAIL, "Bank confirms the account holder is 'X', not the applicant", "REVIEW", internal="Someone else's."), "PENDING_REVIEW")
    assert "doesn't match" in bank["title"] and "Bank confirms" in bank["detail"]
    other = _card(R("R-XD-03", "consistency", FAIL, "GST registration belongs to a different legal entity (X)", "REJECT", internal="i"), "REJECTED")
    assert other["title"].startswith("GST registration belongs to a different legal entity")   # already leads with the problem


# --- the five golden scenarios through the scenario launcher, every flag off --------------------------------------
LAUNCH = {"happy_nilgiri": ("APPROVED", False), "wrongdoc_tejas": ("PENDING_VENDOR", False), "borrowed_gstin_kaveri": ("REJECTED", False),
          "shared_bank_rangoli": ("PENDING_REVIEW", True), "proprietor_shinde": ("APPROVED", False)}


def test_the_five_golden_scenarios_through_the_launcher_with_every_flag_off(db, monkeypatch):
    from onboarding import mailer, runner
    from onboarding.demo_data import SCENARIOS
    from onboarding.models import Run
    from onboarding.pipeline import sessions
    pending: list[asyncio.Task] = []
    monkeypatch.setattr(runner, "PACE", 0)
    monkeypatch.setattr(runner, "start", lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True))))
    monkeypatch.setattr(mailer, "start", lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id))))

    async def drain():
        while pending:
            batch = list(pending)
            pending.clear()
            await asyncio.gather(*batch)

    async def go():
        out = {}
        async with _client() as staff:
            await _staff(staff)
            for key in LAUNCH:
                loc = (await staff.get(f"/demo/{key}", follow_redirects=False)).headers["location"]
                assert loc.startswith("/apply/"), loc
                form = {k: ("" if v is None else str(v)) for k, v in SCENARIOS[key]["form"].items() if not isinstance(v, bool)}
                form["demo"] = key
                if SCENARIOS[key]["form"].get("msme"):
                    form["msme"] = "on"
                form["gst_registered"] = "on"
                async with _client() as guest:                       # the demo vendor in a fresh window
                    page = await guest.get(loc)
                    assert page.status_code == 200
                    r = await guest.post(loc.split("?")[0], data=form)
                    assert r.status_code == 303 and r.headers["location"].startswith("/runs/"), (key, r.status_code, r.text[:300])
                run_id = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
                await drain()
                async with sessions()() as s:
                    run = await s.get(Run, run_id)
                    out[key] = (run.status, bool((run.summary or {}).get("fraud")), run.state)
                page = (await staff.get(f"/runs/{run_id}")).text
                assert 'id="reliability"' not in page and "Possible fraud: check before approving" not in page
                for gone in ('href="/invoices"', 'href="/purchase-orders"', 'href="/audit"', 'href="/vendors"', 'href="/prequalified"'):
                    assert gone not in page, (key, gone)           # the Jinja menu on the run page has no hidden feature
        return out
    out = asyncio.run(go())
    assert {k: v[:2] for k, v in out.items()} == LAUNCH
    assert all(v[2] == "done" for v in out.values())


def test_the_intel_and_reliability_tables_are_not_read_by_the_cross_checks():
    """R-XD-03 and R-RISK-02 decide from the form, the documents and VendorMaster only (no Vendor Intelligence tables)."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "onboarding" / "rules.py").read_text(encoding="utf-8")
    assert "intel" not in src.lower() and "reliab" not in src.lower()
    assert "ctx.master" in src   # R-RISK-02's input, loaded by the pipeline from VendorMaster
    pipe = (Path(__file__).resolve().parent.parent / "onboarding" / "pipeline.py").read_text(encoding="utf-8")
    assert "master=" in pipe and "select(VendorMaster)" in pipe


# --- the demo video: Tejas resubmits on the launcher link as a guest; the vendor lands on /thanks; replay -----------
def _guest_form(key: str) -> dict:
    from onboarding.demo_data import SCENARIOS
    form = {k: ("" if v is None else str(v)) for k, v in SCENARIOS[key]["form"].items() if not isinstance(v, bool)}
    form["demo"], form["gst_registered"] = key, "on"
    if SCENARIOS[key]["form"].get("msme"):
        form["msme"] = "on"
    return form


def _gst_file_input(html: str) -> str:
    return re.search(r'<input type="file"[^>]*name="gst_certificate"[^>]*>', html).group(0)


def test_launcher_forms_do_not_demand_a_gst_file_that_is_already_attached(db):
    """apply.html's script makes [data-gst] inputs required when the vendor is GST-registered; an attached demo or
    previous GST certificate must not carry data-gst/data-req, or the browser blocks the submit ("Please select a file")."""
    async def go():
        async with _client() as staff:
            await _staff(staff)
            out = {}
            for key in ("borrowed_gstin_kaveri", "shared_bank_rangoli", "wrongdoc_tejas"):
                loc = (await staff.get(f"/demo/{key}", follow_redirects=False)).headers["location"]
                async with _client() as guest:
                    out[key] = _gst_file_input((await guest.get(loc)).text)
            return out
    for key, tag in asyncio.run(go()).items():
        assert "data-req" not in tag and "data-gst" not in tag, (key, tag)


def test_a_run_followed_live_is_not_replayed_after_its_reload():
    """run.html: following a run live marks it seen, so the reload when it finishes shows the static result."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "onboarding" / "templates" / "run.html").read_text(encoding="utf-8")
    body = src[src.index("function startLive() {"):]
    assert body.index("markSeen();") < body.index("new EventSource")


def test_launcher_tejas_then_the_guest_resubmission_is_approved_with_the_diff(db, monkeypatch):
    from onboarding import mailer, runner
    from onboarding.models import Run
    from onboarding.pipeline import sessions
    pending: list[asyncio.Task] = []
    monkeypatch.setattr(runner, "PACE", 0)
    monkeypatch.setattr(runner, "start", lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True))))
    monkeypatch.setattr(mailer, "start", lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id))))

    async def drain():
        while pending:
            batch = list(pending)
            pending.clear()
            await asyncio.gather(*batch)

    async def go():
        out = {}
        async with _client() as staff:
            await _staff(staff)
            loc = (await staff.get("/demo/wrongdoc_tejas", follow_redirects=False)).headers["location"]
        link = loc.split("?")[0]
        async with _client() as guest:
            r = await guest.post(link, data=_guest_form("wrongdoc_tejas"))
            first = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            await drain()
            page = await guest.get(f"{link}?demo=wrongdoc_tejas_resubmit")
            out["page"] = page.status_code
            out["gst_input_resubmit"] = _gst_file_input(page.text)
            out["gst_input_prev_only"] = _gst_file_input((await guest.get(link)).text)   # previous documents, no demo files
            r = await guest.post(link, data=_guest_form("wrongdoc_tejas_resubmit"))
            out["resubmit"] = (r.status_code, r.headers.get("location", ""))
            second = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            await drain()
        async with sessions()() as s:
            a, b = await s.get(Run, first), await s.get(Run, second)
            out["first"], out["second"] = a.status, (b.status, b.parent_run_id == a.id, (b.summary or {}).get("diff"))
        return out

    o = asyncio.run(go())
    assert o["first"] == "PENDING_VENDOR" and o["page"] == 200 and o["resubmit"][0] == 303
    for k in ("gst_input_resubmit", "gst_input_prev_only"):   # a file already on hand: the browser must not demand one
        assert "data-req" not in o[k] and "data-gst" not in o[k] and " required" not in o[k], (k, o[k])
    assert o["second"] == ("APPROVED", True, {"resolved": ["R-COMP-02", "R-DOC-01"], "still_open": [], "new": []})


def test_a_vendor_only_browser_lands_on_thanks_and_the_nilgiri_demo_vendor_can_sign_in(db, monkeypatch):
    from onboarding import runner
    from onboarding.models import Invite
    from onboarding.pipeline import sessions
    from sqlalchemy import select

    from onboarding.seeding import DEMO_PASSWORD, DEMO_VENDOR_NILGIRI
    monkeypatch.setattr(runner, "start", lambda run_id, **kw: None)

    async def go():
        async with sessions()() as s:
            token = (await s.execute(select(Invite.token).where(Invite.scenario_key == "happy_nilgiri"))).scalars().first()
        async with _client() as v:   # the incognito window of beat 1: a vendor, not staff
            r = await v.post("/vendor/login", data={"email": DEMO_VENDOR_NILGIRI["email"], "password": DEMO_PASSWORD})
            login = r.status_code
            page = await v.get(f"/apply/{token}?demo=happy_nilgiri")
            r = await v.post(f"/apply/{token}", data=_guest_form("happy_nilgiri"))
            return login, page.status_code, r.headers.get("location", ""), (await v.get("/vendor")).text

    login, page, loc, home = asyncio.run(go())
    assert login == 303 and page == 200
    assert loc.startswith("/thanks?for=registration")          # never the staff live view in a vendor-only browser
    assert "Nilgiri Packaging" in home


def test_the_run_page_offers_a_replay_of_the_recorded_checks(db, monkeypatch):
    from onboarding import mailer, runner
    pending: list[asyncio.Task] = []
    monkeypatch.setattr(runner, "PACE", 0)
    monkeypatch.setattr(runner, "start", lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True))))
    monkeypatch.setattr(mailer, "start", lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id))))

    async def go():
        async with _client() as staff:
            await _staff(staff)
            loc = (await staff.get("/demo/happy_nilgiri", follow_redirects=False)).headers["location"]
            async with _client() as guest:
                r = await guest.post(loc.split("?")[0], data=_guest_form("happy_nilgiri"))
            while pending:
                batch = list(pending)
                pending.clear()
                await asyncio.gather(*batch)
            return (await staff.get(r.headers["location"].split("?")[0])).text

    page = asyncio.run(go())
    assert 'id="replay-btn"' in page and 'id="run-result"' in page and 'id="replay-note"' in page
    ago = float(re.search(r"const FINISHED_AGO = ([0-9.]+);", page).group(1))
    assert 0 <= ago < 120                                       # just finished: the page auto-plays the replay
    assert re.search(r'const TOOK = "\d+\.\d";', page)           # the real duration, from started_at/finished_at
