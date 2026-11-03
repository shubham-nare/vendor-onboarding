"""Ready-made replies to a vendor about a wrong invoice, filled with the right figures.

We already hold the correct numbers: the purchase order (what was agreed, at what price), the delivery
recorded on it (how much was actually done) and the vendor's registration (GSTIN, verified bank account).
So when an invoice doesn't match, the reviewer doesn't need to work out what to say: each failed check
turns into a message that names the right amount, quantity or rate. The reviewer picks one, edits it if
needed, and sends it with "Ask the vendor to fix something". Nothing is sent automatically.
"""

from __future__ import annotations

from onboarding.rules import inr
from onboarding.validators import mask_account


def _inr(x) -> str:
    try:
        return inr(float(x))
    except (TypeError, ValueError):
        return str(x)


def _num(x) -> str:
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def suggested_replies(b, case, po, vm, buyer: dict) -> list[dict]:
    """One reply per problem found on this invoice, most specific first, then two general ones."""
    rules = {r.get("rule_id"): r for r in (b.rules or []) if r.get("result") == "FAIL"}
    m = (case.match if case else None) or {}
    inv = b.invoice_number or b.ref
    po_no = po.po_number if po else (b.po_number or "")
    out: list[dict] = []

    def add(key, title, text, tone="red"):
        out.append(dict(key=key, title=title, text=text.strip(), tone=tone))

    if "R-PO-06" in rules:
        ev = rules["R-PO-06"].get("evidence", {})
        exp, billed = ev.get("expected", m.get("expected_total")), ev.get("billed", m.get("invoiced_total"))
        add("total", f"Amount should be {_inr(exp)}",
            f"Please recheck invoice {inv}. Against our purchase order {po_no} and the work delivered so far, the amount due is "
            f"{_inr(exp)} including GST. Your invoice shows {_inr(billed)}. Please send a corrected invoice for {_inr(exp)}.")
    qty = [ln for ln in m.get("lines", []) if ln.get("billed_qty") is not None and ln.get("received") is not None
           and ln["billed_qty"] + (ln.get("billed_before") or 0) > ln["received"] + 1e-9]
    if "R-PO-04" in rules and qty:
        parts = "; ".join(f"{ln['po_desc'] or ln['description']}: delivered {_num(ln['received'])} {ln.get('unit') or ''}".strip()
                          + f", billed {_num(ln['billed_qty'])}" + (f" ({_num(ln['billed_before'])} billed before)" if ln.get("billed_before") else "")
                          for ln in qty)
        add("quantity", "Bill only what was delivered",
            f"Invoice {inv} charges for more than we have received against purchase order {po_no}: {parts}. "
            f"Please send a corrected invoice for the quantity delivered. The rest can be invoiced once it is delivered.")
    price = [ln for ln in m.get("lines", []) if ln.get("billed_price") is not None and ln.get("po_price") is not None
             and abs(ln["billed_price"] - ln["po_price"]) > max(1.0, ln["po_price"] * 0.01)]
    if "R-PO-05" in rules and price:
        parts = "; ".join(f"{ln['po_desc'] or ln['description']}: agreed rate {_inr(ln['po_price'])} per {ln.get('unit') or 'unit'}, invoice shows {_inr(ln['billed_price'])}"
                          for ln in price)
        add("price", "Use the agreed rate",
            f"The rates on invoice {inv} don't match purchase order {po_no}: {parts}. Please send a corrected invoice at the agreed rate. "
            f"If a new rate was agreed, tell us who agreed it so we can update the order.")
    for rid, key, title in (("R-PO-07", "gst_rate", "GST rate differs from the order"), ("R-PO-01", "po", "Purchase order number"),
                            ("R-PO-02", "po_two", "Two different PO numbers"), ("R-BILL-05", "adds_up", "Invoice doesn't add up"),
                            ("R-BILL-06", "gst_type", "Wrong type of GST"), ("R-BILL-01", "inv_no", "Invoice number")):
        if rid in rules and rules[rid].get("vendor_text"):
            add(key, title, f"About invoice {inv}: {rules[rid]['vendor_text']}")
    if "R-BILL-02" in rules:
        seller = rules["R-BILL-02"].get("evidence", {}).get("seller_gstin")
        add("gstin", "Invoice under the registered GSTIN",
            f"Invoice {inv} is issued under GSTIN {seller or 'that we could not read'}, but the GSTIN registered with us is {vm.gstin}. "
            f"We can only pay invoices issued under your registered GSTIN. Please reissue the invoice under {vm.gstin}.")
    if "R-BILL-10" in rules:
        add("bank", "We pay only the verified account",
            f"Invoice {inv} gives bank details that differ from the account we verified for you (ending {mask_account(vm.account)[-4:]}). "
            f"We only pay into your verified account. If your bank account has changed, please submit a bank change request from your "
            f"vendor portal; please don't put new bank details on invoices.", tone="red")
    if "R-DUP-PATTERN" in rules or "R-DUP-FILE" in rules:
        add("duplicate", "Looks like an invoice already sent",
            f"Invoice {inv} looks the same as one we have already received for purchase order {po_no}. If it is a new invoice, please give "
            f"it its own invoice number and tell us what work it covers. If it was sent twice by mistake, no action is needed.", tone="amber")
    add("clear_copy", "Send a clearer copy",
        f"We couldn't read all of invoice {inv} clearly. Please upload the original PDF, or a complete, sharp scan with every page, "
        f"so the invoice number, date, amounts and GSTINs are readable.", tone="slate")
    add("addressed", "Address the invoice to us",
        f"Please make sure invoice {inv} is addressed to {buyer['legal_name']}, GSTIN {buyer['gstin']}, and quotes our purchase order "
        f"number{(' ' + po_no) if po_no else ''}.", tone="slate")
    return out
