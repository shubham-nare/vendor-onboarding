"""The web app end to end, through HTTP: sponsor invite, vendor form, live events, decision page,
human actions (incl. segregation of duties), resubmission and the document check.
Uses a throwaway SQLite database and cached AI readings (no API calls)."""

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from tests.flags import flags_on
from tests.helpers import set_actor

# this module covers the optional features too (bills, Vendor Intelligence, reliability, follow-ups, pre-qualified suppliers)
_features = flags_on("payables", "intel", "reliability", "followups", "unsolicited")

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "fixtures" / "read_cache"   # committed saved readings of the fictional demo documents
assert CACHE.exists() and any(CACHE.iterdir()), "fixtures/read_cache/ (committed saved AI readings) is missing: a broken checkout, not a skip"

from pathlib import Path as _Path  # noqa: E402

APP_JS = (_Path(__file__).resolve().parent.parent / "onboarding" / "static" / "app.js").read_text(encoding="utf-8")


def _form_data(form: dict, demo: str) -> dict:
    d = {k: ("" if v is None else str(v)) for k, v in form.items() if not isinstance(v, bool)}
    if form.get("msme"):
        d["msme"] = "on"
    d["gst_registered"] = "on"
    d["demo"] = demo
    return d


@pytest.fixture(scope="module")
def flows(tmp_path_factory):
    db = tmp_path_factory.mktemp("webdb") / "web.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    import httpx

    from onboarding import runner, web
    from onboarding.main import app
    from onboarding.models import Employee
    from onboarding.pipeline import sessions
    from onboarding.seeding import seed
    from sqlalchemy import select

    runner.PACE = 0
    pending: list[asyncio.Task] = []
    runner.start = lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True)))
    out: dict = {}

    async def go():
        await seed(reset=True, dispose=False)
        async with sessions()() as s:
            emp = {e.role if e.role != "sponsor" else e.name: e.id for e in (await s.execute(select(Employee))).scalars()}
        out["emp"] = emp
        cat = web.demo_catalog()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD, DEMO_VENDOR
            await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})
            await c.post("/vendor/login", data={"email": DEMO_VENDOR["email"], "password": DEMO_PASSWORD})   # demo pre-fill needs a vendor login too

            async def as_(who):
                set_actor(c, str(emp[who]))

            async def submit(key, files=None, token=None, demo=None, extra=None):
                if token is None:
                    r = await c.get(f"/demo/{key}")
                    assert r.status_code == 303
                    loc = r.headers["location"]
                    token = re.search(r"/apply/([^?]+)", loc).group(1) if "/apply/" in loc else ""
                    page = await c.get(loc)
                    assert page.status_code == 200
                url = f"/apply/{token}" if token else "/apply"
                r = await c.post(url, data=_form_data(cat[demo or key]["form"], demo or key) | (extra or {}), files=files or {})
                assert r.status_code == 303, r.text
                run_id = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
                await asyncio.gather(*pending)
                pending.clear()
                return run_id, token

            out["dashboard_empty"] = (await c.get("/")).status_code
            # happy path, with a real upload in one slot
            pan = ROOT / "fixtures" / "documents" / "happy_nilgiri" / "pan_card.pdf"
            files = {"pan_card": (pan.name, pan.read_bytes(), "application/pdf")} if pan.exists() else None
            hf = cat["happy_nilgiri"]["form"]       # the vendor started with the documents and kept what we read
            rec = {k: {"value": hf[k], "from": "GST certificate"} for k in ("legal_name", "gstin", "pan", "bank_account", "ifsc")}
            rid, tok = await submit("happy_nilgiri", files=files, extra={"prefill": json.dumps(rec)})
            out["happy_page"] = (await c.get(f"/runs/{rid}")).text
            out["happy_events"] = (await c.get(f"/runs/{rid}/events")).json()
            out["happy_stream"] = (await c.get(f"/runs/{rid}/stream")).text
            await as_("Priya Nair")
            out["sponsor_activate"] = (await c.post(f"/runs/{rid}/action", data={"action": "activate"})).status_code
            await as_("maker")
            out["maker_activate"] = (await c.post(f"/runs/{rid}/action", data={"action": "activate"})).status_code
            out["happy_after"] = (await c.get(f"/runs/{rid}")).text
            out["happy_status"] = (await c.get(f"/status/{tok}")).text

            # Tejas: pending vendor -> resubmit -> approved
            rid1, tok = await submit("wrongdoc_tejas")
            out["tejas_status"] = (await c.get(f"/status/{tok}")).text
            out["tejas_resubmit_form"] = (await c.get(f"/apply/{tok}")).text
            rid2, _ = await submit("wrongdoc_tejas", token=tok, demo="wrongdoc_tejas_resubmit")
            out["tejas_runs"] = (rid1, rid2)
            out["tejas_page2"] = (await c.get(f"/runs/{rid2}")).text

            # Kaveri: rejected, held, confirmed by a person
            rid, tok = await submit("borrowed_gstin_kaveri")
            out["kaveri_page"] = (await c.get(f"/runs/{rid}")).text
            out["kaveri_vendor_before"] = (await c.get(f"/status/{tok}")).text
            await as_("checker")
            out["kaveri_confirm"] = (await c.post(f"/runs/{rid}/action", data={"action": "confirm_reject"})).status_code
            out["kaveri_vendor_after"] = (await c.get(f"/status/{tok}")).text

            # Rangoli: review, fraud class -> maker can't approve; checker asks the vendor
            rid, tok = await submit("shared_bank_rangoli")
            await as_("checker")
            out["rangoli_page"] = (await c.get(f"/runs/{rid}")).text  # before anyone decides
            await as_("maker")
            out["rangoli_maker_approve"] = (await c.post(f"/runs/{rid}/action", data={"action": "review_approve", "comment": "looks fine"})).status_code
            await as_("checker")
            out["rangoli_no_comment"] = (await c.post(f"/runs/{rid}/action", data={"action": "ask_vendor", "comment": ""})).status_code
            out["rangoli_ask"] = (await c.post(f"/runs/{rid}/action", data={"action": "ask_vendor", "comment": "Please send a letter from your bank confirming the account holder."})).status_code
            out["rangoli_status"] = (await c.get(f"/status/{tok}")).text
            rangoli_tok = tok

            # unsolicited
            rid, _ = await submit("unsolicited_nilgiri", token="")
            out["unsolicited_page"] = (await c.get(f"/runs/{rid}")).text
            out["unsolicited_rid"] = rid

            # invites: maker can't, sponsor can
            inv = dict(company_name="Acme Fasteners LLP", contact_email="a@acme.example.com", business_reason="Bolts for the new press line", spend_category="MRO", spend_band="50 lakh - 1 crore")
            await as_("maker")
            out["maker_invite"] = (await c.post("/invites", data=inv)).status_code
            await as_("Rahul Desai")
            r = await c.post("/invites", data=inv)
            out["sponsor_invite"] = (r.status_code, r.headers.get("location", ""))
            out["invites_page"] = (await c.get("/api/v1/invites")).text
            await as_("maker")
            out["maker_invite_api"] = await c.post("/api/v1/invites", json=inv)
            await as_("Rahul Desai")
            out["sponsor_invite_api"] = (await c.post("/api/v1/invites", json=inv | {"company_name": "Acme Bolts LLP"})).json()

            # bill-first: a vendor who already did work registers with its bill (no invite)
            async def submit_bill(key):
                await as_("maker")  # the reviewer watches the run (a requester sees only their own)
                r = await c.get(f"/demo/{key}")
                assert r.status_code == 303 and r.headers["location"].startswith("/bill")
                bill_form = await c.get(r.headers["location"])
                assert bill_form.status_code == 200
                out.setdefault("bill_form", bill_form.text)
                d = _form_data(cat[key]["form"], key)
                d["bill_mode"] = "1"
                r = await c.post("/bill", data=d)
                assert r.status_code == 303, r.text
                await asyncio.gather(*pending)
                pending.clear()
                rid = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
                page = (await c.get(r.headers["location"])).text
                token = re.search(r'href="/status/([^"]+)"', page).group(1)
                return rid, token

            rid, tok = await submit_bill("bill_kesari")
            out["kesari_page"] = (await c.get(f"/runs/{rid}")).text
            out["kesari_events"] = (await c.get(f"/runs/{rid}/events")).json()
            steps = []
            for who, action in (("maker", "activate"), ("maker", "confirm_engagement"), ("Priya Nair", "confirm_engagement"),
                                ("Priya Nair", "activate"), ("maker", "activate")):
                await as_(who)
                steps.append((who, action, (await c.post(f"/runs/{rid}/action", data={"action": action})).status_code))
            out["kesari_steps"] = steps
            out["kesari_after"] = (await c.get(f"/runs/{rid}")).text
            out["kesari_status"] = (await c.get(f"/status/{tok}")).text
            rid, _ = await submit_bill("bill_kesari")  # the same invoice again
            out["kesari_dup_events"] = (await c.get(f"/runs/{rid}/events")).json()

            rid, tok = await submit_bill("bill_brindavan")
            out["brindavan_page"] = (await c.get(f"/runs/{rid}")).text
            await as_("Rahul Desai")
            out["brindavan_deny"] = (await c.post(f"/runs/{rid}/action", data={"action": "deny_engagement", "comment": "I never asked them for this work."})).status_code
            await as_("maker")
            out["brindavan_maker_approve"] = (await c.post(f"/runs/{rid}/action", data={"action": "review_approve", "comment": "seems fine"})).status_code
            out["brindavan_after"] = (await c.get(f"/runs/{rid}")).text
            out["brindavan_status"] = (await c.get(f"/status/{tok}")).text

            # follow-ups: nothing due today; a reminder on day 3+; a second reminder and a note to the requester on day 7+
            from datetime import timedelta
            from onboarding import followups
            from onboarding.models import now as _now
            out["fu_today"] = await followups.run_once()
            out["fu_day4"] = await followups.run_once(_now() + timedelta(days=4))
            out["fu_day4_again"] = await followups.run_once(_now() + timedelta(days=4))
            out["fu_day8"] = await followups.run_once(_now() + timedelta(days=8))
            out["rangoli_status_chased"] = (await c.get(f"/status/{rangoli_tok}")).text
            await as_("checker")
            out["fu_button"] = await c.post("/system/followups")
            out["console_chasing"] = (await c.get("/api/v1/console/home")).text

            for p in ("/", "/outbox", "/assumptions", "/system", "/check?sample=genuine", "/invites"):
                out[p] = await c.get("/api/v1" + p if p in ("/outbox", "/system") else "/api/v1/check/sample" if p.startswith("/check") else p)
            for who in ("maker", "checker", "Rahul Desai"):  # each person's "Needs your action" queue
                await as_(who)
                out[f"todo_{who}"] = json.dumps((await c.get("/api/v1/console/home")).json()["todo"])   # the Waiting for you list

            # registered for future work -> pre-qualified (not payable) -> a requester needs them -> every check again
            rid = out["unsolicited_rid"]
            await as_("checker")
            out["pq_page_before"] = (await c.get(f"/runs/{rid}")).text
            out["pq_approve"] = await c.post(f"/runs/{rid}/action", data={"action": "review_approve", "comment": "Good packaging supplier for later"})
            out["pq_run"] = (await c.get(f"/runs/{rid}")).text
            from onboarding.models import Application, Message, ReliabilityCheck, Run, VendorMaster
            async with sessions()() as s:
                run = await s.get(Run, rid)
                app_ = await s.get(Application, run.application_id)
                out["pq_status"] = app_.current_status
                out["pq_master"] = (await s.execute(select(VendorMaster).where(VendorMaster.source_run_id == rid))).scalars().first()
                out["pq_msg"] = (await s.execute(select(Message).where(Message.run_id == rid, Message.audience == "vendor"))).scalars().all()[-1].subject
                out["pq_checks"] = (await s.execute(select(ReliabilityCheck).where(ReliabilityCheck.run_id == rid))).scalars().all()
            out["pq_list_checker"] = (await c.get("/api/v1/prequalified")).json()
            await as_("Rahul Desai")
            out["pq_list_requester"] = (await c.get("/api/v1/prequalified")).json()
            app_id = out["pq_list_requester"]["suppliers"][0]["id"]
            out["pq_short_reason"] = (await c.post(f"/prequalified/{app_id}/request", data={"business_reason": "boxes", "spend_band": web.SPEND_BANDS[0]})).status_code
            r = await c.post(f"/prequalified/{app_id}/request", data={"business_reason": "Export cartons for the new line from January",
                                                                      "spend_category": "Packaging", "spend_band": web.SPEND_BANDS[0]})
            out["pq_request"] = (r.status_code, r.headers.get("location", ""))
            await asyncio.gather(*pending)
            pending.clear()
            new_rid = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            await as_("checker")
            out["pq_new_page"] = (await c.get(f"/runs/{new_rid}")).text
            async with sessions()() as s:
                nr = await s.get(Run, new_rid)
                a2 = await s.get(Application, nr.application_id)
                out["pq_new"] = dict(parent=nr.parent_run_id, invite=a2.invite_id, status=a2.current_status, app=a2.id == app_id)
                # a serious reliability finding: approving needs the warning read first
                s.add(ReliabilityCheck(application_id=a2.id, run_id=new_rid, score=75, level="high",
                                       signals=[dict(source="history", weight=40, title="Fraud signal in this check", detail="test", link="")],
                                       sources={"history": "checked", "news": "off", "sanctions": "not connected", "reviews": "not connected"}))
                a2.current_status = "PENDING_REVIEW"
                await s.commit()
            out["rel_page"] = (await c.get(f"/runs/{new_rid}")).text
            out["rel_no_ack"] = (await c.post(f"/runs/{new_rid}/action", data={"action": "review_approve", "comment": "Checked by phone"})).status_code
            out["rel_ack"] = (await c.post(f"/runs/{new_rid}/action", data={"action": "review_approve", "comment": "Checked by phone", "reliability_ack": "1"})).status_code
            async with sessions()() as s:
                out["rel_after"] = (await s.get(Application, app_id)).current_status
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


def test_happy_path_approved_and_streamed(flows):
    assert flows["dashboard_empty"] == 200
    assert "Approved" in flows["happy_page"] and "How well each fact is proven" in flows["happy_page"]
    stages = [e["stage"] for e in flows["happy_events"]["events"]]
    assert stages[0] == "invite" and stages[-1] == "decision" and stages.count("read") >= 4
    assert "event: end" in flows["happy_stream"] and '"stage": "decision"' in flows["happy_stream"]


def test_sponsor_cannot_activate_but_maker_can(flows):
    assert flows["sponsor_activate"] == 403
    assert flows["maker_activate"] == 303
    assert "Active vendor" in flows["happy_after"] and "V-1001" in flows["happy_after"]
    assert "V-1001" in flows["happy_status"]


def test_pan_is_masked_on_the_run_page(flows):
    page = flows["happy_page"].replace("29AAHCN4821K1Z4", "")  # the GSTIN embeds the PAN and is public business data
    leaks = [page[max(0, m.start() - 120):m.end() + 20] for m in re.finditer("AAHCN4821K", page)]
    assert not leaks, leaks
    assert "AAHC••••1K" in page


def test_tejas_fix_and_resubmit(flows):
    assert "Action needed" in flows["tejas_status"] and "tax invoice" in flows["tejas_status"]
    assert "Update your registration" in flows["tejas_resubmit_form"]
    assert "Submission 2" in flows["tejas_page2"] and "Approved" in flows["tejas_page2"] and "Resolved" in flows["tejas_page2"]


def test_rejection_held_until_a_person_confirms(flows):
    assert "Rejected" in flows["kaveri_page"]
    assert "different legal entity" not in flows["kaveri_vendor_before"]
    assert flows["kaveri_confirm"] == 303
    assert "different legal entity" in flows["kaveri_vendor_after"]


def test_fraud_class_needs_finance_controller(flows):
    assert flows["rangoli_maker_approve"] == 403
    assert flows["rangoli_no_comment"] == 400
    assert flows["rangoli_ask"] == 303
    assert "letter from your bank" in flows["rangoli_status"] and "DECCAN" not in flows["rangoli_status"]


def test_unsolicited_goes_to_review(flows):
    assert "Pending: internal review" in flows["unsolicited_page"] and "unsolicited" in flows["unsolicited_page"].lower()


def test_only_sponsors_send_invites(flows):
    assert flows["maker_invite"] == 403
    code, loc = flows["sponsor_invite"]
    assert code == 303 and "created=" in loc and "Acme Fasteners LLP" in flows["invites_page"]
    assert flows["maker_invite_api"].status_code == 403 and "requester" in flows["maker_invite_api"].json()["error"]
    assert flows["sponsor_invite_api"]["link"].startswith("/apply/")


def test_other_pages_render(flows):
    for p in ("/", "/outbox", "/assumptions", "/system", "/check?sample=genuine", "/invites"):
        assert flows[p].status_code == 200, p
    sample = flows["/check?sample=genuine"].json()["results"][0]
    assert sample["signature"]["verified"] and sample["stamp"] == "verified" and "Intact and cryptographically valid" in APP_JS


def _rules(events, stage="bill"):
    return {r["rule_id"]: r["result"] for e in events["events"] if e["stage"] == stage for r in e["evidence"].get("rules", [])}


def test_bill_first_clean_bill_is_approved_but_needs_the_engager(flows):
    page = flows["kesari_page"]
    assert "Approved" in page and "The bill" in page and "Waiting for Priya Nair to confirm" in page
    bill = _rules(flows["kesari_events"])
    assert all(bill.get(r) == "PASS" for r in ("R-BILL-01", "R-BILL-02", "R-BILL-03", "R-BILL-04", "R-BILL-05", "R-BILL-06", "R-BILL-09"))
    assert "R-INV-01" in page and "No invite: the vendor registered with a bill" in page  # a warning, not a block


def test_bill_first_only_the_named_employee_confirms_and_cannot_approve(flows):
    assert [code for _, _, code in flows["kesari_steps"]] == [403, 403, 303, 403, 303]
    assert "Confirmed by Priya Nair" in flows["kesari_after"] and "Passed to accounts payable" in flows["kesari_after"]
    assert "Passed to accounts payable" in flows["kesari_status"]


def test_bill_first_same_invoice_twice_is_flagged(flows):
    assert _rules(flows["kesari_dup_events"]).get("R-BILL-08") == "FAIL"


def test_bill_first_wrong_gst_type_goes_back_to_the_vendor(flows):
    page = flows["brindavan_page"]
    assert "Pending: vendor to fix" in page
    assert "must charge IGST" in page
    assert "94,872.00" in page     # the figures come from the bill itself


def test_bill_form_asks_only_who_engaged_the_vendor(flows):
    form = flows["bill_form"]
    assert 'name="bill_engaged_by"' in form
    assert not any(f'name="{k}"' in form for k in ("bill_invoice_number", "bill_invoice_date", "bill_amount", "bill_description", "bill_po"))


def test_bill_first_denied_engagement_goes_to_finance_and_vendor_learns_nothing(flows):
    assert flows["brindavan_deny"] == 303
    assert flows["brindavan_maker_approve"] == 403
    assert "says they didn't engage this vendor" in flows["brindavan_after"]
    assert "didn't engage" not in flows["brindavan_status"] and "Waiting for our team to confirm the work" in flows["brindavan_status"]


def test_a_form_filled_from_documents_runs_end_to_end(flows):
    page = flows["happy_page"]
    assert "5 details filled from the vendor" in page or "5 details filled from the vendor" in str(flows["happy_events"])


def test_action_queue_follows_the_same_rules_as_the_buttons(flows):
    maker, checker, rahul = flows["todo_maker"], flows["todo_checker"], flows["todo_Rahul Desai"]
    assert "Review and decide" in maker                        # the unsolicited application waits for a reviewer
    assert "Kaveri" not in checker                             # its rejection was already confirmed
    assert "Activate vendor" not in rahul and "Review and decide" not in rahul  # a requester never approves


def test_fraud_case_shows_who_decides_and_where_the_doubt_is(flows):
    import html
    page = html.unescape(flows["rangoli_page"])
    assert "Who can decide this" in page
    assert "Requested this vendor, so can't approve" in page          # Rahul, the requester
    assert "Requesters don't approve vendors" in page                 # Priya, another requester
    assert "I verified the flagged facts" in page                     # approving a fraud signal needs a deliberate tick
    facts = page.split("How well each fact is proven", 1)[1].split("Documents", 1)[0]
    assert "already on file for another vendor" in facts              # the conflict sits next to the bank account
    # the bank branch comes from the live RBI directory, or from the bundled copy when that lookup times out (network)
    assert "Registry" in facts and ("Live source" in facts or "bundled snapshot" in facts) and "Simulated" not in facts


def test_vendors_who_go_quiet_are_chased(flows):
    assert flows["fu_today"]["reminders"] == 0 and flows["fu_today"]["escalations"] == 0 and flows["fu_today"]["waiting"] >= 1
    assert flows["fu_day4"]["reminders"] >= 1 and flows["fu_day4"]["escalations"] == 0
    assert flows["fu_day4_again"]["reminders"] == 0          # never the same step twice
    assert flows["fu_day8"]["escalations"] >= 1 and flows["fu_day8"]["reminders"] == 0
    assert "Second reminder" in flows["rangoli_status_chased"] and "letter from your bank" in flows["rangoli_status_chased"]
    assert flows["fu_button"].status_code == 303 and "done=followups" in flows["fu_button"].headers["location"]
    outbox = flows["/outbox"].text
    assert "reminder" in outbox and "hasn&#39;t replied" in outbox or "hasn't replied" in outbox
    home = json.loads(flows["console_chasing"])                      # Home's Waiting on vendors, from the API
    assert home["chasing"] and any(w["tone"] == "red" and w["escalated"] for w in home["chasing"])
    assert flows["/system"].json()["followups"]["waiting"] >= 0 and "Vendor follow-ups" in APP_JS


def test_registering_for_future_work_puts_a_vendor_on_the_prequalified_list(flows):
    import html
    assert "Add to pre-qualified suppliers" in flows["pq_page_before"]
    assert flows["pq_approve"].status_code == 303 and flows["pq_status"] == "PREQUALIFIED"
    assert flows["pq_master"] is None                                  # not payable: no vendor ID, no bank account in the master
    assert "pre-qualified supplier list" in flows["pq_msg"]
    assert "pre-qualified supplier list" in html.unescape(flows["pq_run"])
    pq = flows["pq_list_checker"]
    assert any("Corrugated boxes" in x["supplies"] for x in pq["suppliers"]) and pq["can_request"] is False   # reviewers don't request
    assert flows["pq_list_requester"]["can_request"] is True and "I need this supplier" in APP_JS


def test_a_requester_needing_a_prequalified_supplier_runs_every_check_again(flows):
    assert flows["pq_short_reason"] == 400
    assert flows["pq_request"][0] == 303 and "/runs/" in flows["pq_request"][1]
    n = flows["pq_new"]
    assert n["app"] and n["invite"] and n["parent"] == flows["unsolicited_rid"]
    assert "No business need yet" not in flows["pq_new_page"]              # it came through an employee's request this time


def test_every_finished_check_gets_a_reliability_check(flows):
    assert flows["pq_checks"] and flows["pq_checks"][0].sources["history"] == "checked"
    assert flows["pq_checks"][0].sources["sanctions"] == "not connected" and flows["pq_checks"][0].sources["news"] == "off"
    assert 'id="reliability"' in flows["pq_page_before"]


def test_a_serious_reliability_finding_must_be_read_before_approving(flows):
    page = flows["rel_page"]
    assert "Possible fraud: check before approving" in page and 'id="rel-modal"' in page and 'class="rel-ack" value=""' in page
    assert flows["rel_no_ack"] == 400
    assert flows["rel_ack"] == 303 and flows["rel_after"] == "ACTIVE"
