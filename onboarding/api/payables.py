"""Invoices from active vendors, and the purchase orders they are matched against."""

from __future__ import annotations

from fastapi import APIRouter, Request

from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions

router = APIRouter()

# --- invoices ----------------------------------------------------------------------------------------------------
@router.get("/invoices")
async def invoices(request: Request, status: str = "", q: str = "", vendor: str = "", amin: str = "", amax: str = "", sort: str = ""):
    """Every invoice this person may see, filtered and sorted; status chips count what the other filters leave."""
    from onboarding import bills as B
    from onboarding.ap.web import STATUS_ORDER, invoices_data
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await invoices_data(request, status, q, vendor, amin, amax, sort)
    full = d["full"]
    rows = [{"id": x["b"].id, "invoice_number": x["b"].invoice_number, "ref": x["b"].ref, "created": when(x["b"].created_at),
             "vendor": {"id": x["b"].vendor_id, "name": x["name"], "profile": x["vendor"].vendor_id if x["vendor"] and full else None},
             "po_number": x["b"].po_number, "amount": x["amount"] if x["b"].amount else None, "status": x["status"],
             "tone": B.INVOICE_TONE.get(x["status"], "slate"), "next": {"title": x["next"][0], "detail": x["next"][1]} if x["next"][0] else None}
            for x in d["rows"]]
    chips = [{"status": st, "count": d["counts"][st], "tone": B.INVOICE_TONE.get(st, "slate"),
              "sum": d["sums"][st] if full and st in ("Approved for payment", "Payment on hold", "Needs internal review", "Blocked for investigation") else None}
             for st in STATUS_ORDER if d["counts"].get(st)]
    return {"invoices": rows, "chips": chips, "full": full, "total": d["total"] if full else None,
            "vendors": [{"id": v, "name": n} for v, n in d["vendors_seen"]],
            "filters": {"status": status, "q": q, "vendor": vendor, "amin": amin, "amax": amax, "sort": sort}}


# --- purchase orders --------------------------------------------------------------------------------------------
@router.get("/purchase-orders")
async def purchase_orders(request: Request, q: str = ""):
    """Every order with delivered, invoiced and paid values; red when an invoice against it doesn't match."""
    from onboarding.ap.web import purchase_orders_data
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await purchase_orders_data(request, q)
    emps = d["emps"]
    return {"orders": [{"id": x["po"].id, "number": x["po"].po_number, "cost_centre": x["po"].cost_centre, "status": x["po"].status,
                        "vendor": {"name": x["po"].vendor_name, "gstin": x["po"].vendor_gstin},
                        "requested_by": emps[x["po"].requester_id].name if x["po"].requester_id in emps else None,
                        "tone": x["tone"], "issues": list(x["issues"]), "total": x["total"], "delivered": x["delivered_value"],
                        "delivery_recorded": bool(x["receipts"]), "invoiced": x["invoiced"] if x["invoices"] else None,
                        "paid": x["paid"] or None} for x in d["rows"]], "q": q}
