"""Running the system: health checks, the follow-up job, and resetting the demo data (reviewers and Finance only)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from onboarding import followups as FU
from onboarding.api.common import staff_or_401, when
from onboarding.config import feature
from onboarding.pipeline import read_sessions

router = APIRouter()


@router.get("/system")
async def system(request: Request):
    from onboarding.web import system as system_data
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    d = await system_data(request)
    return {"checks": [{"name": n, "ok": bool(ok), "detail": detail} for n, ok, detail in d["checks"]],
            "followups": {"enabled": feature("followups"), "every_hours": FU.EVERY_HOURS, "remind_after_days": FU.REMIND_AFTER_DAYS, "escalate_after_days": FU.ESCALATE_AFTER_DAYS,
                          "waiting": len(d["chasing"]), "last": when(d["last_fu"].at) if d["last_fu"] else None}}


@router.post("/system/followups")
async def followups_now(request: Request):
    """Send the reminders and escalations that are due now."""
    from onboarding.web import run_followups
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    r = await run_followups(request)
    return {"reminders": r["reminders"], "escalations": r["escalations"], "waiting": r["waiting"]}


class Reset(BaseModel):
    passcode: str


@router.post("/system/reset")
async def reset(request: Request, body: Reset):
    """Delete every run and reload the reference data (needs ADMIN_PASSCODE; refused while it is the default)."""
    from onboarding.web import reset_data
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    await reset_data(request, body.passcode)
    return {"ok": True}
