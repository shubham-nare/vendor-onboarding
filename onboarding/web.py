"""Web pages: sponsor invites, the vendor form, the live run view, the reviewer page with human
actions, the dashboard, the document check, assumptions and system check.

No logins: an "acting as" switcher (cookie) picks one of the seeded employees, so segregation of
duties (sponsor != approver) is visible in the demo.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from onboarding import runner
from onboarding import validators as V
from onboarding.authenticity.assess import assess
from onboarding.config import get_settings
from onboarding.demo_data import SCENARIOS
from onboarding.models import (Application, Document, Employee, Fact, HumanAction, Invite, Message, Run, RunEvent, RuleResult, StoredFile,
                               VendorMaster, now)
from onboarding.pipeline import STAGES, create_run, sessions
from onboarding.rules import SLOT_LABEL, SLOT_TITLE

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "fixtures" / "documents"
PRIVATE = ROOT / "private_inputs"
PUBLIC_SAMPLE = ROOT / "fixtures" / "public" / "gst_certificate_signed_igr_maharashtra.pdf"
MAX_BYTES = 10 * 1024 * 1024
SLOTS = ["gst_certificate", "pan_card", "bank_proof", "udyam_certificate"]
STATUS_LABEL = {"APPROVED": "Approved", "PENDING_VENDOR": "Pending: vendor to fix", "PENDING_REVIEW": "Pending: internal review",
                "REJECTED": "Rejected", "ACTIVE": "Active vendor", "IN_PROGRESS": "In progress", "": "Running"}
LEVEL_NAMES = {"A0": "Declared", "A1": "Evidenced", "A2": "Genuine", "A3": "Cryptographically proven", "A4": "Confirmed at source"}
SPEND_BANDS = ["Under 1 lakh", "1-5 lakh", "5-10 lakh", "10-25 lakh", "25-50 lakh", "50 lakh - 1 crore", "Over 1 crore"]
HIGH_SPEND = {"50 lakh - 1 crore", "Over 1 crore"}
# Internal role codes stay sponsor | maker | checker (stored in the database); people see these labels.
ROLE_LABEL = {"sponsor": "Requester", "maker": "Procurement reviewer", "checker": "Finance controller"}
ROLE_HINT = {
    "sponsor": "Needs a new vendor. Sends the invite with the business reason. Can't approve a vendor they asked for.",
    "maker": "Checks applications. Activates normal-risk vendors and asks vendors to fix things.",
    "checker": "Senior sign-off. Approves high-risk or fraud-flagged vendors; the only one who can reject after review.",
}

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _fmt_dt(d: datetime | None) -> str:
    if not d:
        return ""
    ist = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    return ist.strftime("%d %b, %H:%M IST")


def _mask(name: str, value) -> str:
    """Mask PAN and account numbers wherever extracted fields are displayed."""
    if not isinstance(value, str):
        return value
    n = (name or "").lower()
    if "pan" in n and len(V.normalise_id(value)) == 10:
        return V.mask_pan(value)
    if "account" in n and sum(c.isdigit() for c in value) >= 6:
        return V.mask_account(value)
    return value


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["sigdate"] = lambda v: (f"{v[6:8]}/{v[4:6]}/{v[:4]} {v[8:10]}:{v[10:12]}" if isinstance(v, str) and len(v) >= 12 and v[:12].isdigit() else v)
templates.env.filters["mask"] = lambda value, name="": _mask(name, value)
templates.env.globals.update(STATUS_LABEL=STATUS_LABEL, LEVEL_NAMES=LEVEL_NAMES, SLOT_TITLE=SLOT_TITLE, SLOT_LABEL=SLOT_LABEL,
                             ROLE_LABEL=ROLE_LABEL, ROLE_HINT=ROLE_HINT, BUSINESS_TYPES=V.BUSINESS_TYPES, mask_pan=V.mask_pan, mask_account=V.mask_account)


# --- shared helpers ------------------------------------------------------------------------------
async def _employees(s) -> list[Employee]:
    return list((await s.execute(select(Employee).order_by(Employee.id))).scalars())


async def _actor(request: Request, s) -> Employee | None:
    emps = await _employees(s)
    if not emps:
        return None
    try:
        wanted = int(request.cookies.get("actor", "0"))
    except ValueError:
        wanted = 0
    return next((e for e in emps if e.id == wanted), None) or next((e for e in emps if e.role == "maker"), emps[0])


async def render(request: Request, s, name: str, **ctx) -> HTMLResponse:
    ctx.update(request=request, actor=await _actor(request, s), employees=await _employees(s), path=request.url.path)
    return templates.TemplateResponse(request, name, ctx)


def demo_catalog() -> dict[str, dict]:
    """Demo scenarios the UI can pre-fill: form values + files (fixtures, or private inputs locally)."""
    out = {}
    for key, sc in SCENARIOS.items():
        files = {p.stem: p for p in sorted((DOCS / key).glob("*"))}
        out[key] = dict(title=sc["title"], expected=sc["expected"], form=sc["form"], files=files, invite_scenario=key,
                        resubmission_of=sc.get("resubmission_of"), private=False)
    variants = {
        "handwritten_nilgiri": ("Hand-written PAN on plain paper (phone photo)", "PENDING_VENDOR", {"pan_card": "handwritten_pan.jpg"}),
        "ai_pan_nilgiri": ("AI-generated PAN card image", "PENDING_REVIEW", {"pan_card": "ai_pan.jpg"}),
        "screenshot_gst_nilgiri": ("Screenshot instead of the GST certificate PDF", "PENDING_VENDOR", {"gst_certificate": "screenshot_gst.png"}),
        "ai_cheque_nilgiri": ("AI-generated cancelled cheque", "PENDING_REVIEW", {"bank_proof": "web_cheque_kotak_ai_generated.png"}),
    }
    base = out["happy_nilgiri"]
    for key, (title, expected, swap) in variants.items():
        paths = {slot: PRIVATE / fn for slot, fn in swap.items()}
        if all(p.exists() for p in paths.values()):  # private inputs exist only on Shubham's laptop
            out[key] = dict(base, title=title, expected=expected, files={**base["files"], **paths}, private=True)
    out["unsolicited_nilgiri"] = dict(base, title="Application with no invite (unsolicited)", expected="PENDING_REVIEW", invite_scenario=None)
    return out


def _new_invite_from(tpl: Invite) -> Invite:
    return Invite(token=secrets.token_urlsafe(18), sponsor_id=tpl.sponsor_id, company_name=tpl.company_name, contact_email=tpl.contact_email,
                  business_reason=tpl.business_reason, spend_category=tpl.spend_category, spend_band=tpl.spend_band,
                  high_spend=tpl.high_spend, scenario_key="", expires_at=now() + timedelta(days=14))


async def _latest_run(s, app_id: int) -> Run | None:
    return (await s.execute(select(Run).where(Run.application_id == app_id).order_by(Run.id.desc()))).scalars().first()


# --- dashboard ----------------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    async with sessions()() as s:
        rows = (await s.execute(select(Run, Application).join(Application, Application.id == Run.application_id).order_by(Run.id.desc()).limit(200))).all()
        sponsors = {i.id: i for i in (await s.execute(select(Invite))).scalars()}
        emps = {e.id: e for e in await _employees(s)}
        docs = (await s.execute(select(Document.run_id, Document.read))).all()
        origin: dict[int, list[str]] = {}
        for run_id, read in docs:
            origin.setdefault(run_id, []).append((read or {}).get("origin", ""))
        runs = []
        for run, app in rows:
            inv = sponsors.get(app.invite_id)
            secs = (run.finished_at - run.started_at).total_seconds() if run.finished_at and run.started_at else None
            o = origin.get(run.id, [])
            runs.append(dict(run=run, app=app, sponsor=emps[inv.sponsor_id].name if inv and inv.sponsor_id in emps else "",
                             seconds=secs, fraud=(run.summary or {}).get("fraud"), resubmission=bool(run.parent_run_id),
                             reads="live" if o and all(x == "live" for x in o) else ("saved" if o else "")))
        apps = {r["app"].id: r["app"] for r in runs}
        counts = {k: sum(1 for a in apps.values() if a.current_status == k) for k in ("ACTIVE", "APPROVED", "PENDING_VENDOR", "PENDING_REVIEW", "REJECTED")}
        done = [r for r in runs if r["seconds"] is not None]
        stats = dict(applications=len(apps), runs=len(runs), avg_seconds=round(sum(r["seconds"] for r in done) / len(done), 1) if done else None,
                     fraud=sum(1 for r in runs if r["fraud"]), first_pass=sum(1 for r in runs if not r["resubmission"] and r["run"].status == "APPROVED"))
        return await render(request, s, "dashboard.html", runs=runs, counts=counts, stats=stats, catalog=demo_catalog())


@router.post("/act-as")
async def act_as(request: Request, employee_id: int = Form(...)):
    back = request.headers.get("referer") or "/"
    resp = RedirectResponse(back, status_code=303)
    resp.set_cookie("actor", str(employee_id), max_age=60 * 60 * 24 * 30, samesite="lax")
    return resp


# --- invites (sponsor) -------------------------------------------------------------------------
@router.get("/invites", response_class=HTMLResponse)
async def invites(request: Request, created: str = ""):
    async with sessions()() as s:
        rows = (await s.execute(select(Invite).order_by(Invite.id.desc()).limit(100))).scalars().all()
        emps = {e.id: e for e in await _employees(s)}
        apps = {a.invite_id: a for a in (await s.execute(select(Application).where(Application.invite_id.is_not(None)))).scalars()}
        return await render(request, s, "invites.html", invites=rows, emps=emps, apps=apps, created=created, bands=SPEND_BANDS, high=HIGH_SPEND)


@router.post("/invites")
async def create_invite(request: Request, company_name: str = Form(...), contact_email: str = Form(...), business_reason: str = Form(...),
                        spend_category: str = Form(...), spend_band: str = Form(...)):
    async with sessions()() as s:
        actor = await _actor(request, s)
        if not actor or actor.role != "sponsor":
            raise HTTPException(403, "Only a requester (the employee who needs the vendor) can send an invite. Switch 'Acting as' to Priya Nair or Rahul Desai.")
        if len(business_reason.strip()) < 10:
            raise HTTPException(400, "Please give a business reason (at least a sentence): it's shown to the approver.")
        inv = Invite(token=secrets.token_urlsafe(18), sponsor_id=actor.id, company_name=company_name.strip(), contact_email=contact_email.strip(),
                     business_reason=business_reason.strip(), spend_category=spend_category.strip(), spend_band=spend_band,
                     high_spend=spend_band in HIGH_SPEND, expires_at=now() + timedelta(days=14))
        s.add(inv)
        await s.commit()
        return RedirectResponse(f"/invites?created={inv.token}", status_code=303)


# --- vendor form ---------------------------------------------------------------------------------
@router.get("/demo/{key}")
async def demo_start(key: str):
    """Start a demo scenario as a vendor would: a fresh invite (cloned from the seeded one), then the form."""
    cat = demo_catalog()
    if key not in cat:
        raise HTTPException(404, "Unknown scenario")
    sc = cat[key]
    if sc["invite_scenario"] is None:
        return RedirectResponse(f"/apply?demo={key}", status_code=303)
    async with sessions()() as s:
        tpl = (await s.execute(select(Invite).where(Invite.scenario_key == sc["invite_scenario"]).order_by(Invite.id))).scalars().first()
        if not tpl:
            raise HTTPException(409, "Demo data not loaded. Use 'Reset demo' on the System page.")
        inv = _new_invite_from(tpl)
        s.add(inv)
        await s.commit()
        return RedirectResponse(f"/apply/{inv.token}?demo={key}", status_code=303)


async def _invite_or_404(s, token: str) -> Invite:
    inv = (await s.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "This invite link isn't valid. Please contact the person who invited you.")
    await s.refresh(inv, ["sponsor"])
    return inv


@router.get("/apply/{token}", response_class=HTMLResponse)
async def apply_form(request: Request, token: str, demo: str = ""):
    async with sessions()() as s:
        inv = await _invite_or_404(s, token)
        app = (await s.execute(select(Application).where(Application.invite_id == inv.id))).scalars().first()
        prev, message = None, None
        if app:
            prev = await _latest_run(s, app.id)
            if app.current_status != "PENDING_VENDOR" or (prev and prev.state != "done"):
                return RedirectResponse(f"/status/{token}", status_code=303)
            message = (await s.execute(select(Message).where(Message.run_id == prev.id, Message.audience == "vendor"))).scalars().first()
        prev_docs = {d.slot: d for d in (await s.execute(select(Document).where(Document.run_id == prev.id))).scalars()} if prev else {}
        return await render(request, s, "apply.html", invite=inv, token=token, app=app, prev=prev, prev_docs=prev_docs, message=message,
                            **_form_context(demo, prev.form if prev else {"legal_name": inv.company_name, "contact_email": inv.contact_email}))


@router.get("/apply", response_class=HTMLResponse)
async def apply_unsolicited(request: Request, demo: str = ""):
    async with sessions()() as s:
        return await render(request, s, "apply.html", invite=None, token="", app=None, prev=None, prev_docs={}, message=None, **_form_context(demo, {}))


def _form_context(demo: str, values: dict) -> dict:
    cat = demo_catalog()
    sc = cat.get(demo)
    if sc:
        values = dict(sc["form"])
    states = sorted({v for k, v in V.GST_STATE_CODES.items() if "legacy" not in v and k not in ("97", "99")})
    return dict(values=values, demo=demo if sc else "", demo_files={k: p.name for k, p in sc["files"].items()} if sc else {},
                demo_title=sc["title"] if sc else "", states=states, catalog=cat)


async def _collect_form(request: Request) -> tuple[dict, dict[str, tuple[str, bytes]], str]:
    data = await request.form()
    f = {k: (str(data.get(k) or "")).strip() for k in ("business_type", "legal_name", "proprietor_name", "gstin", "pan", "cin", "llpin", "address",
                                                       "city", "state", "pin", "contact_name", "contact_email", "contact_phone", "bank_holder",
                                                       "bank_account", "ifsc", "udyam_no", "country")}
    for k in ("gstin", "pan", "cin", "llpin", "ifsc", "udyam_no"):
        f[k] = f[k].upper().replace(" ", "")
    f["bank_account"] = f["bank_account"].replace(" ", "").replace("-", "")
    f["country"] = f["country"] or "India"
    f["msme"] = data.get("msme") == "on"
    f["gst_registered"] = data.get("gst_registered", "on") == "on"
    files: dict[str, tuple[str, bytes]] = {}
    for slot in SLOTS:
        up = data.get(slot)
        if up is not None and hasattr(up, "read") and getattr(up, "filename", ""):
            raw = await up.read()
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, f"{SLOT_TITLE[slot]} is larger than 10 MB. Please upload a smaller file.")
            if raw:
                files[slot] = (up.filename, raw)
    return f, files, str(data.get("demo") or "")


def _fill_files(files: dict, demo: str, prev_files: dict[str, tuple[str, bytes]], form: dict) -> dict:
    """Uploaded file > demo scenario file > the file sent last time (resubmissions)."""
    sc = demo_catalog().get(demo)
    needed = SLOTS if form.get("msme") else SLOTS[:3]
    for slot in needed:
        if slot in files:
            continue
        if sc and slot in sc["files"]:
            p = sc["files"][slot]
            files[slot] = (p.name, p.read_bytes())
        elif slot in prev_files:
            files[slot] = prev_files[slot]
    return files


@router.post("/apply/{token}")
async def apply_submit(request: Request, token: str):
    form, files, demo = await _collect_form(request)
    async with sessions()() as s:
        inv = await _invite_or_404(s, token)
        app = (await s.execute(select(Application).where(Application.invite_id == inv.id))).scalars().first()
        prev_files, parent = {}, None
        if app:
            prev = await _latest_run(s, app.id)
            if app.current_status != "PENDING_VENDOR":
                return RedirectResponse(f"/status/{token}", status_code=303)
            parent = prev.id
            for d in (await s.execute(select(Document).where(Document.run_id == prev.id))).scalars():
                sf = await s.get(StoredFile, d.sha256)
                prev_files[d.slot] = (d.filename, sf.data)
        files = _fill_files(files, demo, prev_files, form)
        run = await create_run(s, form, files, invite_token=token, parent_run_id=parent)
        if app:
            app.current_status = "IN_PROGRESS"
            await s.commit()
    runner.start(run.id)
    return RedirectResponse(f"/runs/{run.id}?from=vendor", status_code=303)


@router.post("/apply")
async def apply_unsolicited_submit(request: Request):
    form, files, demo = await _collect_form(request)
    files = _fill_files(files, demo, {}, form)
    async with sessions()() as s:
        run = await create_run(s, form, files, invite_token=None)
    runner.start(run.id)
    return RedirectResponse(f"/runs/{run.id}?from=vendor", status_code=303)


@router.get("/status/{token}", response_class=HTMLResponse)
async def vendor_status(request: Request, token: str):
    """What the vendor sees: their reference, status and the messages sent to them."""
    async with sessions()() as s:
        inv = await _invite_or_404(s, token)
        app = (await s.execute(select(Application).where(Application.invite_id == inv.id))).scalars().first()
        msgs, run = [], None
        if app:
            run = await _latest_run(s, app.id)
            run_ids = [r for (r,) in (await s.execute(select(Run.id).where(Run.application_id == app.id))).all()]
            msgs = (await s.execute(select(Message).where(Message.run_id.in_(run_ids), Message.audience == "vendor", Message.state == "sent")
                                    .order_by(Message.id.desc()))).scalars().all()
        return await render(request, s, "status.html", invite=inv, app=app, run=run, msgs=msgs, token=token)


# --- run view ------------------------------------------------------------------------------------
def _event_dict(e: RunEvent) -> dict:
    """What the browser gets: rule titles and results only. Raw evidence (which can hold a PAN or an
    account number) stays server-side and is shown masked on the decision page."""
    ev = dict(e.evidence or {})
    if "rules" in ev:
        ev["rules"] = [{k: r.get(k) for k in ("rule_id", "result", "title")} for r in ev["rules"]]
    ev = {k: v for k, v in ev.items() if k in ("rules", "slot", "origin", "form", "status")}
    return dict(seq=e.seq, stage=e.stage, state=e.state, summary=e.summary, evidence=ev, at=_fmt_dt(e.at))


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_view(request: Request, run_id: int):
    async with sessions()() as s:
        run = await s.get(Run, run_id)
        if not run:
            raise HTTPException(404, "No such run")
        app = await s.get(Application, run.application_id)
        inv = await s.get(Invite, app.invite_id) if app.invite_id else None
        sponsor = await s.get(Employee, inv.sponsor_id) if inv else None
        events = [_event_dict(e) for e in (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq))).scalars()]
        docs = sorted((await s.execute(select(Document).where(Document.run_id == run_id))).scalars().all(),
                      key=lambda d: SLOTS.index(d.slot) if d.slot in SLOTS else 99)
        rules = (await s.execute(select(RuleResult).where(RuleResult.run_id == run_id).order_by(RuleResult.id))).scalars().all()
        facts = (await s.execute(select(Fact).where(Fact.run_id == run_id).order_by(Fact.id))).scalars().all()
        msgs = {m.audience: m for m in (await s.execute(select(Message).where(Message.run_id == run_id).order_by(Message.id))).scalars()}
        extra_msgs = (await s.execute(select(Message).where(Message.run_id == run_id, Message.audience == "vendor").order_by(Message.id))).scalars().all()
        actions = (await s.execute(select(HumanAction, Employee).join(Employee, Employee.id == HumanAction.employee_id)
                                   .where(HumanAction.run_id.in_(select(Run.id).where(Run.application_id == app.id))).order_by(HumanAction.id))).all()
        history = (await s.execute(select(Run).where(Run.application_id == app.id).order_by(Run.id))).scalars().all()
        latest = history[-1].id == run.id
        vendor = (await s.execute(select(VendorMaster).where(VendorMaster.source_run_id.in_([r.id for r in history])))).scalars().first()
        actor = await _actor(request, s)
        return await render(request, s, "run.html", run=run, app=app, invite=inv, sponsor=sponsor, events=events, stages=STAGES, docs=docs,
                            rules=rules, facts=facts, vendor_msg=msgs.get("vendor"), all_vendor_msgs=extra_msgs, internal=msgs.get("internal"),
                            actions=actions, history=history, latest=latest, vendor=vendor, allowed=_allowed_actions(run, app, inv, actor),
                            from_vendor=request.query_params.get("from") == "vendor")


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int, after: int = 0):
    async with sessions()() as s:
        evs = (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after).order_by(RunEvent.seq))).scalars().all()
        run = await s.get(Run, run_id)
        return JSONResponse({"events": [_event_dict(e) for e in evs], "state": run.state if run else "missing"})


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: int, after: int = 0):
    """Server-sent events, tailing run_events in the database (so a refresh or a second viewer sees the same thing)."""
    async def gen():
        last, started, quiet = after, time.monotonic(), 0
        while time.monotonic() - started < 300:
            async with sessions()() as s:
                evs = (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > last).order_by(RunEvent.seq))).scalars().all()
                run = await s.get(Run, run_id)
            finished = False
            for e in evs:
                last = e.seq
                yield f"id: {e.seq}\ndata: {json.dumps(_event_dict(e))}\n\n"
                finished = finished or (e.stage == "decision" and e.state in ("done", "failed"))
            if finished or run is None or (run.state == "interrupted" and not evs):
                yield "event: end\ndata: {}\n\n"
                return
            quiet = 0 if evs else quiet + 1
            if quiet and quiet % 20 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.4)
        yield "event: end\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/files/{sha}")
async def file_view(sha: str):
    async with sessions()() as s:
        sf = await s.get(StoredFile, sha)
        if not sf:
            raise HTTPException(404, "No such file")
        return Response(sf.data, media_type=sf.mime, headers={"Content-Disposition": "inline", "Cache-Control": "private, max-age=3600"})


# --- human actions ---------------------------------------------------------------------------------
ACTIONS = {
    "activate": "Activate vendor",
    "confirm_reject": "Confirm rejection and notify the vendor",
    "override_reject": "Don't reject: send to internal review",
    "review_approve": "Approve and activate",
    "ask_vendor": "Ask the vendor for something",
    "review_reject": "Reject",
}


def _allowed_actions(run: Run, app: Application, inv: Invite | None, actor: Employee | None) -> dict:
    """Which actions apply now, and for each, whether the current person may take it (and why not)."""
    if run.state != "done":
        return {}
    status = app.current_status
    applicable = {"APPROVED": ["activate"], "REJECTED": ["confirm_reject", "override_reject"],
                  "PENDING_REVIEW": ["review_approve", "ask_vendor", "review_reject"]}.get(status, [])
    out = {}
    high = run.risk_tier == "high" or (run.summary or {}).get("fraud")
    for a in applicable:
        why = ""
        if not actor:
            why = "Pick who you're acting as."
        elif actor.role == "sponsor" or (inv and inv.sponsor_id == actor.id):
            why = "Segregation of duties: the employee who requested this vendor can't approve, activate or reject it."
        elif a in ("review_reject",) and actor.role != "checker":
            why = "Only the Finance controller can reject after review."
        elif a in ("activate", "review_approve") and high and actor.role != "checker":
            why = "High-risk or fraud-flagged: needs the Finance controller."
        out[a] = dict(label=ACTIONS[a], blocked=why, needs_comment=a in ("override_reject", "review_approve", "ask_vendor", "review_reject"))
    return out


async def _activate(s, run: Run, app: Application) -> VendorMaster:
    n = (await s.execute(select(func.count(VendorMaster.id)).where(VendorMaster.source_run_id.is_not(None)))).scalar() or 0
    f = run.form
    vm = VendorMaster(vendor_id=f"V-{1001 + n}", legal_name=f.get("legal_name", ""), pan=f.get("pan", "").upper(), gstin=f.get("gstin", "").upper(),
                      account=f.get("bank_account", ""), ifsc=f.get("ifsc", "").upper(), status="Active", source_run_id=run.id)
    s.add(vm)
    app.current_status = "ACTIVE"
    hi = f"Hi {f.get('contact_name') or 'there'},"
    s.add(Message(run_id=run.id, audience="vendor", subject=f"Your vendor account is active (Ref {app.ref})", state="sent",
                  body=f"{hi}\n\n{f.get('legal_name')} is now an active vendor. Your vendor ID is {vm.vendor_id}. Please quote it on every invoice; "
                       "invoices are paid after the purchase order and goods receipt are matched.\n\nVendor Onboarding Team"))
    return vm


@router.post("/runs/{run_id}/action")
async def run_action(request: Request, run_id: int, action: str = Form(...), comment: str = Form("")):
    async with sessions()() as s:
        run = await s.get(Run, run_id)
        if not run:
            raise HTTPException(404, "No such run")
        app = await s.get(Application, run.application_id)
        latest = await _latest_run(s, app.id)
        if latest.id != run.id:
            raise HTTPException(409, "A newer submission exists; act on that one.")
        inv = await s.get(Invite, app.invite_id) if app.invite_id else None
        actor = await _actor(request, s)
        allowed = _allowed_actions(run, app, inv, actor)
        if action not in allowed:
            raise HTTPException(409, "That action doesn't apply to this application right now.")
        if allowed[action]["blocked"]:
            raise HTTPException(403, allowed[action]["blocked"])
        comment = comment.strip()
        if allowed[action]["needs_comment"] and len(comment) < 5:
            raise HTTPException(400, "Please write a short reason: it goes on the audit trail.")
        held = (await s.execute(select(Message).where(Message.run_id == run.id, Message.audience == "vendor", Message.state == "held"))).scalars().first()
        hi = f"Hi {run.form.get('contact_name') or 'there'},"
        if action == "activate":
            if held:
                held.state = "sent"
            await _activate(s, run, app)
        elif action == "confirm_reject":
            if held:
                held.state = "sent"
            app.current_status = "REJECTED"
        elif action == "override_reject":
            app.current_status = "PENDING_REVIEW"
            if held:
                held.state = "draft"
        elif action == "review_approve":
            await _activate(s, run, app)
        elif action == "ask_vendor":
            app.current_status = "PENDING_VENDOR"
            s.add(Message(run_id=run.id, audience="vendor", subject=f"Action needed: your vendor registration (Ref {app.ref})", state="sent",
                          body=f"{hi}\n\n{comment}\n\nUpdate your submission using the same link you received from us.\n\nVendor Onboarding Team"))
        elif action == "review_reject":
            app.current_status = "REJECTED"
            s.add(Message(run_id=run.id, audience="vendor", subject=f"Your vendor registration (Ref {app.ref}): unable to proceed", state="sent",
                          body=f"{hi}\n\nThank you for your interest. After review, we're unable to proceed with your registration at this time.\n\nVendor Onboarding Team"))
        s.add(HumanAction(run_id=run.id, employee_id=actor.id, action=action, comment=comment))
        await s.commit()
    return RedirectResponse(f"/runs/{run_id}#actions", status_code=303)


# --- outbox, document check, assumptions, system -----------------------------------------------------
@router.get("/outbox", response_class=HTMLResponse)
async def outbox(request: Request):
    async with sessions()() as s:
        rows = (await s.execute(select(Message, Run, Application).join(Run, Run.id == Message.run_id).join(Application, Application.id == Run.application_id)
                                .where(Message.audience == "vendor").order_by(Message.id.desc()).limit(100))).all()
        return await render(request, s, "outbox.html", rows=rows)


@router.get("/check", response_class=HTMLResponse)
async def doc_check(request: Request, sample: str = ""):
    async with sessions()() as s:
        results = []
        if sample == "genuine" and PUBLIC_SAMPLE.exists():
            results.append(_check_one(PUBLIC_SAMPLE.name, PUBLIC_SAMPLE.read_bytes()))
        return await render(request, s, "check.html", results=results)


def _check_one(filename: str, raw: bytes, label: str = "") -> dict:
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    a = assess(raw, mime, None)
    d = a.as_dict()
    d["facts"] = {k: v for k, v in d["facts"].items() if k != "text"}
    return dict(filename=filename + (f" ({label})" if label else ""), size=len(raw), mime=mime, auth=d)


@router.post("/check", response_class=HTMLResponse)
async def doc_check_post(request: Request, file_a: UploadFile = File(None), file_b: UploadFile = File(None), with_sample: str = Form("")):
    results = []
    if with_sample and PUBLIC_SAMPLE.exists():
        results.append(_check_one(PUBLIC_SAMPLE.name, PUBLIC_SAMPLE.read_bytes(), "genuine sample"))
    for up in (file_a, file_b):
        if up is not None and up.filename:
            raw = await up.read()
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, "File larger than 10 MB")
            results.append(_check_one(up.filename, raw))
    async with sessions()() as s:
        return await render(request, s, "check.html", results=results)


@router.get("/assumptions", response_class=HTMLResponse)
async def assumptions(request: Request):
    async with sessions()() as s:
        return await render(request, s, "assumptions.html")


@router.get("/system", response_class=HTMLResponse)
async def system(request: Request, done: str = ""):
    st = get_settings()
    checks = []
    t = time.monotonic()
    async with sessions()() as s:
        try:
            counts = {m.__tablename__: (await s.execute(select(func.count()).select_from(m))).scalar() for m in (Employee, Invite, Application, Run, VendorMaster)}
            checks.append(("Database (Neon Postgres)", True, f"connected in {round((time.monotonic() - t) * 1000)} ms; " + ", ".join(f"{k}: {v}" for k, v in counts.items())))
        except Exception as e:
            checks.append(("Database", False, type(e).__name__))
        checks.append(("Gemini API key", bool(st.gemini_api_key), f"models: {st.gemini_model} (fallback {st.gemini_fallback_model})" if st.gemini_api_key else "missing: documents can only be read from saved readings"))
        from onboarding.sources import ifsc_lookup
        r = await ifsc_lookup("HDFC0000009")
        checks.append(("Bank branch lookup (Razorpay IFSC, live)", r.live and r.status == "FOUND", r.source + (f": {r.data.get('BANK')}, {r.data.get('BRANCH')}" if r.data else "")))
        checks.append(("Simulated sources", True, "GST status, PAN status, penny-drop, CIN, Udyam answer from the seeded sim_registry table (labelled SIMULATED)"))
        checks.append(("Background runs", True, f"{runner.busy()} running now (max 2 at a time)"))
        return await render(request, s, "system.html", checks=checks, done=done)


@router.post("/system/reset")
async def reset(passcode: str = Form(...)):
    if not secrets.compare_digest(passcode, get_settings().admin_passcode):
        raise HTTPException(403, "Wrong passcode")
    if runner.busy():
        raise HTTPException(409, "A run is in progress; try again in a minute.")
    from onboarding.seeding import seed
    await seed(reset=True, dispose=False)
    return RedirectResponse("/system?done=reset", status_code=303)
