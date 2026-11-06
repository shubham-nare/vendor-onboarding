"""Invoices from active vendors, and the purchase orders they are matched against."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions
from onboarding.rules import money

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



def _invoice_line(b, c) -> dict:
    from onboarding import bills as B
    st = B.invoice_status(b, c)
    return {"id": b.id, "number": b.invoice_number or b.ref, "amount": float(money(b.amount)) if b.amount else None,
            "status": st, "tone": B.INVOICE_TONE.get(st, "slate")}


@router.get("/purchase-orders/options")
async def po_options(request: Request):
    """Active vendors and employees, for raising a new order."""
    from onboarding.ap.web import po_options as options
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await options(request)
    return {"vendors": [{"id": m.vendor_id, "name": m.legal_name, "gstin": m.gstin} for m in d["masters"]],
            "employees": [person(e) for e in d["emps"]]}


@router.get("/purchase-orders/{po_id}")
async def po_detail(request: Request, po_id: int):
    """One order with its lines, deliveries, invoices and history."""
    from onboarding.ap.web import po_detail as detail
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    x = await detail(request, po_id)
    d, po, emps = x["d"], x["d"]["po"], x["emps"]
    name = lambda i: emps[i].name if i in emps else None  # noqa: E731
    return {"id": po.id, "number": po.po_number, "status": po.status, "cost_centre": po.cost_centre,
            "vendor": {"name": po.vendor_name, "gstin": po.vendor_gstin, "id": x["vendor"].vendor_id if x["vendor"] else None},
            "requested_by": name(po.requester_id), "approved_by": name(po.approver_id),
            "service_period": f"{po.service_from} to {po.service_to}" if po.service_from else None,
            "pays_into": f"{po.payee_account_display} · {po.payee_ifsc}",
            "totals": {"order": d["total"], "delivered": d["delivered_value"], "invoiced": d["invoiced"], "paid": d["paid"]},
            "lines": [{"id": ln.id, "description": ln.description, "quantity": ln.quantity, "unit": ln.unit, "unit_price": ln.unit_price,
                       "tax_rate": ln.tax_rate, "delivered": d["received"][ln.id], "value": ln.quantity * ln.unit_price * (1 + ln.tax_rate / 100)}
                      for ln in d["lines"]],
            "deliveries": [{"number": g.number, "kind": g.kind, "on": g.received_on, "by": name(g.confirmed_by), "note": g.note} for g in d["receipts"]],
            "invoices": [_invoice_line(b, c) for b, c in d["invoices"]],
            "history": [{"when": when(e.at), "who": e.actor_label, "what": e.action.replace("_", " "),
                         "record": e.entity_label if e.entity == "receipt" else ""} for e in x["audit"]]}


class NewOrderLine(BaseModel):
    description: str
    quantity: float
    unit: str = ""
    unit_price: float
    tax_rate: float = 18


class NewOrder(BaseModel):
    po_number: str
    vendor_id: str
    cost_centre: str = ""
    requester_id: int | None = None
    approver_id: int | None = None
    service_from: str = ""
    service_to: str = ""
    lines: list[NewOrderLine]


@router.post("/purchase-orders")
async def po_create(request: Request, body: NewOrder):
    """Raise a purchase order for an active vendor (reviewers and Finance). Answers with the new order's page."""
    from onboarding.ap.web import po_create_core
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    if not 1 <= len(body.lines) <= 10:
        raise ApiError(400, "An order needs between 1 and 10 lines.")
    form = {k: v for k, v in body.model_dump(exclude={"lines"}).items() if v is not None}
    for i, ln in enumerate(body.lines, 1):
        form |= {f"desc_{i}": ln.description, f"qty_{i}": ln.quantity, f"unit_{i}": ln.unit, f"price_{i}": ln.unit_price, f"tax_{i}": ln.tax_rate}
    pid = await po_create_core(request, {k: (str(v) if not isinstance(v, str) else v) for k, v in form.items()})
    return {"ok": True, "id": pid, "next": f"/purchase-orders/{pid}"}


class Delivery(BaseModel):
    kind: str = "service"
    received_on: str = ""
    note: str = ""
    quantities: dict[int, float]


@router.post("/purchase-orders/{po_id}/deliveries")
async def record_delivery(request: Request, po_id: int, body: Delivery):
    """Record goods received or a service confirmed (the order's requester, reviewers and Finance)."""
    from onboarding.ap.web import po_receipt_core
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    form = {"kind": body.kind, "received_on": body.received_on, "note": body.note} | {f"qty_{k}": str(v) for k, v in body.quantities.items()}
    await po_receipt_core(request, po_id, form)
    return {"ok": True}



# --- bills (vendor-side status) ---------------------------------------------------------------------------------------
@router.get("/bills")
async def bills(request: Request):
    """Bills from active vendors (with the checks' status) and bills sent with a registration."""
    from onboarding import bills as B
    from onboarding.portal import bills_list
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await bills_list(request)
    emps, full = d["emps"], d["full"]
    confirmation = {"confirmed": "confirmed", "denied": "denies", "awaiting": "not confirmed yet"}
    return {"full": full,
            "bills": [{"id": b.id, "ref": b.ref, "vendor": {"name": vm.legal_name, "id": vm.vendor_id}, "invoice_number": b.invoice_number,
                       "amount": float(money(b.amount) or 0), "status": b.status, "status_label": B.STATUS_TEXT.get(b.status, b.status),
                       "risk": b.risk_tier, "fraud": bool(b.fraud) and full,
                       "asked_for_by": emps[b.engaged_employee_id].name if b.engaged_employee_id in emps else b.engaged_by_text,
                       "confirmation": b.confirmation} for b, vm in d["rows"]],
            "with_registration": [{"ref": r["app"].ref, "name": r["app"].legal_name, "run_id": r["run"].id if r["run"] else None,
                                   "invoice_number": (r["run"].form or {}).get("bill_invoice_number") if r["run"] else None,
                                   "amount": float(money((r["run"].form or {}).get("bill_amount")) or 0) if r["run"] else 0,
                                   "asked_for_by": r["emp"].name if r["emp"] else r["bill"].engaged_by_text,
                                   "confirmation": confirmation.get(r["bill"].confirmation, r["bill"].confirmation)} for r in d["regs"]]}
