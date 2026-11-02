"""Three-way match for an invoice from an active vendor: the bill (as read by the AI) against the company's purchase
order and its goods receipt / service confirmation, plus duplicate and payment-history checks.

Each check is a rule result (R-PO-*, R-DUP-*), like the existing bill rules, so the same status logic, vendor
messages and reviewer actions apply. A mismatch is never called fraud by itself: it says exactly what differs,
how much, and what the reviewer should do. Identity, GSTIN, tax type and payee-bank checks are the existing bill
rules (R-BILL-02, -05, -06, -10) and run alongside these.
"""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select

from onboarding.ap.models import GoodsReceipt, InvoiceCase, POLine, PurchaseOrder, ReceiptLine
from onboarding.models import Document, Employee, VendorBill
from onboarding.rules import FAIL, PASS, WARN, R, inr, money

TOLERANCE_PCT = 1.0     # unit price and total may differ by 1% ...
TOLERANCE_ABS = 1.0     # ... or ₹1, whichever is larger (rounding)
PAID_OR_APPROVED = ("approved",)


def norm_po(x: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (x or "").upper())


def _num(x) -> float | None:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return money(x)


def _tol(base: float) -> float:
    return max(TOLERANCE_ABS, abs(base) * TOLERANCE_PCT / 100)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def _best_line(desc: str, lines: list[POLine]) -> POLine | None:
    if len(lines) == 1:
        return lines[0]
    w = _words(desc)
    scored = sorted(((len(w & _words(l.description)) / max(1, len(w | _words(l.description))), l) for l in lines), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] > 0.2 else None


async def find_po(s, number: str) -> PurchaseOrder | None:
    want = norm_po(number)
    if not want:
        return None
    for po in (await s.execute(select(PurchaseOrder))).scalars():
        if norm_po(po.po_number) == want:
            return po
    return None


async def match_invoice(s, b: VendorBill, read, vendor_gstin: str, dups: list[dict]) -> tuple[list[R], dict]:
    """Returns (rule results, match detail for display). `dups` are other bills with the same invoice number."""
    out: list[R] = []
    add = out.append
    info: dict = {"po": None, "receipts": [], "lines": [], "expected_total": None, "invoiced_total": None,
                  "tolerance": f"{TOLERANCE_PCT:g}% or {inr(TOLERANCE_ABS)}"}
    clear = {f.name: (f.value or "").strip() for f in (read.fields if read else []) if f.value and f.legibility == "clear"}
    printed, chosen = clear.get("po_number", ""), (b.po_number or "").strip()

    # --- duplicates and payment history (run even without a PO) ------------------------------------------------
    others = (await s.execute(select(VendorBill).where(VendorBill.vendor_id == b.vendor_id, VendorBill.id != b.id))).scalars().all()
    cases = {c.bill_id: c for c in (await s.execute(select(InvoiceCase).where(InvoiceCase.bill_id.in_([o.id for o in others] or [-1])))).scalars()}

    def state(o: VendorBill) -> str:
        c = cases.get(o.id)
        if c and c.payment_status == "paid":
            return "paid"
        return {"approved": "approved for payment", "rejected": "rejected", "blocked": "blocked"}.get(o.status, "under review")

    info["blocking_duplicate"] = ""
    for d in dups:
        o = next((x for x in others if x.ref == d.get("ref")), None)
        if o is not None and state(o) in ("paid", "approved for payment"):
            info["blocking_duplicate"] = f"{o.ref} with the same invoice number is already {state(o)}"
    same_file = [o for o in others if o.sha256 == b.sha256]
    reg_file = (await s.execute(select(Document.id).where(Document.sha256 == b.sha256))).first()
    if same_file or reg_file:
        o = same_file[0] if same_file else None
        what = f"{o.ref} ({state(o)})" if o else "a registration document"
        add(R("R-DUP-FILE", "bill", FAIL, f"The same invoice file was already submitted: {what}", "REVIEW", {"other": what},
              internal="Byte-for-byte the same file (SHA-256) as an earlier submission. Pay at most once: check the earlier one first."))
        if o is not None and state(o) in ("paid", "approved for payment"):
            info["blocking_duplicate"] = f"the same file as {o.ref}, which is already {state(o)}"
    else:
        add(R("R-DUP-FILE", "bill", PASS, "This invoice file hasn't been submitted before"))

    # --- purchase order ------------------------------------------------------------------------------------------
    if chosen and printed and norm_po(chosen) != norm_po(printed):
        add(R("R-PO-02", "bill", FAIL, f"PO on the bill ({printed}) differs from the PO you gave ({chosen})", "VENDOR",
              {"printed": printed, "given": chosen},
              vendor_text=f"The purchase order printed on your bill ({printed}) is different from the one you gave ({chosen}). Please tell us which is right."))
    number = chosen or printed
    if not number:
        add(R("R-PO-01", "bill", FAIL, "No purchase order given or printed on the bill", "VENDOR",
              vendor_text="Please tell us the purchase-order number this bill is for (it's on the order we sent you)."))
        return out, info
    po = await find_po(s, number)
    if po is None:
        add(R("R-PO-01", "bill", FAIL, f"Purchase order {number} isn't in our records", "VENDOR", {"po": number},
              vendor_text=f"We couldn't find purchase order {number}. Please check the number on the order we sent you."))
        return out, info
    info["po"] = po.id
    if (po.vendor_gstin or "").upper() != (vendor_gstin or "").upper():
        add(R("R-PO-01", "bill", FAIL, f"Purchase order {po.po_number} was issued to another supplier ({po.vendor_name})", "REVIEW",
              {"po": po.po_number, "po_supplier": po.vendor_name},
              internal="The bill quotes a PO that belongs to a different supplier. Don't pay against it; ask the requester which order this work was for."))
        return out, info
    if po.status != "open":
        add(R("R-PO-01", "bill", FAIL, f"Purchase order {po.po_number} is {po.status}", "REVIEW", {"po": po.po_number},
              internal=f"The order is {po.status}: check with the requester before accepting a bill against it."))
    else:
        add(R("R-PO-01", "bill", PASS, f"Purchase order {po.po_number} found, issued to this vendor", {"po": po.po_number}))

    lines = (await s.execute(select(POLine).where(POLine.po_id == po.id).order_by(POLine.line_no))).scalars().all()
    receipts = (await s.execute(select(GoodsReceipt).where(GoodsReceipt.po_id == po.id).order_by(GoodsReceipt.id))).scalars().all()
    rlines = (await s.execute(select(ReceiptLine).where(ReceiptLine.receipt_id.in_([r.id for r in receipts] or [-1])))).scalars().all()
    received = defaultdict(float)
    for rl in rlines:
        received[rl.po_line_id] += rl.quantity
    names = {e.id: e.name for e in (await s.execute(select(Employee))).scalars()}
    info["receipts"] = [{"id": r.id, "number": r.number, "kind": r.kind, "on": r.received_on, "by": names.get(r.confirmed_by, "")} for r in receipts]
    if not receipts:
        who = names.get(po.requester_id, "the requester")
        add(R("R-PO-03", "bill", FAIL, f"No goods receipt or service confirmation recorded for {po.po_number}", "REVIEW", {"po": po.po_number},
              internal=f"Ask {who} to record what was delivered on the PO before this bill is approved."))
    else:
        add(R("R-PO-03", "bill", PASS, "Delivery confirmed: " + ", ".join(f"{r['number']} by {r['by'] or 'someone'}" for r in info["receipts"]),
              {"receipts": [r["number"] for r in info["receipts"]]}))

    # quantities already billed on this PO by approved invoices (so a PO line can't be billed twice)
    billed_before = defaultdict(float)
    for c in (await s.execute(select(InvoiceCase).where(InvoiceCase.po_id == po.id, InvoiceCase.bill_id != b.id))).scalars():
        ob = next((o for o in others if o.id == c.bill_id), None)
        if ob is not None and ob.status in PAID_OR_APPROVED:
            for ln in (c.match or {}).get("lines", []):
                if ln.get("po_line_id"):
                    billed_before[ln["po_line_id"]] += ln.get("billed_qty") or 0

    items = list(read.line_items) if read and getattr(read, "line_items", None) else []
    expected_total, qty_problems, price_problems = 0.0, [], []
    if not items:
        add(R("R-PO-04", "bill", WARN, "The bill's line items couldn't be read: compared on totals only", "WARN",
              internal="Check the quantities on the bill against the receipt by eye."))
        expected_total = sum(min(received[l.id], l.quantity) * l.unit_price * (1 + l.tax_rate / 100) for l in lines)
    for it in items:
        q, price = _num(it.quantity), _num(it.unit_price)
        pl = _best_line(it.description or "", lines)
        row = {"description": it.description, "billed_qty": q, "billed_price": price, "po_line_id": pl.id if pl else None,
               "po_desc": pl.description if pl else "", "ordered": pl.quantity if pl else None, "received": received[pl.id] if pl else None,
               "billed_before": billed_before[pl.id] if pl else 0, "po_price": pl.unit_price if pl else None, "unit": pl.unit if pl else ""}
        info["lines"].append(row)
        if pl is None:
            qty_problems.append(f"'{(it.description or '')[:60]}' isn't on the purchase order")
            continue
        if q is not None:
            if q + billed_before[pl.id] > received[pl.id] + 1e-9:
                qty_problems.append(f"{pl.description[:60]}: billed {q:g} {pl.unit}, delivery confirmed for {received[pl.id]:g}"
                                    + (f" ({billed_before[pl.id]:g} already billed)" if billed_before[pl.id] else ""))
            elif q + billed_before[pl.id] > pl.quantity + 1e-9:
                qty_problems.append(f"{pl.description[:60]}: billed {q:g}, but the order is for {pl.quantity:g}")
            expected_total += q * pl.unit_price * (1 + pl.tax_rate / 100)
        if price is not None and abs(price - pl.unit_price) > _tol(pl.unit_price):
            price_problems.append(f"{pl.description[:60]}: {inr(price)} per {pl.unit or 'unit'} on the bill, {inr(pl.unit_price)} on the order")
    if items:
        if qty_problems:
            add(R("R-PO-04", "bill", FAIL, "Billed quantity exceeds what was confirmed: " + "; ".join(qty_problems), "REVIEW",
                  {"problems": qty_problems},
                  internal="Hold the bill. Ask the requester whether the rest was delivered (then record it on the PO), or ask the vendor for a corrected bill."))
        else:
            add(R("R-PO-04", "bill", PASS, "Billed quantities are within what was ordered and confirmed delivered"))
        if price_problems:
            add(R("R-PO-05", "bill", FAIL, "Unit price differs from the order: " + "; ".join(price_problems), "REVIEW", {"problems": price_problems},
                  internal=f"Prices may differ by {info['tolerance']}. Ask the requester whether a new rate was agreed, or ask for a corrected bill."))
        else:
            add(R("R-PO-05", "bill", PASS, "Unit prices match the order"))

    total = money(clear.get("total_amount"))
    info["invoiced_total"], info["expected_total"] = total, round(expected_total, 2) if expected_total else None
    if total is not None and expected_total:
        if abs(total - expected_total) <= _tol(expected_total):
            add(R("R-PO-06", "bill", PASS, f"Total matches the order and receipt: {inr(total)}", {"expected": round(expected_total, 2), "billed": total}))
        else:
            add(R("R-PO-06", "bill", FAIL, f"Total {inr(total)} differs from {inr(expected_total)} expected from the order and receipt "
                  f"(by {inr(abs(total - expected_total))})", "REVIEW", {"expected": round(expected_total, 2), "billed": total},
                  internal="The expected total is the billed quantities at the PO prices plus the PO's GST rate."))

    taxable = money(clear.get("taxable_value"))
    gst = sum(money(clear.get(k)) or 0 for k in ("cgst_amount", "sgst_amount", "igst_amount"))
    rates = {l.tax_rate for l in lines}
    if taxable and gst and len(rates) == 1:
        rate = next(iter(rates))
        eff = gst / taxable * 100
        if abs(eff - rate) <= 0.5:
            add(R("R-PO-07", "bill", PASS, f"GST rate matches the order ({rate:g}%)"))
        else:
            add(R("R-PO-07", "bill", FAIL, f"GST on the bill is {eff:.1f}%, the order says {rate:g}%", "VENDOR", {"bill_rate": round(eff, 2), "po_rate": rate},
                  vendor_text=f"The GST rate on your bill ({eff:.1f}%) doesn't match the rate on our purchase order ({rate:g}%). Please send a corrected bill."))

    # same amount + same PO + close dates, under a different invoice number
    for o in others:
        oc = cases.get(o.id)
        if not oc or oc.po_id != po.id or o.status == "rejected" or total is None:
            continue
        if money(o.amount) is not None and abs((money(o.amount) or 0) - total) <= 1 and norm_po(o.invoice_number) != norm_po(b.invoice_number):
            add(R("R-DUP-PATTERN", "bill", FAIL, f"Same amount and purchase order as {o.ref} ({o.invoice_number}, {state(o)}): possible duplicate", "REVIEW",
                  {"other": o.ref}, internal="Two bills for the same amount against the same PO under different numbers. Confirm with the requester that both are real."))
            break
    return out, info
