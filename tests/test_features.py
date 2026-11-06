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


def test_launcher_forms_can_be_submitted_as_the_browser_sees_them(db):
    """apply.html's script turns [data-req] (and [data-gst] for GST-registered vendors) into required inputs. On a
    launcher form the scenario decides the files (Tejas leaves out the Udyam certificate on purpose, for R-DOC-01), so
    no file input may carry data-req/data-gst, or the browser blocks the submit ("Please select a file") and nothing
    reaches the server. And every other field the script will require must already hold the scenario's value."""
    from onboarding.demo_data import SCENARIOS

    async def go():
        async with _client() as staff:
            await _staff(staff)
            out = {}
            for key in LAUNCH:
                loc = (await staff.get(f"/demo/{key}", follow_redirects=False)).headers["location"]
                async with _client() as guest:
                    out[key] = (await guest.get(loc)).text
            return out
    for key, page in asyncio.run(go()).items():
        for tag in re.findall(r'<input type="file"[^>]*>', page):
            assert "data-req" not in tag and "data-gst" not in tag, (key, tag)
        form = SCENARIOS[key]["form"]
        for tag in re.findall(r"<input [^>]*data-(?:req|gst)[^>]*>", page):
            name = re.search(r'name="([^"]+)"', tag).group(1)
            want = form.get(name)
            if isinstance(want, str) and want:   # a field this scenario fills: it must be on the page already
                assert re.search(r'value="[^"]+"', tag), (key, name, tag)


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


# --- PR 2: real-document happy path, PIN state spellings, display and validation fixes ----------------------------
def test_india_post_old_state_spellings_still_fit():
    from onboarding.pincode import live_pin_problem
    raipur = {"states": ["Chattisgarh"], "districts": ["Raipur"], "offices": ["N.I.T. Raipur"], "blocks": []}
    assert live_pin_problem("492010", "Chhattisgarh", "Raipur", raipur) == ("", "")       # same state, old spelling
    assert live_pin_problem("751001", "Odisha", "Bhubaneswar", {"states": ["Orissa"], "districts": ["Khurda"], "offices": [], "blocks": []})[0] == ""
    why, _ = live_pin_problem("492010", "Maharashtra", "Raipur", raipur)
    assert "not Maharashtra" in why                                                           # a real mismatch still fails


def test_nit_raipur_is_in_the_simulated_registry_and_reaches_an_older_database(db):
    from onboarding.demo_data import NITRR
    from onboarding.models import SimRegistry
    from onboarding.pipeline import sessions
    from sqlalchemy import select

    from onboarding.seeding import ensure_sim_registry, sim_records
    keys = {(r["kind"], r["key"]) for r in sim_records()}
    assert {("gst", NITRR["gstin"]), ("pan", NITRR["pan"]), ("bank", f"{NITRR['bank']['account']}@{NITRR['bank']['ifsc']}")} <= keys

    async def go():
        async with sessions()() as s:   # a database seeded before NIT Raipur was added
            await s.execute(SimRegistry.__table__.delete().where(SimRegistry.key == NITRR["gstin"]))
            await s.commit()
            added = await ensure_sim_registry(s)
            await s.commit()
            again = await ensure_sim_registry(s)
            row = (await s.execute(select(SimRegistry).where(SimRegistry.key == NITRR["gstin"]))).scalar_one()
            return added, again, row.data
    added, again, data = asyncio.run(go())
    assert added == 1 and again == 0 and data["status"] == "Active" and data["legal_name"] == "NATIONAL INSTITUTE OF TECHNOLOGY RAIPUR"


def test_the_nit_raipur_identifiers_are_well_formed():
    """The real-document happy path: NIT Raipur's GSTIN and PAN, as on its published documents, pass the format,
    check-digit and PAN-inside-GSTIN rules (the registry part is covered above)."""
    from onboarding import validators as V
    from onboarding.demo_data import NITRR, form
    f = form(NITRR, "INSTITUTION")
    assert f["gstin"][2:12] == f["pan"] and V.gstin_checksum_ok(f["gstin"]) and f["gstin"][:2] == "22"   # 22 = Chhattisgarh


def test_the_server_refuses_a_registration_without_a_legal_name(db):
    async def go():
        async with _client() as staff:
            await _staff(staff)
            loc = (await staff.get("/demo/proprietor_shinde", follow_redirects=False)).headers["location"]
        async with _client() as guest:
            r = await guest.post(loc.split("?")[0], data=_guest_form("proprietor_shinde") | {"legal_name": "  "})
            return r.status_code, r.text
    code, text = asyncio.run(go())
    assert code == 400 and "legal name" in text


def test_documents_sends_anonymous_visitors_to_the_staff_login(db):
    async def go():
        async with _client() as c:
            return await c.get("/documents", follow_redirects=False)
    r = asyncio.run(go())
    assert r.status_code == 303 and r.headers["location"].startswith("/company/login")


def test_applications_show_the_vendor_id_and_run_pages_show_no_none(db, monkeypatch):
    from onboarding import mailer, runner
    pending: list[asyncio.Task] = []
    monkeypatch.setattr(runner, "PACE", 0)
    monkeypatch.setattr(runner, "start", lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True))))
    monkeypatch.setattr(mailer, "start", lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id))))

    async def go():
        async with _client() as staff:
            await _staff(staff)                                      # Arjun
            loc = (await staff.get("/demo/happy_nilgiri", follow_redirects=False)).headers["location"]
            async with _client() as guest:
                r = await guest.post(loc.split("?")[0], data=_guest_form("happy_nilgiri"))
            rid = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            while pending:
                batch = list(pending)
                pending.clear()
                await asyncio.gather(*batch)
            page = (await staff.get(f"/runs/{rid}")).text
            await staff.post(f"/runs/{rid}/action", data={"action": "activate"})
            apps = (await staff.get("/api/v1/applications")).json()["applications"]
            return page, next(a for a in apps if a["run_id"] == rid)
    page, row = asyncio.run(go())
    assert ">None<" not in page and "not_present" not in page
    assert row["status"] == "ACTIVE" and row["vendor"] and row["vendor"]["id"].startswith("V-")


def test_console_screens_ignore_the_routers_params_object():
    """The console router calls every screen as render(view, params) with params an object. A screen whose second
    argument means something else (Invites: the new invite's link; System: a notice) must ignore non-strings, or it
    shows '[object Object]': a broken 'Open as the vendor' link, a bogus notice."""
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "onboarding" / "static" / "app.js").read_text(encoding="utf-8")
    second = re.findall(r"async render\(view, (\w+)", js)
    assert second, "expected screens with a second render argument"
    for name in second:
        body = js[js.index(f"async render(view, {name}"):][:600]
        assert f"typeof {name}" in body, f"render(view, {name}) uses its argument without checking it is a string"


# --- specimens are fake documents on the live site (ACCEPT_SPECIMEN_DOCUMENTS is only for these tests) -------------
def test_a_specimen_document_is_an_absolute_fraud_flag(monkeypatch):
    from pathlib import Path

    from onboarding.authenticity.assess import assess
    from onboarding.config import get_settings
    monkeypatch.setattr(get_settings(), "accept_specimen_documents", False)
    root = Path(__file__).resolve().parent.parent / "fixtures"
    fixture = (root / "documents" / "happy_nilgiri" / "gst_certificate.pdf").read_bytes()
    known = assess(fixture, "application/pdf", None)                                     # matched by fingerprint
    copied = assess(fixture + b"\n%re-saved\n", "application/pdf", None)                 # different file, same banner text
    real = assess((root / "public" / "gst_certificate_signed_igr_maharashtra.pdf").read_bytes(), "application/pdf", None)
    for a in (known, copied):
        codes = {s.code: s.severity for s in a.signals}
        assert codes.get("AU-15") == "fraud" and a.level == "A1" and not a.specimen and "SPECIMEN" not in codes
    assert "AU-15" not in {s.code for s in real.signals} and real.level == "A3"           # a genuine signed certificate


def test_a_registration_with_specimen_documents_is_rejected(db, monkeypatch):
    from onboarding import mailer, runner
    from onboarding.config import get_settings
    monkeypatch.setattr(get_settings(), "accept_specimen_documents", False)
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
            rid = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            while pending:
                batch = list(pending)
                pending.clear()
                await asyncio.gather(*batch)
            ev = (await staff.get(f"/runs/{rid}/events")).json()["events"]
            row = next(a for a in (await staff.get("/api/v1/applications")).json()["applications"] if a["run_id"] == rid)
            return row, {x["rule_id"] for e in ev for x in ((e.get("evidence") or {}).get("rules") or []) if x["result"] == "FAIL"}
    row, fails = asyncio.run(go())
    assert row["status"] == "REJECTED" and "R-AU-15" in fails       # the clean-looking Nilgiri specimens never pass


def test_the_applications_list_says_what_the_next_step_is(db, monkeypatch):
    """'Waiting for you' on an Approved row meant 'activate it' but didn't say so: the list names the step."""
    from onboarding import mailer, runner
    pending: list[asyncio.Task] = []
    monkeypatch.setattr(runner, "PACE", 0)
    monkeypatch.setattr(runner, "start", lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True))))
    monkeypatch.setattr(mailer, "start", lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id))))

    async def go():
        async with _client() as staff:
            await _staff(staff)                                                  # Arjun (Procurement)
            for key in ("proprietor_shinde", "borrowed_gstin_kaveri"):
                loc = (await staff.get(f"/demo/{key}", follow_redirects=False)).headers["location"]
                async with _client() as guest:
                    await guest.post(loc.split("?")[0], data=_guest_form(key))
            while pending:
                batch = list(pending)
                pending.clear()
                await asyncio.gather(*batch)
            return {a["status"]: a.get("next_step") for a in (await staff.get("/api/v1/applications")).json()["applications"]}
    steps = asyncio.run(go())
    assert steps.get("APPROVED") == "Activate vendor" and steps.get("REJECTED") == "Confirm the rejection"
