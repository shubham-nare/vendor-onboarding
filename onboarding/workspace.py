"""Workspace pages: Applications, Review queue, Relationships."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from onboarding import access
from onboarding.ap.models import ChangeRequest
from onboarding.intel.models import GraphEdge, GraphNode, RiskEvent, Vendor, VendorApplication
from onboarding.models import Application, Bill, Document, Invite, Run, VendorMaster
from onboarding.pipeline import read_sessions
from onboarding.web import _actor, _all, _employees, _reads, _rows, render

router = APIRouter()


async def _apps(s, actor):
    full = access.full_view(actor)
    latest = select(func.max(Run.id)).group_by(Run.application_id)
    r = await _reads(apps=_all(select(Application).order_by(Application.id.desc())), runs=_all(select(Run).where(Run.id.in_(latest))),
                     invites=_all(select(Invite)), bills=_all(select(Bill)),
                     links=_rows(select(VendorApplication.application_id, Vendor).join(Vendor, Vendor.id == VendorApplication.vendor_pk)))
    runs = {x.application_id: x for x in r["runs"]}
    invites, bills, vendors = {i.id: i for i in r["invites"]}, {b.application_id: b for b in r["bills"]}, dict(r["links"])
    out = []
    for a in r["apps"]:
        inv, bill = invites.get(a.invite_id), bills.get(a.id)
        if not full and not access.owns_application(actor, inv, bill):
            continue
        out.append(dict(app=a, run=runs.get(a.id), invite=inv, bill=bill, vendor=vendors.get(a.id)))
    return out


@router.get("/applications")
async def applications():
    """Drawn by the browser app from GET /api/v1/applications."""
    from onboarding.appshell import app_shell
    return app_shell()


@router.get("/review")
async def review_queue():
    """Drawn by the browser app from GET /api/v1/review."""
    from onboarding.appshell import app_shell
    return app_shell()


@router.get("/relationships", response_class=HTMLResponse)
async def relationships(request: Request):
    """Risk flags raised by the onboarding rules, and every bank account or document shared between vendors."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        access.require_full(actor, "Relationship intelligence")
        src, dst = aliased(GraphNode), aliased(GraphNode)
        r = await _reads(risks=_all(select(RiskEvent).order_by(RiskEvent.opened_at.desc())), vendors=_all(select(Vendor)),
                         edges=_rows(select(GraphEdge, src, dst).join(src, src.id == GraphEdge.src_id).join(dst, dst.id == GraphEdge.dst_id)
                                     .where(src.kind == "VENDOR", dst.kind.in_(("BANK_ACCOUNT", "DOCUMENT", "ADDRESS", "EMAIL", "PHONE")), GraphEdge.valid_to.is_(None))))
        vendors = {v.id: v for v in r["vendors"]}
        by_node: dict[int, dict] = {}
        for e, sv, n in r["edges"]:
            d = by_node.setdefault(n.id, dict(node=n, members={}))
            d["members"][sv.vendor_pk] = e
        shared = [d for d in by_node.values() if len(d["members"]) > 1]
        shared.sort(key=lambda d: (d["node"].kind not in ("BANK_ACCOUNT", "DOCUMENT"), d["node"].kind))
        risks = sorted(r["risks"], key=lambda x: (x.status != "open", x.severity != "fraud"))
        return await render(request, s, "ws_relationships.html", risks=risks, shared=shared, vendors=vendors)


@router.get("/documents", response_class=HTMLResponse)
async def documents(request: Request, q: str = "", kind: str = "", show: str = ""):
    """Every file vendors uploaded, newest first; documents from older submissions are marked replaced."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        access.require_full(actor, "Documents")
        latest = select(func.max(Run.id)).group_by(Run.application_id)
        r = await _reads(rows=_rows(select(Document, Run, Application).join(Run, Run.id == Document.run_id).join(Application, Application.id == Run.application_id)
                                    .order_by(Document.id.desc())),
                         latest=_rows(latest),
                         links=_rows(select(VendorApplication.application_id, Vendor).join(Vendor, Vendor.id == VendorApplication.vendor_pk)))
        newest = {x for (x,) in r["latest"]}
        vendors = dict(r["links"])
        rows = [dict(doc=d, run=run, app=app, vendor=vendors.get(app.id), current=run.id in newest) for d, run, app in r["rows"]]
        kinds = sorted({x["doc"].slot for x in rows})
        if not show:
            rows = [x for x in rows if x["current"]]
        if kind:
            rows = [x for x in rows if x["doc"].slot == kind]
        if q:
            rows = [x for x in rows if q.lower() in f"{x['app'].legal_name} {x['doc'].filename} {x['app'].ref}".lower()]
        return await render(request, s, "ws_documents.html", rows=rows, kinds=kinds, q=q, kind=kind, show=show)

