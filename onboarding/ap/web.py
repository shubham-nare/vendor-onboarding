"""Internal pages for accounts payable: Invoice verification, Purchase orders (list, create, detail, record delivery)
and the Decisions & audit log."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from onboarding import access
from onboarding import bills as B
from onboarding.ap.audit import record
from onboarding.ap.models import AuditEvent, GoodsReceipt, InvoiceCase, POLine, PurchaseOrder, ReceiptLine
from onboarding.intel.crypto import lookup_key, mask
from onboarding.intel.models import Vendor
from onboarding.models import Employee, VendorBill, VendorMaster, now
from onboarding.pipeline import read_sessions, sessions
from onboarding.rules import money
from onboarding.web import ROLE_LABEL, _actor, _all, _employees, _reads, render

router = APIRouter()
STATUS_ORDER = ["Blocked for investigation", "Needs internal review", "Matched and ready for approval", "Approved for payment", "Payment on hold",
                "Payment in progress", "Needs vendor information", "Being checked", "Draft", "Paid", "Rejected"]


def _po_total(lines) -> float:
    return round(sum(l.quantity * l.unit_price * (1 + l.tax_rate / 100) for l in lines), 2)


@router.get("/invoices", response_class=HTMLResponse)
async def invoices(request: Request, status: str = "", q: str = ""):
    """Every invoice from active vendors, newest first, with its status, the amount and the specific next step."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        full = access.full_view(actor)
        r = await _reads(bills=_all(select(VendorBill).order_by(VendorBill.id.desc())), cases=_all(select(InvoiceCase)),
                         masters=_all(select(VendorMaster)), vendors=_all(select(Vendor)), pos=_all(select(PurchaseOrder)))
        cases = {c.bill_id: c for c in r["cases"]}
        vm = {m.vendor_id: m for m in r["masters"]}
        vend = {v.erp_vendor_id: v for v in r["vendors"] if v.erp_vendor_id}
        rows = []
        for b in r["bills"]:
            if not full and not access.can_open_bill(actor, b):
                continue
            c = cases.get(b.id)
            st = B.invoice_status(b, c)
            name = vm[b.vendor_id].legal_name if b.vendor_id in vm else b.vendor_id
            if q and q.lower() not in f"{name} {b.invoice_number} {b.ref} {b.po_number} {b.vendor_id}".lower():
                continue
            rows.append(dict(b=b, case=c, status=st, vendor=vend.get(b.vendor_id), name=name, amount=money(b.amount) or 0.0, next=B.next_action(b, c)))
        counts = defaultdict(int)
        sums = defaultdict(float)
        for x in rows:
            counts[x["status"]] += 1
            sums[x["status"]] += x["amount"]
        if status:
            rows = [x for x in rows if x["status"] == status]
        rows.sort(key=lambda x: (STATUS_ORDER.index(x["status"]) if x["status"] in STATUS_ORDER else 99, -x["b"].id))
        return await render(request, s, "ap_invoices.html", rows=rows, counts=counts, sums=sums, status=status, q=q, full=full,
                            STATUS_ORDER=STATUS_ORDER, B=B)


async def _po_bundle(s, po_ids=None):
    pos = (await s.execute(select(PurchaseOrder).order_by(PurchaseOrder.id.desc()))).scalars().all()
    if po_ids is not None:
        pos = [p for p in pos if p.id in po_ids]
    ids = [p.id for p in pos] or [-1]
    lines = (await s.execute(select(POLine).where(POLine.po_id.in_(ids)).order_by(POLine.line_no))).scalars().all()
    receipts = (await s.execute(select(GoodsReceipt).where(GoodsReceipt.po_id.in_(ids)).order_by(GoodsReceipt.id))).scalars().all()
    rlines = (await s.execute(select(ReceiptLine).where(ReceiptLine.receipt_id.in_([g.id for g in receipts] or [-1])))).scalars().all()
    cases = (await s.execute(select(InvoiceCase).where(InvoiceCase.po_id.in_(ids)))).scalars().all()
    bills = {b.id: b for b in (await s.execute(select(VendorBill).where(VendorBill.id.in_([c.bill_id for c in cases] or [-1])))).scalars()}
    by_po = {p.id: dict(po=p, lines=[], receipts=[], received=defaultdict(float), invoices=[]) for p in pos}
    for l in lines:
        by_po[l.po_id]["lines"].append(l)
    rec_po = {}
    for g in receipts:
        by_po[g.po_id]["receipts"].append(g)
        rec_po[g.id] = g.po_id
    for rl in rlines:
        by_po[rec_po[rl.receipt_id]]["received"][rl.po_line_id] += rl.quantity
    for c in cases:
        if c.bill_id in bills:
            by_po[c.po_id]["invoices"].append((bills[c.bill_id], c))
    for d in by_po.values():
        d["total"] = _po_total(d["lines"])
        d["delivered_value"] = round(sum(min(d["received"][l.id], l.quantity) * l.unit_price * (1 + l.tax_rate / 100) for l in d["lines"]), 2)
        d["invoiced"] = round(sum(money(b.amount) or 0 for b, c in d["invoices"] if b.status not in ("rejected",)), 2)
        d["paid"] = round(sum(c.paid_amount or 0 for b, c in d["invoices"] if c.payment_status == "paid"), 2)
    return [by_po[p.id] for p in pos]


@router.get("/purchase-orders", response_class=HTMLResponse)
async def purchase_orders(request: Request, q: str = ""):
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        access.require_full(actor, "Purchase orders")
        rows = await _po_bundle(s)
        if q:
            rows = [d for d in rows if q.lower() in f"{d['po'].po_number} {d['po'].vendor_name} {d['po'].cost_centre}".lower()]
        emps = {e.id: e for e in await _employees(s)}
        return await render(request, s, "ap_pos.html", rows=rows, emps=emps, q=q)


@router.get("/purchase-orders/new", response_class=HTMLResponse)
async def po_new(request: Request):
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        access.require_full(actor, "Purchase orders")
        masters = (await s.execute(select(VendorMaster).where(VendorMaster.status == "Active").order_by(VendorMaster.legal_name))).scalars().all()
        return await render(request, s, "ap_po_new.html", masters=masters, emps=await _employees(s), error="")


@router.post("/purchase-orders/new")
async def po_create(request: Request):
    form = await request.form()
    async with sessions()() as s:
        actor = await _actor(request, s)
        access.require_full(actor, "Purchase orders")
        number = str(form.get("po_number") or "").strip().upper()
        vm = (await s.execute(select(VendorMaster).where(VendorMaster.vendor_id == str(form.get("vendor_id") or "")))).scalar_one_or_none()
        lines = []
        for i in range(1, 11):
            desc = str(form.get(f"desc_{i}") or "").strip()
            if not desc:
                continue
            try:
                qty, price, tax = float(form.get(f"qty_{i}") or 0), float(str(form.get(f"price_{i}") or 0).replace(",", "")), float(form.get(f"tax_{i}") or 18)
            except ValueError:
                raise HTTPException(400, f"Line {i}: quantity, price and GST must be numbers.")
            if qty <= 0 or price < 0:
                raise HTTPException(400, f"Line {i}: quantity must be above zero and the price can't be negative.")
            lines.append((desc, qty, str(form.get(f"unit_{i}") or "").strip(), price, tax))
        if not number or not vm or not lines:
            raise HTTPException(400, "A purchase order needs a number, an active vendor and at least one line.")
        if (await s.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == number))).scalar_one_or_none():
            raise HTTPException(409, f"Purchase order {number} already exists.")
        vendor_pk = (await s.execute(select(Vendor.id).where(Vendor.erp_vendor_id == vm.vendor_id))).scalar()
        def emp_id(key):
            v = str(form.get(key) or "")
            return int(v) if v.isdigit() else None
        po = PurchaseOrder(po_number=number, vendor_gstin=vm.gstin, vendor_name=vm.legal_name, vendor_pk=vendor_pk, cost_centre=str(form.get("cost_centre") or "").strip(),
                           requester_id=emp_id("requester_id"), approver_id=emp_id("approver_id"), service_from=str(form.get("service_from") or ""),
                           service_to=str(form.get("service_to") or ""), payee_account_key=lookup_key("BANK_ACCOUNT", vm.account),
                           payee_account_display=mask("BANK_ACCOUNT", vm.account), payee_ifsc=vm.ifsc, source="manual", created_by=actor.id)
        s.add(po)
        await s.flush()
        for n, (desc, qty, unit, price, tax) in enumerate(lines, 1):
            s.add(POLine(po_id=po.id, line_no=n, description=desc, quantity=qty, unit=unit, unit_price=price, tax_rate=tax))
        record(s, entity="purchase_order", entity_id=po.id, entity_label=number, action="created", actor=actor,
               actor_label=f"{actor.name} ({ROLE_LABEL.get(actor.role, actor.role)})", vendor_pk=vendor_pk,
               detail={"vendor": vm.vendor_id, "lines": len(lines)})
        await s.commit()
        pid = po.id
    return RedirectResponse(f"/purchase-orders/{pid}", status_code=303)


@router.get("/purchase-orders/{po_id}", response_class=HTMLResponse)
async def po_detail(request: Request, po_id: int):
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        found = await _po_bundle(s, {po_id})
        if not found:
            raise HTTPException(404, "No such purchase order")
        d = found[0]
        if not access.full_view(actor) and not (actor and actor.id == d["po"].requester_id):
            raise access.forbid("This purchase order")
        vendor = await s.get(Vendor, d["po"].vendor_pk) if d["po"].vendor_pk else (await s.execute(select(Vendor).join(VendorMaster, VendorMaster.vendor_id == Vendor.erp_vendor_id)
                                                                                                     .where(VendorMaster.gstin == d["po"].vendor_gstin))).scalars().first()
        po = d["po"]
        audit = [e for e in (await s.execute(select(AuditEvent).where(AuditEvent.entity.in_(("purchase_order", "receipt"))).order_by(AuditEvent.id))).scalars()
                 if (e.entity == "purchase_order" and e.entity_id == str(po_id)) or (e.entity == "receipt" and e.entity_label.endswith(po.po_number))]
        emps = {e.id: e for e in await _employees(s)}
        return await render(request, s, "ap_po.html", d=d, po=d["po"], vendor=vendor, emps=emps, audit=audit, B=B)


@router.post("/purchase-orders/{po_id}/receipts")
async def po_receipt(request: Request, po_id: int):
    """Record what was delivered (goods receipt) or performed (service confirmation)."""
    form = await request.form()
    async with sessions()() as s:
        actor = await _actor(request, s)
        if not actor:
            raise HTTPException(403, "Log in first.")
        po = await s.get(PurchaseOrder, po_id)
        if not po:
            raise HTTPException(404, "No such purchase order")
        if not access.full_view(actor) and actor.id != po.requester_id:
            raise HTTPException(403, "Only the requester on this order, Procurement or Finance can record a delivery.")
        lines = (await s.execute(select(POLine).where(POLine.po_id == po_id))).scalars().all()
        qtys = []
        for l in lines:
            try:
                q = float(form.get(f"qty_{l.id}") or 0)
            except ValueError:
                raise HTTPException(400, "Quantities must be numbers.")
            if q < 0:
                raise HTTPException(400, "Quantities can't be negative.")
            qtys.append((l, q))
        if not any(q for _, q in qtys):
            raise HTTPException(400, "Enter the quantity delivered on at least one line.")
        n = len((await s.execute(select(GoodsReceipt.id))).all()) + 1
        g = GoodsReceipt(po_id=po_id, number=f"{'GRN' if form.get('kind') == 'goods' else 'SC'}-{now().year}-{n:04d}", kind="goods" if form.get("kind") == "goods" else "service",
                         received_on=str(form.get("received_on") or now().date().isoformat()), confirmed_by=actor.id, note=str(form.get("note") or "").strip())
        s.add(g)
        await s.flush()
        for l, q in qtys:
            if q:
                s.add(ReceiptLine(receipt_id=g.id, po_line_id=l.id, quantity=q))
        record(s, entity="receipt", entity_id=g.id, entity_label=f"{g.number} on {po.po_number}", action="delivery_recorded", actor=actor,
               actor_label=f"{actor.name} ({ROLE_LABEL.get(actor.role, actor.role)})", vendor_pk=po.vendor_pk,
               detail={"po": po.po_number, "quantities": {l.description[:40]: q for l, q in qtys if q}})
        await s.commit()
    return RedirectResponse(f"/purchase-orders/{po_id}", status_code=303)


@router.get("/audit", response_class=HTMLResponse)
async def audit_log(request: Request, entity: str = ""):
    """Decisions and audit history: every material action, newest first."""
    from onboarding.models import HumanAction, Run, Application
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        access.require_full(actor, "The audit log")
        q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(300)
        if entity:
            q = q.where(AuditEvent.entity == entity)
        events = (await s.execute(q)).scalars().all()
        decisions = (await s.execute(select(HumanAction, Employee, Application).join(Employee, Employee.id == HumanAction.employee_id)
                                     .join(Run, Run.id == HumanAction.run_id).join(Application, Application.id == Run.application_id)
                                     .order_by(HumanAction.id.desc()).limit(200))).all() if entity in ("", "application") else []
        vendors = {v.id: v for v in (await s.execute(select(Vendor))).scalars()}
        rows = [dict(at=e.at, who=e.actor_label, entity=e.entity, label=e.entity_label, action=e.action, reason=e.reason, override=e.override,
                     vendor=vendors.get(e.vendor_pk), href=f"/bills/{e.entity_id}" if e.entity == "invoice" else "") for e in events]
        for a, emp, app in decisions:
            rows.append(dict(at=a.at, who=f"{emp.name} ({ROLE_LABEL.get(emp.role, emp.role)})", entity="application", label=app.ref, action=a.action,
                             reason=a.comment, override=a.action in ("override_reject", "review_approve"), vendor=None, href=f"/runs/{a.run_id}"))
        rows.sort(key=lambda x: x["at"].replace(tzinfo=None) if x["at"] else x["at"], reverse=True)
        return await render(request, s, "ap_audit.html", rows=rows, entity=entity, labels=B.BILL_ACTION_LABEL)


@router.post("/change-requests/{cr_id}/decide")
async def decide_change(request: Request, cr_id: int):
    """A bank-account change needs its own review by Finance (not the vendor's word, not the old account's status):
    approve only after confirming it independently, e.g. a call to a number already on record."""
    import json as _json
    from onboarding.ap.models import ChangeRequest
    from onboarding.intel.crypto import decrypt
    from onboarding.intel.project import _identifier
    form = await request.form()
    decision, note = str(form.get("decision") or ""), str(form.get("note") or "").strip()
    async with sessions()() as s:
        actor = await _actor(request, s)
        cr = await s.get(ChangeRequest, cr_id)
        if not cr:
            raise HTTPException(404, "No such change request")
        if not actor or (cr.kind == "bank_account" and actor.role != "checker") or (cr.kind != "bank_account" and not access.full_view(actor)):
            raise HTTPException(403, "Bank-account changes are reviewed by the Finance controller; other changes by Procurement or Finance.")
        if cr.status != "submitted":
            raise HTTPException(409, "This request has already been decided.")
        if decision not in ("approve", "reject") or len(note) < 5:
            raise HTTPException(400, "Choose approve or reject and say how you checked it (it goes on the audit trail).")
        vm = (await s.execute(select(VendorMaster).where(VendorMaster.vendor_id == cr.erp_vendor_id))).scalar_one_or_none()
        if decision == "approve" and vm is not None:
            if cr.kind == "bank_account":
                new = _json.loads(decrypt(cr.requested_enc))
                old = vm.account
                vm.account, vm.ifsc = new["account"], new["ifsc"]
                vendor = await s.get(Vendor, cr.vendor_pk) if cr.vendor_pk else None
                if vendor is not None:
                    from onboarding.intel.models import VendorIdentifier
                    await _identifier(s, vendor, "BANK_ACCOUNT", new["account"])
                    await _identifier(s, vendor, "IFSC", new["ifsc"])
                    old_ifsc_key = lookup_key("IFSC", (await s.execute(select(VendorIdentifier.display).where(VendorIdentifier.vendor_pk == vendor.id,
                                                   VendorIdentifier.kind == "IFSC", VendorIdentifier.status == "current"))).scalars().first() or "")
                    for idf in (await s.execute(select(VendorIdentifier).where(VendorIdentifier.vendor_pk == vendor.id))).scalars():
                        if (idf.kind == "BANK_ACCOUNT" and idf.lookup_key == lookup_key("BANK_ACCOUNT", old)) or                            (idf.kind == "IFSC" and idf.lookup_key == old_ifsc_key and old_ifsc_key != lookup_key("IFSC", new["ifsc"])):
                            idf.status = "previous"
                    # the new account starts from its own evidence: not the old account's level, never A4 without a real source
                    from onboarding.intel.models import EvidenceItem, FactObservation
                    ev = EvidenceItem(vendor_pk=vendor.id, kind="human_decision", ref=f"change:{cr.id}", basis="human", source_label=f"Bank change approved by {actor.name}",
                                      payload={"note": note, "document": cr.document_name}, content_sha256=cr.document_sha256)
                    s.add(ev)
                    await s.flush()
                    prev = (await s.execute(select(FactObservation).where(FactObservation.vendor_pk == vendor.id, FactObservation.fact == "BANK_ACCOUNT")
                                            .order_by(FactObservation.id.desc()))).scalars().first()
                    s.add(FactObservation(vendor_pk=vendor.id, fact="BANK_ACCOUNT", value_display=mask("BANK_ACCOUNT", new["account"]), value_key=lookup_key("BANK_ACCOUNT", new["account"]),
                                          level="A1", basis="human", source_label="Change request: bank letter or cheque, reviewer's callback",
                                          note=f"Changed on request {cr.id}; checked by {actor.name}: {note}. Not confirmed at source.", evidence_item_id=ev.id,
                                          run_id=None, supersedes_id=prev.id if prev else None))
        cr.status, cr.reviewed_by, cr.reviewed_at, cr.review_note = ("approved" if decision == "approve" else "rejected"), actor.id, now(), note
        record(s, entity="change_request", entity_id=cr.id, entity_label=f"{'Bank account' if cr.kind == 'bank_account' else 'Contact'} change · {cr.erp_vendor_id}",
               action=f"{decision}d", actor=actor, actor_label=f"{actor.name} ({ROLE_LABEL.get(actor.role, actor.role)})", vendor_pk=cr.vendor_pk, reason=note,
               detail=cr.requested)
        await s.commit()
    return RedirectResponse(str(form.get("back") or "/review"), status_code=303)

