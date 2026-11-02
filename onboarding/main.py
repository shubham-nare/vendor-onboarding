"""Web app entry point."""

from __future__ import annotations

import asyncio
import html
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from urllib.parse import quote

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from onboarding import auth, db
from onboarding.db import is_dropped_connection
from onboarding.models import Base
from onboarding.pipeline import sweep_interrupted

log = logging.getLogger("onboarding")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        async with db.engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # no-op when tables exist
        from onboarding.pipeline import sessions
        from onboarding.seeding import ensure_demo_logins
        async with sessions()() as s:  # a fresh deploy can always be logged into
            await ensure_demo_logins(s)
            await s.commit()
        n = await sweep_interrupted()
        if n:
            log.warning("marked %s unfinished run(s) as interrupted", n)
        asyncio.get_running_loop().create_task(db.warm_pool())  # in the background: startup isn't held up
        from onboarding.intel.project import backfill
        asyncio.get_running_loop().create_task(_intel_backfill(backfill))  # Vendor Intelligence catches up on older runs
    except Exception as e:  # the app still starts; /readyz and /system show the problem
        log.error("startup database step failed: %s", type(e).__name__)
    yield


async def _intel_backfill(fn) -> None:
    try:
        n = await fn()
        if n["runs"] or n["decisions"]:
            log.info("vendor intelligence: projected %s run(s), %s decision(s)", n["runs"], n["decisions"])
    except Exception:
        log.exception("vendor intelligence backfill failed (pages still work; it retries on the next start)")


app = FastAPI(title="Vendor onboarding", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=__file__.rsplit("main.py", 1)[0] + "static"), name="static")


# Company pages (the console) need an employee login; vendor pages have their own login (portal.py).
COMPANY_AREAS = {"console", "act-as", "invites", "runs", "files", "outbox", "check", "assumptions", "system", "demo", "bills", "vendors", "supplier-accounts"}


@app.middleware("http")
async def company_login_required(request: Request, call_next):
    area = request.url.path.strip("/").split("/", 1)[0]
    if area in COMPANY_AREAS and auth.read_session(request.cookies.get(auth.COMPANY_COOKIE), purpose="company") is None:
        if request.method != "GET" or request.url.path.endswith(("/events", "/stream")):
            return JSONResponse({"error": "Please log in to the company console."}, status_code=401)
        nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/company/login?next={quote(nxt)}", status_code=303)
    return await call_next(request)


class RetryPageOnce:
    """Opening a page only reads, so if the database connection drops before anything was sent,
    try once more on a fresh connection instead of showing an error. Forms (POST) are never retried.
    (A plain ASGI wrapper: Starlette's @app.middleware re-raises the first error even after a retry.)"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "GET" or scope["path"].endswith("/stream"):
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as e:
            if started or not is_dropped_connection(e):
                raise
            log.warning("database connection dropped on GET %s (%s); retrying once", scope["path"], type(e).__name__)
            await asyncio.sleep(1.0)  # local network refusals tend to come in short bursts
            await self.app(scope, receive, send)


app.add_middleware(RetryPageOnce)


@app.exception_handler(HTTPException)
async def friendly_errors(request: Request, exc: HTTPException):
    if request.url.path.startswith(("/runs/", "/healthz", "/readyz")) and "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    area = request.url.path.strip("/").split("/", 1)[0]
    home = ('<a class="text-indigo-700 underline" href="/console">Go to the dashboard</a>' if area in COMPANY_AREAS else
            '<a class="text-indigo-700 underline" href="/">Home</a>')
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Can't do that</title>
<script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-50 font-sans">
<div class="max-w-xl mx-auto mt-24 bg-white border rounded-xl p-8 shadow-sm">
<p class="text-xs uppercase tracking-wide text-slate-500">Error {exc.status_code}</p>
<p class="mt-2 text-lg text-slate-800">{html.escape(str(exc.detail))}</p>
<div class="mt-6 flex gap-5 text-sm"><a class="text-indigo-700 underline" href="javascript:history.back()">Go back</a>{home}</div></div></body></html>"""
    return HTMLResponse(body, status_code=exc.status_code)


@app.exception_handler(Exception)
async def database_unreachable(request: Request, exc: Exception):
    """The database couldn't be reached even after a retry (no internet, DNS down, Neon waking up).
    Say so plainly instead of a bare "Internal Server Error"; a page view reloads itself."""
    if not is_dropped_connection(exc):
        return HTMLResponse("Internal Server Error", status_code=500)
    if request.method != "GET" or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": "Can't reach the database right now. Please try again."}, status_code=503)
    body = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5"><title>Reconnecting…</title>
<script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-50 font-sans">
<div class="max-w-xl mx-4 sm:mx-auto mt-24 bg-white border rounded-xl p-8 shadow-sm">
<p class="text-xs uppercase tracking-wide text-slate-500">Reconnecting</p>
<p class="mt-2 text-lg text-slate-800">Can't reach the database right now.</p>
<p class="mt-2 text-sm text-slate-600">Usually a brief internet or DNS hiccup. This page tries again every 5 seconds; nothing you entered was lost.</p>
<div class="mt-6 text-sm"><a class="text-indigo-700 underline" href="">Try now</a></div></div></body></html>"""
    return HTMLResponse(body, status_code=503, headers={"Retry-After": "5"})


@app.get("/healthz")
async def healthz():
    """Liveness for the uptime pinger. Deliberately does not touch the database."""
    return {"ok": True}


@app.get("/readyz")
async def readyz():
    """Readiness: can we reach the database?"""
    try:
        await db.ping()
        return {"ok": True, "db": "ok"}
    except Exception as e:  # report the failure type, not secrets
        return JSONResponse({"ok": False, "db": type(e).__name__}, status_code=503)


from onboarding.portal import router as portal_router  # noqa: E402
from onboarding.web import router  # noqa: E402

app.include_router(router)
app.include_router(portal_router)
