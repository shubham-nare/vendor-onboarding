"""The vendor directory: one row per legal entity."""

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
