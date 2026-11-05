"""The vendor directory (one row per legal entity) and the history of every decision."""

from __future__ import annotations

from fastapi import APIRouter, Request

from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions

router = APIRouter()

# --- vendors -------------------------------------------------------------------------------------------------------
@router.get("/vendors")
async def vendors(request: Request, q: str = "", status: str = "", risk: str = "", pay: str = "", inv: str = "", sort: str = ""):
    """One row per legal entity. Requesters see only the vendors they asked for, without PAN, GSTIN or risk."""
    from onboarding.intel.vendor360 import STATUS_TEXT
    from onboarding.web import vendor_directory
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await vendor_directory(request, q, status, risk, pay, inv, sort)
    full = d["full"]
    out = []
    for r in d["rows"]:
        v = r["v"]
        own = [f for f in r["flags"] if f != "linked"]
        out.append({"id": v.vendor_id, "name": v.display_name, "erp_id": v.erp_vendor_id, "status": v.status, "status_label": STATUS_TEXT.get(v.status, v.status),
                    "latest_application": r["apps"][-1].ref if r["apps"] else None,
                    "pan": r["pan"] or None if full else None, "gstins": r["gstins"][:2] if full else [],
                    "risk": ({"open": len(own), "fraud": "fraud" in own, "linked": "linked" in r["flags"]} if full else None),
                    "payment": r["pay"], "active_invoices": r["msum"]["active"], "awaiting_review": r["msum"]["awaiting_review"],
                    "approved_unpaid": r["msum"]["approved_unpaid"], "last_activity": when(r["last"]), "next": r["next"] or None})
    return {"vendors": out, "full": full, "filters": {"q": q, "status": status, "risk": risk, "pay": pay, "inv": inv, "sort": sort}}


# --- history ------------------------------------------------------------------------------------------------------
HISTORY_KINDS = ("", "application", "invoice", "purchase_order", "receipt", "change_request")


@router.get("/history")
async def history(request: Request, entity: str = ""):
    """Every material decision, override, invoice step, payment, order, delivery and change request, newest first."""
    from onboarding import bills as B
    from onboarding.ap.web import audit_log
    if entity not in HISTORY_KINDS:
        raise ApiError(400, "Unknown kind of record.")
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    rows = await audit_log(request, entity)
    return {"events": [{"when": when(r["at"]), "who": r["who"], "kind": r["entity"], "record": r["label"], "href": r["href"] or None,
                        "action": B.BILL_ACTION_LABEL.get(r["action"], r["action"].replace("_", " ")), "override": bool(r["override"]),
                        "reason": r["reason"] or None,
                        "vendor": {"id": r["vendor"].vendor_id, "name": r["vendor"].display_name} if r["vendor"] else None} for r in rows],
            "entity": entity}
