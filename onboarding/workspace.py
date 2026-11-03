"""Workspace pages: Applications, Review queue, Relationships."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from onboarding import access
from onboarding import bills as B
from onboarding.ap.models import ChangeRequest, InvoiceCase
from onboarding.intel.models import GraphEdge, GraphNode, RiskEvent, Vendor, VendorApplication
from onboarding.models import Application, Bill, HumanAction, Invite, Run, VendorBill, VendorMaster
from onboarding.pipeline import read_sessions
from onboarding.web import _actor, _all, _employees, _reads, _rows, _todo, render

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


@router.get("/applications", response_class=HTMLResponse)
async def applications(request: Request, status: str = "", q: str = ""):
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        rows = await _apps(s, actor)
        emps = {e.id: e for e in await _employees(s)}
        if status:
            rows = [x for x in rows if x["app"].current_status == status]
        if q:
            rows = [x for x in rows if q.lower() in f"{x['app'].ref} {x['app'].legal_name} {(x['run'].form or {}).get('gstin', '') if x['run'] else ''}".lower()]
        return await render(request, s, "ws_applications.html", rows=rows, emps=emps, status=status, q=q, full=access.full_view(actor))


@router.get("/review", response_class=HTMLResponse)
async def review_queue(request: Request):
    """Everything waiting on a person, most urgent first: vendor decisions, invoices and change requests."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        full = access.full_view(actor)
        emps = {e.id: e for e in await _employees(s)}
        r = await _reads(rows=_rows(select(Run, Application).join(Application, Application.id == Run.application_id).order_by(Run.id.desc())),
                         invites=_all(select(Invite)), bills=_all(select(Bill)), acted=_rows(select(HumanAction.run_id, HumanAction.action)),
                         vbills=_all(select(VendorBill).order_by(VendorBill.id.desc())), cases=_all(select(InvoiceCase)),
                         changes=_all(select(ChangeRequest).where(ChangeRequest.status == "submitted").order_by(ChangeRequest.id)),
                         masters=_all(select(VendorMaster)), vendors=_all(select(Vendor)))
        invites, bills = {i.id: i for i in r["invites"]}, {b.application_id: b for b in r["bills"]}
        runs = [dict(run=run, app=app, bill=bills.get(app.id), fraud=(run.summary or {}).get("fraud"))
                for run, app in r["rows"] if full or access.owns_application(actor, invites.get(app.invite_id), bills.get(app.id))]
        apps_todo = _todo(actor, runs, invites, emps, r["acted"], [])
        cases = {c.bill_id: c for c in r["cases"]}
        names = {m.vendor_id: m.legal_name for m in r["masters"]}
        vend = {v.erp_vendor_id: v for v in r["vendors"] if v.erp_vendor_id}
        invoices = []
        for b in r["vbills"]:
            if not (full or access.can_open_bill(actor, b)):
                continue
            c = cases.get(b.id)
            st = B.invoice_status(b, c)
            engaged = emps.get(b.engaged_employee_id)
            allowed = {k: v for k, v in B.allowed_bill_actions(b, actor, engaged, c).items() if not v["blocked"]}
            if st in ("Paid", "Rejected", "Draft", "Being checked", "Needs vendor information") or not allowed:
                continue
            na = B.next_action(b, c)
            invoices.append(dict(b=b, status=st, next=na, vendor=vend.get(b.vendor_id), name=names.get(b.vendor_id, b.vendor_id), urgent=st == "Blocked for investigation"))
        changes = [dict(cr=c, name=names.get(c.erp_vendor_id, c.erp_vendor_id), vendor=vend.get(c.erp_vendor_id),
                        mine=(actor and ((c.kind == "bank_account" and actor.role == "checker") or (c.kind != "bank_account" and full))))
                   for c in r["changes"] if full]
        return await render(request, s, "ws_review.html", apps_todo=apps_todo, invoices=invoices, changes=changes, full=full, B=B)


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
