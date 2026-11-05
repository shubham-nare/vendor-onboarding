"""Shared by every API module: the error type, who is logged in, and how people, dates and to-do items are shown."""

from __future__ import annotations

from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse

from onboarding import followups as FU
from onboarding.rules import money


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def error_response(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


def iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def person(e) -> dict | None:
    from onboarding.web import ROLE_LABEL
    if not e:
        return None
    return {"id": e.id, "name": e.name, "first_name": e.name.split()[0], "role": e.role, "role_label": ROLE_LABEL.get(e.role, e.role),
            "department": e.department, "email": e.email}


async def staff_or_401(request: Request, s):
    from onboarding.web import _actor, staff_member
    staff = await staff_member(request, s)
    if not staff:
        raise ApiError(401, "Please log in to the company console.")
    return staff, (await _actor(request, s)) or staff


def counts(todo: list[dict]) -> dict:
    return {"review": len(todo), "apps": sum(t["status"] not in ("BILL", "CHANGE") for t in todo)}


def todo_item(t: dict) -> dict:
    amount = money(t.get("amount")) if t.get("amount") else None
    return {"href": t["href"], "ref": t["ref"], "name": t["name"], "verb": t["verb"], "status": t["status"],
            "detail": t.get("detail") or "", "amount": float(amount) if amount is not None else None,
            "fraud": bool(t.get("fraud")), "risk": t.get("risk") or "", "waiting": t.get("waiting") or ""}


def chasing_item(w) -> dict:
    nxt = w.next_step
    return {"run_id": w.run.id, "name": w.app.legal_name, "ref": w.app.ref, "requester": w.requester.name if w.requester else None,
            "tone": w.tone, "days": w.days, "asked": FU.day(w.since),
            "reminded": FU.day(w.reminded.at) if w.reminded else None, "escalated": FU.day(w.escalated.at) if w.escalated else None,
            "next": {"what": nxt[0], "on": FU.day(nxt[1])} if nxt else None}


def when(d) -> dict:
    from onboarding.web import _fmt_dt
    return {"at": iso(d), "label": _fmt_dt(d)}
