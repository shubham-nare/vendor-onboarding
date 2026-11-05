"""Runs applications in the background (in-process asyncio tasks, at most 2 at a time so the
Gemini free tier's 15 requests/minute isn't exceeded). A crash marks the run failed; a server
restart re-queues or parks unfinished runs (pipeline.recover_interrupted)."""

from __future__ import annotations

import asyncio
import logging

from onboarding.pipeline import mark_failed, run_pipeline

log = logging.getLogger("onboarding.runner")
_slots = asyncio.Semaphore(2)
_tasks: set[asyncio.Task] = set()
PACE = 0.45  # seconds between rule-stage updates in the live view


async def _after(run_id: int) -> None:
    """Work after the decision is committed. Each step is isolated: its failure is logged, never turns the
    finished run into a failed one."""
    from onboarding import mailer, reliability
    from onboarding.intel.project import on_run_completed
    for name, step in (("intelligence", on_run_completed), ("mail", mailer.deliver_for_run), ("reliability", reliability.check_run)):
        try:
            await step(run_id)
        except Exception:
            log.exception("run %s: %s step after the decision failed (the decision stands)", run_id, name)


async def _run(run_id: int, prefer_cache: bool | None = None) -> None:
    """prefer_cache None: settings.read_cache_first (saved readings first)."""
    async with _slots:
        try:
            dec = await run_pipeline(run_id, prefer_cache=prefer_cache, pace=PACE)
        except Exception as e:  # never lose a run silently
            log.exception("run %s failed", run_id)
            await mark_failed(run_id, type(e).__name__)
            return
        if dec is not None:   # None: not queued any more (a duplicate start)
            await _after(run_id)


def start(run_id: int, *, prefer_cache: bool | None = None) -> None:
    task = asyncio.create_task(_run(run_id, prefer_cache))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def busy() -> int:
    return len(_tasks)
