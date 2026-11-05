"""Decide the status from rule results (fixed precedence), grade each key fact (A0-A4),
set the risk tier, and write the vendor message + internal note. Pure functions.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from onboarding.rules import BILL_HIGH_RISK, ERROR, FAIL, PASS, SKIPPED, WARN, Context, R, inr, money
from onboarding.validators import mask_account, mask_pan

APPROVED, PENDING_VENDOR, PENDING_REVIEW, REJECTED = "APPROVED", "PENDING_VENDOR", "PENDING_REVIEW", "REJECTED"
# Rules that must PASS for an approval (if they apply).
REQUIRED = {"R-INV-01", "R-INV-02", "R-COMP-01", "R-COMP-02", "R-ID-01", "R-ID-02", "R-ID-03", "R-ID-04", "R-ID-05", "R-ID-06",
            "R-BANK-01", "R-XD-01", "R-XD-02", "R-XD-04", "R-NAME-01", "R-NAME-03", "R-RISK-01", "R-RISK-02"}
INVARIANT = "INTERNAL-INVARIANT"   # reason code when decide() would approve without every applicable required rule passing
LEVEL_NAMES ={"A0": "Declared", "A1": "Evidenced", "A2": "Genuine", "A3": "Cryptographically proven", "A4": "Confirmed at source"}


@dataclass
class Fact:
    name: str
    value: str
    level: str
    source: str
    live: bool = False
    note: str = ""


@dataclass
class Decision:
    status: str
    reason_codes: list[str]
    fraud: bool
    risk_tier: str
    cards: list[dict] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    vendor_subject: str = ""
    vendor_body: str = ""
    vendor_state: str = "draft"     # sent (auto) | held (needs a human) | draft
    internal_note: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["facts"] = [asdict(f) for f in self.facts]
        return d


def _failing(rules: list[R], outcome: str) -> list[R]:
    return [r for r in rules if r.result == FAIL and r.outcome == outcome]


def decide(rules: list[R], ctx: Context, ref: str = "") -> Decision:
    errors = [r for r in rules if r.result == ERROR]
    scope = [r for r in rules if r.rule_id.startswith("R-SCOPE") and r.result == FAIL]
    if scope:
        status, winners = PENDING_REVIEW, scope
    elif rej := _failing(rules, "REJECT"):
        status, winners = REJECTED, rej
    elif (rev := _failing(rules, "REVIEW")) or errors:
        status, winners = PENDING_REVIEW, rev + errors
    elif ven := _failing(rules, "VENDOR"):
        status, winners = PENDING_VENDOR, ven
    else:
        status, winners = APPROVED, []

    broken: list[str] = []
    if status == APPROVED:  # invariant: every applicable required rule passed (SKIPPED never counts)
        by_id = {r.rule_id: r for r in rules}
        broken = sorted(rid for rid in REQUIRED if rid in by_id and by_id[rid].result in (FAIL, SKIPPED, ERROR))
        if broken:  # a rule-table bug, never an approval and never a crash: a person looks at it
            status, winners = PENDING_REVIEW, []

    fraud = any(r.fraud and r.result == FAIL for r in rules)
    tier = _tier(rules, ctx, fraud)
    d = Decision(status=status, reason_codes=sorted({r.rule_id for r in winners} | ({INVARIANT} if broken else set())), fraud=fraud, risk_tier=tier)
    d.cards = [_card(r, status) for r in winners][:6]
    if broken:
        d.cards.insert(0, {"rule": INVARIANT, "title": "Internal error: the checks didn't add up, so this was not approved",
                           "detail": f"No check failed in a way that stops approval, but these required checks did not pass: {', '.join(broken)}. "
                                     "Review them and the documents before deciding.",
                           "fraud": False, "next": "A reviewer decides: approve, ask the vendor, or reject."})
    d.facts = grade(rules, ctx)
    _messages(d, rules, ctx, ref)
    if broken:
        d.internal_note += f"\n- [INTERNAL] {INVARIANT}: required checks did not pass but nothing stopped approval: {', '.join(broken)}"
        logging.getLogger("onboarding.decision").error("approval invariant broken for %s: %s", ref or "?", broken)
    return d


def _tier(rules: list[R], ctx: Context, fraud: bool) -> str:
    if fraud or (ctx.invite and ctx.invite.get("high_spend")):
        return "high"
    if ctx.form.get("bill_mode") and (money(ctx.form.get("bill_amount")) or 0) >= BILL_HIGH_RISK:
        return "high"
    by_id = {r.rule_id: r for r in rules}
    personal = by_id.get("R-NAME-03") and "proprietor" in by_id["R-NAME-03"].title
    if personal or any(r.result == WARN for r in rules):
        return "medium"
    return "low"


def _card(r: R, status: str) -> dict:
    nxt = {REJECTED: "A person confirms the rejection before the vendor is told.",
           PENDING_REVIEW: "A reviewer decides: approve, ask the vendor, or reject.",
           PENDING_VENDOR: "The vendor has been asked to fix this."}.get(status, "")
    return {"rule": r.rule_id, "title": r.title, "detail": r.internal or r.vendor_text, "fraud": r.fraud, "next": nxt}


def grade(rules: list[R], ctx: Context) -> list[Fact]:
    """How well each key fact is proven. Simulated sources never raise a fact to A4."""
    by_id = {r.rule_id: r for r in rules}
    ok = lambda rid: rid in by_id and by_id[rid].result == PASS  # noqa: E731
    doc_level = lambda slot: (ctx.docs[slot].auth.level if slot in ctx.docs and ctx.docs[slot].auth else "A0")  # noqa: E731
    f = ctx.form
    facts = []

    def level_for(passed: bool, slot: str, cap: str = "A3") -> str:
        if not passed:
            return "A0"
        lv = doc_level(slot)
        return min(lv, cap) if lv != "A0" else "A1"

    conflict = by_id.get("R-XD-03") is not None and by_id["R-XD-03"].result == FAIL
    gst_level = "A0" if conflict else level_for(ok("R-XD-01"), "gst_certificate")
    facts.append(Fact("GSTIN", f.get("gstin", ""), gst_level, "GST certificate" + (" (GSTN digital signature)" if gst_level == "A3" else ""),
                      note="Checked against the GST registry"))
    facts.append(Fact("Legal name", f.get("legal_name", ""), level_for(ok("R-NAME-01"), "gst_certificate"), "GST certificate"))
    facts.append(Fact("PAN", mask_pan(f.get("pan", "")), level_for(ok("R-XD-02"), "pan_card", "A2"), "PAN card",
                      note="Checked against the PAN registry"))
    facts.append(Fact("Bank account", mask_account(f.get("bank_account", "")), level_for(ok("R-XD-04") and ok("R-NAME-03"), "bank_proof", "A2"),
                      "Cancelled cheque / bank letter", note="Checked by penny-drop"))
    ifsc = ctx.sources.get("ifsc")
    if ifsc and ifsc.status == "FOUND":
        facts.append(Fact("Bank branch", f"{ifsc.data.get('BANK')}, {ifsc.data.get('BRANCH')}", "A4" if ifsc.live else "A1", ifsc.source, live=ifsc.live))
    if f.get("msme"):
        facts.append(Fact("MSME (Udyam)", f.get("udyam_no", ""), level_for(ok("R-MSME-01"), "udyam_certificate", "A2"), "Udyam certificate"))
    return facts


def _messages(d: Decision, rules: list[R], ctx: Context, ref: str) -> None:
    f = ctx.form
    hi = f"Hi {f.get('contact_name') or 'there'},"
    company = f.get("legal_name") or "your business"
    if d.status == PENDING_VENDOR:
        items, seen = [], set()
        for r in _failing(rules, "VENDOR"):
            if r.vendor_text and r.vendor_text not in seen:
                seen.add(r.vendor_text)
                items.append(r.vendor_text)
        ok_bits = [lbl for lbl, rid in (("PAN", "R-XD-02"), ("GSTIN", "R-ID-02"), ("bank details", "R-XD-04")) if any(r.rule_id == rid and r.result == PASS for r in rules)]
        body = [hi, "", f"Thank you for submitting {company}'s details. We need {'one thing' if len(items) == 1 else f'{len(items)} things'} to complete your registration:", ""]
        body += [f"{i}. {t}" for i, t in enumerate(items, 1)]
        if ok_bits:
            joined = ok_bits[0] if len(ok_bits) == 1 else ", ".join(ok_bits[:-1]) + " and " + ok_bits[-1]
            body += ["", f"Your {joined} checked out, so you won't need to re-enter them."]
        body += ["", "Update your submission using the same link you received from us.", "", "Vendor Onboarding Team"]
        d.vendor_subject, d.vendor_body, d.vendor_state = f"Action needed: your vendor registration (Ref {ref})", "\n".join(body), "sent"
    elif d.status == PENDING_REVIEW:
        scope = next((r for r in rules if r.rule_id.startswith("R-SCOPE") and r.result == FAIL), None)
        text = scope.vendor_text if scope else "Your application is being reviewed by our team. No action is needed from you right now; we'll be in touch within 2 business days."
        d.vendor_subject, d.vendor_body, d.vendor_state = f"Your vendor registration (Ref {ref}) is under review", f"{hi}\n\nThank you. {text}\n\nVendor Onboarding Team", "sent"
    elif d.status == REJECTED:
        r = _failing(rules, "REJECT")[0]
        d.vendor_subject = f"Your vendor registration (Ref {ref}): unable to proceed"
        d.vendor_body, d.vendor_state = f"{hi}\n\n{r.vendor_text}\n\nVendor Onboarding Team", "held"
    else:
        d.vendor_subject = f"Your vendor registration (Ref {ref}) is approved"
        d.vendor_body = f"{hi}\n\nGood news: {company} has passed our checks. You'll receive a confirmation once your vendor account is activated.\n\nVendor Onboarding Team"
        d.vendor_state = "held"
    if f.get("bill_mode") and d.status in (PENDING_REVIEW, APPROVED):
        about = f"your bill {f.get('bill_invoice_number')} for {inr(money(f.get('bill_amount')))}" if f.get("bill_invoice_number") and f.get("bill_amount") else "your bill"
        note = (f"About {about}: we'll process it once your registration is "
                "complete and our team has confirmed the work. Payment then follows our usual purchase-order and receipt checks.")
        d.vendor_body = d.vendor_body.replace("\n\nVendor Onboarding Team", f"\n\n{note}\n\nVendor Onboarding Team")
    lines = [f"Status: {d.status} | risk tier: {d.risk_tier}" + (" | FRAUD-CLASS SIGNAL (vendor told nothing specific)" if d.fraud else "")]
    for r in rules:
        if r.result in (FAIL, ERROR, WARN):
            lines.append(f"- [{r.result}{'/' + r.outcome if r.outcome else ''}] {r.rule_id}: {r.title}" + (f" | {r.internal}" if r.internal else ""))
    d.internal_note = "\n".join(lines)
