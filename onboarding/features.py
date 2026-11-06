"""Which URLs belong to a switched-off feature (see config.feature). One table, checked by a middleware in main.py,
so a hidden feature answers 404 on its pages and its /api/v1 endpoints without touching each route."""

from __future__ import annotations

import re

from onboarding.config import feature

_A = r"^(?:/api/v1)?"
RULES: list[tuple[str, re.Pattern]] = [
    ("payables", re.compile(_A + r"/(?:bill|bills|invoices|purchase-orders|change-requests|audit)(?:/.*)?$|^/api/v1/history$|^/vendor/bills(?:/.*)?$|^/vendor/profile/change$")),
    ("intel", re.compile(_A + r"/(?:vendors|relationships)(?:/.*)?$|^/runs/[^/]+/simulate$")),
    ("reliability", re.compile(r"^/runs/[^/]+/reliability$")),
    ("followups", re.compile(_A + r"/system/followups$")),
    ("unsolicited", re.compile(_A + r"/apply$|" + _A + r"/prequalified(?:/.*)?$")),
]


def scenario_on(sc: dict) -> bool:
    """Demo scenarios of a hidden feature are not offered: bill ones need Payables, no-invite ones need Unsolicited."""
    if sc.get("bill"):
        return feature("payables")
    if sc.get("invite_scenario") is None:
        return feature("unsolicited")
    return True


def hidden(path: str) -> str | None:
    """The name of the switched-off feature this path belongs to, or None."""
    path = path.rstrip("/") or "/"
    for name, rx in RULES:
        if rx.match(path) and not feature(name):
            return name
    return None
