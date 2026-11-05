"""The vendor directory (one row per legal entity) and the history of every decision."""

from __future__ import annotations

from fastapi import APIRouter, Request

from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions
from onboarding.rules import money

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


# --- relationships ------------------------------------------------------------------------------------------------
SHARED_KIND = {"BANK_ACCOUNT": "Shared bank account", "DOCUMENT": "Same document file", "ADDRESS": "Same address", "EMAIL": "Same email", "PHONE": "Same phone"}
SHARED_WHY = {"BANK_ACCOUNT": "Payments to one account from two supplier records can divert money. It can be legitimate (group companies): confirm with the bank.",
              "DOCUMENT": "The same file from two applicants usually means a template was reused. Ask for originals.",
              "ADDRESS": "Common in industrial estates and shared offices. Context only, not a risk by itself.",
              "EMAIL": "Often a shared accountant or agent. Context only.", "PHONE": "Often a shared agent. Context only."}


@router.get("/relationships")
async def relationships(request: Request):
    """Flags raised by the onboarding rules, and details shared between vendors (reviewers and Finance only)."""
    from onboarding.workspace import relationships as relationship_data
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await relationship_data(request)
    vendors = d["vendors"]
    ref = lambda pk: {"id": vendors[pk].vendor_id, "name": vendors[pk].display_name} if pk in vendors else None  # noqa: E731
    return {
        "flags": [{"status": r.status, "severity": r.severity, "title": r.title, "rule": r.rule_id, "opened": when(r.opened_at),
                   "vendor": ref(r.vendor_pk), "related": ref(r.related_vendor_pk),
                   "action": r.reviewer_action if r.status == "open" else None, "resolution": r.resolution if r.status != "open" else None}
                  for r in d["risks"]],
        "shared": [{"kind": x["node"].kind, "label": SHARED_KIND.get(x["node"].kind, x["node"].kind), "value": x["node"].display,
                    "needs_reviewer": x["node"].kind in ("BANK_ACCOUNT", "DOCUMENT"), "why": SHARED_WHY.get(x["node"].kind, ""),
                    "vendors": [{"vendor": ref(pk), "status": e.status, "basis": e.basis.replace("_", " "), "since": when(e.valid_from)}
                                for pk, e in x["members"].items()]} for x in d["shared"]],
    }


# --- supplier portal accounts ---------------------------------------------------------------------------------------
@router.get("/supplier-accounts")
async def supplier_accounts(request: Request):
    """Every supplier portal account, its registrations and its bills (reviewers and Finance only)."""
    from onboarding import bills as B
    from onboarding.portal import supplier_accounts as account_rows
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    rows = await account_rows(request)
    out = []
    for r in rows:
        a = r["acct"]
        out.append({"company": a.company_name, "contact": a.contact_name, "email": a.email, "since": when(a.created_at),
                    "vendor_id": r["active"]["vendor"].vendor_id if r["active"] else None,
                    "pending_invites": [i.sponsor.name if i.sponsor else "an employee" for i in r["pending_invites"]],
                    "registrations": [{"ref": x["app"].ref, "status": x["app"].current_status, "run_id": x["run"].id if x["run"] else None,
                                       "came_in": "invited" if x["invite"] else ("bill-first" if x["bill"] else "unsolicited")} for x in r["regs"]],
                    "bills": [{"id": b.id, "ref": b.ref, "amount": float(money(b.amount) or 0), "status": B.STATUS_TEXT.get(b.status, b.status).lower()}
                              for b in r["vbills"]]})
    return {"accounts": out}
