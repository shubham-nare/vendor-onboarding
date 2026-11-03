"""Builds Vendor Intelligence from finished runs and people's decisions. Idempotent: running it twice, or replaying
every run (backfill), never duplicates anything.

Event flow (domain_events records each one):
  run.completed      identity (which vendor) -> evidence items -> fact observations (history) -> identifiers
                     -> graph nodes/edges -> risk flags -> vendor status
  decision.recorded  evidence of the person's decision -> resolve the risk flags it addressed -> vendor status

It never changes an application, a run or a decision: it only reads them and writes the Vendor Intelligence tables.
Errors here are logged and never reach the onboarding flow (see on_run_completed / on_decision).
"""

from __future__ import annotations

from onboarding.countries import code_for

import logging
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from onboarding import validators as V
from onboarding.intel.crypto import SENSITIVE, encrypt, lookup_key, mask
from onboarding.intel.models import (DecisionSnapshot, DomainEvent, EvidenceItem, FactObservation, GraphEdge, GraphNode, RiskEvent,
                                     Vendor, VendorApplication, VendorIdentifier)
from onboarding.models import Application, Document, Employee, Fact, HumanAction, Run, RuleResult, VendorMaster, now
from onboarding.rules import SLOT_TITLE

log = logging.getLogger("onboarding.intel")

# onboarding fact name -> (fact key, identifier kind, form field, document slot it comes from)
FACTS = {"GSTIN": ("GSTIN", "GSTIN", "gstin", "gst_certificate"), "Legal name": ("LEGAL_NAME", "NAME", "legal_name", "gst_certificate"),
         "PAN": ("PAN", "PAN", "pan", "pan_card"), "Bank account": ("BANK_ACCOUNT", "BANK_ACCOUNT", "bank_account", "bank_proof"),
         "Bank branch": ("BANK_BRANCH", "IFSC", "ifsc", None), "MSME (Udyam)": ("MSME", "UDYAM", "udyam_no", "udyam_certificate")}

# Risk flags are raised ONLY where an existing onboarding rule already raised the alert. Each says what a reviewer does.
RISK_RULES = {
    "R-RISK-02": ("shared_bank_account", "Confirm with the bank, on a number you already hold, who owns this account, and ask both vendors how it "
                                         "is shared. A shared account can be legitimate (group companies); decide only after checking."),
    "R-RISK-04": ("reused_document", "Open both applications and compare the documents; ask this vendor for the original file. "
                                     "The same file from two different applicants usually means a template was reused."),
    "R-XD-03": ("identity_conflict", "Ask the vendor which legal entity is applying: the GST registration belongs to a different PAN. "
                                     "Confirm the rejection, or send it to review if there's a legitimate explanation."),
    "R-RISK-01": ("blocklist", "Check the blocklist entry and confirm the rejection; the vendor is told nothing specific."),
    "R-RISK-03": ("duplicate_registration", "Check whether this is the same company registering again; avoid a second vendor record "
                                            "(double payment risk)."),
}
STRONG = ("A2", "A3", "A4")


# --- small helpers -----------------------------------------------------------------------------------------
async def _one(s, stmt):
    return (await s.execute(stmt)).scalars().first()


async def _new_vendor(s, name: str, entity_type: str = "", country: str = "IN", origin: str = "application", status: str = "onboarding") -> Vendor:
    v = Vendor(vendor_id=f"TMP-{uuid.uuid4().hex[:12]}", display_name=name or "Unnamed vendor", entity_type=entity_type,
               country=(country or "IN")[:2].upper(), origin=origin, status=status)
    s.add(v)
    await s.flush()
    v.vendor_id = f"VND-{v.id:04d}"   # generated once, never changed
    await s.flush()
    return v


async def _evidence(s, vendor: Vendor, kind: str, ref: str, basis: str, label: str, payload: dict, *, run_id=None, sha: str = "", at=None) -> EvidenceItem:
    ev = await _one(s, select(EvidenceItem).where(EvidenceItem.vendor_pk == vendor.id, EvidenceItem.kind == kind, EvidenceItem.ref == ref))
    if ev:
        return ev   # evidence is immutable: the first record stands
    ev = EvidenceItem(vendor_pk=vendor.id, run_id=run_id, kind=kind, ref=ref, basis=basis, source_label=label, payload=payload,
                      content_sha256=sha, captured_at=at or now())
    s.add(ev)
    await s.flush()
    return ev


async def _node(s, kind: str, key: str, display: str, vendor_pk: int | None = None) -> GraphNode:
    n = await _one(s, select(GraphNode).where(GraphNode.tenant_id == "default", GraphNode.kind == kind, GraphNode.lookup_key == key))
    if n:
        if display and n.display != display and kind == "VENDOR":
            n.display = display
        return n
    n = GraphNode(kind=kind, lookup_key=key, display=display, vendor_pk=vendor_pk)
    s.add(n)
    await s.flush()
    return n


async def _edge(s, src: GraphNode, dst: GraphNode, type_: str, status: str, basis: str, *, evidence: EvidenceItem | None = None,
                rule_id: str = "", run_id=None, note: str = "", at=None) -> GraphEdge:
    e = await _one(s, select(GraphEdge).where(GraphEdge.src_id == src.id, GraphEdge.dst_id == dst.id, GraphEdge.type == type_))
    if e is None:
        e = GraphEdge(src_id=src.id, dst_id=dst.id, type=type_, status=status, basis=basis, rule_id=rule_id, note=note,
                      evidence_item_id=evidence.id if evidence else None, first_run_id=run_id, last_run_id=run_id, valid_from=at or now())
        s.add(e)
        await s.flush()
        return e
    if run_id is None or e.last_run_id is None or run_id >= e.last_run_id:   # the latest observation describes it now
        e.status, e.basis, e.rule_id, e.note, e.last_run_id, e.valid_to = status, basis, rule_id, note, run_id, None
        if evidence:
            e.evidence_item_id = evidence.id
    return e


async def _vendor_node(s, v: Vendor) -> GraphNode:
    return await _node(s, "VENDOR", v.vendor_id, v.display_name, v.id)


async def _identifier(s, v: Vendor, kind: str, raw: str, run_id=None, at=None) -> VendorIdentifier | None:
    key = lookup_key(kind, raw)
    if not key:
        return None
    idf = await _one(s, select(VendorIdentifier).where(VendorIdentifier.vendor_pk == v.id, VendorIdentifier.kind == kind, VendorIdentifier.lookup_key == key))
    if idf is None:
        idf = VendorIdentifier(vendor_pk=v.id, kind=kind, lookup_key=key, value_enc=encrypt(raw) if kind in SENSITIVE else "",
                               display=mask(kind, raw) if kind in SENSITIVE else raw.strip(), first_seen_at=at or now(),
                               last_seen_at=at or now(), first_run_id=run_id, last_run_id=run_id)
        s.add(idf)
        await s.flush()
    elif run_id is None or idf.last_run_id is None or run_id >= idf.last_run_id:
        idf.status, idf.last_seen_at, idf.last_run_id = "current", at or now(), run_id
    return idf


def _address(form: dict) -> str:
    return ", ".join(x for x in (form.get("address"), form.get("city"), form.get("pin")) if x)


# --- vendor-master records that existed before this system ----------------------------------------------------
async def ensure_master_vendors(s) -> None:
    """Existing vendor-master records become vendors too (origin vendor_master), so a new applicant sharing their bank
    account connects to them. Records created by our own activation are linked to the applicant's vendor instead."""
    linked = select(Vendor.erp_vendor_id).where(Vendor.erp_vendor_id != "")
    pending = (await s.execute(select(VendorMaster).where(VendorMaster.vendor_id.not_in(linked)).order_by(VendorMaster.id))).scalars().all()
    for m in pending:   # usually none: one query and done
        if await _one(s, select(Vendor).where(Vendor.erp_vendor_id == m.vendor_id)):
            continue
        if m.source_run_id:
            app_id = await _one(s, select(Run.application_id).where(Run.id == m.source_run_id))
            va = await _one(s, select(VendorApplication).where(VendorApplication.application_id == app_id))
            if va:
                v = await s.get(Vendor, va.vendor_pk)
                v.erp_vendor_id, v.status, v.updated_at = m.vendor_id, "active", now()
            continue
        v = await _new_vendor(s, m.legal_name, origin="vendor_master", status="on_record" if (m.status or "").lower() == "active" else "inactive")
        v.erp_vendor_id = m.vendor_id
        ev = await _evidence(s, v, "vendor_master_record", f"vm:{m.vendor_id}", "vendor_master", f"Vendor master record {m.vendor_id}",
                             {"vendor_id": m.vendor_id, "legal_name": m.legal_name, "status": m.status, "pan": V.mask_pan(m.pan), "gstin": m.gstin,
                              "account": V.mask_account(m.account), "ifsc": m.ifsc})
        vn = await _vendor_node(s, v)
        for kind, raw, etype in (("PAN", m.pan, "HAS_PAN"), ("GSTIN", m.gstin, "HAS_GSTIN"), ("BANK_ACCOUNT", m.account, "PAYS_TO")):
            if not raw:
                continue
            await _identifier(s, v, kind, raw)
            n = await _node(s, kind, lookup_key(kind, raw), mask(kind, raw))
            await _edge(s, vn, n, etype, "declared", "vendor_master", evidence=ev, note="On record in the vendor master")
        if m.account and m.ifsc:
            await _identifier(s, v, "IFSC", m.ifsc)
            acct = await _node(s, "BANK_ACCOUNT", lookup_key("BANK_ACCOUNT", m.account), mask("BANK_ACCOUNT", m.account))
            await _edge(s, acct, await _node(s, "IFSC", lookup_key("IFSC", m.ifsc), m.ifsc.upper()), "ACCOUNT_AT", "declared", "vendor_master", evidence=ev)
        emb = V.gstin_embedded_pan(m.gstin or "")
        if emb:
            await _edge(s, await _node(s, "GSTIN", lookup_key("GSTIN", m.gstin), m.gstin.upper()),
                        await _node(s, "PAN", lookup_key("PAN", emb), mask("PAN", emb)), "GSTIN_OF_PAN", "verified", "math",
                        note="Characters 3-12 of a GSTIN are the holder's PAN")
    await s.flush()


# --- identity ---------------------------------------------------------------------------------------------------
async def resolve_vendor(s, app: Application, form: dict) -> tuple[Vendor, str]:
    """PAN is the matching attribute: an application joins the vendor already holding its PAN. Shared bank accounts,
    addresses, emails or files never merge vendors: they become relationships."""
    va = await _one(s, select(VendorApplication).where(VendorApplication.application_id == app.id))
    if va:
        return await s.get(Vendor, va.vendor_pk), va.method
    pan = V.normalise_id(form.get("pan", ""))
    vendor, method = None, "no_pan"
    if pan:
        idf = await _one(s, select(VendorIdentifier).where(VendorIdentifier.kind == "PAN", VendorIdentifier.lookup_key == lookup_key("PAN", pan))
                         .order_by(VendorIdentifier.id))
        if idf:
            vendor, method = await s.get(Vendor, idf.vendor_pk), "pan_match"
        else:
            method = "new_vendor"
    if vendor is None:
        country = code_for(form.get("country")) or "XX"
        vendor = await _new_vendor(s, form.get("legal_name") or app.legal_name, form.get("business_type", ""), country)
    s.add(VendorApplication(vendor_pk=vendor.id, application_id=app.id, method=method))
    await s.flush()
    return vendor, method


async def refresh_vendor_status(s, vendor: Vendor) -> None:
    statuses = [st for (st,) in (await s.execute(select(Application.current_status).join(VendorApplication, VendorApplication.application_id == Application.id)
                                                 .where(VendorApplication.vendor_pk == vendor.id))).all()]
    if "ACTIVE" in statuses or vendor.erp_vendor_id and vendor.origin == "application":
        vendor.status = "active"
    elif vendor.origin == "vendor_master" and not statuses:
        pass
    elif statuses and all(st == "REJECTED" for st in statuses):
        vendor.status = "rejected"
    elif statuses:
        vendor.status = "onboarding"
    vendor.updated_at = now()


# --- run.completed ------------------------------------------------------------------------------------------------
async def project_run(s, run_id: int, *, force: bool = False) -> Vendor | None:
    run = await s.get(Run, run_id)
    if run is None or run.state != "done":
        return None
    done = await _one(s, select(DomainEvent).where(DomainEvent.type == "run.completed", DomainEvent.aggregate_id == str(run_id),
                                                   DomainEvent.processed_at.is_not(None)))
    if done and not force:
        va = await _one(s, select(VendorApplication).where(VendorApplication.application_id == run.application_id))
        return await s.get(Vendor, va.vendor_pk) if va else None
    app = await s.get(Application, run.application_id)
    form = run.form or {}
    at = run.finished_at or run.started_at
    await ensure_master_vendors(s)

    # decision snapshot: exact for new runs; rebuilt (and checked) for runs from before snapshots existed
    snap = await _one(s, select(DecisionSnapshot).where(DecisionSnapshot.run_id == run_id))
    ctx = None
    if snap is None:
        try:
            from onboarding.intel.snapshot import reconstruct
            snap = await reconstruct(s, run)
            if snap:
                s.add(snap)
                await s.flush()
        except Exception:
            log.exception("could not rebuild the decision input of run %s", run_id)
            snap = None
    if snap is not None:
        try:
            from onboarding.intel.snapshot import load_context
            ctx = load_context(snap)
        except Exception:
            log.exception("could not read the decision snapshot of run %s", run_id)

    vendor, method = await resolve_vendor(s, app, form)
    vn = await _vendor_node(s, vendor)
    vendor.display_name = form.get("legal_name") or vendor.display_name
    vendor.entity_type = form.get("business_type") or vendor.entity_type
    vn.display = vendor.display_name

    # evidence --------------------------------------------------------------------------------------------------
    check = f"{app.ref} · check #{run.id}"
    ev_form = await _evidence(s, vendor, "form_submission", f"run:{run.id}:form", "declared", f"Submitted form ({check})",
                              {"legal_name": form.get("legal_name"), "business_type": form.get("business_type"), "pan": V.mask_pan(form.get("pan", "")),
                               "gstin": form.get("gstin"), "bank_account": V.mask_account(form.get("bank_account", "")), "ifsc": form.get("ifsc"),
                               "city": form.get("city"), "state": form.get("state")}, run_id=run.id, at=at)
    docs = (await s.execute(select(Document).where(Document.run_id == run.id))).scalars().all()
    ev_doc: dict[str, EvidenceItem] = {}
    for d in docs:
        rd, au = d.read or {}, d.authenticity or {}
        sig = au.get("signature") or {}
        signed = bool(sig.get("present") and sig.get("intact") and sig.get("valid"))
        ev_doc[d.slot] = await _evidence(s, vendor, "document", f"run:{run.id}:doc:{d.slot}", "signature" if signed else "document",
                                         f"{SLOT_TITLE.get(d.slot, d.slot)} · {d.filename} ({check})",
                                         {"slot": d.slot, "filename": d.filename, "ai_read_as": rd.get("doc_type"), "document_form": rd.get("document_form"),
                                          "reading": rd.get("origin"), "authenticity_level": au.get("level"), "specimen": bool(au.get("specimen")),
                                          "signed": signed}, run_id=run.id, sha=d.sha256, at=at)
    ev_src: dict[str, EvidenceItem] = {}
    keep = {"ifsc": ("BANK", "BRANCH", "CITY"), "gst": ("legal_name", "status"), "pan": ("name", "status"), "bank": ("holder",), "cin": ("name", "status")}
    for k, sr in (ctx.sources.items() if ctx else []):
        label = sr.source
        basis = "live" if sr.live else ("simulated" if "SIMULATED" in label.upper() else "snapshot")
        ev_src[k] = await _evidence(s, vendor, "source_response", f"run:{run.id}:source:{k}", basis,
                                    ("SIMULATED SOURCE · " + label.replace("SIMULATED ", "")) if basis == "simulated" else label,
                                    {"status": sr.status, "live": sr.live, "checked_at": sr.checked_at,
                                     **{f: (sr.data or {}).get(f) for f in keep.get(k, ()) if (sr.data or {}).get(f)}}, run_id=run.id, at=at)
    rules = (await s.execute(select(RuleResult).where(RuleResult.run_id == run.id))).scalars().all()
    rr = {r.rule_id: r for r in rules}
    ev_rule: dict[str, EvidenceItem] = {}
    for r in rules:
        if r.result == "FAIL" and (r.rule_id in RISK_RULES or r.rule_id == "R-SRC-BANK"):
            ev_rule[r.rule_id] = await _evidence(s, vendor, "rule_result", f"run:{run.id}:rule:{r.rule_id}", "rule", f"Rule {r.rule_id} ({check})",
                                                 {"rule": r.rule_id, "result": r.result, "outcome": r.outcome_if_fail, "title": r.title,
                                                  "fraud_class": bool((r.evidence or {}).get("fraud"))}, run_id=run.id, at=at)

    # fact history ------------------------------------------------------------------------------------------------
    facts = (await s.execute(select(Fact).where(Fact.run_id == run.id).order_by(Fact.id))).scalars().all()
    notes = {f.get("name"): f.get("note", "") for f in (run.summary or {}).get("facts", [])}
    levels = {}
    for f in facts:
        if f.name not in FACTS:
            continue
        key, kind, field, slot = FACTS[f.name]
        levels[f.name] = f.level
        if await _one(s, select(FactObservation.id).where(FactObservation.vendor_pk == vendor.id, FactObservation.fact == key, FactObservation.run_id == run.id)):
            continue
        basis = ("live" if f.live else "snapshot") if f.name == "Bank branch" else ("signature" if f.level == "A3" else ("document" if f.level in ("A1", "A2") else "declared"))
        evid = ev_src.get("ifsc") if f.name == "Bank branch" else ev_doc.get(slot) or ev_form
        prev = await _one(s, select(FactObservation).where(FactObservation.vendor_pk == vendor.id, FactObservation.fact == key,
                                                           FactObservation.run_id < run.id).order_by(FactObservation.run_id.desc()))
        s.add(FactObservation(vendor_pk=vendor.id, fact=key, value_display=f.value, value_key=lookup_key(kind, form.get(field, "")), level=f.level,
                              basis=basis, source_label=f.source, note=notes.get(f.name, ""), evidence_item_id=evid.id if evid else None,
                              run_id=run.id, observed_at=at, supersedes_id=prev.id if prev else None,
                              valid_until=at + timedelta(days=365) if basis == "live" else None))
    await s.flush()

    # identifiers -------------------------------------------------------------------------------------------------
    pan, gstin, acct, ifsc = form.get("pan", ""), form.get("gstin", ""), form.get("bank_account", ""), form.get("ifsc", "")
    seen = []
    for kind, raw in (("PAN", pan), ("GSTIN", gstin), ("CIN", form.get("cin")), ("LLPIN", form.get("llpin")),
                      ("UDYAM", form.get("udyam_no") if form.get("msme") else ""), ("BANK_ACCOUNT", acct), ("IFSC", ifsc),
                      ("EMAIL", form.get("contact_email")), ("PHONE", form.get("contact_phone")), ("ADDRESS", _address(form))):
        idf = await _identifier(s, vendor, kind, raw or "", run.id, at)
        if idf:
            seen.append(idf.id)
    earlier = [rid for (rid,) in (await s.execute(select(Run.id).where(Run.application_id == app.id, Run.id < run.id))).all()]
    if earlier:   # changed in a resubmission of the same application: kept as history, no longer current
        for idf in (await s.execute(select(VendorIdentifier).where(VendorIdentifier.vendor_pk == vendor.id, VendorIdentifier.last_run_id.in_(earlier)))).scalars():
            if idf.id not in seen and idf.kind in ("BANK_ACCOUNT", "IFSC", "EMAIL", "PHONE", "ADDRESS"):
                idf.status = "previous"

    # graph -----------------------------------------------------------------------------------------------------
    def status_for(fact_name: str) -> tuple[str, str]:
        lv = levels.get(fact_name, "A0")
        basis = "signature" if lv == "A3" else ("live" if lv == "A4" else "document")
        return ("verified", basis) if lv in STRONG else ("declared", "declared")

    edges: dict[str, GraphEdge] = {}
    if pan:
        st, b = status_for("PAN")
        edges["PAN"] = await _edge(s, vn, await _node(s, "PAN", lookup_key("PAN", pan), mask("PAN", pan)), "HAS_PAN", st, b,
                                   evidence=ev_doc.get("pan_card") or ev_form, run_id=run.id, at=at)
    if gstin:
        gnode = await _node(s, "GSTIN", lookup_key("GSTIN", gstin), V.normalise_id(gstin))
        conflict = rr.get("R-XD-03") is not None and rr["R-XD-03"].result == "FAIL"
        st, b = ("unresolved", "rule") if conflict else status_for("GSTIN")
        edges["GSTIN"] = await _edge(s, vn, gnode, "HAS_GSTIN", st, b, evidence=ev_doc.get("gst_certificate") or ev_form,
                                     rule_id="R-XD-03" if conflict else "", run_id=run.id, at=at)
        emb = V.gstin_embedded_pan(gstin)
        if emb and V.gstin_format_ok(V.normalise_id(gstin)):
            pnode = await _node(s, "PAN", lookup_key("PAN", emb), mask("PAN", emb))
            await _edge(s, gnode, pnode, "GSTIN_OF_PAN", "verified", "math", note="Characters 3-12 of a GSTIN are the holder's PAN", run_id=run.id, at=at)
            if conflict:
                edges["CONFLICT"] = await _edge(s, vn, pnode, "IDENTITY_CONFLICT", "unresolved", "rule", evidence=ev_rule.get("R-XD-03"),
                                                rule_id="R-XD-03", note="The GSTIN this vendor submitted belongs to this other PAN", run_id=run.id, at=at)
    if acct:
        anode = await _node(s, "BANK_ACCOUNT", lookup_key("BANK_ACCOUNT", acct), mask("BANK_ACCOUNT", acct))
        bank = rr.get("R-SRC-BANK")
        if bank is not None and bank.result == "FAIL":
            st, b, rule, note = "unresolved", "simulated", "R-SRC-BANK", "SIMULATED SOURCE: the penny-drop stand-in names a different holder"
        else:
            (st, b), rule, note = status_for("Bank account"), "", ""
        edges["ACCOUNT"] = await _edge(s, vn, anode, "PAYS_TO", st, b, evidence=ev_doc.get("bank_proof") or ev_form, rule_id=rule, note=note, run_id=run.id, at=at)
        if ifsc:
            src = ctx.sources.get("ifsc") if ctx else None
            live = bool(src and src.status == "FOUND" and src.live)
            await _edge(s, anode, await _node(s, "IFSC", lookup_key("IFSC", ifsc), V.normalise_id(ifsc)), "ACCOUNT_AT",
                        "verified" if live else "declared", "live" if live else "declared", evidence=ev_src.get("ifsc"), run_id=run.id, at=at)
    for kind, raw, etype in (("CIN", form.get("cin"), "HAS_CIN"), ("LLPIN", form.get("llpin"), "HAS_LLPIN")):
        if raw:
            await _edge(s, vn, await _node(s, kind, lookup_key(kind, raw), V.normalise_id(raw)), etype, "declared", "declared", evidence=ev_form, run_id=run.id, at=at)
    if form.get("msme") and form.get("udyam_no"):
        st, b = status_for("MSME (Udyam)")
        await _edge(s, vn, await _node(s, "UDYAM", lookup_key("UDYAM", form["udyam_no"]), V.normalise_id(form["udyam_no"])), "HAS_UDYAM", st, b,
                    evidence=ev_doc.get("udyam_certificate") or ev_form, run_id=run.id, at=at)
    for kind, raw, etype in (("ADDRESS", _address(form), "REGISTERED_AT"), ("EMAIL", form.get("contact_email"), "CONTACT_EMAIL"),
                             ("PHONE", form.get("contact_phone"), "CONTACT_PHONE")):
        if raw:
            await _edge(s, vn, await _node(s, kind, lookup_key(kind, raw), mask(kind, raw)), etype, "declared", "declared", evidence=ev_form, run_id=run.id, at=at)
    doc_edges = {}
    for d in docs:
        doc_edges[d.sha256] = await _edge(s, vn, await _node(s, "DOCUMENT", d.sha256, f"{SLOT_TITLE.get(d.slot, d.slot)} · {d.filename}"), "SUBMITTED",
                                          "verified", "document", evidence=ev_doc.get(d.slot), note="Same bytes (SHA-256) as the submitted file",
                                          run_id=run.id, at=at)
    if earlier:   # relationships the latest submission no longer declares stop being current (history is kept)
        for e in (await s.execute(select(GraphEdge).where(GraphEdge.src_id == vn.id, GraphEdge.last_run_id.in_(earlier),
                                                          GraphEdge.type.in_(("PAYS_TO", "REGISTERED_AT", "CONTACT_EMAIL", "CONTACT_PHONE", "SUBMITTED")),
                                                          GraphEdge.valid_to.is_(None)))).scalars():
            e.valid_to = at

    # risk flags (only where an existing rule raised the alert) ----------------------------------------------------
    for rid, r in rr.items():
        if rid not in RISK_RULES or r.result != "FAIL":
            continue
        if await _one(s, select(RiskEvent.id).where(RiskEvent.run_id == run.id, RiskEvent.rule_id == rid)):
            continue
        kind, todo = RISK_RULES[rid]
        evd = r.evidence or {}
        related, edge = None, None
        if rid == "R-RISK-02":
            related = await _one(s, select(Vendor.id).where(Vendor.erp_vendor_id == evd.get("other_vendor")))
            edge = edges.get("ACCOUNT")
        elif rid == "R-RISK-03":
            related = await _one(s, select(Vendor.id).where(Vendor.erp_vendor_id == evd.get("vendor")))
        elif rid == "R-RISK-04":
            refs = [x.get("other_application") for x in evd.get("reused", []) if x.get("other_application")]
            if refs:
                related = await _one(s, select(VendorApplication.vendor_pk).join(Application, Application.id == VendorApplication.application_id)
                                     .where(Application.ref == refs[0]))
            edge = next(iter(doc_edges.values()), None)
        elif rid == "R-XD-03":
            edge = edges.get("CONFLICT")
            emb = V.gstin_embedded_pan(gstin or "")
            if emb:
                related = await _one(s, select(VendorIdentifier.vendor_pk).where(VendorIdentifier.kind == "PAN", VendorIdentifier.lookup_key == lookup_key("PAN", emb),
                                                                                 VendorIdentifier.vendor_pk != vendor.id))
        s.add(RiskEvent(vendor_pk=vendor.id, application_id=app.id, run_id=run.id, rule_id=rid, kind=kind,
                        severity="fraud" if evd.get("fraud") else "review", title=r.title, reviewer_action=todo,
                        evidence_item_id=ev_rule[rid].id if rid in ev_rule else None, edge_id=edge.id if edge else None,
                        related_vendor_pk=related if related != vendor.id else None, opened_at=at))
    for ev in (await s.execute(select(RiskEvent).where(RiskEvent.application_id == app.id, RiskEvent.status == "open", RiskEvent.run_id < run.id))).scalars():
        cur = rr.get(ev.rule_id)
        if cur is None or cur.result != "FAIL":
            ev.status, ev.resolved_at, ev.resolution = "resolved", at, f"No longer found in the resubmission (check #{run.id})."

    await refresh_vendor_status(s, vendor)
    if done is None:
        s.add(DomainEvent(type="run.completed", aggregate="run", aggregate_id=str(run.id),
                          payload={"application": app.ref, "vendor_id": vendor.vendor_id, "link": method}, occurred_at=at, processed_at=now()))
    await s.flush()
    return vendor


# --- decision.recorded ----------------------------------------------------------------------------------------------
ACTION_TEXT = {"activate": "Activated", "review_approve": "Approved after review", "confirm_reject": "Rejection confirmed",
               "review_reject": "Rejected after review", "ask_vendor": "Asked the vendor for something", "override_reject": "Sent to review instead of rejecting",
               "confirm_engagement": "Engagement confirmed", "deny_engagement": "Engagement denied"}


async def project_decision(s, action_id: int) -> None:
    a = await s.get(HumanAction, action_id)
    if a is None:
        return
    if await _one(s, select(DomainEvent.id).where(DomainEvent.type == "decision.recorded", DomainEvent.aggregate_id == str(action_id))):
        return
    run = await s.get(Run, a.run_id)
    va = await _one(s, select(VendorApplication).where(VendorApplication.application_id == run.application_id))
    if va is None:   # the run hasn't been projected yet; project it first
        await project_run(s, run.id)
        va = await _one(s, select(VendorApplication).where(VendorApplication.application_id == run.application_id))
        if va is None:
            return
    vendor = await s.get(Vendor, va.vendor_pk)
    app = await s.get(Application, run.application_id)
    emp = await s.get(Employee, a.employee_id)
    from onboarding.web import ROLE_LABEL
    who = f"{emp.name} ({ROLE_LABEL.get(emp.role, emp.role)})" if emp else "someone"
    ev = await _evidence(s, vendor, "human_decision", f"action:{a.id}", "human", f"{ACTION_TEXT.get(a.action, a.action)} by {who}",
                         {"action": a.action, "by": emp.name if emp else "", "role": emp.role if emp else "", "comment": a.comment, "application": app.ref},
                         run_id=run.id, at=a.at)
    if app.current_status in ("ACTIVE", "REJECTED") and a.action in ("activate", "review_approve", "confirm_reject", "review_reject"):
        for r in (await s.execute(select(RiskEvent).where(RiskEvent.application_id == app.id, RiskEvent.status == "open"))).scalars():
            r.status, r.resolved_at = "resolved", a.at
            r.resolution = f"{ACTION_TEXT.get(a.action, a.action)} by {who}" + (f": \"{a.comment}\"" if a.comment else "") + f" (evidence #{ev.id})."
    await ensure_master_vendors(s)   # an activation adds a vendor-master row: link it
    await refresh_vendor_status(s, vendor)
    s.add(DomainEvent(type="decision.recorded", aggregate="application", aggregate_id=str(action_id),
                      payload={"application": app.ref, "vendor_id": vendor.vendor_id, "action": a.action}, occurred_at=a.at, processed_at=now()))
    await s.flush()


# --- entry points (never let Vendor Intelligence break onboarding) --------------------------------------------------
async def on_run_completed(run_id: int) -> None:
    from onboarding.pipeline import sessions
    try:
        async with sessions()() as s:
            await project_run(s, run_id)
            await s.commit()
    except Exception:
        log.exception("vendor intelligence: run %s not projected (backfill will retry)", run_id)


async def on_decision(action_id: int) -> None:
    from onboarding.pipeline import sessions
    try:
        async with sessions()() as s:
            await project_decision(s, action_id)
            await s.commit()
    except Exception:
        log.exception("vendor intelligence: decision %s not projected (backfill will retry)", action_id)


async def backfill() -> dict:
    """Project every finished run and every decision not projected yet, oldest first. Safe to run any time."""
    from onboarding.pipeline import sessions
    counts = {"runs": 0, "decisions": 0}
    async with sessions()() as s:
        await ensure_master_vendors(s)
        await s.commit()
        done = {int(x) for (x,) in (await s.execute(select(DomainEvent.aggregate_id).where(DomainEvent.type == "run.completed"))).all()}
        run_ids = [rid for (rid,) in (await s.execute(select(Run.id).where(Run.state == "done").order_by(Run.id))).all() if rid not in done]
        acted = {int(x) for (x,) in (await s.execute(select(DomainEvent.aggregate_id).where(DomainEvent.type == "decision.recorded"))).all()}
        action_ids = [aid for (aid,) in (await s.execute(select(HumanAction.id).order_by(HumanAction.id))).all() if aid not in acted]
    # decisions interleave with runs in time order, so risk flags close in the right order
    run_at = {}
    async with sessions()() as s:
        for rid in run_ids:
            run_at[("run", rid)] = (await s.get(Run, rid)).finished_at
        for aid in action_ids:
            run_at[("action", aid)] = (await s.get(HumanAction, aid)).at
    for kind, oid in sorted(run_at, key=lambda k: (_utc(run_at[k]), k[0] != "run")):
        async with sessions()() as s:
            if kind == "run":
                await project_run(s, oid)
                counts["runs"] += 1
            else:
                await project_decision(s, oid)
                counts["decisions"] += 1
            await s.commit()
    return counts


def _utc(dt):
    from datetime import datetime, timezone
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def vendor_count(s) -> int:
    return (await s.execute(select(func.count(Vendor.id)))).scalar() or 0


