"""The seeded employees, kept in memory for a short while.

Every console page needs the employee list (the "Acting as" menu, who is logged in, who asked for a
vendor). It's four rows that almost never change, yet it was fetched three or four times per page,
and each fetch is a round trip to the database. Cached as detached rows for EMPLOYEE_TTL seconds;
a reset or reseed clears it straight away."""

from __future__ import annotations

import time

from sqlalchemy import select

from onboarding.models import Employee

EMPLOYEE_TTL = 60.0
_cache: tuple[float, list[Employee]] | None = None


async def employees(s) -> list[Employee]:
    global _cache
    if _cache and time.monotonic() - _cache[0] < EMPLOYEE_TTL:
        return _cache[1]
    rows = list((await s.execute(select(Employee).order_by(Employee.id))).scalars())
    for e in rows:  # detach: read-only copies, safe to share between requests
        s.expunge(e)
    _cache = (time.monotonic(), rows)
    return rows


def clear() -> None:
    global _cache
    _cache = None
