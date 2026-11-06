"""The two front doors and everything behind the vendor one.

  /                     choose: "I work at Mamoni" (console) or "I'm a vendor" (portal)
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
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func

from onboarding.demo_data import BUYER
from onboarding.ap.replies import suggested_replies
from onboarding import captcha, security
from onboarding.config import get_settings
from onboarding import access, auth
from onboarding import bills as B
from onboarding.demo_data import KESARI, SCENARIOS
from onboarding.models import (Application, Bill, Document, Employee, Fact, Invite, Message, Run, StaffLogin, StoredFile, VendorAccount, VendorBill,
                               VendorLink, VendorMaster, now)
from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD, DEMO_VENDOR, EMPLOYEES
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
    resp.set_cookie(name, auth.make_session(account_id, purpose), httponly=True, samesite="lax", secure=secure)
    return resp


# Demo logins shown on the login pages (fictional people; defined in seeding.py)
DEMO = dict(password=DEMO_PASSWORD, company_email=DEMO_COMPANY_EMAIL, vendor=DEMO_VENDOR)


def _demo() -> dict:
    """Demo credentials for the login pages, or nothing at all outside demo mode."""
    from onboarding.config import get_settings
    return DEMO if get_settings().demo_tools else {}


# --- company login ---------------------------------------------------------------------------------
@router.get("/company/login", response_class=HTMLResponse)
async def company_login_form(request: Request, next: str = ""):
    async with sessions()() as s:
        return await render(request, s, "company_login.html", next=safe_next(next, "/console"), email="", error="", demo=_demo())


@router.post("/company/login", response_class=HTMLResponse)
async def company_login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("")):
    email, nxt = email.strip().lower(), safe_next(next, "/console")
    async with sessions()() as s:
        try:
            security.check_login(request, email)
        except HTTPException as e:
            return await render(request, s, "company_login.html", next=nxt, email=email, demo=_demo(), error=e.detail)
        if bot := await captcha.check(request):
            return await render(request, s, "company_login.html", next=nxt, email=email, demo=_demo(), error=bot)
        emp = (await s.execute(select(Employee).where(Employee.email == email))).scalars().first()
        login = (await s.execute(select(StaffLogin).where(StaffLogin.employee_id == emp.id))).scalar_one_or_none() if emp else None
        if not await auth.verify_password_async(password, login.password_hash if login else None):
            return await render(request, s, "company_login.html", next=nxt, email=email, demo=_demo(),
                                error="That email and password don't match an employee login.")
        login.last_login_at = now()
        await s.commit()
        resp = _cookie(RedirectResponse(nxt, status_code=303), request, emp.id, "company")
        resp.delete_cookie(auth.ACTOR_COOKIE)   # start as yourself (no actor cookie = the logged-in employee)
        return resp


@router.post("/company/logout")
async def company_logout(request: Request):
    await auth.revoke(request.cookies.get(auth.COMPANY_COOKIE), "company")
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(auth.COMPANY_COOKIE)
    resp.delete_cookie("actor")
    return resp


# --- the two doors --------------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    async with sessions()() as s:
        demo = _demo()
        return await render(request, s, "landing.html", demo=demo, team=EMPLOYEES if demo else [])


@router.get("/tour", response_class=HTMLResponse)
async def tour(request: Request):
    async with sessions()() as s:
        return await render(request, s, "tour.html")


CONTACT_TOPICS = ("Registering as a supplier", "My registration", "A bill or payment", "Something else")


@router.get("/contact", response_class=HTMLResponse)
async def contact_form(request: Request):
    async with sessions()() as s:
        return await render(request, s, "contact.html", values={}, error="", topics=CONTACT_TOPICS)


@router.post("/contact", response_class=HTMLResponse)
async def contact_send(request: Request, name: str = Form(""), company: str = Form(""), email: str = Form(""), topic: str = Form(""),
                       body: str = Form("")):
    from onboarding.models import ContactMessage
    values = dict(name=name.strip()[:120], company=company.strip()[:200], email=email.strip().lower()[:200], topic=topic, body=body.strip()[:4000])
    async with sessions()() as s:
        error = await captcha.check(request)
        if not error and not security.CONTACT_PER_IP.allow(security.client_ip(request)) and get_settings().rate_limits:
            error = security.CONTACT_PER_IP.message
        if not error and (not values["name"] or len(values["body"]) < 10):
            error = "Please give your name and a short message."
        elif not error and not EMAIL_RE.match(values["email"]):
            error = "Please enter a valid email address, so we can reply."
        if error:
            return await render(request, s, "contact.html", values=values, error=error, topics=CONTACT_TOPICS)
        s.add(ContactMessage(name=values["name"], company=values["company"], email=values["email"],
                             topic=topic if topic in CONTACT_TOPICS else "", body=values["body"]))
        await s.commit()
    return RedirectResponse("/thanks?for=contact", status_code=303)


THANKS = {
    "registration": ("Thank you for registering.", "We are checking your details and will email you shortly."),
    "future": ("Thank you for registering for future work.", "We are checking your details and will email you shortly."),
    "update": ("Thank you for updating your registration.", "We are checking your details and will email you shortly."),
    "bill": ("Thank you for submitting your bill.", "We are checking your details and will email you shortly."),
    "contact": ("Thank you for getting in touch.", "We'll reply by email within two working days."),
}


@router.get("/thanks", response_class=HTMLResponse)
async def thanks(request: Request, ref: str = ""):
    kind = request.query_params.get("for", "registration")
    title, lead = THANKS.get(kind, THANKS["registration"])
    async with sessions()() as s:
        return await render(request, s, "thanks.html", kind=kind, title=title, lead=lead, ref=re.sub(r"[^A-Z0-9-]", "", ref.upper())[:20])


@router.post("/lang")
async def set_language(request: Request, to: str = Form("en"), next: str = Form("/")):
    from onboarding import i18n
    resp = RedirectResponse(safe_next(next, "/"), status_code=303)
    resp.set_cookie(i18n.COOKIE, to if to in i18n.LANGS else "en", max_age=365 * 24 * 3600, samesite="lax")
    return resp


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
        error = await captcha.check(request)
        try:
            security.check_login(request, email)
            security.SIGNUP_PER_IP.check(security.client_ip(request))
        except HTTPException as e:
            error = error or e.detail
        if error:
            pass
        elif not values["company_name"] or not values["contact_name"]:
            error = "Please fill in your company and your name."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif problem := auth.password_problem(password):
            error = problem
        elif existing := (await s.execute(select(VendorAccount).where(VendorAccount.email == email))).scalar_one_or_none():
            if await auth.verify_password_async(password, existing.password_hash):
                existing.last_login_at = now()
                await s.commit()
                return _cookie(RedirectResponse(nxt, status_code=303), request, existing.id)
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
        return await render(request, s, "vendor_auth.html", mode="login", next=nxt, values={}, invite=await _invite_from_next(s, nxt), error="", demo=_demo())


@router.post("/vendor/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("")):
    email, nxt = email.strip().lower(), safe_next(next)
    async with sessions()() as s:
        try:
            security.check_login(request, email)
        except HTTPException as e:
            return await render(request, s, "vendor_auth.html", mode="login", next=nxt, values={"email": email}, invite=None, error=e.detail, demo=_demo())
        if bot := await captcha.check(request):
            return await render(request, s, "vendor_auth.html", mode="login", next=nxt, values={"email": email}, invite=None, error=bot, demo=_demo())
        acct = (await s.execute(select(VendorAccount).where(VendorAccount.email == email))).scalar_one_or_none()
        if not await auth.verify_password_async(password, acct.password_hash if acct else None):
            # same message either way: don't reveal which emails have accounts
            return await render(request, s, "vendor_auth.html", mode="login", next=nxt, values={"email": email}, invite=None,
                                error="That email and password don't match.", demo=_demo())
        acct.last_login_at = now()
        await s.commit()
        return _cookie(RedirectResponse(nxt, status_code=303), request, acct.id)


@router.get("/vendor/google")
async def google_start(request: Request, next: str = ""):
    from onboarding import google_auth
    if not google_auth.configured():
        return RedirectResponse("/vendor/login", status_code=303)
    url, cookie = google_auth.start(request, safe_next(next))
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(google_auth.STATE_COOKIE, cookie, max_age=google_auth.TTL, httponly=True, samesite="lax")
    return resp


@router.get("/vendor/google/callback", response_class=HTMLResponse)
async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    from onboarding import google_auth
    saved = google_auth.unseal(request.cookies.get(google_auth.STATE_COOKIE), 2)
    async with sessions()() as s:
        async def fail(msg: str):
            r = await render(request, s, "vendor_auth.html", mode="login", next=safe_next(saved[1] if saved else ""), values={}, invite=None,
                             error=msg, demo=_demo())
            r.delete_cookie(google_auth.STATE_COOKIE)
            return r
        if error:
            return await fail("Google sign-in was cancelled. You can try again or log in with your email.")
        if not saved or not code or not secrets_eq(state, saved[0]):
            return await fail("That Google sign-in link has expired. Please try again.")
        try:
            who = await google_auth.exchange(request, code)
        except Exception:
            return await fail("We couldn't reach Google just now. Please try again, or log in with your email.")
        email = str(who.get("email", "")).strip().lower()
        if not email or not who.get("email_verified"):
            return await fail("Your Google account's email isn't verified, so we can't use it to sign you in.")
        nxt = safe_next(saved[1])
        acct = (await s.execute(select(VendorAccount).where(VendorAccount.email == email))).scalar_one_or_none()
        if acct:
            acct.last_login_at = now()
            await s.commit()
            resp = _cookie(RedirectResponse(nxt, status_code=303), request, acct.id)
        else:   # first time: ask for the company name once
            resp = RedirectResponse(f"/vendor/google/finish?next={quote(nxt)}", status_code=303)
            resp.set_cookie(google_auth.NEW_COOKIE, google_auth.seal(email, str(who.get("name", ""))[:120]),
                            max_age=google_auth.TTL, httponly=True, samesite="lax")
        resp.delete_cookie(google_auth.STATE_COOKIE)
        return resp


@router.get("/vendor/google/finish", response_class=HTMLResponse)
async def google_finish_form(request: Request, next: str = ""):
    from onboarding import google_auth
    who = google_auth.unseal(request.cookies.get(google_auth.NEW_COOKIE), 2)
    if not who:
        return RedirectResponse("/vendor/register", status_code=303)
    async with sessions()() as s:
        inv = await _invite_from_next(s, safe_next(next))
        return await render(request, s, "vendor_google_finish.html", next=safe_next(next), email=who[0], error="",
                            values={"contact_name": who[1], "company_name": inv.company_name if inv else ""})


@router.post("/vendor/google/finish", response_class=HTMLResponse)
async def google_finish(request: Request, company_name: str = Form(""), contact_name: str = Form(""), next: str = Form("")):
    from onboarding import google_auth
    who = google_auth.unseal(request.cookies.get(google_auth.NEW_COOKIE), 2)
    if not who:
        return RedirectResponse("/vendor/register", status_code=303)
    nxt, values = safe_next(next), {"company_name": company_name.strip(), "contact_name": contact_name.strip()}
    async with sessions()() as s:
        if not values["company_name"] or not values["contact_name"]:
            return await render(request, s, "vendor_google_finish.html", next=nxt, email=who[0], values=values,
                                error="Please fill in your company and your name.")
        acct = (await s.execute(select(VendorAccount).where(VendorAccount.email == who[0]))).scalar_one_or_none()
        if not acct:
            acct = VendorAccount(email=who[0], password_hash=google_auth.NO_PASSWORD, company_name=values["company_name"],
                                 contact_name=values["contact_name"], last_login_at=now())
            s.add(acct)
            await s.commit()
        resp = _cookie(RedirectResponse(nxt, status_code=303), request, acct.id)
        resp.delete_cookie(google_auth.NEW_COOKIE)
        return resp


def secrets_eq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


@router.post("/vendor/logout")
async def logout(request: Request):
    await auth.revoke(request.cookies.get(auth.COOKIE), "vendor")
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
    security.SUBMIT_PER_IP.check(security.client_ip(request))   # each bill is read by Gemini
    data = await request.form()
    f = {"engaged_by": str(data.get("engaged_by") or "").strip()}   # number, date, amount, work and PO are read from the bill
    up, file = data.get("invoice"), None
    if up is not None and hasattr(up, "read") and getattr(up, "filename", ""):
        raw = await security.read_upload(up, "The bill")   # stops reading past 10 MB
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "The bill is larger than 10 MB. Please upload a smaller file.")
        if raw:
            security.require_document(raw, "The bill")
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
        s.add(StoredFile(sha256=sha, mime=security.sniff(raw) or B.file_mime(filename), size=len(raw), data=raw))
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
@router.get("/bills")
async def bills_list_page():
    """Drawn by the browser app from GET /api/v1/bills."""
    from onboarding.appshell import app_shell
    return app_shell()


async def bills_list(request: Request) -> dict:
    """Bills from active vendors and bills sent with a registration (requesters: the ones that name them)."""
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
        return dict(rows=rows, emps=emps, regs=regs, full=full)


@router.get("/bills/{bill_id}", response_class=HTMLResponse)
async def bill_page(request: Request, bill_id: int):
    async with sessions()() as s:
        b = await s.get(VendorBill, bill_id)
        if not b:
            raise HTTPException(404, "No such bill")
        actor = await _actor(request, s)
        from onboarding.ap.models import BillTag
        tags = (await s.execute(select(BillTag).where(BillTag.bill_id == b.id).order_by(BillTag.id))).scalars().all()
        tagged_me = bool(actor and any(t.to_employee_id == actor.id for t in tags))
        if not access.can_open_bill(actor, b) and not tagged_me:
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
                            emps=emps, vendor=vendor, allowed=B.allowed_bill_actions(b, actor, engaged, case), labels=B.BILL_ACTION_LABEL, B=B,
                            replies=suggested_replies(b, case, po, vm, BUYER), tags=tags, team=[e for e in emps.values() if not actor or e.id != actor.id])


@router.post("/bills/{bill_id}/tag")
async def bill_tag(request: Request, bill_id: int, to_employee_id: int = Form(...), note: str = Form("")):
    """Tag a teammate on an invoice problem. They see it on Home and in their reminder, and get an email."""
    from onboarding.ap.audit import record
    from onboarding.ap.models import BillTag
    note = note.strip()
    async with sessions()() as s:
        b = await s.get(VendorBill, bill_id)
        if not b:
            raise HTTPException(404, "No such bill")
        actor = await _actor(request, s)
        if not actor:
            raise HTTPException(403, "Sign in first.")
        mine = (await s.execute(select(BillTag).where(BillTag.bill_id == b.id, BillTag.to_employee_id == actor.id))).scalars().first()
        if not access.can_open_bill(actor, b) and not mine:
            raise access.forbid("This bill")
        to = await s.get(Employee, to_employee_id)
        if not to or to.id == actor.id:
            raise HTTPException(400, "Pick a teammate to tag.")
        if len(note) < 3:
            raise HTTPException(400, "Say what you need from them.")
        s.add(BillTag(bill_id=b.id, from_employee_id=actor.id, to_employee_id=to.id, note=note))
        record(s, entity="invoice", entity_id=b.id, action="tagged", actor=actor, entity_label=b.ref, reason=f"{to.name}: {note}")
        await s.commit()
        ref, inv, to_email, frm = b.ref, b.invoice_number, to.email, actor.name
    from onboarding import mailer
    mailer.notify(to_email, f"{frm} tagged you on invoice {inv or ref}",
                  f"{frm} tagged you on invoice {inv or ref} ({ref}):\n\n{note}\n\nOpen it: /bills/{bill_id}#team")
    return RedirectResponse(f"/bills/{bill_id}#team", status_code=303)


@router.post("/bills/{bill_id}/tag/{tag_id}/done")
async def bill_tag_done(request: Request, bill_id: int, tag_id: int, reply: str = Form("")):
    """The tagged teammate answers and closes the tag."""
    from onboarding.ap.audit import record
    from onboarding.ap.models import BillTag
    async with sessions()() as s:
        tag = await s.get(BillTag, tag_id)
        actor = await _actor(request, s)
        if not tag or tag.bill_id != bill_id:
            raise HTTPException(404, "No such tag")
        if not actor or actor.id != tag.to_employee_id:
            raise HTTPException(403, "Only the person tagged can answer this.")
        tag.done_at, tag.reply = now(), reply.strip()
        b = await s.get(VendorBill, bill_id)
        record(s, entity="invoice", entity_id=bill_id, action="tag_answered", actor=actor, entity_label=b.ref if b else "", reason=tag.reply)
        await s.commit()
    return RedirectResponse(f"/bills/{bill_id}#team", status_code=303)


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


@router.get("/supplier-accounts")
async def vendors_list_page():
    """Drawn by the browser app from GET /api/v1/supplier-accounts."""
    from onboarding.appshell import app_shell
    return app_shell()


async def supplier_accounts(request: Request) -> list[dict]:
    """Every supplier portal account with its registrations and bills. Reviewers and Finance only (the menu
    hid it from requesters, but nothing on the server stopped them before)."""
    async with read_sessions()() as s:
        access.require_full(await _actor(request, s), "Supplier accounts")
        accts = (await s.execute(select(VendorAccount).order_by(VendorAccount.id.desc()))).scalars().all()
        pfs = await asyncio.gather(*(_portfolio(s, a) for a in accts))  # side by side, not one account after another
        return [dict(acct=a, **pf) for a, pf in zip(accts, pfs)]


# --- company profile: one-time onboarding, controlled changes ------------------------------------------------------
@router.get("/vendor/profile", response_class=HTMLResponse)
async def vendor_profile_page(request: Request, sent: str = ""):
    """The vendor's verified company details, documents and change requests. Material changes are re-verified."""
    from onboarding.ap.models import ChangeRequest
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return RedirectResponse("/vendor/login?next=/vendor/profile", status_code=303)
        pf = await _portfolio(s, acct)
        reg = pf["active"] or (pf["regs"][0] if pf["regs"] else None)
        run = reg["run"] if reg else None
        docs = (await s.execute(select(Document).where(Document.run_id == run.id).order_by(Document.id))).scalars().all() if run else []
        changes = (await s.execute(select(ChangeRequest).where(ChangeRequest.account_id == acct.id).order_by(ChangeRequest.id.desc()))).scalars().all()
        return await render(request, s, "vendor_profile.html", acct=acct, reg=reg, run=run, f=(run.form if run else {}), docs=docs, changes=changes,
                            sent=sent, active=pf["active"])


@router.post("/vendor/profile/change")
async def vendor_change_request(request: Request):
    from onboarding.ap.audit import record
    from onboarding.ap.models import ChangeRequest
    from onboarding.intel.crypto import encrypt, mask
    from onboarding.intel.models import Vendor
    import json as _json
    data = await request.form()
    kind = str(data.get("kind") or "")
    if kind not in ("bank_account", "contact"):
        raise HTTPException(400, "Unknown change.")
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return RedirectResponse("/vendor/login", status_code=303)
        pf = await _portfolio(s, acct)
        if not pf["active"]:
            raise HTTPException(409, "Changes can be requested once your registration is approved and active. Until then, update your registration.")
        vm = pf["active"]["vendor"]
        reason = str(data.get("reason") or "").strip()
        cr = ChangeRequest(account_id=acct.id, erp_vendor_id=vm.vendor_id, kind=kind, reason=reason,
                           vendor_pk=(await s.execute(select(Vendor.id).where(Vendor.erp_vendor_id == vm.vendor_id))).scalar())
        if kind == "bank_account":
            account = re.sub(r"\D", "", str(data.get("account") or ""))
            ifsc = str(data.get("ifsc") or "").strip().upper()
            holder = str(data.get("holder") or "").strip()
            if len(account) < 6 or len(ifsc) != 11 or not holder:
                raise HTTPException(400, "Please give the new account number, its 11-character IFSC and the account holder's name.")
            up = data.get("proof")
            if up is None or not getattr(up, "filename", ""):
                raise HTTPException(400, "Please attach a cancelled cheque or a bank letter for the new account.")
            raw = await security.read_upload(up, "The bank proof")   # stops reading past 10 MB
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, "The file is larger than 10 MB.")
            security.require_document(raw, "The bank proof")
            cr.document_sha256, cr.document_name = await _store(s, up.filename, raw), up.filename
            cr.requested = {"account": mask("BANK_ACCOUNT", account), "ifsc": ifsc, "holder": holder}
            cr.requested_enc = encrypt(_json.dumps({"account": account, "ifsc": ifsc, "holder": holder}))
        else:
            email, phone = str(data.get("email") or "").strip(), str(data.get("phone") or "").strip()
            if not email and not phone:
                raise HTTPException(400, "Please give the new email or phone.")
            cr.requested = {"email": email, "phone": phone}
        s.add(cr)
        await s.flush()
        record(s, entity="change_request", entity_id=cr.id, entity_label=f"{'Bank account' if kind == 'bank_account' else 'Contact'} change · {vm.vendor_id}",
               action="requested", actor_label=f"{acct.contact_name or acct.email} (vendor)", vendor_pk=cr.vendor_pk, reason=reason, detail=cr.requested)
        await s.commit()
    return RedirectResponse("/vendor/profile?sent=1", status_code=303)

