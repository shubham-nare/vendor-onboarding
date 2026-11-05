"""The JSON API (/api/v1). Every response is application/json; errors are {"error": "..."} with the right status.

The browser app (onboarding/frontend, built into /static/app.js) draws the screens from these answers.
Logins are the signed cookies (employee: company_session; vendor: vendor_session), and every endpoint applies the
same role rules as the pages. One module per area:

  session.py      who is logged in, person switcher (demo), log-out
  console.py      Home and the menu counts
  registrations.py applications, review queue, change requests, pre-qualified suppliers, invites
  payables.py     invoices
  vendors.py      vendor directory, history, relationships, supplier accounts
  admin.py        system health, follow-ups now, reset (passcode)
  common.py       ApiError, staff_or_401, and how people, dates and to-do items are shown
"""

from fastapi import APIRouter

from onboarding.api import admin, console, payables, registrations, session, vendors
from onboarding.api.common import ApiError, error_response  # noqa: F401  (registered in main.py)

router = APIRouter(prefix="/api/v1")
for _module in (session, console, registrations, payables, vendors, admin):
    router.include_router(_module.router)
