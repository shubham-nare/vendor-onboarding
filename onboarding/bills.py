"""Bills from ACTIVE vendors (after onboarding).

One bill = one invoice file. The check reuses the registration rules for bills (R-BILL-01..10,
document type, authenticity) against the vendor's VERIFIED record in the vendor master. Then:

  checking -> vendor_fix            the vendor corrects and resubmits (same bill, re-checked)
           -> for_review            a person must look (wrong seller, duplicate, bank change, unknown employee...)
           -> awaiting_confirmation the employee who engaged the vendor confirms the work
  awaiting_confirmation -> ready_for_approval -> approved (for payment; PO + goods receipt next)
  "didn't engage them" -> for_review, fraud class (Finance controller only)

Nothing here pays anything. Rules decide; the AI only reads the invoice.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from datetime import datetime

from sqlalchemy import func, select

from onboarding import runner
from onboarding.ai.read import read_with_cache
from onboarding.authenticity.assess import assess
from onboarding.models import Application, Employee, Run, StoredFile, VendorBill, VendorMaster, now
from onboarding.pipeline import sessions
from onboarding.rules import (BILL_HIGH_RISK, DOC_LABEL, ERROR, FAIL, PASS, WARN, Context, DocInfo, R, _bill_rules, money)

log = logging.getLogger("onboarding.bills")
_tasks: set[asyncio.Task] = set()

STATUS_TEXT = {
    "checking": "Checking", "vendor_fix": "Vendor to fix", "for_review": "Internal review",
    "awaiting_confirmation": "Awaiting confirmation", "ready_for_approval": "Ready for approval",
    "approved": "Approved for payment", "rejected": "Rejected", "failed": "Check failed", "blocked": "Blocked for investigation",
    "draft": "Draft",
}
VENDOR_TEXT = {  # what the vendor sees: never the internal reasoning
    "checking": "We're checking your bill. This takes under a minute.",
    "vendor_fix": "We need you to fix something on this bill (see below).",
    "for_review": "Your bill is being reviewed by our team. No action is needed from you.",
    "awaiting_confirmation": "Waiting for our team to confirm the work. No action is needed from you.",
    "ready_for_approval": "Waiting for our team to confirm the work. No action is needed from you.",
    "approved": "Approved. It is paid once the purchase order and receipt are matched.",
    "rejected": "We're unable to pay this bill. Please contact the person who engaged you.",
    "failed": "Your bill is being reviewed by our team. No action is needed from you.",
    "blocked": "Your bill is being reviewed by our team. No action is needed from you.",
    "draft": "Not sent yet: check the details we read from your bill, then send it.",
}

# The invoice statuses people see. Internal: the full lifecycle. Vendor: only what's safe to say.
INVOICE_TONE = {"Draft": "slate", "Being checked": "indigo", "Needs vendor information": "amber", "Needs internal review": "amber",
                "Matched and ready for approval": "indigo", "Approved for payment": "emerald", "Payment on hold": "amber",
                "Payment in progress": "indigo", "Paid": "emerald", "Rejected": "rose", "Blocked for investigation": "rose"}


def invoice_status(b, case=None) -> str:
    pay = case.payment_status if case else "none"
    if b.status == "approved":
        return {"on_hold": "Payment on hold", "in_progress": "Payment in progress", "paid": "Paid"}.get(pay, "Approved for payment")
    return {"draft": "Draft", "checking": "Being checked", "vendor_fix": "Needs vendor information", "for_review": "Needs internal review",
            "awaiting_confirmation": "Needs internal review", "failed": "Needs internal review", "ready_for_approval": "Matched and ready for approval",
            "rejected": "Rejected", "blocked": "Blocked for investigation"}.get(b.status, b.status)


def vendor_invoice_status(b, case=None) -> str:
    pay = case.payment_status if case else "none"
    if b.status == "approved":
        return "Paid" if pay == "paid" else "Approved for payment"
    return {"draft": "Draft", "checking": "Received", "vendor_fix": "More information required", "rejected": "Rejected"}.get(b.status, "Under review")


def norm_number(x: str) -> str:
    return "".join(ch for ch in (x or "").upper() if ch.isalnum())


async def next_ref(s) -> str:
    n = (await s.execute(select(func.count(VendorBill.id)))).scalar() or 0
    return f"BILL-{n + 1:04d}"


def trail(bill: VendorBill, who: str, role: str, action: str, comment: str = "") -> None:
    bill.trail = [*(bill.trail or []), {"at": now().isoformat(), "who": who, "role": role, "action": action, "comment": comment}]


def start_check(bill_id: int, *, prefer_cache: bool = False) -> None:
    task = asyncio.create_task(_guarded(bill_id, prefer_cache))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _guarded(bill_id: int, prefer_cache: bool) -> None:
    async with runner._slots:  # shares the 2-at-a-time Gemini budget with applications
        try:
            await check_bill(bill_id, prefer_cache=prefer_cache)
        except Exception as e:
            log.exception("bill %s check failed", bill_id)
            async with sessions()() as s:
                b = await s.get(VendorBill, bill_id)
                if b:
                    b.status = "failed"
                    trail(b, "system", "", "check_failed", type(e).__name__)
                    await s.commit()


async def check_bill(bill_id: int, *, prefer_cache: bool = False) -> VendorBill:
    async with sessions()() as s:
        b = await s.get(VendorBill, bill_id)
        sf = await s.get(StoredFile, b.sha256)
        vm = (await s.execute(select(VendorMaster).where(VendorMaster.vendor_id == b.vendor_id))).scalar_one()
        emp = await s.get(Employee, b.engaged_employee_id) if b.engaged_employee_id else None

        res, origin = await read_with_cache(sf.data, sf.mime, prefer="cache" if prefer_cache else "live")
        read = res.read if res.ok else None
        b.read = {"origin": origin, "model": res.model, "seconds": res.seconds, **(read.model_dump() if read else {"error": res.error})}
        auth = assess(sf.data, sf.mime, read)
        b.authenticity = auth.as_dict()
        # the bill's own details come from the bill (AI reading), not from the vendor retyping them
        from onboarding.rules import bill_fields_from_read
        got = bill_fields_from_read(read if read and read.doc_type == "TAX_INVOICE" else None)
        b.invoice_number, b.invoice_date, b.amount = got["bill_invoice_number"], got["bill_invoice_date"], got["bill_amount"]
        b.description, b.po_number = got["bill_description"], got["bill_po"]

        # duplicates: the same invoice number from this vendor, in another bill or in its registration
        number = norm_number(b.invoice_number)
        dups = [{"ref": o.ref} for o in (await s.execute(select(VendorBill).where(VendorBill.vendor_id == b.vendor_id, VendorBill.id != b.id,
                                                                                   VendorBill.status != "rejected"))).scalars()
                if number and norm_number(o.invoice_number) == number]
        for form, ref in (await s.execute(select(Run.form, Application.ref).join(Application, Application.id == Run.application_id)
                                          .where(Run.application_id == b.application_id))).all():
            if number and (form or {}).get("bill_mode") and norm_number(form.get("bill_invoice_number", "")) == number:
                dups.append({"ref": f"{ref} (registration bill)"})
                break

        rules: list[R] = []
        add = rules.append
        info = DocInfo("invoice", b.filename, b.sha256, sf.mime, read, origin, auth)
        if not read:
            add(R("R-DOC-00", "documents", ERROR, "Automatic reading of the bill failed", "REVIEW", internal="Check the file by hand."))
        elif read.doc_type != "TAX_INVOICE":
            got = DOC_LABEL.get(read.doc_type, read.doc_type)
            add(R("R-DOC-01", "documents", FAIL, f"The file isn't a tax invoice: it's a {got}", "VENDOR",
                  vendor_text=f"The file you uploaded ({b.filename}) appears to be a {got}, not a tax invoice. Please upload the tax invoice for this work."))
        else:
            add(R("R-DOC-01", "documents", PASS, "Tax invoice recognised"))
        for sig in auth.signals:
            if sig.severity == "info":
                continue
            outcome = {"vendor": "VENDOR", "review": "REVIEW", "fraud": "REVIEW", "warn": "WARN"}[sig.severity]
            add(R(f"R-{sig.code}", "authenticity", WARN if outcome == "WARN" else FAIL, f"Bill: {sig.title}", outcome,
                  {"detail": sig.detail}, vendor_text=sig.vendor_text, internal=sig.detail, fraud=sig.severity == "fraud"))
        form = {"gstin": vm.gstin, "bank_account": vm.account, "bill_mode": True, "bill_invoice_number": b.invoice_number,
                "bill_invoice_date": b.invoice_date, "bill_amount": b.amount, "bill_engaged_by": b.engaged_by_text,
                "bill_read_from_document": True}
        ctx = Context(form=form, docs={"invoice": info},
                      bill={"engaged_employee": emp.name if emp else None, "engaged_department": emp.department if emp else "", "duplicates": dups})
        _bill_rules(add, ctx, info if read and read.doc_type == "TAX_INVOICE" else None)

        # three-way match against the company's purchase order and its receipt / service confirmation
        from onboarding.ap.match import match_invoice
        from onboarding.ap.models import InvoiceCase
        from onboarding.intel.models import Vendor
        match = {"po": None, "receipts": [], "lines": [], "blocking_duplicate": ""}
        if read and read.doc_type == "TAX_INVOICE":
            po_rules, match = await match_invoice(s, b, read, vm.gstin, dups)
            rules.extend(po_rules)
            if not b.po_number and match.get("po"):
                from onboarding.ap.models import PurchaseOrder
                b.po_number = (await s.get(PurchaseOrder, match["po"])).po_number
        if match.get("receipts") and b.confirmation == "awaiting":   # the company's own record that the work was delivered
            b.confirmation = "confirmed"
            trail(b, "system", "", "work_confirmed", "Delivery confirmed by " + ", ".join(f"{r['number']} ({r['by']})" for r in match["receipts"]))
        case = (await s.execute(select(InvoiceCase).where(InvoiceCase.bill_id == b.id))).scalar_one_or_none()
        if case is None:
            case = InvoiceCase(bill_id=b.id)
            s.add(case)
        case.vendor_pk = (await s.execute(select(Vendor.id).where(Vendor.erp_vendor_id == b.vendor_id))).scalar()
        case.po_id, case.receipt_ids = match.get("po"), [r["id"] for r in match.get("receipts", [])]
        case.match = {k: v for k, v in match.items() if k != "receipts"} | {"receipts": match.get("receipts", [])}
        case.updated_at = now()

        failing = [r for r in rules if r.result in (FAIL, ERROR)]
        b.fraud = any(r.fraud for r in failing)
        b.rules = [r.as_dict() for r in rules]
        b.vendor_items = list(dict.fromkeys(r.vendor_text for r in failing if r.outcome == "VENDOR" and r.vendor_text))
        if match.get("blocking_duplicate"):   # never pay twice: stop it outright and say why
            b.status = "blocked"
            case.blocked_reason = f"Duplicate: {match['blocking_duplicate']}."
        elif b.confirmation == "denied" or any(r.outcome == "REVIEW" or r.result == ERROR for r in failing):
            b.status = "for_review"
        elif b.vendor_items or any(r.outcome == "VENDOR" for r in failing):
            b.status = "vendor_fix"
        else:
            b.status = "ready_for_approval" if b.confirmation == "confirmed" else "awaiting_confirmation"
        b.risk_tier = ("high" if b.fraud or b.confirmation == "denied" or (money(b.amount) or 0) >= BILL_HIGH_RISK
                       else "medium" if any(r.result == WARN for r in rules) else "low")
        b.checked_at = now()
        trail(b, "system", "", "checked", STATUS_TEXT[b.status])
        await s.commit()
        return b


def failing_review(b: VendorBill) -> list[dict]:
    return [r for r in (b.rules or []) if r.get("result") in ("FAIL", "ERROR") and r.get("outcome") == "REVIEW"]


def allowed_bill_actions(b: VendorBill, actor: Employee | None, engaged: Employee | None, case=None) -> dict:
    """Actions on a vendor bill, each with why it's blocked for the current person (if it is).
    Approving an invoice is not paying it: payment is released afterwards by a different person (maker-checker)."""
    acts: list[str] = []
    pay = case.payment_status if case else "none"
    if b.status in ("awaiting_confirmation", "for_review", "vendor_fix", "ready_for_approval") and b.confirmation == "awaiting" and engaged:
        acts += ["confirm_engagement", "deny_engagement"]
    if b.status in ("ready_for_approval", "for_review"):
        acts += ["approve_payment", "ask_vendor", "reject_bill"]
    if b.status == "approved":
        acts += {"none": ["release_payment", "hold_payment"], "unpaid": ["release_payment", "hold_payment"], "on_hold": ["release_hold"],
                 "in_progress": ["mark_paid", "hold_payment"]}.get(pay, [])
    if b.status == "blocked":
        acts += ["unblock"]
    elif b.status not in ("rejected", "draft", "checking") and pay != "paid":
        acts += ["block"]
    out = {}
    high = b.risk_tier == "high" or b.fraud or b.confirmation == "denied"
    for a in acts:
        why = ""
        if a in ("confirm_engagement", "deny_engagement"):
            if not actor or actor.id != b.engaged_employee_id:
                why = f"Only {engaged.name}, who the vendor named, can answer this. Switch 'Acting as' to them."
        elif not actor:
            why = "Pick who you're acting as."
        elif actor.role == "sponsor" or actor.id == b.engaged_employee_id:
            why = "Segregation of duties: the employee who engaged the vendor can't approve or reject its bill."
        elif a == "approve_payment" and b.confirmation != "confirmed":
            why = ("Nobody has confirmed the work yet." if b.confirmation == "awaiting"
                   else f"{engaged.name if engaged else 'The named employee'} says they didn't engage this vendor.")
        elif a == "reject_bill" and actor.role != "checker":
            why = "Only the Finance controller can reject a bill."
        elif a == "approve_payment" and high and actor.role != "checker":
            why = "High-risk bill (₹10 lakh or more, or a fraud signal): needs the Finance controller."
        elif a == "approve_payment" and failing_review(b) and actor.role != "checker":
            why = "Checks found discrepancies: only the Finance controller can approve over them, with a reason."
        elif a in ("release_payment", "mark_paid", "release_hold", "unblock") and actor.role != "checker":
            why = "Only Finance releases payments, records them and lifts holds."
        elif a == "release_payment" and case and case.approved_by == actor.id:
            why = "Maker-checker: the person who approved this invoice can't also release its payment."
        out[a] = {"blocked": why, "needs_comment": a in ("deny_engagement", "ask_vendor", "reject_bill", "block", "unblock", "hold_payment",
                                                          "release_hold", "mark_paid")
                  or (a == "approve_payment" and bool(failing_review(b)))}
    return out


BILL_ACTION_LABEL = {
    "confirm_engagement": "Yes, I engaged this vendor for this work",
    "deny_engagement": "No, I didn't engage them",
    "approve_payment": "Approve for payment",
    "ask_vendor": "Ask the vendor to fix something",
    "reject_bill": "Reject the bill",
    "release_payment": "Release payment",
    "mark_paid": "Record the payment",
    "hold_payment": "Put payment on hold",
    "release_hold": "Lift the hold",
    "block": "Block for investigation",
    "unblock": "Unblock and send to review",
}
COMMENT_HINT = {"mark_paid": "Bank payment reference (UTR)", "hold_payment": "Why payment is on hold", "release_hold": "Why the hold is lifted",
                "block": "What needs investigating", "unblock": "What was found", "ask_vendor": "Message to the vendor",
                "approve_payment": "Why you approve despite the discrepancies (audit trail)"}


def file_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def parse_date(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except (TypeError, ValueError):
            continue
    return None
