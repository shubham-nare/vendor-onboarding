"""The exact input of a decision, saved encrypted, and replayed through the unchanged rules and decision code.

A replay with no changes must reproduce the original decision exactly (status, risk tier, every rule result and
every fact level). If it doesn't, the snapshot is marked replay_ok=False and simulation is refused for that run,
so a counterfactual can never be built on a decision we can't reproduce.

New runs save an exact snapshot inside their final commit (pipeline.run_pipeline). Runs from before this existed
are reconstructed from stored data (reconstructed=True) and checked the same way.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy import select

from onboarding import decision as D
from onboarding.ai.read import DocRead
from onboarding.authenticity.assess import Authenticity, Signal
from onboarding.intel.crypto import decrypt, encrypt
from onboarding.intel.models import DecisionSnapshot
from onboarding.rules import Context, DocInfo, evaluate
from onboarding.sources import SourceResult

log = logging.getLogger("onboarding.intel")
POLICY_VERSION = "v1"   # today's rules and decision precedence, unchanged


# --- (de)serialising a rules.Context ---------------------------------------------------------------
def context_to_dict(ctx: Context) -> dict:
    inv = dict(ctx.invite) if ctx.invite else None
    if inv and isinstance(inv.get("expires_at"), datetime):
        inv["expires_at"] = inv["expires_at"].isoformat()
    return {
        "form": ctx.form,
        "docs": {slot: {"filename": d.filename, "sha256": d.sha256, "mime": d.mime, "read_origin": d.read_origin,
                        "read": d.read.model_dump(mode="json") if d.read else None,
                        "auth": d.auth.as_dict() if d.auth else None} for slot, d in ctx.docs.items()},
        "invite": inv,
        "application_id": ctx.application_id,
        "sources": {k: v.as_dict() for k, v in ctx.sources.items()},
        "master": ctx.master, "blocklist": ctx.blocklist, "reused_files": ctx.reused_files, "bill": ctx.bill,
        "as_of": ctx.as_of.isoformat() if ctx.as_of else None,
    }


def _auth_from(d: dict | None) -> Authenticity | None:
    if not d:
        return None
    return Authenticity(level=d.get("level", "A1"), worst=d.get("worst", ""), specimen=bool(d.get("specimen")),
                        signals=[Signal(**sg) for sg in d.get("signals", [])], signature=d.get("signature") or {}, facts=d.get("facts") or {})


def context_from_dict(d: dict) -> Context:
    inv = dict(d["invite"]) if d.get("invite") else None
    if inv and isinstance(inv.get("expires_at"), str):
        inv["expires_at"] = datetime.fromisoformat(inv["expires_at"])
    docs = {slot: DocInfo(slot, x["filename"], x["sha256"], x["mime"], DocRead.model_validate(x["read"]) if x.get("read") else None,
                          x["read_origin"], _auth_from(x.get("auth"))) for slot, x in d["docs"].items()}
    return Context(form=d["form"], docs=docs, invite=inv, application_id=d.get("application_id"),
                   sources={k: SourceResult(**v) for k, v in d.get("sources", {}).items()}, master=d.get("master") or [],
                   blocklist=d.get("blocklist") or [], reused_files=d.get("reused_files") or [], bill=d.get("bill"),
                   as_of=datetime.fromisoformat(d["as_of"]) if d.get("as_of") else None)


def _dumps(d: dict) -> str:
    return json.dumps(d, sort_keys=True, default=str, ensure_ascii=False)


# --- outcomes -----------------------------------------------------------------------------------------
def outcome_of(rules, dec: D.Decision) -> dict:
    return {"status": dec.status, "risk_tier": dec.risk_tier, "fraud": bool(dec.fraud),
            "rules": sorted([r.rule_id, r.result, r.outcome or ""] for r in rules),
            "facts": [[f.name, f.level] for f in dec.facts]}


def replay(ctx: Context, ref: str = ""):
    rules = evaluate(ctx)
    return rules, D.decide(rules, ctx, ref=ref)


def same_outcome(a: dict, b: dict) -> tuple[bool, str]:
    for key in ("status", "risk_tier", "rules", "facts"):
        if a.get(key) != b.get(key):
            return False, f"{key} differs"
    return True, ""


# --- snapshot rows --------------------------------------------------------------------------------------
def snapshot_row(run, ctx: Context, rules, dec: D.Decision, *, reconstructed: bool, expected: dict | None = None) -> DecisionSnapshot:
    """Build the row; check the serialised context replays to the same outcome before calling it reproducible."""
    plain = _dumps(context_to_dict(ctx))
    outcome = expected or outcome_of(rules, dec)
    try:
        r2, d2 = replay(context_from_dict(json.loads(plain)), ref="")
        ok, note = same_outcome(outcome, outcome_of(r2, d2))
    except Exception as e:  # a snapshot we can't replay is kept, but marked unusable
        ok, note = False, f"replay failed: {type(e).__name__}"
    return DecisionSnapshot(run_id=run.id, policy_version=POLICY_VERSION, context_enc=encrypt(plain),
                            context_sha256=hashlib.sha256(plain.encode()).hexdigest(), outcome=outcome,
                            reconstructed=reconstructed, replay_ok=ok, replay_note=note)


def load_context(snap: DecisionSnapshot) -> Context:
    return context_from_dict(json.loads(decrypt(snap.context_enc)))


async def stored_outcome(s, run) -> dict:
    """The decision as it was recorded (rule_results + facts + run), to check a reconstruction against."""
    from onboarding.models import Fact, RuleResult
    rules = (await s.execute(select(RuleResult.rule_id, RuleResult.result, RuleResult.outcome_if_fail).where(RuleResult.run_id == run.id))).all()
    facts = (await s.execute(select(Fact.name, Fact.level).where(Fact.run_id == run.id).order_by(Fact.id))).all()
    return {"status": run.status, "risk_tier": run.risk_tier, "fraud": bool((run.summary or {}).get("fraud")),
            "rules": sorted([r[0], r[1], r[2] or ""] for r in rules), "facts": [[f[0], f[1]] for f in facts]}


async def reconstruct(s, run) -> DecisionSnapshot | None:
    """Rebuild the input of a run decided before snapshots existed, from what was stored: the form, the AI readings,
    the authenticity results, the simulated registries (deterministic), the IFSC answer as recorded in the run's events
    (branch details from the bundled snapshot), and only vendor-master rows / files / bills that existed before it."""
    from onboarding.models import Application, Document, RunEvent, StoredFile
    from onboarding import sources as S
    from onboarding.pipeline import gather_context, invite_context

    if run.state != "done":
        return None
    app = await s.get(Application, run.application_id)
    docs_rows = (await s.execute(select(Document).where(Document.run_id == run.id))).scalars().all()
    mimes = dict((await s.execute(select(StoredFile.sha256, StoredFile.mime).where(StoredFile.sha256.in_([d.sha256 for d in docs_rows] or [""])))).all())
    infos = {}
    for d in docs_rows:
        rd = dict(d.read or {})
        origin = rd.pop("origin", "failed")
        for k in ("model", "seconds", "error"):
            rd.pop(k, None)
        read = DocRead.model_validate(rd) if rd.get("doc_type") else None
        infos[d.slot] = DocInfo(d.slot, d.filename, d.sha256, mimes.get(d.sha256, ""), read, origin, _auth_from(d.authenticity))
    form = run.form or {}
    srcs = {"gst": await S.gst_status(s, form.get("gstin", "")), "pan": await S.pan_status(s, form.get("pan", "")),
            "bank": await S.penny_drop(s, form.get("bank_account", ""), form.get("ifsc", ""))}
    if form.get("cin"):
        srcs["cin"] = await S.cin_status(s, form["cin"])
    ev = (await s.execute(select(RunEvent.evidence).where(RunEvent.run_id == run.id, RunEvent.stage == "sources").order_by(RunEvent.seq.desc()))).scalars().first() or {}
    rec = (ev.get("sources") or {}).get("ifsc") or {}
    snap = json.loads(S.SNAPSHOT.read_text(encoding="utf-8")) if S.SNAPSHOT.exists() else {"records": {}}
    code = (form.get("ifsc") or "").strip().upper()
    srcs["ifsc"] = SourceResult(rec.get("source", "IFSC (as recorded)"), rec.get("status", "ERROR"), bool(rec.get("live")),
                                snap["records"].get(code, {}) if rec.get("status") == "FOUND" else {})
    inv = await invite_context(s, app)
    ctx = await gather_context(s, app, form, docs_rows, infos, inv, as_of=run.finished_at or run.started_at, sources=srcs, before_run_id=run.id)
    expected = await stored_outcome(s, run)
    rules, dec = replay(ctx, ref=app.ref)
    row = snapshot_row(run, ctx, rules, dec, reconstructed=True, expected=expected)
    ok, note = same_outcome(expected, outcome_of(rules, dec))
    if not ok:  # the rebuild itself doesn't reproduce what was decided
        row.replay_ok, row.replay_note = False, f"rebuilt input doesn't reproduce the recorded decision ({note})"
    return row
