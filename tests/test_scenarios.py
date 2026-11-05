"""Golden scenarios through the real front door: a requester logs in and sends an invite (POST /invites), the vendor
registers from the invite link, opens /apply/{token} and uploads the scenario's fixture files, the background run
finishes, and people act on the decision. Pins each scenario's status, risk tier, stages and reason codes: they
define "identical output" for refactors. Throwaway SQLite, committed saved AI readings (fixtures/read_cache/),
no API calls."""

import asyncio
import html
import mimetypes
import os
import re
import secrets
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "fixtures" / "read_cache"   # committed saved readings of the fictional demo documents
DOCS = ROOT / "fixtures" / "documents"
assert CACHE.exists() and any(CACHE.iterdir()), "fixtures/read_cache/ (committed saved AI readings) is missing: a broken checkout, not a skip"
PW = "Vn@7" + secrets.token_urlsafe(10)

ORDER = ["happy_nilgiri", "wrongdoc_tejas", "borrowed_gstin_kaveri", "shared_bank_rangoli", "proprietor_shinde"]
STAGES_NO_BILL = ["invite", "intake", "completeness", "read", "authenticity", "identifiers", "consistency", "sources", "risk", "decision"]

# GOLDEN VALUES, recorded from the app at 98cadb2 (refactor/ps2-lean) through the invite path below. They define "identical
# output" for the refactor: change one only on purpose, and say why in the commit. `flagged` is every rule result that
# is not PASS/SKIPPED (rule_id -> FAIL | WARN | ERROR); `reason_codes` are the rules that decided the status.
GOLDEN = {
    "happy_nilgiri": dict(status="APPROVED", risk="low", fraud=False, reason_codes=[], flagged={}),
    "wrongdoc_tejas": dict(status="PENDING_VENDOR", risk="low", fraud=False, reason_codes=["R-COMP-02", "R-DOC-01"],
                           flagged={"R-COMP-02": "FAIL", "R-DOC-01": "FAIL"}),
    "wrongdoc_tejas_resubmit": dict(status="APPROVED", risk="medium", fraud=False, reason_codes=[], flagged={"R-MSME-02": "WARN"}),
    "borrowed_gstin_kaveri": dict(status="REJECTED", risk="low", fraud=False, reason_codes=["R-XD-03"],
                                  flagged={"R-ADDR-01": "FAIL", "R-ID-04": "FAIL", "R-NAME-01": "FAIL", "R-SRC-GST": "FAIL", "R-XD-03": "FAIL",
                                           "R-XD-05": "FAIL"}),
    "shared_bank_rangoli": dict(status="PENDING_REVIEW", risk="high", fraud=True, reason_codes=["R-RISK-02", "R-SRC-BANK"],
                                flagged={"R-RISK-02": "FAIL", "R-SRC-BANK": "FAIL"}),
    "proprietor_shinde": dict(status="APPROVED", risk="medium", fraud=False, reason_codes=[], flagged={}),
}


def _form_data(form: dict) -> dict:
    """The scenario's form as the browser posts it (checkboxes are 'on' or absent). No 'demo' key: the files are uploaded."""
    d = {k: ("" if v is None else str(v)) for k, v in form.items() if not isinstance(v, bool)}
    if form.get("msme"):
        d["msme"] = "on"
    if form.get("gst_registered", True):
        d["gst_registered"] = "on"
    return d


def _files(key: str) -> dict:
    return {p.stem: (p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            for p in sorted((DOCS / key).glob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def golden(tmp_path_factory):
    db = tmp_path_factory.mktemp("scenariodb") / "scenarios.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    import httpx
    from sqlalchemy import select

    from onboarding import mailer, runner
    from onboarding.demo_data import SCENARIOS
    from onboarding.main import app
    from onboarding.models import (
        Application,
        Employee,
        Invite,
        Message,
        RuleResult,
        Run,
        VendorMaster,
    )
    from onboarding.pipeline import sessions, stages_for
    from onboarding.seeding import DEMO_PASSWORD, EMPLOYEES, INVITES, seed

    pending: list[asyncio.Task] = []
    out: dict = {}

    async def drain():
        while pending:
            batch = list(pending)
            pending.clear()
            await asyncio.gather(*batch)

    async def go():
        await seed(reset=True, dispose=False)
        async with sessions()() as s:
            emp = {e.name: e for e in (await s.execute(select(Employee))).scalars()}
        out["emp"] = {n: (e.id, e.role) for n, e in emp.items()}
        t = httpx.ASGITransport(app=app)
        staff = {}
        for e in EMPLOYEES:   # every employee logs in with their own work email (no person switcher)
            c = httpx.AsyncClient(transport=t, base_url="http://t")
            r = await c.post("/company/login", data={"email": e["email"], "password": DEMO_PASSWORD})
            assert r.status_code == 303, r.text
            staff[e["name"]] = c

        async def invite(key: str) -> str:
            sponsor, company, reason, cat, band, _high = INVITES[key]
            r = await staff[sponsor].post("/invites", data=dict(company_name=company, contact_email=SCENARIOS[key]["form"]["contact_email"],
                                                                business_reason=reason, spend_category=cat, spend_band=band))
            assert r.status_code == 303, r.text
            return re.search(r"created=([^&]+)", r.headers["location"]).group(1)

        async def latest_run(token: str) -> Run | None:
            async with sessions()() as s:
                inv = (await s.execute(select(Invite).where(Invite.token == token))).scalar_one()
                a = (await s.execute(select(Application).where(Application.invite_id == inv.id))).scalar_one_or_none()
                if a is None:
                    return None
                return (await s.execute(select(Run).where(Run.application_id == a.id).order_by(Run.id.desc()))).scalars().first()

        async def submit(v: httpx.AsyncClient, token: str, key: str) -> dict:
            page = await v.get(f"/apply/{token}")
            assert page.status_code == 200, page.headers.get("location")
            before = await latest_run(token)
            t0 = time.perf_counter()
            r = await v.post(f"/apply/{token}", data=_form_data(SCENARIOS[key]["form"]), files=_files(key))
            assert r.status_code == 303 and r.headers["location"].startswith("/thanks"), (r.status_code, r.headers.get("location"), r.text[:500])
            run = await latest_run(token)
            assert run and (before is None or run.id != before.id)
            await drain()                                        # the background run (and its follow-on work) finishes
            seconds = round(time.perf_counter() - t0, 2)
            ev = (await staff["Arjun Mehta"].get(f"/runs/{run.id}/events")).json()   # what the live view replays
            async with sessions()() as s:
                run = await s.get(Run, run.id)
                a = await s.get(Application, run.application_id)
                rules = (await s.execute(select(RuleResult).where(RuleResult.run_id == run.id))).scalars().all()
                msg = (await s.execute(select(Message).where(Message.run_id == run.id, Message.audience == "vendor"))).scalars().first()
            return dict(run_id=run.id, parent=run.parent_run_id, token=token, state=run.state, run_status=run.status, app_status=a.current_status,
                        risk=run.risk_tier, reason_codes=list(run.reason_codes or []), fraud=bool((run.summary or {}).get("fraud")),
                        diff=(run.summary or {}).get("diff"),
                        flagged={x.rule_id: x.result for x in rules if x.result in ("FAIL", "WARN", "ERROR")},
                        expected_stages=[st for st, _ in stages_for(run.form)], events=ev["events"], events_state=ev["state"],
                        vendor_msg=dict(subject=msg.subject, body=msg.body, state=msg.state) if msg else None, seconds=seconds)

        async def message_states(run_id: int) -> list[str]:
            async with sessions()() as s:
                return [m.state for m in (await s.execute(select(Message).where(Message.run_id == run_id, Message.audience == "vendor")
                                                          .order_by(Message.id))).scalars()]

        async def action(who: str, run_id: int, act: str, comment: str = "", **extra):
            r = await staff[who].post(f"/runs/{run_id}/action", data={"action": act, "comment": comment, **extra})
            await drain()
            return r.status_code, html.unescape(r.text)

        async def status_of(run_id: int) -> str:
            async with sessions()() as s:
                return (await s.get(Application, (await s.get(Run, run_id)).application_id)).current_status

        for key in ORDER:
            token = await invite(key)
            v = httpx.AsyncClient(transport=t, base_url="http://t")
            f = SCENARIOS[key]["form"]
            r = await v.get(f"/apply/{token}")                   # a new invite needs a vendor account first
            out.setdefault("needs_account", []).append(r.headers.get("location", ""))
            nxt = f"/apply/{token}"
            r = await v.post("/vendor/register", data={"company_name": f["legal_name"], "contact_name": f["contact_name"],
                                                       "email": f["contact_email"], "password": PW, "next": nxt})
            assert r.status_code == 303 and r.headers["location"] == nxt, r.text[:500]
            res = out[key] = await submit(v, token, key)
            rid = res["run_id"]

            if key == "happy_nilgiri":
                res["requester_activate"] = await action("Priya Nair", rid, "activate")
                res["maker_activate"] = await action("Arjun Mehta", rid, "activate")
                res["after"] = await status_of(rid)
                async with sessions()() as s:
                    vm = (await s.execute(select(VendorMaster).where(VendorMaster.source_run_id == rid))).scalars().first()
                    res["vendor_id"] = vm.vendor_id if vm else None
                res["vendor_status_page"] = (await v.get(f"/status/{token}")).text

            if key == "wrongdoc_tejas":
                res["vendor_status_page"] = (await v.get(f"/status/{token}")).text
                res["resubmit_form"] = (await v.get(f"/apply/{token}")).status_code
                again = out["wrongdoc_tejas_resubmit"] = await submit(v, token, "wrongdoc_tejas_resubmit")   # the same link
                again["page"] = (await staff["Arjun Mehta"].get(f"/runs/{again['run_id']}")).text

            if key == "borrowed_gstin_kaveri":
                res["vendor_status_before"] = (await v.get(f"/status/{token}")).text
                res["msg_states_before"] = await message_states(rid)
                res["confirm"] = await action("Kavita Rao", rid, "confirm_reject")
                res["msg_states_after"] = await message_states(rid)
                res["vendor_status_after"] = (await v.get(f"/status/{token}")).text
                res["after"] = await status_of(rid)

            if key == "shared_bank_rangoli":
                res["page_maker"] = (await staff["Arjun Mehta"].get(f"/runs/{rid}")).text
                res["maker_approve"] = await action("Arjun Mehta", rid, "review_approve", "Bank letter seen, looks fine")
                res["after_maker"] = await status_of(rid)
                res["checker_approve_no_ack"] = await action("Kavita Rao", rid, "review_approve", "Called the bank: account confirmed")
                res["checker_approve"] = await action("Kavita Rao", rid, "review_approve", "Called the bank: account confirmed", reliability_ack="1")
                res["after"] = await status_of(rid)
            await v.aclose()
        for c in staff.values():
            await c.aclose()
        await dbm.engine().dispose()

    with pytest.MonkeyPatch.context() as mp:
        # The app's background runner, made awaitable: same _run (pipeline, intelligence, mail, reliability), saved readings first.
        mp.setattr(runner, "PACE", 0)
        mp.setattr(runner, "start", lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True))))
        mp.setattr(mailer, "start", lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id))))
        asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


ALL = ORDER + ["wrongdoc_tejas_resubmit"]


@pytest.mark.parametrize("key", ALL)
def test_golden_outcome(golden, key):
    """Status, risk tier, fraud class, the decision's reason codes and every rule that did not pass, exactly."""
    r, g = golden[key], GOLDEN[key]
    assert (r["run_status"], r["risk"], r["fraud"]) == (g["status"], g["risk"], g["fraud"])
    assert r["reason_codes"] == g["reason_codes"]
    assert r["flagged"] == g["flagged"]


@pytest.mark.parametrize("key", ALL)
def test_run_finished_with_every_stage(golden, key):
    r = golden[key]
    assert r["state"] == "done" and r["events_state"] == "done"
    seen = []
    for e in r["events"]:
        if e["stage"] not in seen:
            seen.append(e["stage"])
    assert seen == r["expected_stages"]                     # every stage the pipeline emits for this run, in order
    assert r["expected_stages"] == STAGES_NO_BILL           # invite-path registrations have no bill stage
    last = r["events"][-1]
    assert last["stage"] == "decision" and last["state"] == "done" and last["evidence"]["status"] == GOLDEN[key]["status"]
    for st in r["expected_stages"]:                         # each stage ends done (or failed: it found problems)
        assert [e for e in r["events"] if e["stage"] == st][-1]["state"] in ("done", "failed"), st


@pytest.mark.parametrize("key", ALL)
def test_documents_were_read_from_the_saved_readings(golden, key):
    """No live AI call: every document's reading came from fixtures/read_cache/ (a miss would fall back to Gemini)."""
    origins = [e["evidence"]["origin"] for e in golden[key]["events"] if e["stage"] == "read" and "origin" in e["evidence"]]
    assert origins and set(origins) == {"cache"}
    assert golden[key]["seconds"] < 30


def test_a_new_invite_link_asks_the_vendor_to_register_first(golden):
    assert all(loc.startswith("/vendor/register?next=/apply/") for loc in golden["needs_account"])
    assert golden["emp"] == {"Priya Nair": (1, "sponsor"), "Rahul Desai": (2, "sponsor"), "Arjun Mehta": (3, "maker"), "Kavita Rao": (4, "checker")}


def test_happy_nilgiri_is_activated_by_procurement(golden):
    r = golden["happy_nilgiri"]
    assert r["vendor_msg"]["state"] == "held"                 # the approval mail waits for activation
    code, body = r["requester_activate"]
    assert code == 403 and "Segregation of duties" in body    # Priya requested this vendor
    assert r["maker_activate"][0] == 303
    assert r["after"] == "ACTIVE" and re.fullmatch(r"V-\d{4}", r["vendor_id"] or "")
    assert r["vendor_id"] in html.unescape(r["vendor_status_page"])


def test_wrongdoc_tejas_vendor_is_told_exactly_what_to_send(golden):
    r = golden["wrongdoc_tejas"]
    m = r["vendor_msg"]
    assert m["state"] == "sent" and m["subject"].startswith("Action needed")
    assert "2 things" in m["body"]
    assert "uploaded as your GST registration certificate (gst_certificate.pdf) appears to be a tax invoice" in m["body"]
    assert "Udyam (MSME) certificate" in m["body"]
    assert "appears to be a tax invoice" in html.unescape(r["vendor_status_page"])   # and the vendor sees it
    assert r["resubmit_form"] == 200                                                   # the same link opens the form again


def test_wrongdoc_tejas_resubmission_on_the_same_link_is_approved_with_a_diff(golden):
    first, again = golden["wrongdoc_tejas"], golden["wrongdoc_tejas_resubmit"]
    assert again["token"] == first["token"] and again["parent"] == first["run_id"]
    assert again["app_status"] == "APPROVED"
    assert again["diff"] == {"resolved": ["R-COMP-02", "R-DOC-01"], "still_open": [], "new": []}
    page = html.unescape(again["page"])
    assert all(w in page for w in ("Resolved", "Still open", "New", "Compared with the previous submission."))
    assert "R-COMP-02, R-DOC-01" in page


def test_borrowed_gstin_kaveri_rejection_is_held_until_a_person_confirms(golden):
    r = golden["borrowed_gstin_kaveri"]
    assert r["vendor_msg"]["state"] == "held" and "different legal entity" in r["vendor_msg"]["body"]
    assert r["msg_states_before"] == ["held"]
    assert "different legal entity" not in html.unescape(r["vendor_status_before"])   # not sent yet
    assert r["confirm"][0] == 303                                                      # Kavita confirms
    assert r["msg_states_after"] == ["sent"] and r["after"] == "REJECTED"
    assert "different legal entity" in html.unescape(r["vendor_status_after"])


def test_shared_bank_rangoli_needs_the_finance_controller(golden):
    r = golden["shared_bank_rangoli"]
    assert r["fraud"] and r["risk"] == "high"
    assert "under review" in r["vendor_msg"]["subject"] and r["vendor_msg"]["state"] == "sent"   # neutral message, nothing specific
    code, body = r["maker_approve"]
    assert code == 403 and "needs the Finance controller" in body                                 # Arjun cannot
    assert r["after_maker"] == "PENDING_REVIEW"
    code, body = r["checker_approve_no_ack"]
    assert code == 400 and "reliability check found serious concerns" in body                     # Kavita must read the warning first
    assert r["checker_approve"][0] == 303 and r["after"] == "ACTIVE"                              # then Kavita can


def test_proprietor_shinde_is_approved_at_medium_risk(golden):
    r = golden["proprietor_shinde"]
    assert r["app_status"] == "APPROVED" and r["risk"] == "medium" and r["reason_codes"] == []
