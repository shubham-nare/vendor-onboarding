"""Vendor onboarding: applications, the review queue, change requests, pre-qualified suppliers and invites."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions

router = APIRouter()

# --- applications ------------------------------------------------------------------------------------------------
@router.get("/applications")
async def applications(request: Request, status: str = "", q: str = ""):
    """Every registration this person may see; the ones waiting for their decision first."""
    from onboarding import access
    from onboarding.web import _dashboard_ctx, _employees
    from onboarding.workspace import _apps
    async with read_sessions()() as s:
        _, actor = await staff_or_401(request, s)
        full = access.full_view(actor)
        todo = (await _dashboard_ctx(request, s))["todo"]
        waiting = {t["href"] for t in todo if t["status"] not in ("BILL", "CHANGE")}
        emps = {e.id: e for e in await _employees(s)}
        rows = await _apps(s, actor)
        if status:
            rows = [x for x in rows if x["app"].current_status == status]
        if q:
            rows = [x for x in rows if q.lower() in f"{x['app'].ref} {x['app'].legal_name} {(x['run'].form or {}).get('gstin', '') if x['run'] else ''}".lower()]
        out = []
        for x in rows:
            a, run, inv = x["app"], x["run"], x["invite"]
            came = (f"Invite from {emps[inv.sponsor_id].name if inv.sponsor_id in emps else 'an employee'}" if inv
                    else "A bill for work done" if x["bill"] else "No invite")
            out.append({"ref": a.ref, "name": a.legal_name, "run_id": run.id if run else None, "status": a.current_status,
                        "waiting": bool(run and f"/runs/{run.id}" in waiting), "risk": (run.risk_tier if run and full else None),
                        "vendor": {"id": x["vendor"].vendor_id, "name": x["vendor"].display_name} if x["vendor"] and full else None,
                        "came_in": came, "submitted": when(a.created_at)})
        out.sort(key=lambda r: not r["waiting"])   # stable: otherwise newest first
        return {"applications": out, "filters": {"status": status, "q": q}, "counts": counts(todo)}


# --- review --------------------------------------------------------------------------------------------------------
@router.get("/review")
async def review(request: Request):
    """Everything waiting on this person, grouped: change requests, invoices, vendor decisions."""
    from sqlalchemy import select
    from onboarding import access
    from onboarding.ap.models import ChangeRequest
    from onboarding.intel.models import Vendor
    from onboarding.models import VendorMaster
    from onboarding.web import _all, _dashboard_ctx, _reads
    async with read_sessions()() as s:
        _, actor = await staff_or_401(request, s)
        todo = (await _dashboard_ctx(request, s))["todo"]
        full = access.full_view(actor)
        changes = []
        if full:
            r = await _reads(changes=_all(select(ChangeRequest).where(ChangeRequest.status == "submitted").order_by(ChangeRequest.id)),
                             masters=_all(select(VendorMaster)), vendors=_all(select(Vendor)))
            names = {m.vendor_id: m.legal_name for m in r["masters"]}
            vend = {v.erp_vendor_id: v for v in r["vendors"] if v.erp_vendor_id}
            for c in r["changes"]:
                v = vend.get(c.erp_vendor_id)
                changes.append({"id": c.id, "kind": c.kind, "name": names.get(c.erp_vendor_id, c.erp_vendor_id), "vendor_id": v.vendor_id if v else None,
                                "created": when(c.created_at), "requested": {k: v for k, v in (c.requested or {}).items() if v},
                                "reason": c.reason or "", "document": {"sha256": c.document_sha256, "name": c.document_name} if c.document_sha256 else None,
                                "mine": c.kind != "bank_account" or actor.role == "checker"})
        items = [todo_item(t) for t in todo]
        return {"full": full, "changes": changes, "invoices": [t for t in items if t["status"] == "BILL"],
                "apps": [t for t in items if t["status"] not in ("BILL", "CHANGE")], "counts": counts(todo)}


class Decision(BaseModel):
    decision: str
    note: str = ""


@router.post("/change-requests/{cr_id}/decision")
async def decide_change(request: Request, cr_id: int, body: Decision):
    """Approve or reject a bank-account or contact change (same rules as before: Finance decides bank changes)."""
    from onboarding.ap.web import decide_change_core
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    await decide_change_core(request, cr_id, body.decision, body.note.strip())
    return {"ok": True}


# --- pre-qualified suppliers -----------------------------------------------------------------------------------------
@router.get("/prequalified")
async def prequalified(request: Request, q: str = ""):
    """Registered for future work and checked; not payable until a requester asks for one."""
    from onboarding.web import SPEND_BANDS, prequalified as pq_rows
    async with read_sessions()() as s:
        _, actor = await staff_or_401(request, s)
    rows = await pq_rows(request, q)
    return {"suppliers": [{"id": x["app"].id, "ref": x["app"].ref, "name": x["app"].legal_name, "run_id": x["run"].id if x["run"] else None,
                           "city": x["form"].get("city", ""), "state": x["form"].get("state", ""), "supplies": x["form"].get("supply_note", ""),
                           "reliability": {"level": x["check"].level, "score": x["check"].score} if x["check"] else None} for x in rows],
            "can_request": actor.role == "sponsor", "spend_bands": SPEND_BANDS, "q": q}


class SupplierNeed(BaseModel):
    business_reason: str
    spend_category: str = ""
    spend_band: str


@router.post("/prequalified/{app_id}/request")
async def need_supplier(request: Request, app_id: int, body: SupplierNeed):
    """A requester needs this supplier: invite them and run every check again. Answers with the new application page."""
    from onboarding.web import prequalified_request_core
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    run_id = await prequalified_request_core(request, app_id, body.business_reason, body.spend_category, body.spend_band)
    return {"ok": True, "run_id": run_id, "next": f"/runs/{run_id}"}


# --- invites -----------------------------------------------------------------------------------------------------------
@router.get("/invites")
async def invites(request: Request):
    """Recent invites (requesters see their own) and what is needed to send one."""
    from onboarding.web import SPEND_BANDS, invites as invite_rows
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await invite_rows(request)
    emps, apps, actor = d["emps"], d["apps"], d["actor"]
    rows = []
    for i in d["invites"]:
        a = apps.get(i.id)
        rows.append({"company": i.company_name, "email": i.contact_email, "requested_by": emps[i.sponsor_id].name if i.sponsor_id in emps else "",
                     "reason": i.business_reason, "spend_band": i.spend_band, "high_spend": bool(i.high_spend),
                     "application": {"status": a.current_status, "ref": a.ref} if a else None, "invite_status": i.status,
                     "link": (f"/status/{i.token}" if a else (f"/apply/{i.token}" if not i.scenario_key else None)),
                     "link_label": "vendor view" if a else "open link"})
    return {"invites": rows, "can_invite": actor.role == "sponsor", "actor": person(actor), "demo": get_settings().demo_tools,
            "spend_bands": SPEND_BANDS}


class NewInvite(BaseModel):
    company_name: str
    contact_email: str
    business_reason: str
    spend_category: str
    spend_band: str


@router.post("/invites")
async def create_invite(request: Request, body: NewInvite):
    """A requester invites a vendor; answers with the registration link to send them."""
    from onboarding.web import create_invite_core
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    token = await create_invite_core(request, body.company_name, body.contact_email, body.business_reason, body.spend_category, body.spend_band)
    return {"ok": True, "token": token, "link": f"/apply/{token}"}
