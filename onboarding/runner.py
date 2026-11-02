"""Runs applications in the background (in-process asyncio tasks, at most 2 at a time so the
Gemini free tier's 15 requests/minute isn't exceeded). A crash marks the run failed; a server
restart marks unfinished runs interrupted (pipeline.sweep_interrupted)."""

from __future__ import annotations

import asyncio
import logging

from onboarding.pipeline import mark_failed, run_pipeline

log = logging.getLogger("onboarding.runner")
_slots = asyncio.Semaphore(2)
_tasks: set[asyncio.Task] = set()
PACE = 0.45  # seconds between rule-stage updates in the live view


async def _run(run_id: int, prefer_cache: bool) -> None:
    async with _slots:
        try:
            await run_pipeline(run_id, prefer_cache=prefer_cache, pace=PACE)
            from onboarding.intel.project import on_run_completed
            await on_run_completed(run_id)   # Vendor Intelligence; never raises
        except Exception as e:  # never lose a run silently
            log.exception("run %s failed", run_id)
            await mark_failed(run_id, type(e).__name__)


def start(run_id: int, *, prefer_cache: bool = False) -> None:
    task = asyncio.create_task(_run(run_id, prefer_cache))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def busy() -> int:
    return len(_tasks)
