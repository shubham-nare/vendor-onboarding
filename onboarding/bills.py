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
    "approved": "Approved for payment", "rejected": "Rejected", "failed": "Check failed",
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
}


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

        # duplicates: the same invoice number from this vendor, in another bill or in its registration
        number = norm_number(b.invoice_number)
        dups = [{"ref": o.ref} for o in (await s.execute(select(VendorBill).where(VendorBill.vendor_id == b.vendor_id, VendorBill.id != b.id,
                                                                                   VendorBill.status != "rejected"))).scalars()
                if norm_number(o.invoice_number) == number]
        for form, ref in (await s.execute(select(Run.form, Application.ref).join(Application, Application.id == Run.application_id)
                                          .where(Run.application_id == b.application_id))).all():
            if (form or {}).get("bill_mode") and norm_number(form.get("bill_invoice_number", "")) == number:
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
                "bill_invoice_date": b.invoice_date, "bill_amount": b.amount, "bill_engaged_by": b.engaged_by_text}
        ctx = Context(form=form, docs={"invoice": info},
                      bill={"engaged_employee": emp.name if emp else None, "engaged_department": emp.department if emp else "", "duplicates": dups})
        _bill_rules(add, ctx, info if read and read.doc_type == "TAX_INVOICE" else None)

        failing = [r for r in rules if r.result in (FAIL, ERROR)]
        b.fraud = any(r.fraud for r in failing)
        b.rules = [r.as_dict() for r in rules]
        b.vendor_items = list(dict.fromkeys(r.vendor_text for r in failing if r.outcome == "VENDOR" and r.vendor_text))
        if b.confirmation == "denied" or any(r.outcome == "REVIEW" or r.result == ERROR for r in failing):
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


def allowed_bill_actions(b: VendorBill, actor: Employee | None, engaged: Employee | None) -> dict:
    """Actions on a vendor bill, each with why it's blocked for the current person (if it is)."""
    acts: list[str] = []
    if b.status in ("awaiting_confirmation", "for_review", "vendor_fix", "ready_for_approval") and b.confirmation == "awaiting" and engaged:
        acts += ["confirm_engagement", "deny_engagement"]
    if b.status in ("ready_for_approval", "for_review"):
        acts += ["approve_payment", "ask_vendor", "reject_bill"]
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
        out[a] = {"blocked": why, "needs_comment": a in ("deny_engagement", "ask_vendor", "reject_bill")}
    return out


BILL_ACTION_LABEL = {
    "confirm_engagement": "Yes, I engaged this vendor for this work",
    "deny_engagement": "No, I didn't engage them",
    "approve_payment": "Approve for payment",
    "ask_vendor": "Ask the vendor to fix something",
    "reject_bill": "Reject the bill",
}


def file_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def parse_date(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except (TypeError, ValueError):
            continue
    return None
