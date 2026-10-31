"""The web app end to end, through HTTP: sponsor invite, vendor form, live events, decision page,
human actions (incl. segregation of duties), resubmission and the document check.
Uses a throwaway SQLite database and cached AI readings (no API calls)."""

import asyncio
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".read_cache"
pytestmark = pytest.mark.skipif(not CACHE.exists() or not any(CACHE.iterdir()), reason="no cached AI readings")


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
            async def as_(who):
                c.cookies.set("actor", str(emp[who]))

            async def submit(key, files=None, token=None, demo=None):
                if token is None:
                    r = await c.get(f"/demo/{key}")
                    assert r.status_code == 303
                    loc = r.headers["location"]
                    token = re.search(r"/apply/([^?]+)", loc).group(1) if "/apply/" in loc else ""
                    page = await c.get(loc)
                    assert page.status_code == 200
                url = f"/apply/{token}" if token else "/apply"
                r = await c.post(url, data=_form_data(cat[demo or key]["form"], demo or key), files=files or {})
                assert r.status_code == 303, r.text
                run_id = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
                await asyncio.gather(*pending)
                pending.clear()
                return run_id, token

            out["dashboard_empty"] = (await c.get("/")).status_code
            # happy path, with a real upload in one slot
            pan = ROOT / "fixtures" / "documents" / "happy_nilgiri" / "pan_card.pdf"
            files = {"pan_card": (pan.name, pan.read_bytes(), "application/pdf")} if pan.exists() else None
            rid, tok = await submit("happy_nilgiri", files=files)
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
            await as_("maker")
            out["rangoli_maker_approve"] = (await c.post(f"/runs/{rid}/action", data={"action": "review_approve", "comment": "looks fine"})).status_code
            await as_("checker")
            out["rangoli_no_comment"] = (await c.post(f"/runs/{rid}/action", data={"action": "ask_vendor", "comment": ""})).status_code
            out["rangoli_ask"] = (await c.post(f"/runs/{rid}/action", data={"action": "ask_vendor", "comment": "Please send a letter from your bank confirming the account holder."})).status_code
            out["rangoli_status"] = (await c.get(f"/status/{tok}")).text

            # unsolicited
            rid, _ = await submit("unsolicited_nilgiri", token="")
            out["unsolicited_page"] = (await c.get(f"/runs/{rid}")).text

            # invites: maker can't, sponsor can
            inv = dict(company_name="Acme Fasteners LLP", contact_email="a@acme.example.com", business_reason="Bolts for the new press line", spend_category="MRO", spend_band="50 lakh - 1 crore")
            await as_("maker")
            out["maker_invite"] = (await c.post("/invites", data=inv)).status_code
            await as_("Rahul Desai")
            r = await c.post("/invites", data=inv)
            out["sponsor_invite"] = (r.status_code, r.headers.get("location", ""))
            out["invites_page"] = (await c.get(r.headers["location"])).text

            for p in ("/", "/outbox", "/assumptions", "/system", "/check?sample=genuine", "/invites"):
                out[p] = await c.get(p)
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
    assert "We need something from you" in flows["tejas_status"] and "tax invoice" in flows["tejas_status"]
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


def test_other_pages_render(flows):
    for p in ("/", "/outbox", "/assumptions", "/system", "/check?sample=genuine", "/invites"):
        assert flows[p].status_code == 200, p
    assert "Intact and cryptographically valid" in flows["/check?sample=genuine"].text
