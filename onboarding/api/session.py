"""Who is logged in, the demo person switcher, and log-out."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from fastapi.responses import JSONResponse

from onboarding import auth
from onboarding.api.common import ApiError, chasing_item, counts, iso, person, staff_or_401, todo_item, when  # noqa: F401
from onboarding.config import get_settings  # noqa: F401
from onboarding.pipeline import read_sessions

router = APIRouter()

# --- session ---------------------------------------------------------------------------------------------------
@router.get("/session")
async def session(request: Request):
    """Who is logged in, who they are acting as (demo person switcher), and the counts for the menu."""
    from onboarding.web import _dashboard_ctx, _employees
    async with read_sessions()() as s:
        staff, actor = await staff_or_401(request, s)
        demo = get_settings().demo_tools
        todo = (await _dashboard_ctx(request, s))["todo"]
        return {"staff": person(staff), "actor": person(actor), "demo": demo,
                "people": [person(e) for e in await _employees(s)] if demo else [],
                "counts": counts(todo)}


class ActAs(BaseModel):
    employee_id: int


@router.post("/session/actor")
async def act_as(request: Request, body: ActAs):
    """Demo only: use the console as another employee."""
    from onboarding.web import _employees
    if not get_settings().demo_tools:
        raise ApiError(404, "Not found")
    async with read_sessions()() as s:
        await staff_or_401(request, s)
        if not any(e.id == body.employee_id for e in await _employees(s)):
            raise ApiError(400, "No such employee.")
    resp = JSONResponse({"ok": True})
    resp.set_cookie("actor", str(body.employee_id), max_age=60 * 60 * 24 * 30, samesite="lax")
    return resp


@router.post("/session/logout")
async def logout(request: Request):
    await auth.revoke(request.cookies.get(auth.COMPANY_COOKIE), "company")
    resp = JSONResponse({"ok": True, "next": "/"})
    resp.delete_cookie(auth.COMPANY_COOKIE)
    resp.delete_cookie("actor")
    return resp
