"""Reliability: failed and interrupted runs are recoverable (never stuck IN_PROGRESS), work after the decision can't
flip a finished run, double submits make one run, and reading never hangs or crashes a run. Own throwaway SQLite
file, committed saved readings, no API calls."""

import asyncio
import mimetypes
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "fixtures" / "documents"
KEY = "happy_nilgiri"
PW = "Vn@7" + secrets.token_urlsafe(10)


def _files(key: str = KEY) -> dict:
    return {p.stem: (p.name, p.read_bytes()) for p in sorted((DOCS / key).glob("*")) if p.is_file()}


def _form_data(form: dict) -> dict:
    d = {k: ("" if v is None else str(v)) for k, v in form.items() if not isinstance(v, bool)}
    if form.get("msme"):
        d["msme"] = "on"
    if form.get("gst_registered", True):
        d["gst_registered"] = "on"
    return d


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    db = tmp_path_factory.mktemp("recoverydb") / "recovery.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    from onboarding import runner
    started: list[int] = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner, "PACE", 0)
        mp.setattr(runner, "start", lambda run_id, prefer_cache=None: started.append(run_id))
        yield started
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None


def run(coro):
    async def wrapped():
        import onboarding.db as dbm
        try:
            return await coro
        finally:
            await dbm.engine().dispose()
    return asyncio.run(wrapped())


async def _seeded():
    from onboarding.seeding import seed
    await seed(reset=True, dispose=False)


async def _new_run(form_extra: dict | None = None):
    from onboarding.demo_data import SCENARIOS
    from onboarding.pipeline import create_run, sessions
    async with sessions()() as s:
        return await create_run(s, {**SCENARIOS[KEY]["form"], **(form_extra or {})}, _files(), invite_token=None)


async def _get(model, pk):
    from onboarding.pipeline import sessions
    async with sessions()() as s:
        return await s.get(model, pk)


async def _events(run_id):
    from sqlalchemy import select

    from onboarding.models import RunEvent
    from onboarding.pipeline import sessions
    async with sessions()() as s:
        return (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq))).scalars().all()


# --- failed runs -----------------------------------------------------------------------------------------
def test_a_failed_run_leaves_in_progress_and_a_done_run_is_never_marked_failed(env):
    from onboarding.models import Application, Run
    from onboarding.pipeline import mark_failed

    async def go():
        await _seeded()
        r = await _new_run()
        assert (await _get(Application, r.application_id)).current_status == "IN_PROGRESS"
        assert await mark_failed(r.id, "RuntimeError")
        run_, app = await _get(Run, r.id), await _get(Application, r.application_id)
        ev = (await _events(r.id))[-1]
        done = await _new_run()
        from onboarding import runner
        await runner._run(done.id)
        refused = await mark_failed(done.id, "RuntimeError")
        return run_, app, ev, refused, await _get(Run, done.id)

    run_, app, ev, refused, done = run(go())
    assert run_.state == "failed" and app.current_status == "PENDING_REVIEW"
    assert "re-run the checks" in ev.summary and "resubmit" in ev.summary
    assert refused is False and done.state == "done" and done.status   # unsolicited: decided, whatever the status


def test_application_refs_come_from_the_primary_key(env):
    from onboarding.models import Application

    async def go():
        await _seeded()
        a, b = await _new_run(), await _new_run()
        return await _get(Application, a.application_id), await _get(Application, b.application_id)

    a, b = run(go())
    assert a.ref == f"VOB-{a.id:04d}" and b.ref == f"VOB-{b.id:04d}"


# --- work after the decision ------------------------------------------------------------------------------
def test_a_failing_step_after_the_decision_does_not_flip_the_run(env, monkeypatch):
    from onboarding import mailer, reliability, runner
    from onboarding.models import Run

    async def boom(_run_id):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(mailer, "deliver_for_run", boom)
    monkeypatch.setattr(reliability, "check_run", boom)

    async def go():
        await _seeded()
        r = await _new_run()
        await runner._run(r.id)
        await runner._run(r.id)   # a duplicate start is a no-op: the run isn't queued any more
        return await _get(Run, r.id), await _events(r.id)

    r, evs = run(go())
    assert r.state == "done" and r.status
    assert [e.stage for e in evs].count("decision") == 1


# --- restart recovery -------------------------------------------------------------------------------------
def test_recovery_requeues_once_and_parks_old_runs(env):
    from sqlalchemy import update

    from onboarding.models import Application, Run
    from onboarding.models import now as _now
    from onboarding.pipeline import recover_interrupted, sessions

    async def go():
        await _seeded()
        env.clear()
        fresh, old = await _new_run(), await _new_run()
        async with sessions()() as s:   # 'running' when the process died; one of them two hours ago
            await s.execute(update(Run).where(Run.id.in_([fresh.id, old.id])).values(state="running"))
            await s.execute(update(Run).where(Run.id == old.id).values(started_at=_now() - timedelta(hours=2)))
            await s.commit()
        first = await recover_interrupted()
        started_first = list(env)
        child = await _get(Run, first["requeued"][0])
        second = await recover_interrupted()   # the re-queued run dies too (still queued): not re-queued again
        return (first, started_first, second, child, await _get(Run, fresh.id), await _get(Run, old.id),
                await _get(Application, old.application_id), await _get(Application, fresh.application_id), await _events(old.id))

    first, started_first, second, child, fresh, old, old_app, fresh_app, old_events = run(go())
    assert first["parked"] == [old.id] and len(first["requeued"]) == 1
    assert started_first == first["requeued"]
    assert child.parent_run_id == fresh.id and child.form == fresh.form
    assert fresh.state == "interrupted" and old.state == "interrupted"
    assert old_app.current_status == "PENDING_REVIEW" and "re-run available" in old_events[-1].summary
    assert second == {"requeued": [], "parked": [child.id]}       # once per run, recorded in the database
    assert fresh_app.current_status == "PENDING_REVIEW"


# --- reviewer re-run, vendor resubmission, double submit (through the web app) -------------------------
def test_rerun_resubmit_and_concurrent_submits(env):
    import httpx
    from sqlalchemy import select, update

    from onboarding.demo_data import SCENARIOS
    from onboarding.main import app
    from onboarding.models import Application, Invite, Run
    from onboarding.pipeline import sessions
    from onboarding.seeding import DEMO_PASSWORD, INVITES

    async def go():
        await _seeded()
        t = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        staff = {}
        for name, email in (("Priya", "priya.nair@parakh.tech"), ("Arjun", "arjun.mehta@parakh.tech")):
            c = staff[name] = httpx.AsyncClient(transport=t, base_url="http://t")
            assert (await c.post("/company/login", data={"email": email, "password": DEMO_PASSWORD})).status_code == 303
        sponsor, company, reason, cat, band, _high = INVITES[KEY]
        f = SCENARIOS[KEY]["form"]
        r = await staff["Priya"].post("/invites", data=dict(company_name=company, contact_email=f["contact_email"], business_reason=reason,
                                                            spend_category=cat, spend_band=band))
        token = re.search(r"created=([^&]+)", r.headers["location"]).group(1)
        v = httpx.AsyncClient(transport=t, base_url="http://t")
        r = await v.post("/vendor/register", data={"company_name": f["legal_name"], "contact_name": f["contact_name"], "email": f["contact_email"],
                                                   "password": PW, "next": f"/apply/{token}"})
        assert r.status_code == 303

        files = {k: (n, b, mimetypes.guess_type(n)[0]) for k, (n, b) in _files().items()}
        env.clear()
        codes = [x.status_code for x in await asyncio.gather(*(v.post(f"/apply/{token}", data=_form_data(f), files=files) for _ in range(4)))]
        async with sessions()() as s:
            inv = (await s.execute(select(Invite).where(Invite.token == token))).scalar_one()
            apps = (await s.execute(select(Application).where(Application.invite_id == inv.id))).scalars().all()
            runs = (await s.execute(select(Run).where(Run.application_id == apps[0].id))).scalars().all()
        out = dict(codes=codes, apps=len(apps), runs=len(runs), started=sorted(set(env)))
        first = runs[0]
        out["first"] = first.id

        # the run dies: the vendor may send the form again, a reviewer may re-run the checks
        from onboarding.pipeline import mark_failed
        await mark_failed(first.id, "RuntimeError")
        out["page"] = (await staff["Arjun"].get(f"/runs/{first.id}")).text
        out["form_after_fail"] = (await v.get(f"/apply/{token}")).status_code
        out["priya_rerun"] = (await staff["Priya"].post(f"/runs/{first.id}/action", data={"action": "rerun"})).status_code
        env.clear()
        r = await staff["Arjun"].post(f"/runs/{first.id}/action", data={"action": "rerun"})
        out["arjun_rerun"] = (r.status_code, r.headers.get("location"))
        out["rerun_started"] = list(env)
        async with sessions()() as s:
            new = (await s.execute(select(Run).where(Run.application_id == apps[0].id).order_by(Run.id.desc()))).scalars().first()
            out["new"] = (new.id, new.parent_run_id, new.state)
            out["status_during"] = (await s.get(Application, apps[0].id)).current_status
            await s.execute(update(Run).where(Run.id == new.id).values(state="interrupted"))
            await s.commit()
        out["resubmit"] = (await v.post(f"/apply/{token}", data=_form_data(f), files=files)).status_code
        for c in (*staff.values(), v):
            await c.aclose()
        return out

    o = run(go())
    assert o["codes"] == [303] * 4                       # no 500
    assert o["apps"] == 1 and o["runs"] == 1 and len(o["started"]) == 1
    assert "Re-run checks" in o["page"] and "can re-run the checks" in o["page"]
    assert o["form_after_fail"] == 200                   # the vendor isn't bounced to the status page
    assert o["priya_rerun"] == 403                       # requesters don't re-run
    new_id, parent, state = o["new"]
    assert o["arjun_rerun"] == (303, f"/runs/{new_id}") and o["rerun_started"] == [new_id]
    assert parent == o["first"] and state == "queued" and o["status_during"] == "IN_PROGRESS"
    assert o["resubmit"] == 303


# --- reading ------------------------------------------------------------------------------------------------
def test_reading_without_a_key_fails_fast_and_builds_no_client(monkeypatch):
    from onboarding.ai import read as R
    monkeypatch.setattr(R, "_client", None)
    res = asyncio.run(R.read_document(b"%PDF-1.4 nothing", "application/pdf"))
    assert not res.ok and res.error == R.NO_KEY and res.attempts == 0 and R._client is None


def _fake_client(monkeypatch, exc):
    from onboarding.ai import read as R
    calls = []

    class Models:
        async def generate_content(self, **kw):
            calls.append(kw["model"])
            if isinstance(exc, float):
                await asyncio.sleep(exc)
            raise exc

    class Client:
        aio = type("Aio", (), {"models": Models()})()

    monkeypatch.setattr(R, "client", lambda: Client())
    monkeypatch.setattr(R, "_MIN_GAP", 0)
    monkeypatch.setattr(R.asyncio, "sleep", _nosleep)
    return calls


_real_sleep = asyncio.sleep


async def _nosleep(seconds):
    await _real_sleep(0)


def test_any_reading_error_is_caught_and_a_key_problem_is_not_retried(monkeypatch):
    import httpx

    from onboarding.ai import read as R
    calls = _fake_client(monkeypatch, httpx.ConnectError("no route"))
    res = asyncio.run(R.read_document(b"x", "application/pdf"))
    assert not res.ok and "ConnectError" in res.error and len(calls) == 4      # 2 tries x 2 models

    class Forbidden(Exception):
        code = 403
    calls = _fake_client(monkeypatch, Forbidden("bad key"))
    res = asyncio.run(R.read_document(b"x", "application/pdf"))
    assert not res.ok and len(calls) == 1


def test_the_reading_deadline_falls_back_to_the_saved_reading(monkeypatch):
    from onboarding.ai import read as R
    monkeypatch.setattr(asyncio, "sleep", _real_sleep)
    calls = []

    async def slow(data, mime, **kw):
        calls.append(1)
        await _real_sleep(5)

    monkeypatch.setattr(R, "read_document", slow)
    saved = next((DOCS / KEY).glob("pan_card*")).read_bytes()

    async def go():
        dl = asyncio.get_running_loop().time() + 0.2
        hit = await R.read_with_cache(saved, "image/png", prefer="live", deadline=dl)
        miss = await R.read_with_cache(b"never seen", "image/png", prefer="live", deadline=dl)
        cached = await R.read_with_cache(saved, "image/png")     # default: saved reading first, no AI call
        return hit, miss, cached

    (hit, origin), (miss, morigin), (cached, corigin) = asyncio.run(go())
    assert origin == "cache-fallback" and hit.ok
    assert morigin == "failed" and miss.error == R.DEADLINE
    assert corigin == "cache" and len(calls) == 1   # the deadline had passed: the second document never asked the AI
