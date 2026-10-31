"""Who can SEE what in the company console: need to know. (Who can DO what is in web._allowed_actions
and bills.allowed_bill_actions.)

  Requester (Priya, Rahul)     their own requests only: invites they sent, registrations and bills that
                               name them. Status in plain words, the bill, what the vendor was told, their
                               buttons. No documents, ID numbers, AI readings, detailed checks or fraud
                               flags: a requester may be the person a fraud check is about.
  Procurement reviewer (Arjun) every application and bill, with documents, checks and fraud flags.
                               PAN and bank account numbers masked.
  Finance controller (Kavita)  everything the reviewer sees, plus the full bank account number of active
                               vendors (Finance releases the payments).
"""

from __future__ import annotations

from fastapi import HTTPException

REVIEWERS = ("maker", "checker")

# Shown on the "What is verified" page and in the docs.
MATRIX = [
    ("Applications and bills listed", "Only their own", "All", "All"),
    ("Status and what the vendor was told", "Their own", "Yes", "Yes"),
    ("Documents and what the AI read", "No", "Yes", "Yes"),
    ("Every check, reasons, internal note", "No", "Yes", "Yes"),
    ("Fraud flags", "No", "Yes", "Yes"),
    ("PAN, bank account", "No", "Masked", "Masked PAN · full bank account of active vendors"),
    ("Vendor directory", "Names, vendor IDs, status", "With contacts", "With contacts"),
    ("Outbox, document check, system", "No", "Yes", "Yes"),
]


def full_view(actor) -> bool:
    return actor is not None and actor.role in REVIEWERS


def sees_full_bank(actor) -> bool:
    return actor is not None and actor.role == "checker"


def owns_application(actor, invite, bill) -> bool:
    """A requester's own: they sent the invite, or the vendor's registration bill names them."""
    return actor is not None and ((invite is not None and invite.sponsor_id == actor.id) or
                                  (bill is not None and bill.engaged_employee_id == actor.id))


def can_open_application(actor, invite, bill) -> bool:
    return full_view(actor) or owns_application(actor, invite, bill)


def can_open_bill(actor, vbill) -> bool:
    return full_view(actor) or (actor is not None and vbill.engaged_employee_id == actor.id)


def forbid(what: str = "This") -> HTTPException:
    return HTTPException(403, f"{what} is visible to the Procurement reviewer and the Finance controller only. "
                              "Requesters see their own requests (switch 'Acting as' to see another person's view).")


def require_full(actor, what: str) -> None:
    if not full_view(actor):
        raise forbid(what)
