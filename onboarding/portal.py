"""The two front doors and everything behind the vendor one.

  /                     choose: "I work at Nare Enterprises" (console) or "I'm a vendor" (portal)
  /vendor/register      create a vendor account        /vendor/login, /vendor/logout
  /vendor               the vendor's home: registration status, messages, next step, bills
  /vendor/bills/new     an ACTIVE vendor submits another bill
  /vendor/bills/{id}    the vendor's view of one bill (and the fix-and-resubmit form)
  /bills, /bills/{id}   company side: every vendor bill, with checks, the vendor's verified profile and actions
  /vendors              company side: every vendor account and where it stands
  /company/login        employees log in with their work email (every company page needs it; see main.py)
"""

from __future__ import annotations

import asyncio

import re
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func

from onboarding import access, auth
from onboarding import bills as B
from onboarding.demo_data import KESARI, SCENARIOS
from onboarding.models import (Application, Bill, Employee, Fact, Invite, Message, Run, StaffLogin, StoredFile, VendorAccount, VendorBill,
                               VendorLink, VendorMaster, now)
from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD, DEMO_VENDOR
from onboarding.pipeline import read_sessions, sessions
from onboarding.rules import money
from onboarding.web import (MAX_BYTES, ROLE_LABEL, _actor, _all, _employees, _reads, _resolve_employee, _rows, render, safe_next,
                             vendor_account)

router = APIRouter()
ROOT = Path(__file__).resolve().parent.parent
EXTRA = ROOT / "fixtures" / "documents" / "extra"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Demo bills for the Kesari demo vendor (fictional; files rendered by scripts/make_documents.py)
DEMO_BILLS = {
    "clean": dict(title="A normal monthly bill", file="kesari_bill_clean.pdf", invoice_number="KFS/2026-27/0207", invoice_date="2026-10-28",
                  amount="40120.00", description="Housekeeping of Plant 2 canteen and washrooms, October 2026", engaged_by="Priya Nair"),
    "newbank": dict(title="A bill asking for payment to a new bank account", file="kesari_bill_newbank.pdf", invoice_number="KFS/2026-27/0211",
                    invoice_date="2026-10-30", amount="23600.00", description="Pest control treatment, Plant 2 stores", engaged_by="Priya Nair"),
    "overbilled": dict(title="A bill for more shifts than were confirmed", file="kesari_bill_overbilled.pdf", engaged_by="Priya Nair"),
}


def _cookie(resp: RedirectResponse, request: Request, account_id: int, purpose: str = "vendor") -> RedirectResponse:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    name = auth.COMPANY_COOKIE if purpose == "company" else auth.COOKIE
    resp.set_cookie(name, auth.make_session(account_id, purpose), max_age=auth.MAX_AGE, httponly=True, samesite="lax", secure=secure)
    return resp


# Demo logins shown on the login pages (fictional people; defined in seeding.py)
DEMO = dict(password=DEMO_PASSWORD, company_email=DEMO_COMPANY_EMAIL, vendor=DEMO_VENDOR)


# --- company login ---------------------------------------------------------------------------------
@router.get("/company/login", response_class=HTMLResponse)
async def company_login_form(request: Request, next: str = ""):
    async with sessions()() as s:
        return await render(request, s, "company_login.html", next=safe_next(next, "/console"), email="", error="", demo=DEMO)


@router.post("/company/login", response_class=HTMLResponse)
async def company_login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("")):
    email, nxt = email.strip().lower(), safe_next(next, "/console")
    async with sessions()() as s:
        emp = (await s.execute(select(Employee).where(Employee.email == email))).scalars().first()
        login = (await s.execute(select(StaffLogin).where(StaffLogin.employee_id == emp.id))).scalar_one_or_none() if emp else None
        if not await auth.verify_password_async(password, login.password_hash if login else None):
            return await render(request, s, "company_login.html", next=nxt, email=email, demo=DEMO,
                                error="That email and password don't match an employee login.")
        login.last_login_at = now()
        await s.commit()
        resp = _cookie(RedirectResponse(nxt, status_code=303), request, emp.id, "company")
        resp.set_cookie("actor", str(emp.id), max_age=auth.MAX_AGE, samesite="lax")   # start as yourself
        return resp


@router.post("/company/logout")
async def company_logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(auth.COMPANY_COOKIE)
    resp.delete_cookie("actor")
    return resp


# --- the two doors --------------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    async with sessions()() as s:
        return await render(request, s, "landing.html")


# --- vendor accounts ------------------------------------------------------------------------------
async def _invite_from_next(s, nxt: str) -> Invite | None:
    m = re.match(r"^/apply/([\w-]+)$", nxt or "")
    if not m:
        return None
    inv = (await s.execute(select(Invite).where(Invite.token == m.group(1)))).scalar_one_or_none()
    if inv:
        await s.refresh(inv, ["sponsor"])
    return inv


@router.get("/vendor/register", response_class=HTMLResponse)
async def register_form(request: Request, next: str = ""):
    async with sessions()() as s:
        nxt = safe_next(next)
        inv = await _invite_from_next(s, nxt)
        values = {"company_name": inv.company_name, "email": inv.contact_email} if inv else {}
        return await render(request, s, "vendor_auth.html", mode="register", next=nxt, values=values, invite=inv, error="")


@router.post("/vendor/register", response_class=HTMLResponse)
async def register(request: Request, company_name: str = Form(""), contact_name: str = Form(""), email: str = Form(""),
                   password: str = Form(""), next: str = Form("")):
    email, nxt = email.strip().lower(), safe_next(next)
    values = {"company_name": company_name.strip(), "contact_name": contact_name.strip(), "email": email}
    async with sessions()() as s:
        error = ""
        if not values["company_name"] or not values["contact_name"]:
            error = "Please fill in your company and your name."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif problem := auth.password_problem(password):
            error = problem
        elif (await s.execute(select(VendorAccount).where(VendorAccount.email == email))).scalar_one_or_none():
            error = "An account with this email already exists. Log in instead."
        if error:
            return await render(request, s, "vendor_auth.html", mode="register", next=nxt, values=values, invite=await _invite_from_next(s, nxt), error=error)
        acct = VendorAccount(email=email, password_hash=await auth.hash_password_async(password), company_name=values["company_name"],
                             contact_name=values["contact_name"], last_login_at=now())
        s.add(acct)
        await s.commit()
        return _cookie(RedirectResponse(nxt, status_code=303), request, acct.id)


@router.get("/vendor/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = ""):
    async with sessions()() as s:
        nxt = safe_next(next)
        return await render(request, s, "vendor_auth.html", mode="login", next=nxt, values={}, invite=await _invite_from_next(s, nxt), error="", demo=DEMO)


@router.post("/vendor/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("")):
    email, nxt = email.strip().lower(), safe_next(next)
    async with sessions()() as s:
        acct = (await s.execute(select(VendorAccount).where(VendorAccount.email == email))).scalar_one_or_none()
        if not await auth.verify_password_async(password, acct.password_hash if acct else None):
            # same message either way: don't reveal which emails have accounts
            return await render(request, s, "vendor_auth.html", mode="login", next=nxt, values={"email": email}, invite=None,
                                error="That email and password don't match.", demo=DEMO)
        acct.last_login_at = now()
        await s.commit()
        return _cookie(RedirectResponse(nxt, status_code=303), request, acct.id)


@router.post("/vendor/logout")
async def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


# --- the vendor's home ----------------------------------------------------------------------------
async def _nothing(_s) -> list:
    return []


async def _registration(app_id: int) -> dict:
    """One registration on a vendor's account: latest run, invite or bill, messages sent, vendor ID."""
    async with read_sessions()() as s:
        app = await s.get(Application, app_id)
    app_runs = select(Run.id).where(Run.application_id == app_id)
    r = await _reads(
        run=_all(select(Run).where(Run.application_id == app_id).order_by(Run.id.desc()).limit(1)),
        invite=_all(select(Invite).where(Invite.id == app.invite_id)) if app.invite_id else _nothing,
        bill=_all(select(Bill).where(Bill.application_id == app_id)),
        msgs=_all(select(Message).where(Message.run_id.in_(app_runs), Message.audience == "vendor", Message.state == "sent").order_by(Message.id.desc())),
        vendor=_all(select(VendorMaster).where(VendorMaster.source_run_id.in_(app_runs)).order_by(VendorMaster.id).limit(1)),
    )
    inv, bill = (r["invite"] or [None])[0], (r["bill"] or [None])[0]
    return dict(app=app, run=(r["run"] or [None])[0], invite=inv, bill=bill, token=inv.token if inv else (bill.token if bill else ""),
                msgs=r["msgs"], vendor=(r["vendor"] or [None])[0])


async def _pending_invite(invite_id: int):
    async with read_sessions()() as s:
        inv = await s.get(Invite, invite_id)
        if inv:
            await s.refresh(inv, ["sponsor"])
        return inv


async def _portfolio(s, acct: VendorAccount) -> dict:
    """Everything this account can see: invitations it opened, its registration(s), its vendor ID, its bills.
    Registrations are fetched side by side (each is a handful of queries), not one after another."""
    r = await _reads(links=_all(select(VendorLink).where(VendorLink.account_id == acct.id).order_by(VendorLink.id)),
                     vbills=_all(select(VendorBill).where(VendorBill.account_id == acct.id).order_by(VendorBill.id.desc())))
    parts = await asyncio.gather(*(_registration(ln.application_id) if ln.application_id is not None else _pending_invite(ln.invite_id)
                                   for ln in r["links"] if ln.application_id is not None or ln.invite_id))
    regs = [x for x in parts if isinstance(x, dict)]
    pending_invites = [x for x in parts if isinstance(x, Invite)]
    active = next((g for g in regs if g["vendor"] and g["app"].current_status == "ACTIVE"), None)
    from onboarding.ap.models import InvoiceCase
    vcases = {c.bill_id: c for c in (await s.execute(select(InvoiceCase).where(InvoiceCase.bill_id.in_([b.id for b in r["vbills"]] or [-1])))).scalars()}
    return dict(regs=regs, pending_invites=pending_invites, vbills=r["vbills"], active=active, vcases=vcases)


@router.get("/vendor", response_class=HTMLResponse)
async def vendor_home(request: Request, submitted: int = 0):
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return RedirectResponse("/vendor/login", status_code=303)
        # demo shortcut: the demo vendor account can pre-fill its bill-first registration
        demo_bill = next((k for k, sc in SCENARIOS.items() if sc.get("bill") and sc["form"].get("contact_email") == acct.email), "")
        return await render(request, s, "vendor_home.html", acct=acct, submitted=submitted, B=B, demo_bill=demo_bill, **await _portfolio(s, acct))


@router.post("/vendor/invite")
async def vendor_use_invite(request: Request, link: str = Form("")):
    """'I have an invitation link': accept the full link or just the token."""
    m = re.search(r"/apply/([\w-]+)", link) or re.match(r"^\s*([\w-]{12,})\s*$", link)
    if not m:
        raise HTTPException(400, "That doesn't look like an invitation link. Paste the whole link from the email.")
    return RedirectResponse(f"/apply/{m.group(1)}", status_code=303)


# --- the vendor's bills ---------------------------------------------------------------------------
@router.get("/vendor/bills/new", response_class=HTMLResponse)
async def vendor_bill_form(request: Request, demo: str = ""):
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return RedirectResponse("/vendor/login?next=/vendor/bills/new", status_code=303)
        pf = await _portfolio(s, acct)
        if not pf["active"]:
            raise HTTPException(409, "You can submit bills once your vendor registration is approved and active.")
        vm = pf["active"]["vendor"]
        demo_ok = vm.gstin == KESARI["gstin"]
        values = DEMO_BILLS.get(demo, {}) if demo_ok else {}
        return await render(request, s, "vendor_bill_new.html", acct=acct, vm=vm, values=values, demo=demo if values else "",
                            demo_bills=DEMO_BILLS if demo_ok else {}, bill=None)


async def _bill_fields(request: Request) -> tuple[dict, tuple[str, bytes] | None, str]:
    data = await request.form()
    f = {"engaged_by": str(data.get("engaged_by") or "").strip()}   # number, date, amount, work and PO are read from the bill
    up, file = data.get("invoice"), None
    if up is not None and hasattr(up, "read") and getattr(up, "filename", ""):
        raw = await up.read()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "The bill is larger than 10 MB. Please upload a smaller file.")
        if raw:
            file = (up.filename, raw)
    demo = str(data.get("demo") or "")
    if file is None and demo in DEMO_BILLS and (EXTRA / DEMO_BILLS[demo]["file"]).exists():
        p = EXTRA / DEMO_BILLS[demo]["file"]
        file = (p.name, p.read_bytes())
    if not f["engaged_by"]:
        raise HTTPException(400, "Please fill in: who engaged you.")
    return f, file, demo


async def _store(s, filename: str, raw: bytes) -> str:
    import hashlib
    sha = hashlib.sha256(raw).hexdigest()
    if not await s.get(StoredFile, sha):
        s.add(StoredFile(sha256=sha, mime=B.file_mime(filename), size=len(raw), data=raw))
        await s.flush()
    return sha


@router.post("/vendor/bills/new")
async def vendor_bill_submit(request: Request):
    f, file, demo = await _bill_fields(request)
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return RedirectResponse("/vendor/login", status_code=303)
        pf = await _portfolio(s, acct)
        if not pf["active"]:
            raise HTTPException(409, "You can submit bills once your vendor registration is approved and active.")
        if not file:
            raise HTTPException(400, "Please attach the bill (PDF, JPG or PNG).")
        emp = await _resolve_employee(s, f["engaged_by"])
        reg = pf["active"]
        b = VendorBill(ref=await B.next_ref(s), account_id=acct.id, application_id=reg["app"].id, vendor_id=reg["vendor"].vendor_id,
                       invoice_number="", invoice_date="", amount="", description="",   # filled from the bill when it's read
                       engaged_by_text=f["engaged_by"], engaged_employee_id=emp.id if emp else None, po_number="",
                       filename=file[0], sha256=await _store(s, *file))
        b.status = "draft"
        s.add(b)
        await s.flush()
        B.trail(b, acct.contact_name or acct.email, "Vendor", "uploaded", file[0])
        await s.commit()
        bid = b.id
    await B.read_draft(bid, prefer_cache=bool(demo))   # read now: the vendor checks it before sending
    return RedirectResponse(f"/vendor/bills/{bid}", status_code=303)


@router.post("/vendor/bills/{bill_id}/send")
async def vendor_bill_send(request: Request, bill_id: int, po_number: str = Form(""), engaged_by: str = Form("")):
    """The vendor confirms what was read and which purchase order the bill is for; then it's checked."""
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        b = await _own_bill(s, acct, bill_id)
        if b.status != "draft":
            raise HTTPException(409, "This bill has already been sent.")
        b.po_number = po_number.strip().upper()
        if engaged_by.strip():
            emp = await _resolve_employee(s, engaged_by.strip())
            b.engaged_by_text, b.engaged_employee_id = engaged_by.strip(), emp.id if emp else None
        b.status = "checking"
        B.trail(b, acct.contact_name or acct.email, "Vendor", "submitted", f"PO {b.po_number}" if b.po_number else "no PO given")
        await s.commit()
    B.start_check(bill_id, prefer_cache=True)   # the draft reading is already saved
    return RedirectResponse(f"/vendor/bills/{bill_id}", status_code=303)


async def _own_bill(s, acct: VendorAccount | None, bill_id: int) -> VendorBill:
    b = await s.get(VendorBill, bill_id)
    if not b or not acct or b.account_id != acct.id:
        raise HTTPException(404, "No such bill on your account.")
    return b


@router.get("/vendor/bills/{bill_id}", response_class=HTMLResponse)
async def vendor_bill(request: Request, bill_id: int):
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return RedirectResponse(f"/vendor/login?next=/vendor/bills/{bill_id}", status_code=303)
        b = await _own_bill(s, acct, bill_id)
        from onboarding.ap.models import InvoiceCase, PurchaseOrder
        case = (await s.execute(select(InvoiceCase).where(InvoiceCase.bill_id == b.id))).scalar_one_or_none()
        vm = (await s.execute(select(VendorMaster).where(VendorMaster.vendor_id == b.vendor_id))).scalar_one_or_none()
        pos = (await s.execute(select(PurchaseOrder).where(PurchaseOrder.vendor_gstin == (vm.gstin if vm else ""), PurchaseOrder.status == "open")
                               .order_by(PurchaseOrder.id.desc()))).scalars().all() if b.status == "draft" else []
        return await render(request, s, "vendor_bill.html", acct=acct, b=b, B=B, case=case, pos=pos)


@router.post("/vendor/bills/{bill_id}")
async def vendor_bill_resubmit(request: Request, bill_id: int):
    f, file, demo = await _bill_fields(request)
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        b = await _own_bill(s, acct, bill_id)
        if b.status != "vendor_fix":
            raise HTTPException(409, "This bill isn't waiting for changes from you.")
        if b.confirmation == "awaiting":
            emp = await _resolve_employee(s, f["engaged_by"])
            b.engaged_by_text, b.engaged_employee_id = f["engaged_by"], emp.id if emp else None
        if file:
            b.filename, b.sha256 = file[0], await _store(s, *file)
        b.status, b.submissions = "checking", (b.submissions or 1) + 1
        B.trail(b, acct.contact_name or acct.email, "Vendor", "resubmitted", f"submission {b.submissions}")
        await s.commit()
    B.start_check(bill_id, prefer_cache=bool(demo))
    return RedirectResponse(f"/vendor/bills/{bill_id}", status_code=303)


# --- company side: bills and vendors --------------------------------------------------------------
@router.get("/bills", response_class=HTMLResponse)
async def bills_list(request: Request):
    async with read_sessions()() as s:
        emps = {e.id: e for e in await _employees(s)}
        actor = await _actor(request, s)
        full = access.full_view(actor)
        latest = select(func.max(Run.id)).group_by(Run.application_id)
        r = await _reads(rows=_rows(select(VendorBill, VendorMaster).join(VendorMaster, VendorMaster.vendor_id == VendorBill.vendor_id)
                                    .order_by(VendorBill.id.desc())),
                         reg_bills=_rows(select(Bill, Application).join(Application, Application.id == Bill.application_id).order_by(Bill.id.desc())),
                         runs=_all(select(Run).where(Run.id.in_(latest))))  # the latest run of every application, in one go
        rows = r["rows"]
        latest_run = {run.application_id: run for run in r["runs"]}
        regs = []
        for bill, app in r["reg_bills"]:
            if not full and not access.owns_application(actor, None, bill):
                continue
            regs.append(dict(bill=bill, app=app, run=latest_run.get(app.id), emp=emps.get(bill.engaged_employee_id)))
        if not full:  # a requester sees the bills that name them
            rows = [(b, vm) for b, vm in rows if access.can_open_bill(actor, b)]
        return await render(request, s, "bills.html", rows=rows, emps=emps, regs=regs, B=B, full=full)


@router.get("/bills/{bill_id}", response_class=HTMLResponse)
async def bill_page(request: Request, bill_id: int):
    async with sessions()() as s:
        b = await s.get(VendorBill, bill_id)
        if not b:
            raise HTTPException(404, "No such bill")
        actor = await _actor(request, s)
        if not access.can_open_bill(actor, b):
            raise access.forbid("This bill")
        vm = (await s.execute(select(VendorMaster).where(VendorMaster.vendor_id == b.vendor_id))).scalar_one()
        app = await s.get(Application, b.application_id)
        acct = await s.get(VendorAccount, b.account_id)
        engaged = await s.get(Employee, b.engaged_employee_id) if b.engaged_employee_id else None
        reg_run = await s.get(Run, vm.source_run_id) if vm.source_run_id else None
        facts = (await s.execute(select(Fact).where(Fact.run_id == vm.source_run_id).order_by(Fact.id))).scalars().all() if reg_run else []
        other = (await s.execute(select(VendorBill).where(VendorBill.vendor_id == b.vendor_id, VendorBill.id != b.id).order_by(VendorBill.id.desc()))).scalars().all()
        other = [o for o in other if access.can_open_bill(actor, o)]
        from onboarding.ap.models import AuditEvent, InvoiceCase, POLine, PurchaseOrder
        from onboarding.intel.models import Vendor
        case = (await s.execute(select(InvoiceCase).where(InvoiceCase.bill_id == b.id))).scalar_one_or_none()
        po = await s.get(PurchaseOrder, case.po_id) if case and case.po_id else None
        po_lines = (await s.execute(select(POLine).where(POLine.po_id == po.id).order_by(POLine.line_no))).scalars().all() if po else []
        audit = (await s.execute(select(AuditEvent).where(AuditEvent.entity == "invoice", AuditEvent.entity_id == str(b.id)).order_by(AuditEvent.id))).scalars().all()
        emps = {e.id: e for e in await _employees(s)}
        vendor = (await s.execute(select(Vendor).where(Vendor.erp_vendor_id == b.vendor_id))).scalar_one_or_none()
        return await render(request, s, "bill.html", b=b, vm=vm, app=app, acct=acct, engaged=engaged, reg_run=reg_run, facts=facts, other=other,
                            full=access.full_view(actor), full_bank=access.sees_full_bank(actor), case=case, po=po, po_lines=po_lines, audit=audit,
                            emps=emps, vendor=vendor, allowed=B.allowed_bill_actions(b, actor, engaged, case), labels=B.BILL_ACTION_LABEL, B=B)


@router.post("/bills/{bill_id}/action")
async def bill_action(request: Request, bill_id: int, action: str = Form(...), comment: str = Form("")):
    async with sessions()() as s:
        b = await s.get(VendorBill, bill_id)
        if not b:
            raise HTTPException(404, "No such bill")
        actor = await _actor(request, s)
        if not access.can_open_bill(actor, b):
            raise access.forbid("This bill")
        engaged = await s.get(Employee, b.engaged_employee_id) if b.engaged_employee_id else None
        from onboarding.ap.audit import record
        from onboarding.ap.models import InvoiceCase
        case = (await s.execute(select(InvoiceCase).where(InvoiceCase.bill_id == b.id))).scalar_one_or_none()
        if case is None:
            case = InvoiceCase(bill_id=b.id)
            s.add(case)
        allowed = B.allowed_bill_actions(b, actor, engaged, case)
        if action not in allowed:
            raise HTTPException(409, "That action doesn't apply to this bill right now.")
        if allowed[action]["blocked"]:
            raise HTTPException(403, allowed[action]["blocked"])
        comment = comment.strip()
        if allowed[action]["needs_comment"] and len(comment) < 5:
            raise HTTPException(400, "Please write a short note: it goes on the audit trail" + (" and to the vendor." if action == "ask_vendor" else "."))
        if action == "confirm_engagement":
            b.confirmation = "confirmed"
            if b.status == "awaiting_confirmation":
                b.status = "ready_for_approval"
        elif action == "deny_engagement":
            b.confirmation, b.status, b.risk_tier = "denied", "for_review", "high"
        elif action == "approve_payment":
            b.status = "approved"
            case.approved_by, case.approved_at, case.payment_status = actor.id, now(), "unpaid"
        elif action == "ask_vendor":
            b.status, b.vendor_items = "vendor_fix", [comment]
        elif action == "reject_bill":
            b.status = "rejected"
        elif action == "release_payment":
            case.payment_status, case.released_by, case.released_at = "in_progress", actor.id, now()
        elif action == "mark_paid":
            case.payment_status, case.payment_reference, case.paid_at = "paid", comment[:60], now()
            case.paid_amount, case.payment_recorded_by = money(b.amount), actor.id
        elif action == "hold_payment":
            case.payment_status, case.hold_reason = "on_hold", comment
        elif action == "release_hold":
            case.payment_status, case.hold_reason = ("in_progress" if case.released_by else "unpaid"), ""
        elif action == "block":
            b.status, case.blocked_reason = "blocked", comment
        elif action == "unblock":
            b.status = "for_review"
        case.updated_at = now()
        B.trail(b, actor.name, ROLE_LABEL.get(actor.role, actor.role), action, comment)
        record(s, entity="invoice", entity_id=b.id, entity_label=f"{b.ref} · {b.invoice_number or b.filename}", action=action, actor=actor,
               actor_label=f"{actor.name} ({ROLE_LABEL.get(actor.role, actor.role)})", vendor_pk=case.vendor_pk, reason=comment,
               detail={"status": B.invoice_status(b, case), "amount": b.amount}, override=action == "approve_payment" and bool(B.failing_review(b)))
        await s.commit()
    return RedirectResponse(f"/bills/{bill_id}#actions", status_code=303)


@router.get("/supplier-accounts", response_class=HTMLResponse)
async def vendors_list(request: Request):
    async with read_sessions()() as s:
        accts = (await s.execute(select(VendorAccount).order_by(VendorAccount.id.desc()))).scalars().all()
        pfs = await asyncio.gather(*(_portfolio(s, a) for a in accts))  # side by side, not one account after another
        rows = [dict(acct=a, **pf) for a, pf in zip(accts, pfs)]
        actor = await _actor(request, s)
        return await render(request, s, "vendors.html", rows=rows, B=B, full=access.full_view(actor))
