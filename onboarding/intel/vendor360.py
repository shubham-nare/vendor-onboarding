"""Read side of Vendor Intelligence: turns the stored rows into one vendor's profile. Pure functions (the web layer
does the queries, in parallel), so the logic is easy to test.

Connections between vendors are derived when read, from two current edges reaching the same node (for example two
vendors paying into one bank account). Each keeps the provenance of both edges. Only bank accounts, document files
and identity conflicts are "actionable"; shared addresses, emails and phones are context, never a risk by themselves.
"""

from __future__ import annotations

import math
from datetime import datetime
from collections import defaultdict

FACT_ORDER = ["LEGAL_NAME", "PAN", "GSTIN", "BANK_ACCOUNT", "BANK_BRANCH", "MSME"]
FACT_LABEL = {"LEGAL_NAME": "Legal name", "PAN": "PAN", "GSTIN": "GSTIN", "BANK_ACCOUNT": "Bank account", "BANK_BRANCH": "Bank branch", "MSME": "MSME (Udyam)"}
KIND_LABEL = {"PAN": "PAN", "GSTIN": "GSTIN", "CIN": "CIN", "LLPIN": "LLPIN", "UDYAM": "Udyam", "BANK_ACCOUNT": "Bank account", "IFSC": "IFSC",
              "EMAIL": "Email", "PHONE": "Phone", "ADDRESS": "Address", "DOCUMENT": "Document", "VENDOR": "Vendor"}
EDGE_LABEL = {"HAS_PAN": "has PAN", "HAS_GSTIN": "has GSTIN", "PAYS_TO": "is paid into", "ACCOUNT_AT": "is held at", "REGISTERED_AT": "is registered at",
              "CONTACT_EMAIL": "uses email", "CONTACT_PHONE": "uses phone", "SUBMITTED": "submitted", "HAS_CIN": "has CIN", "HAS_LLPIN": "has LLPIN",
              "HAS_UDYAM": "has Udyam", "IDENTITY_CONFLICT": "conflicts with PAN", "GSTIN_OF_PAN": "belongs to PAN"}
BASIS_LABEL = {"live": "live source", "simulated": "SIMULATED SOURCE", "snapshot": "bundled snapshot", "document": "document", "signature": "digital signature",
               "math": "ID arithmetic", "declared": "declared by the vendor", "vendor_master": "vendor master record", "rule": "onboarding rule", "human": "a person"}
ACTIONABLE = {"BANK_ACCOUNT": "Shared bank account", "DOCUMENT": "Same document file", "PAN": "Identity conflict"}
CONTEXT = {"ADDRESS": "Same address", "EMAIL": "Same email", "PHONE": "Same phone", "IFSC": "Same bank branch", "GSTIN": "Same GSTIN"}
LEVEL_RANK = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}
RISK_TITLE = {"shared_bank_account": "Verify who owns the shared bank account", "reused_document": "Compare the reused document with the other application",
              "identity_conflict": "Establish which legal entity is applying", "blocklist": "Confirm the blocklist rejection",
              "duplicate_registration": "Check for a duplicate vendor record"}
# which fact a relationship or a flag puts in doubt
EDGE_FACT = {"HAS_PAN": "PAN", "HAS_GSTIN": "GSTIN", "PAYS_TO": "BANK_ACCOUNT", "HAS_UDYAM": "MSME"}
RULE_FACT = {"R-RISK-02": "BANK_ACCOUNT", "R-XD-03": "GSTIN", "R-RISK-01": "PAN", "R-RISK-03": "PAN"}
STATUS_TEXT = {"onboarding": "Onboarding", "active": "Active vendor", "rejected": "Rejected", "on_record": "On record (vendor master)", "inactive": "Inactive"}


def fact_history(observations) -> list[dict]:
    """Per fact: the current observation and the earlier ones it superseded (newest first)."""
    by = defaultdict(list)
    for o in observations:
        by[o.fact].append(o)
    out = []
    for fact in FACT_ORDER + sorted(set(by) - set(FACT_ORDER)):
        if fact not in by:
            continue
        obs = sorted(by[fact], key=lambda o: (o.observed_at.replace(tzinfo=None) if o.observed_at else datetime.min, o.id), reverse=True)
        cur = obs[0]
        changed = len({o.value_key for o in obs if o.value_key}) > 1
        out.append(dict(fact=fact, label=FACT_LABEL.get(fact, fact), current=cur, history=obs[1:], changed=changed))
    return out


def fact_doubts(vendor, my_edges, risks) -> dict[str, list[str]]:
    """Why a fact is in doubt even if its evidence level is good: an unresolved relationship (e.g. the penny-drop names
    someone else) or an open flag (e.g. the account belongs to another vendor). The level alone must never reassure."""
    out: dict[str, list[str]] = defaultdict(list)
    for e, n in my_edges:
        if e.valid_to is None and e.status == "unresolved" and e.type in EDGE_FACT:
            out[EDGE_FACT[e.type]].append((e.note or f"Unresolved ({e.rule_id})") + (f" · rule {e.rule_id}" if e.rule_id and e.note else ""))
    for r in risks:
        if r.status == "open" and r.vendor_pk == vendor.id and r.rule_id in RULE_FACT:
            out[RULE_FACT[r.rule_id]].append(f"{r.title} · rule {r.rule_id}")
    return dict(out)


def connections(my_edges, shared_edges, vendors_by_pk: dict, risks) -> list[dict]:
    """my_edges: [(edge, node)] from this vendor. shared_edges: [(edge, src_vendor_node, node)] from OTHER vendors into the
    same nodes. Returns one entry per other vendor with what is shared, both sides' provenance, and whether it's actionable."""
    mine = {}
    for e, n in my_edges:
        if e.valid_to is None:
            mine.setdefault(n.id, (e, n))
    flagged = {r.related_vendor_pk for r in risks if r.related_vendor_pk}
    per = {}
    for e, vnode, n in shared_edges:
        if e.valid_to is not None or n.id not in mine or vnode.vendor_pk is None:
            continue
        other = vendors_by_pk.get(vnode.vendor_pk)
        if other is None:
            continue
        my_e, _ = mine[n.id]
        conflict = my_e.type == "IDENTITY_CONFLICT"
        kind = "PAN" if conflict else n.kind
        actionable = kind in ACTIONABLE
        item = dict(node=n, kind=kind, what=ACTIONABLE.get(kind) or CONTEXT.get(kind, f"Same {KIND_LABEL.get(n.kind, n.kind).lower()}"),
                    mine=my_e, theirs=e, actionable=actionable)
        c = per.setdefault(other.id, dict(vendor=other, shared=[], actionable=False, flagged=other.id in flagged))
        c["shared"].append(item)
        c["actionable"] = c["actionable"] or actionable
    return sorted(per.values(), key=lambda c: (not c["actionable"], not c["flagged"], c["vendor"].display_name))


def layout(vendor, my_edges, conns, width: int = 760, height: int = 420) -> dict:
    """Positions for a small relationship picture: this vendor in the middle, its identifiers around it, connected
    vendors further out next to what they share. Documents are only drawn when shared."""
    cx, cy = width / 2, height / 2
    shared_nodes = {i["node"].id for c in conns for i in c["shared"]}
    nodes = [(e, n) for e, n in my_edges if e.valid_to is None and (n.kind != "DOCUMENT" or n.id in shared_nodes)]
    seen, ring = set(), []
    for e, n in nodes:
        if n.id not in seen:
            seen.add(n.id)
            ring.append((e, n))
    pts, lines = {}, []
    k = max(len(ring), 1)
    for i, (e, n) in enumerate(ring):
        a = -math.pi / 2 + 2 * math.pi * i / k
        x, y = cx + 150 * math.cos(a), cy + 130 * math.sin(a)
        pts[n.id] = (x, y, a)
        lines.append(dict(x1=cx, y1=cy, x2=x, y2=y, status=e.status, type=e.type))
    outer = []
    for c in conns:
        for item in c["shared"][:1]:   # one placement per connected vendor, next to the first thing shared
            x, y, a = pts.get(item["node"].id, (cx, cy, 0))
            ox, oy = cx + 300 * math.cos(a), cy + 190 * math.sin(a)
            ox, oy = min(max(ox, 82), width - 82), min(max(oy, 24), height - 24)
            outer.append(dict(x=ox, y=oy, vendor=c["vendor"], actionable=c["actionable"]))
            for it in c["shared"]:
                px, py, _ = pts.get(it["node"].id, (x, y, a))
                lines.append(dict(x1=px, y1=py, x2=ox, y2=oy, status="inferred" if it["actionable"] else "context", type="shared"))
    return dict(w=width, h=height, cx=cx, cy=cy, ring=[dict(x=pts[n.id][0], y=pts[n.id][1], node=n, edge=e) for e, n in ring], outer=outer, lines=lines)


def next_actions(vendor, apps: list[dict], risks, facts: list[dict], rights_by_app: dict, evidence: dict) -> list[dict]:
    """What to do next, most urgent first. Deterministic; every item says why (rule, fact or relationship, with its
    evidence) and who may act. Never decides anything itself."""
    out = []
    open_risks = sorted([r for r in risks if r.status == "open" and r.vendor_pk == vendor.id], key=lambda r: (r.severity != "fraud", r.opened_at))
    flagged_apps = set()
    for r in open_risks:
        app = next((a for a in apps if a["app"].id == r.application_id), None)
        rights = rights_by_app.get(r.application_id, [])
        who = [p["emp"].name for p in rights if any(w in ("approve", "activate", "reject", "confirm the rejection") for w in p["can"])]
        flagged_apps.add(r.application_id)
        out.append(dict(priority="urgent" if r.severity == "fraud" else "high", title=RISK_TITLE.get(r.kind, r.title) + ".",
                        detail=r.reviewer_action, why=f"{r.title} (rule {r.rule_id}, check #{r.run_id})",
                        evidence=[evidence[i] for i in (r.evidence_item_id,) if i in evidence], who=who,
                        href=f"/runs/{app['latest'].id}#actions" if app and app.get("latest") else None, kind="risk"))
    for a in apps:
        app, run = a["app"], a.get("latest")
        if run is None or app.id in flagged_apps:
            continue
        rights = rights_by_app.get(app.id, [])
        if app.current_status == "APPROVED":
            who = [p["emp"].name for p in rights if "activate" in p["can"]]
            out.append(dict(priority="high", title=f"Activate the vendor ({app.ref} passed every check).", why=f"Decision on check #{run.id}: approved.",
                            detail="Activation adds it to the vendor master. Approval is not payment: bills still need a PO and goods receipt.",
                            evidence=[], who=who, href=f"/runs/{run.id}#actions", kind="decision"))
        elif app.current_status == "PENDING_REVIEW":
            who = [p["emp"].name for p in rights if p["can"]]
            out.append(dict(priority="high", title=f"Review {app.ref} and decide.", why=f"Check #{run.id} sent it to internal review.",
                            detail="Open the check for the reasons; approve, ask the vendor, or reject.", evidence=[], who=who,
                            href=f"/runs/{run.id}#actions", kind="decision"))
        elif app.current_status == "PENDING_VENDOR":
            out.append(dict(priority="normal", title=f"Waiting for the vendor to fix {app.ref}.", why=f"Check #{run.id} asked the vendor for changes.",
                            detail="Nothing to do until they resubmit through their link.", evidence=[], who=["the vendor"],
                            href=f"/runs/{run.id}", kind="wait"))
    cur = {f["fact"]: f["current"] for f in facts}
    bank = cur.get("BANK_ACCOUNT")
    if bank is not None and LEVEL_RANK.get(bank.level, 0) < 4 and vendor.status in ("active", "onboarding"):
        out.append(dict(priority="normal", title="Confirm the bank account at source to reach A4.",
                        why=f"Bank account is {bank.level} ({bank.source_label}).",
                        detail=("A penny-drop through a bank or KYB provider would confirm the account holder independently. In this build the "
                                "penny-drop is a SIMULATED SOURCE, which can never confer A4: this needs a real provider."),
                        evidence=[evidence[bank.evidence_item_id]] if bank.evidence_item_id in evidence else [], who=["Procurement, once a provider is connected"],
                        href=None, kind="evidence", needs_integration=True))
    weak = [f for f in facts if LEVEL_RANK.get(f["current"].level, 0) <= 1 and f["fact"] not in ("BANK_BRANCH",)]
    for f in weak:
        out.append(dict(priority="normal", title=f"Get better evidence for the {f['label'].lower()}.", why=f"{f['label']} is only {f['current'].level}.",
                        detail="Ask the vendor for the original document (a clear scan or the file downloaded from the issuing portal).",
                        evidence=[evidence[f['current'].evidence_item_id]] if f["current"].evidence_item_id in evidence else [],
                        who=["Procurement reviewer"], href=None, kind="evidence"))
    if not out:
        out.append(dict(priority="none", title="No action needed.", why="No open flags and no pending decisions.", detail="", evidence=[], who=[], href=None, kind="none"))
    return out


# --- supplier record: payment eligibility, invoices, documents --------------------------------------------------
def payment_eligibility(vendor, risks, facts) -> tuple[str, str]:
    """('eligible' | 'blocked' | 'not_yet', why). Eligibility to be paid at all; each invoice still needs its own approval."""
    open_fraud = [r for r in risks if r.status == "open" and r.vendor_pk == vendor.id and r.severity == "fraud"]
    if vendor.status != "active":
        return "not_yet", ("Not an active supplier yet: onboarding isn't complete." if vendor.status == "onboarding"
                           else "On record in the vendor master, not onboarded through this system." if vendor.status == "on_record"
                           else "Not an active supplier.")
    if open_fraud:
        return "blocked", f"Open flag: {open_fraud[0].title}. Resolve it before paying."
    bank = next((f["current"] for f in facts if f["fact"] == "BANK_ACCOUNT"), None)
    if bank is None:
        return "eligible", "Active supplier."
    return "eligible", f"Active supplier. Pays only into the account verified at onboarding ({bank.level}, {bank.source_label.lower()})."


def money_summary(bills, cases, money) -> dict:
    s = {"approved_unpaid": 0.0, "paid": 0.0, "on_hold": 0.0, "awaiting_review": 0.0, "active": 0}
    for b in bills:
        c = cases.get(b.id)
        amt = money(b.amount) or 0.0
        pay = c.payment_status if c else "none"
        if b.status == "approved":
            if pay == "paid":
                s["paid"] += amt
            elif pay == "on_hold":
                s["on_hold"] += amt
            else:
                s["approved_unpaid"] += amt
        elif b.status in ("for_review", "awaiting_confirmation", "ready_for_approval", "blocked", "failed"):
            s["awaiting_review"] += amt
        if b.status not in ("rejected", "draft") and pay != "paid":
            s["active"] += 1
    return s


def document_rows(docs, runs_by_id: dict, apps_by_id: dict, sizes: dict, reused: dict, evidence_by_sha: dict, observations) -> list[dict]:
    """Every document the vendor ever uploaded, newest first, with what it supports and whether it's still current."""
    latest_run_for_app = {}
    for r in runs_by_id.values():
        if r.application_id not in latest_run_for_app or r.id > latest_run_for_app[r.application_id]:
            latest_run_for_app[r.application_id] = r.id
    facts_by_ev = defaultdict(list)
    for o in observations:
        if o.evidence_item_id:
            facts_by_ev[o.evidence_item_id].append(o)
    out = []
    for d in sorted(docs, key=lambda d: (d.run_id, d.id), reverse=True):
        run = runs_by_id.get(d.run_id)
        app = apps_by_id.get(run.application_id) if run else None
        rd, au = d.read or {}, d.authenticity or {}
        if run and latest_run_for_app.get(run.application_id) != run.id:
            status = "superseded"
        elif reused.get(d.sha256):
            status = "reused"
        elif not rd.get("doc_type"):
            status = "unreadable"
        else:
            status = "current"
        evs = evidence_by_sha.get((d.sha256, d.run_id), [])
        supports = sorted({FACT_LABEL.get(o.fact, o.fact) for e in evs for o in facts_by_ev.get(e.id, [])})
        sig = au.get("signature") or {}
        out.append(dict(doc=d, run=run, app=app, size=sizes.get(d.sha256), status=status, read=rd, auth=au, supports=supports,
                        reused_by=reused.get(d.sha256, []), signed=bool(sig.get("present") and sig.get("intact") and sig.get("valid")),
                        issue_date=next((f.get("value") for f in rd.get("fields", []) if f.get("name") in ("issue_date", "date_on_card") and f.get("value")), "")))
    return out
