"""Web app entry point."""

from __future__ import annotations

import html
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from onboarding import db
from onboarding.models import Base
from onboarding.pipeline import sweep_interrupted

log = logging.getLogger("onboarding")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        async with db.engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # no-op when tables exist
        n = await sweep_interrupted()
        if n:
            log.warning("marked %s unfinished run(s) as interrupted", n)
    except Exception as e:  # the app still starts; /readyz and /system show the problem
        log.error("startup database step failed: %s", type(e).__name__)
    yield


app = FastAPI(title="Vendor onboarding", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=__file__.rsplit("main.py", 1)[0] + "static"), name="static")


@app.exception_handler(HTTPException)
async def friendly_errors(request: Request, exc: HTTPException):
    if request.url.path.startswith(("/runs/", "/healthz", "/readyz")) and "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Can't do that</title>
<script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-50 font-sans">
<div class="max-w-xl mx-auto mt-24 bg-white border rounded-xl p-8 shadow-sm">
<p class="text-xs uppercase tracking-wide text-slate-500">Error {exc.status_code}</p>
<p class="mt-2 text-lg text-slate-800">{html.escape(str(exc.detail))}</p>
<a class="inline-block mt-6 text-indigo-700 underline" href="javascript:history.back()">Go back</a></div></body></html>"""
    return HTMLResponse(body, status_code=exc.status_code)


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


from onboarding.web import router  # noqa: E402

app.include_router(router)
