"""Console Home and the counts in the menu."""

from __future__ import annotations

from fastapi import APIRouter, Request

from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions

router = APIRouter()

@router.get("/console/home")
async def console_home(request: Request):
    from onboarding.web import _dashboard_ctx
    async with read_sessions()() as s:
        _, actor = await staff_or_401(request, s)
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
        return {"actor": person(actor), "requester": actor.role == "sponsor", "open_invites": ctx["open_invites"],
                "stars": stars, "todo": [todo_item(t) | {"fraud": bool(t.get("fraud")) and full} for t in todo],
                "counts": counts(todo), "chasing": [chasing_item(w) for w in ctx["chasing"]],
                "scenarios": [{"key": k, "title": sc["title"], "expected": sc["expected"]}
                              for k, sc in ctx["catalog"].items() if not sc.get("resubmission_of")] if demo else []}


@router.get("/console/pending")
async def pending(request: Request):
    """The counts for the menu and the reminder in the corner."""
    from onboarding.web import _dashboard_ctx
    async with read_sessions()() as s:
        await staff_or_401(request, s)
        todo = (await _dashboard_ctx(request, s))["todo"]
        return counts(todo) | {"count": len(todo), "items": [todo_item(t) for t in todo[:4]]}


@router.get("/help")
async def help_page(request: Request):
    """Who sees what (the same matrix the access rules follow), and whether the demo person switcher is on."""
    from onboarding import access
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    return {"access": [{"information": a, "requester": b, "reviewer": c, "finance": d} for a, b, c, d in access.MATRIX],
            "demo": get_settings().demo_tools}
