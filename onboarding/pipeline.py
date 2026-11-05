"""Run one application through every layer, writing a stage event after each step so the live
run view can replay it (refresh-safe). Used by the web app and the command-line runner.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from onboarding import decision as D
from onboarding import address as A
from onboarding import sources as S
from onboarding.ai.read import DocRead, read_with_cache
from onboarding.authenticity.assess import assess
from onboarding.db import engine
from onboarding.models import (Application, Bill, Blocklist, Document, Employee, Fact, Invite, Message, Run, RunEvent, RuleResult,
                               StoredFile, VendorMaster, now)
from onboarding.rules import SLOT_TITLE, Context, DocInfo, evaluate

STAGES = [
    ("invite", "Invite check"),
    ("intake", "Intake"),
    ("completeness", "Scope & completeness"),
    ("read", "Read documents (AI)"),
    ("authenticity", "Document authenticity"),
    ("identifiers", "Identifier checks"),
    ("consistency", "Cross-document & name checks"),
    ("sources", "Source verification"),
    ("risk", "Risk checks"),
    ("bill", "Bill checks"),
    ("decision", "Decision"),
]


def stages_for(form: dict | None) -> list[tuple[str, str]]:
    """The bill stage only exists for bill-first registrations."""
    return [st for st in STAGES if st[0] != "bill" or (form or {}).get("bill_mode")]
STATUS_TEXT = {"APPROVED": "Approved", "PENDING_VENDOR": "Pending: vendor to fix", "PENDING_REVIEW": "Pending: internal review", "REJECTED": "Rejected"}
LAYER_STAGE = {"invite": "invite", "scope": "completeness", "completeness": "completeness", "documents": "read",
               "authenticity": "authenticity", "identifiers": "identifiers", "bank": "identifiers", "consistency": "consistency",
               "names": "consistency", "sources": "sources", "risk": "risk", "msme": "consistency", "bill": "bill"}


def sessions() -> async_sessionmaker:
    return async_sessionmaker(engine(), expire_on_commit=False)


def read_sessions() -> async_sessionmaker:
    """For pages that only read: autocommit, so there's no BEGIN before and ROLLBACK after the
    request (two network round trips each time). Never use these for writes that must be atomic."""
    return async_sessionmaker(engine().execution_options(isolation_level="AUTOCOMMIT"), expire_on_commit=False)


# --- creating a run -----------------------------------------------------------------------------
async def create_run(s: AsyncSession, form: dict, files: dict[str, tuple[str, bytes]], *, invite_token: str | None,
                     parent_run_id: int | None = None) -> Run:
    """files: slot -> (filename, bytes). Re-uses the application on resubmission."""
    invite = (await s.execute(select(Invite).where(Invite.token == invite_token))).scalar_one_or_none() if invite_token else None
    app = None
    if parent_run_id:
        app = await s.get(Application, (await s.get(Run, parent_run_id)).application_id)
    elif invite:
        app = (await s.execute(select(Application).where(Application.invite_id == invite.id))).scalars().first()
    if app is None:
        n = (await s.execute(select(func.count(Application.id)))).scalar() or 0
        app = Application(ref=f"VOB-{n + 1:04d}", invite_id=invite.id if invite else None, legal_name=form.get("legal_name", ""))
        s.add(app)
        await s.flush()
    if parent_run_id is None:
        parent_run_id = (await s.execute(select(Run.id).where(Run.application_id == app.id).order_by(Run.id.desc()))).scalars().first()
    run = Run(application_id=app.id, parent_run_id=parent_run_id, form=form)
    s.add(run)
    await s.flush()
    shas = {}
    for slot, (filename, data) in files.items():  # files first (documents reference them)
        sha = shas[slot] = hashlib.sha256(data).hexdigest()
        if not await s.get(StoredFile, sha):
            s.add(StoredFile(sha256=sha, mime=mimetypes.guess_type(filename)[0] or "application/octet-stream", size=len(data), data=data))
            await s.flush()
    for slot, (filename, _data) in files.items():
        s.add(Document(run_id=run.id, slot=slot, filename=filename, sha256=shas[slot]))
    if invite and invite.status == "open":
        invite.status = "used"
    await s.commit()
    return run


# --- running it ------------------------------------------------------------------------------------
class Events:
    def __init__(self, s: AsyncSession, run_id: int):
        self.s, self.run_id, self.seq = s, run_id, 0
        self.lock = asyncio.Lock()  # documents are read in parallel; one session, so emits take turns

    async def emit(self, stage: str, state: str, summary: str = "", evidence: dict | None = None) -> None:
        async with self.lock:
            self.seq += 1
            self.s.add(RunEvent(run_id=self.run_id, seq=self.seq, stage=stage, state=state, summary=summary, evidence=evidence or {}))
            await self.s.commit()


async def run_pipeline(run_id: int, *, prefer_cache: bool = False, pace: float = 0.0) -> D.Decision:
    """pace: seconds between the (instant) rule-stage updates, so a viewer can follow them."""
    async with sessions()() as s:
        run = await s.get(Run, run_id)
        app = await s.get(Application, run.application_id)
        run.state = "running"
        ev = Events(s, run_id)
        form = run.form

        # S0 invite
        inv = await invite_context(s, app)
        no_invite = (f"No invite: registered with a bill for work already done (engaged by {form.get('bill_engaged_by') or 'nobody named'})"
                     if form.get("bill_mode") else "No invite: unsolicited application")
        await ev.emit("invite", "done", f"Requested by {inv['sponsor']}: {inv['reason']}" if inv else no_invite,
                      {"invite": {k: str(v) for k, v in (inv or {}).items()}})

        # S1 intake
        docs_rows = (await s.execute(select(Document).where(Document.run_id == run_id))).scalars().all()
        files = {d.slot: (d, (await s.get(StoredFile, d.sha256))) for d in docs_rows}
        await ev.emit("intake", "done", f"{len(files)} documents stored, fingerprinted (SHA-256)",
                      {"documents": [{"slot": d.slot, "file": d.filename, "sha256": d.sha256[:12]} for d in docs_rows]})
        await ev.emit("completeness", "running")

        # S3 read (parallel; Gemini, cache fallback)
        await ev.emit("read", "running", f"Reading {len(files)} documents")
        async def read_one(slot: str, sf: StoredFile):
            res, origin = await read_with_cache(sf.data, sf.mime, prefer="cache" if prefer_cache else "live")
            what = (res.read.doc_type.replace("_", " ").lower() if res.ok and res.read else "could not be read")
            how = {"live": f"live, {res.model}, {res.seconds}s", "cache": "saved reading", "cache-fallback": "AI unavailable: saved reading",
                   "failed": "AI unavailable"}.get(origin, origin)
            await ev.emit("read", "running", f"{SLOT_TITLE.get(slot, slot)}: {what} ({how})",
                          {"slot": slot, "origin": origin, "form": res.read.document_form if res.ok and res.read else None})
            return res, origin

        results = await asyncio.gather(*(read_one(slot, sf) for slot, (_, sf) in files.items()))
        infos: dict[str, DocInfo] = {}
        for (slot, (doc, sf)), (res, origin) in zip(files.items(), results):
            read: DocRead | None = res.read if res.ok else None
            doc.read = {"origin": origin, "model": res.model, "seconds": res.seconds, **(read.model_dump() if read else {"error": res.error})}
            infos[slot] = DocInfo(slot, doc.filename, doc.sha256, sf.mime, read, origin, None)
        if form.get("bill_mode"):   # the bill's number, date, amount and work come from the bill (AI reading), not from retyping
            from onboarding.rules import bill_fields_from_read
            inv_info = infos.get("invoice")
            is_invoice = bool(inv_info and inv_info.read and inv_info.read.doc_type == "TAX_INVOICE")
            form = {**form, **bill_fields_from_read(inv_info.read if is_invoice else None), "bill_read_from_document": True}
            run.form = form

        # S4 authenticity (code)
        for slot, (doc, sf) in files.items():
            a = assess(sf.data, sf.mime, infos[slot].read)
            infos[slot].auth = a
            doc.authenticity = a.as_dict()
        await s.commit()

        # S5-S8 inputs: live IFSC + simulated registries + internal data
        ctx = await gather_context(s, app, form, docs_rows, infos, inv, as_of=now())
        srcs = ctx.sources
        rules = evaluate(ctx)
        dec = D.decide(rules, ctx, ref=app.ref)

        # Emit one event per stage with its rule results (rules are instant; reading is the slow part)
        by_stage: dict[str, list] = {}
        for r in rules:
            by_stage.setdefault(LAYER_STAGE.get(r.layer, r.layer), []).append(r)
        for stage, _label in stages_for(form):
            if stage in ("invite", "intake", "decision"):
                continue
            rs = by_stage.get(stage, [])
            fails = [r for r in rs if r.result in ("FAIL", "ERROR")]
            warns = [r for r in rs if r.result == "WARN"]
            extra = {}
            if stage == "read":
                extra = {"documents": [{"slot": i.slot, "type": i.read.doc_type if i.read else None, "form": i.read.document_form if i.read else None,
                                        "origin": i.read_origin} for i in infos.values()]}
            if stage == "authenticity":
                extra = {"documents": [{"slot": i.slot, "level": i.auth.level, "worst": i.auth.worst, "specimen": i.auth.specimen} for i in infos.values()]}
            if stage == "sources":
                extra = {"sources": {k: {"source": v.source, "status": v.status, "live": v.live, **({"data": v.data} if k in ("pin", "address") else {})}
                                     for k, v in srcs.items()}}
            state = "failed" if fails else "done"
            summary = (f"{len(fails)} problem(s)" if fails else "All checks passed") + (f", {len(warns)} warning(s)" if warns else "") if rs else "Nothing to check"
            if stage == "authenticity" and not rs:
                summary = f"{len(infos)} documents checked: no concerns"
            if pace:
                await asyncio.sleep(pace)
            await ev.emit(stage, state, summary, {"rules": [r.as_dict() for r in rs], **extra})

        # Persist results
        for r in rules:
            s.add(RuleResult(run_id=run_id, rule_id=r.rule_id, layer=r.layer, result=r.result, outcome_if_fail=r.outcome, title=r.title,
                             evidence={**r.evidence, "vendor_text": r.vendor_text, "internal": r.internal, "fraud": r.fraud}))
        for fct in dec.facts:
            s.add(Fact(run_id=run_id, name=fct.name, value=fct.value, level=fct.level, source=fct.source, live=fct.live))
        s.add(Message(run_id=run_id, audience="vendor", subject=dec.vendor_subject, body=dec.vendor_body, state=dec.vendor_state))
        s.add(Message(run_id=run_id, audience="internal", subject="Reviewer note", body=dec.internal_note, state="draft"))
        run.status, run.risk_tier, run.reason_codes = dec.status, dec.risk_tier, dec.reason_codes
        run.summary = {"cards": dec.cards, "fraud": dec.fraud, "facts": [f.__dict__ for f in dec.facts], "diff": await _diff(s, run, rules)}
        run.state, run.finished_at = "done", now()
        app.current_status, app.legal_name = dec.status, form.get("legal_name", app.legal_name)
        # Vendor Intelligence: the exact decision input, encrypted, so the decision can be replayed later.
        # Never allowed to break a run: a missing snapshot only means simulation is unavailable for it.
        try:
            from onboarding.intel.snapshot import snapshot_row
            s.add(snapshot_row(run, ctx, rules, dec, reconstructed=False))
        except Exception:  # pragma: no cover - logged, never fatal
            import logging
            logging.getLogger("onboarding.intel").exception("decision snapshot for run %s not saved", run_id)
        if pace:
            await asyncio.sleep(pace)
        # results, "done" and the final event land in one commit: a viewer never sees one without the other
        await ev.emit("decision", "done", f"{STATUS_TEXT.get(dec.status, dec.status)} (risk tier: {dec.risk_tier})",
                      {"status": dec.status, "reason_codes": dec.reason_codes, "cards": dec.cards})
        return dec


async def invite_context(s: AsyncSession, app: Application) -> dict | None:
    """The invite as the rules see it (None for bill-first and unsolicited applications)."""
    invite = await s.get(Invite, app.invite_id) if app.invite_id else None
    if not invite:
        return None
    await s.refresh(invite, ["sponsor"])
    first_app = (await s.execute(select(Application.id).where(Application.invite_id == invite.id).order_by(Application.id))).scalars().first()
    return dict(status=invite.status, company_name=invite.company_name, expires_at=invite.expires_at.replace(tzinfo=invite.expires_at.tzinfo or timezone.utc),
                application_id=first_app, sponsor=f"{invite.sponsor.name} ({invite.sponsor.department})", reason=invite.business_reason,
                high_spend=invite.high_spend, spend_band=invite.spend_band)


async def gather_context(s: AsyncSession, app: Application, form: dict, docs_rows, infos: dict, inv: dict | None, *, as_of: datetime,
                         sources: dict | None = None, before_run_id: int | None = None) -> Context:
    """Everything the rules need besides the documents: source answers, vendor master, blocklist, reused files, bill
    duplicates. `sources` and `before_run_id` are only for rebuilding an old decision (Vendor Intelligence): given answers,
    and only data that existed before that run."""
    if sources is None:
        ifsc_task = asyncio.create_task(S.ifsc_lookup(form.get("ifsc", "")))
        pin_task = asyncio.create_task(S.pin_lookup(form.get("pin", ""))) if form.get("pin") else None
        addr_task = asyncio.create_task(A.validate(form)) if A.configured() else None
        srcs = {"gst": await S.gst_status(s, form.get("gstin", "")), "pan": await S.pan_status(s, form.get("pan", "")),
                "bank": await S.penny_drop(s, form.get("bank_account", ""), form.get("ifsc", ""))}
        if form.get("cin"):
            srcs["cin"] = await S.cin_status(s, form["cin"])
        srcs["ifsc"] = await ifsc_task
        if pin_task:
            srcs["pin"] = await pin_task
        if addr_task and (got := await addr_task):
            srcs["address"] = got
    else:
        srcs = sources
    pan, gstin, acct = form.get("pan", "").upper(), form.get("gstin", "").upper(), form.get("bank_account", "")
    master = [dict(vendor_id=m.vendor_id, legal_name=m.legal_name, pan=m.pan, gstin=m.gstin, account=m.account, ifsc=m.ifsc, status=m.status)
              for m in (await s.execute(select(VendorMaster).where(or_(VendorMaster.pan == pan, VendorMaster.gstin == gstin, VendorMaster.account == acct)))).scalars()
              if before_run_id is None or m.source_run_id is None or m.source_run_id < before_run_id]
    block = [dict(reason=b.reason) for b in (await s.execute(select(Blocklist).where(or_(Blocklist.pan == pan, Blocklist.gstin == gstin,
                                                                                     (Blocklist.account == acct) & (Blocklist.account != ""))))).scalars()]
    shas = [d.sha256 for d in docs_rows]
    reused = []
    if shas:
        q = select(Document.sha256, Document.filename, Application.ref, Run.form).join(Run, Run.id == Document.run_id).join(Application, Application.id == Run.application_id)
        q = q.where(Document.sha256.in_(shas), Application.id != app.id)
        if before_run_id is not None:
            q = q.where(Run.id < before_run_id)
        for sha, fn, ref, other_form in (await s.execute(q)).all():
            if (other_form or {}).get("pan", "").upper() != pan:
                reused.append({"file": fn, "other_application": ref})

    bill_ctx = None
    if form.get("bill_mode"):
        bill = (await s.execute(select(Bill).where(Bill.application_id == app.id))).scalar_one_or_none()
        emp = await s.get(Employee, bill.engaged_employee_id) if bill and bill.engaged_employee_id else None
        dups = []
        number = "".join(ch for ch in form.get("bill_invoice_number", "").upper() if ch.isalnum())
        if number:
            q = select(Run.form, Application.ref).join(Application, Application.id == Run.application_id).where(Run.application_id != app.id)
            if before_run_id is not None:
                q = q.where(Run.id < before_run_id)
            for other_form, ref in (await s.execute(q)).all():
                of = other_form or {}
                if of.get("bill_mode") and of.get("gstin", "").upper() == gstin and "".join(ch for ch in of.get("bill_invoice_number", "").upper() if ch.isalnum()) == number:
                    dups.append({"ref": ref})
        bill_ctx = {"engaged_employee": emp.name if emp else None, "engaged_department": emp.department if emp else "", "duplicates": dups}
    return Context(form=form, docs=infos, invite=inv, application_id=app.id, sources=srcs, master=master, blocklist=block, reused_files=reused,
                   bill=bill_ctx, as_of=as_of)


async def mark_failed(run_id: int, error: str) -> None:
    """A crash mid-run is shown as a failed run with the error type, never lost."""
    async with sessions()() as s:
        run = await s.get(Run, run_id)
        if run is None:
            return
        run.state, run.finished_at = "failed", now()
        last = (await s.execute(select(func.max(RunEvent.seq)).where(RunEvent.run_id == run_id))).scalar() or 0
        s.add(RunEvent(run_id=run_id, seq=last + 1, stage="decision", state="failed", summary=f"Run stopped by an internal error ({error}). Nothing was decided; retry or review manually."))
        await s.commit()


async def _diff(s: AsyncSession, run: Run, rules) -> dict:
    """For resubmissions: which earlier problems are resolved and which remain."""
    if not run.parent_run_id:
        return {}
    prev = {r.rule_id for r in (await s.execute(select(RuleResult).where(RuleResult.run_id == run.parent_run_id, RuleResult.result.in_(["FAIL", "ERROR"])))).scalars()}
    now_fail = {r.rule_id for r in rules if r.result in ("FAIL", "ERROR")}
    return {"resolved": sorted(prev - now_fail), "still_open": sorted(prev & now_fail), "new": sorted(now_fail - prev)}


async def sweep_interrupted() -> int:
    """On startup: runs left 'running' by a restart are marked interrupted (never silently lost)."""
    async with sessions()() as s:
        stuck = (await s.execute(select(Run).where(Run.state.in_(["queued", "running"])))).scalars().all()
        for r in stuck:
            r.state = "interrupted"
        await s.commit()
        return len(stuck)
