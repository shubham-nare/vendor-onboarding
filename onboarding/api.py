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
