"""The JSON API (/api/v1). Every response is application/json; errors are {"error": "..."} with the right status.

The browser app (onboarding/frontend, built into /static/app.js) draws the screens from these answers.
Logins are the same signed cookies as before (employee: company_session; vendor: vendor_session), and every
endpoint applies the same role rules as the pages did. Screens move here one at a time; the rest are still pages.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from onboarding import auth, followups as FU
from onboarding.config import get_settings
from onboarding.pipeline import read_sessions
from onboarding.rules import money

router = APIRouter(prefix="/api/v1")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def error_response(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _person(e) -> dict | None:
    from onboarding.web import ROLE_LABEL
    if not e:
        return None
    return {"id": e.id, "name": e.name, "first_name": e.name.split()[0], "role": e.role, "role_label": ROLE_LABEL.get(e.role, e.role),
            "department": e.department, "email": e.email}


async def _staff_or_401(request: Request, s):
    from onboarding.web import _actor, staff_member
    staff = await staff_member(request, s)
    if not staff:
        raise ApiError(401, "Please log in to the company console.")
    return staff, (await _actor(request, s)) or staff


def _counts(todo: list[dict]) -> dict:
    return {"review": len(todo), "apps": sum(t["status"] not in ("BILL", "CHANGE") for t in todo)}


# --- session ---------------------------------------------------------------------------------------------------
@router.get("/session")
async def session(request: Request):
    """Who is logged in, who they are acting as (demo person switcher), and the counts for the menu."""
    from onboarding.web import _dashboard_ctx, _employees
    async with read_sessions()() as s:
        staff, actor = await _staff_or_401(request, s)
        demo = get_settings().demo_tools
        todo = (await _dashboard_ctx(request, s))["todo"]
        return {"staff": _person(staff), "actor": _person(actor), "demo": demo,
                "people": [_person(e) for e in await _employees(s)] if demo else [],
                "counts": _counts(todo)}


class ActAs(BaseModel):
    employee_id: int


@router.post("/session/actor")
async def act_as(request: Request, body: ActAs):
    """Demo only: use the console as another employee."""
    from onboarding.web import _employees
    if not get_settings().demo_tools:
        raise ApiError(404, "Not found")
    async with read_sessions()() as s:
        await _staff_or_401(request, s)
        if not any(e.id == body.employee_id for e in await _employees(s)):
            raise ApiError(400, "No such employee.")
    resp = JSONResponse({"ok": True})
    resp.set_cookie("actor", str(body.employee_id), max_age=60 * 60 * 24 * 30, samesite="lax")
    return resp


@router.post("/session/logout")
async def logout():
    resp = JSONResponse({"ok": True, "next": "/"})
    resp.delete_cookie(auth.COMPANY_COOKIE)
    resp.delete_cookie("actor")
    return resp


# --- console home ------------------------------------------------------------------------------------------------
def _todo_item(t: dict) -> dict:
    amount = money(t.get("amount")) if t.get("amount") else None
    return {"href": t["href"], "ref": t["ref"], "name": t["name"], "verb": t["verb"], "status": t["status"],
            "detail": t.get("detail") or "", "amount": float(amount) if amount is not None else None,
            "fraud": bool(t.get("fraud")), "risk": t.get("risk") or "", "waiting": t.get("waiting") or ""}


def _chasing_item(w) -> dict:
    nxt = w.next_step
    return {"run_id": w.run.id, "name": w.app.legal_name, "ref": w.app.ref, "requester": w.requester.name if w.requester else None,
            "tone": w.tone, "days": w.days, "asked": FU.day(w.since),
            "reminded": FU.day(w.reminded.at) if w.reminded else None, "escalated": FU.day(w.escalated.at) if w.escalated else None,
            "next": {"what": nxt[0], "on": FU.day(nxt[1])} if nxt else None}


@router.get("/console/home")
async def console_home(request: Request):
    from onboarding.web import _dashboard_ctx
    async with read_sessions()() as s:
        _, actor = await _staff_or_401(request, s)
        ctx = await _dashboard_ctx(request, s)
        todo, full, work = ctx["todo"], ctx["full"], ctx["work"]
        vendors = sum(t["status"] not in ("BILL", "CHANGE") for t in todo)
        invoices = sum(t["status"] == "BILL" for t in todo)
        stars = [{"label": "Vendors to approve", "count": vendors, "note": "registrations waiting", "href": "/review"},
                 {"label": "Invoices to approve", "count": invoices, "note": "bills waiting", "href": "/review"}]
        if actor.role == "checker":
            stars.append({"label": "Payments to release", "count": work.get("unpaid", 0), "amount": float(work.get("unpaid_amt") or 0),
                          "note": "not yet paid", "href": "/invoices?status=Approved for payment"})
        demo = get_settings().demo_tools
        return {"actor": _person(actor), "requester": actor.role == "sponsor", "open_invites": ctx["open_invites"],
                "stars": stars, "todo": [_todo_item(t) | {"fraud": bool(t.get("fraud")) and full} for t in todo],
                "counts": _counts(todo), "chasing": [_chasing_item(w) for w in ctx["chasing"]],
                "scenarios": [{"key": k, "title": sc["title"], "expected": sc["expected"]}
                              for k, sc in ctx["catalog"].items() if not sc.get("resubmission_of")] if demo else []}


@router.get("/console/pending")
async def pending(request: Request):
    """The counts for the menu and the reminder in the corner."""
    from onboarding.web import _dashboard_ctx
    async with read_sessions()() as s:
        await _staff_or_401(request, s)
        todo = (await _dashboard_ctx(request, s))["todo"]
        return _counts(todo) | {"count": len(todo), "items": [_todo_item(t) for t in todo[:4]]}


def _when(d) -> dict:
    from onboarding.web import _fmt_dt
    return {"at": _iso(d), "label": _fmt_dt(d)}


# --- applications ------------------------------------------------------------------------------------------------
@router.get("/applications")
async def applications(request: Request, status: str = "", q: str = ""):
    """Every registration this person may see; the ones waiting for their decision first."""
    from onboarding import access
    from onboarding.web import _dashboard_ctx, _employees
    from onboarding.workspace import _apps
    async with read_sessions()() as s:
        _, actor = await _staff_or_401(request, s)
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
                        "came_in": came, "submitted": _when(a.created_at)})
        out.sort(key=lambda r: not r["waiting"])   # stable: otherwise newest first
        return {"applications": out, "filters": {"status": status, "q": q}, "counts": _counts(todo)}


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
        _, actor = await _staff_or_401(request, s)
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
                                "created": _when(c.created_at), "requested": {k: v for k, v in (c.requested or {}).items() if v},
                                "reason": c.reason or "", "document": {"sha256": c.document_sha256, "name": c.document_name} if c.document_sha256 else None,
                                "mine": c.kind != "bank_account" or actor.role == "checker"})
        items = [_todo_item(t) for t in todo]
        return {"full": full, "changes": changes, "invoices": [t for t in items if t["status"] == "BILL"],
                "apps": [t for t in items if t["status"] not in ("BILL", "CHANGE")], "counts": _counts(todo)}


class Decision(BaseModel):
    decision: str
    note: str = ""


@router.post("/change-requests/{cr_id}/decision")
async def decide_change(request: Request, cr_id: int, body: Decision):
    """Approve or reject a bank-account or contact change (same rules as before: Finance decides bank changes)."""
    from onboarding.ap.web import decide_change_core
    async with read_sessions()() as s:
        await _staff_or_401(request, s)
    await decide_change_core(request, cr_id, body.decision, body.note.strip())
    return {"ok": True}
