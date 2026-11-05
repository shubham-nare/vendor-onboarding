"""Vendor 360 as JSON: identity, proof, relationships, risk, invoices, documents, decisions and what to do next.
Everything the page needs is worked out here (labels, colours, map positions); the browser only lays it out.
Requesters get only what they asked for: no identifiers, facts, relationships, risk or documents."""

from __future__ import annotations

from fastapi import APIRouter, Request

from onboarding.api.common import staff_or_401, when
from onboarding.intel import vendor360 as V360
from onboarding.pipeline import read_sessions
from onboarding.rules import money

router = APIRouter()
APP_CARD = {"PENDING_REVIEW": "Under review", "PENDING_VENDOR": "Waiting on the vendor", "IN_PROGRESS": "Being checked", "APPROVED": "Approved",
            "ACTIVE": "Approved and activated", "REJECTED": "Rejected"}
PAY_LABEL = {"eligible": "Eligible", "blocked": "Blocked from payment", "not_yet": "Not eligible yet"}


def _edge(e, evidence: dict) -> dict:
    ev = evidence.get(e.evidence_item_id)
    return {"type": V360.EDGE_LABEL.get(e.type, e.type), "status": e.status, "basis": e.basis, "basis_label": V360.BASIS_LABEL.get(e.basis, e.basis),
            "rule": e.rule_id, "evidence": {"id": ev.id, "label": ev.source_label} if ev else None, "note": e.note,
            "since": when(e.valid_from), "until": when(e.valid_to) if e.valid_to else None,
            "checks": (f"#{e.first_run_id}" + (f"–#{e.last_run_id}" if e.last_run_id and e.last_run_id != e.first_run_id else "")) if e.first_run_id else None}


def _ref(v) -> dict | None:
    return {"id": v.vendor_id, "name": v.display_name, "erp_id": v.erp_vendor_id} if v else None


def build(d: dict) -> dict:
    from onboarding import bills as BL
    from onboarding.rules import SLOT_TITLE
    from onboarding.validators import BUSINESS_TYPES
    from onboarding.web import LEVEL_NAMES, ROLE_LABEL, STATUS_LABEL
    v, full, evidence = d["v"], d["full"], d["evidence"]
    ev = lambda i: {"id": evidence[i].id, "label": evidence[i].source_label} if i in evidence else None  # noqa: E731
    open_flags = [r for r in d["risks"] if r.status == "open" and r.vendor_pk == v.id]
    out = {
        "id": v.vendor_id, "name": v.display_name, "status": v.status, "status_label": V360.STATUS_TEXT.get(v.status, v.status), "erp_id": v.erp_vendor_id,
        "entity_type": BUSINESS_TYPES.get(v.entity_type, v.entity_type) if v.entity_type else None, "country": "India" if v.country == "IN" else v.country,
        "open_flags": len(open_flags), "full": full, "origin": v.origin,
        "next": [{"priority": a["priority"], "title": a["title"], "detail": a["detail"] if a.get("detail") and a["detail"] != a["title"] else "",
                  "why": a["why"], "evidence": [ev(e.id) for e in a.get("evidence", []) if ev(e.id)], "who": a.get("who") or [],
                  "nobody": not a.get("who") and a.get("kind") in ("risk", "decision"), "needs_integration": bool(a.get("needs_integration")),
                  "href": a.get("href")} for a in d["nba"]],
    }
    # summary cards
    if full:
        latest = d["apps"][-1] if d["apps"] else None
        active = bool(v.erp_vendor_id and v.status in ("active", "on_record"))
        la = latest["app"].current_status if latest else ""
        la_open = bool(latest and la not in ("APPROVED", "ACTIVE", "REJECTED"))
        pay = d["pay"]
        out["cards"] = [
            {"label": "Supplier master", "value": f"Active · {v.erp_vendor_id}" if active else "Not active yet",
             "note": "activated after approval" if v.origin == "application" and v.erp_vendor_id else ("existing record" if v.erp_vendor_id else "activation follows approval"),
             "tone": "green" if active else "slate"},
            {"label": "Payment eligibility", "value": PAY_LABEL.get(pay[0], "—"), "note": pay[1], "tone": {"eligible": "green", "blocked": "red"}.get(pay[0], "slate")},
            {"label": "Latest application", "value": APP_CARD.get(la, STATUS_LABEL.get(la, la)) if latest else "None",
             "note": (latest["app"].ref + (" · possible duplicate record: this supplier is already active" if active and la_open else "")) if latest else "known from the vendor master",
             "tone": ("amber" if la_open else ("red" if la == "REJECTED" else "slate")) if latest else "slate"},
            {"label": "Risk", "value": f"{len(open_flags)} open flag{'s' if len(open_flags) != 1 else ''}" if open_flags else "No open flags",
             "note": open_flags[0].title[:60] if open_flags else "from the onboarding rules", "tone": "red" if any(r.severity == "fraud" for r in open_flags) else ("amber" if open_flags else "green")},
        ]
    # invoices
    out["invoices"] = {
        "show": bool(d["invoices"] or v.erp_vendor_id),
        "money": {"approved_unpaid": d["msum"]["approved_unpaid"], "on_hold": d["msum"]["on_hold"], "paid": d["msum"]["paid"]} if full else None,
        "rows": [], "registration_bills": sum(1 for x in d["documents"] if x["doc"].slot == "invoice"),
        "orders": [{"id": po.id, "number": po.po_number} for po in d["pos"]],
    }
    for x in d["invoices"]:
        b, c = x["b"], x["case"]
        payment = None
        if c and c.payment_status == "paid":
            payment = {"kind": "paid", "text": f"{c.payment_reference} · " + when(c.paid_at)["label"]}
        elif c and c.payment_status == "on_hold":
            payment = {"kind": "hold", "text": c.hold_reason}
        elif c and c.payment_status == "in_progress":
            payment = {"kind": "released", "text": "released " + when(c.released_at)["label"]}
        out["invoices"]["rows"].append({"id": b.id, "number": b.invoice_number or b.ref, "ref": b.ref, "date": b.invoice_date or "", "po": b.po_number,
                                        "amount": float(money(b.amount)) if b.amount else None, "status": x["status"],
                                        "tone": BL.INVOICE_TONE.get(x["status"], "slate") if full else "slate", "payment": payment})
    if full:
        lf = ((d["apps"][-1]["latest"].form if d["apps"] and d["apps"][-1]["latest"] else {}) or {})
        contact = lambda p: " · ".join(x for x in (lf.get(f"{p}contact_name"), lf.get(f"{p}contact_email"), lf.get(f"{p}contact_phone")) if x)  # noqa: E731
        out["identity"] = {"identifiers": [{"kind": V360.KIND_LABEL.get(i.kind, i.kind), "value": d["full_bank"].get(i.id) or i.display,
                                            "full_bank": bool(d["full_bank"].get(i.id)), "previous": i.status == "previous", "since": when(i.first_seen_at)}
                                           for i in d["idents"]],
                           "contact": contact(""), "alt_contact": contact("alt_")}
        out["facts"] = [{"label": f["label"], "value": f["current"].value_display, "level": f["current"].level,
                         "level_name": LEVEL_NAMES.get(f["current"].level, ""),
                         "basis": f["current"].basis, "basis_label": V360.BASIS_LABEL.get(f["current"].basis, f["current"].basis),
                         "source": f["current"].source_label, "where": f"check #{f['current'].run_id}" if f["current"].run_id else "change request",
                         "evidence": ev(f["current"].evidence_item_id), "note": f["current"].note,
                         "recheck": f["current"].valid_until.strftime("%d %b %Y") if f["current"].valid_until else None,
                         "doubts": d["doubts"].get(f["fact"], []), "changed": bool(f.get("changed")),
                         "history": [{"value": o.value_display, "level": o.level, "basis": V360.BASIS_LABEL.get(o.basis, o.basis),
                                      "where": f"check #{o.run_id}" if o.run_id else "change request", "when": when(o.observed_at)["label"]} for o in f["history"]]}
                        for f in d["facts"]]
        lay = d["lay"]
        out["map"] = None if not (lay and lay.get("ring")) else {
            "w": lay["w"], "h": lay["h"], "cx": lay["cx"], "cy": lay["cy"],
            "lines": [{"x1": round(ln["x1"], 1), "y1": round(ln["y1"], 1), "x2": round(ln["x2"], 1), "y2": round(ln["y2"], 1), "status": ln["status"]} for ln in lay["lines"]],
            "ring": [{"x": round(n["x"], 1), "y": round(n["y"], 1), "kind": V360.KIND_LABEL.get(n["node"].kind, n["node"].kind),
                      "value": (n["node"].display or "")[:22], "status": n["edge"].status} for n in lay["ring"]],
            "outer": [{"x": round(o["x"], 1), "y": round(o["y"], 1), "vendor": _ref(o["vendor"]), "actionable": bool(o["actionable"])} for o in lay["outer"]]}
        out["connections"] = [{"vendor": _ref(c["vendor"]), "flagged": bool(c["flagged"]), "actionable": bool(c["actionable"]),
                               "shared": [{"what": i["what"], "value": i["node"].display, "actionable": bool(i["actionable"]),
                                           "mine": _edge(i["mine"], evidence), "theirs": _edge(i["theirs"], evidence)} for i in c["shared"]]}
                              for c in d["conns"]]
        out["edges"] = [{"kind": V360.KIND_LABEL.get(n.kind, n.kind), "value": n.display, **_edge(e, evidence), "ended": bool(e.valid_to)} for e, n in d["my_edges"]]
        out["risks"] = []
        for r in d["risks"]:
            mine = r.vendor_pk == v.id
            other = d["vendors_by_pk"].get(r.related_vendor_pk if mine else r.vendor_pk)
            out["risks"].append({"status": r.status, "fraud": r.severity == "fraud", "title": r.title, "mine": mine, "other": _ref(other),
                                 "rule": r.rule_id, "run_id": r.run_id, "opened": when(r.opened_at)["label"], "evidence": ev(r.evidence_item_id) if mine else None,
                                 "action": r.reviewer_action if r.status == "open" else None, "resolution": r.resolution if r.status != "open" else None})
        out["documents"] = [{"title": "Onboarding bill" if x["doc"].slot == "invoice" else SLOT_TITLE.get(x["doc"].slot, x["doc"].slot),
                             "registration_bill": x["doc"].slot == "invoice", "status": x["status"], "reused_by": x.get("reused_by") or [],
                             "read_as": (x["read"].get("doc_type") or "unreadable").replace("_", " ").lower(),
                             "form": (x["read"].get("document_form") or "").replace("_", " ").lower(),
                             "saved_reading": x["read"].get("origin") in ("cache", "cache-fallback"),
                             "proof": {"level": x["auth"].get("level"), "name": LEVEL_NAMES.get(x["auth"].get("level"), "")} if x["auth"].get("level") else None,
                             "signed": bool(x.get("signed")), "known_file": bool(x["auth"].get("specimen")), "supports": x.get("supports") or [],
                             "file": {"name": x["doc"].filename, "href": f"/files/{x['doc'].sha256}", "size_kb": round(x["size"] / 1024) if x.get("size") else None,
                                      "fingerprint": x["doc"].sha256[:12]}} for x in d["documents"]]
        out["evidence"] = [{"id": e.id, "basis": e.basis, "basis_label": V360.BASIS_LABEL.get(e.basis, e.basis), "label": e.source_label,
                            "file": {"href": f"/files/{e.content_sha256}", "fingerprint": e.content_sha256[:12]} if e.kind == "document" and e.content_sha256 else None,
                            "captured": when(e.captured_at)["label"]} for e in sorted(d["evidence"].values(), key=lambda e: e.id)]
    out["applications"] = [{"ref": a["app"].ref, "status": a["app"].current_status,
                            "came_in": (f"requested by {a['sponsor'].name if a['sponsor'] else 'an employee'}" if a["invite"] else ("bill-first registration" if a["bill"] else "unsolicited")),
                            "created": when(a["app"].created_at)["label"],
                            "checks": [{"run_id": run.id, "status": STATUS_LABEL.get(run.status, run.status) if run.status else None,
                                        "replay": (d["snaps"][run.id][0] if run.id in d["snaps"] else None) if full else None} for run in a["runs"]]}
                           for a in d["apps"] if full or a["owned"]]
    out["decisions"] = [{"when": when(a.at)["label"], "who": e.name, "role": ROLE_LABEL.get(e.role, e.role), "action": a.action.replace("_", " "),
                         "comment": a.comment, "run_id": a.run_id} for a, e in d["actions"]]
    return out


@router.get("/vendors/{vendor_key}")
async def vendor_profile(request: Request, vendor_key: str):
    """Vendor 360. Requesters see only vendors they asked for, without identifiers, facts, relationships, risk or documents."""
    from onboarding.web import vendor_profile as profile_data
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    return build(await profile_data(request, vendor_key))
