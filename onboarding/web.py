"""Web pages: sponsor invites, the vendor form, the live run view, the reviewer page with human
actions, the dashboard, the document check, assumptions and system check.

No logins: an "acting as" switcher (cookie) picks one of the seeded employees, so segregation of
duties (sponsor != approver) is visible in the demo.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import secrets
import time
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select

from urllib.parse import quote

from onboarding import access, auth, runner, security, staff_cache
from onboarding import validators as V
from onboarding.authenticity.assess import assess
from onboarding.config import db_label, feature, features, get_settings
from onboarding.features import scenario_on
from onboarding.db import WARM_CONNECTIONS, is_dropped_connection
from onboarding.demo_data import BUYER, SCENARIOS
from onboarding.models import (Application, Bill, Document, Employee, Fact, HumanAction, Invite, Message, Run, RunEvent, RuleResult, StoredFile,
                               VendorAccount, VendorBill, VendorLink, VendorMaster, now)
from onboarding.pipeline import create_run, read_sessions, sessions, stages_for
from onboarding.rules import SLOT_LABEL, SLOT_TITLE, inr, money

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "fixtures" / "documents"
PRIVATE = ROOT / "private_inputs"
PUBLIC_SAMPLE = ROOT / "fixtures" / "public" / "gst_certificate_signed_igr_maharashtra.pdf"
MAX_BYTES = 10 * 1024 * 1024
SLOTS = ["gst_certificate", "pan_card", "bank_proof", "udyam_certificate", "invoice"]
BILL_FIELDS = ("bill_invoice_number", "bill_invoice_date", "bill_amount", "bill_description", "bill_engaged_by", "bill_po")
STATUS_LABEL = {"APPROVED": "Approved", "PENDING_VENDOR": "Pending: vendor to fix", "PENDING_REVIEW": "Pending: internal review",
                "REJECTED": "Rejected", "ACTIVE": "Active vendor", "IN_PROGRESS": "In progress", "PREQUALIFIED": "Pre-qualified", "": "Running"}
LEVEL_NAMES = {"A0": "Declared", "A1": "Evidenced", "A2": "Genuine", "A3": "Cryptographically proven", "A4": "Confirmed at source"}
SPEND_BANDS = ["Under 1 lakh", "1-5 lakh", "5-10 lakh", "10-25 lakh", "25-50 lakh", "50 lakh - 1 crore", "Over 1 crore"]
HIGH_SPEND = {"50 lakh - 1 crore", "Over 1 crore"}
# Internal role codes stay sponsor | maker | checker (stored in the database); people see these labels.
ROLE_LABEL = {"sponsor": "Requester", "maker": "Procurement reviewer", "checker": "Finance controller"}
ROLE_HINT = {
    "sponsor": "Needs a new vendor and sends the invite. Sees only their own requests, without documents or ID numbers. Can't approve a vendor they asked for.",
    "maker": "Checks applications: sees every document and check (PAN and bank masked). Activates normal-risk vendors, asks vendors to fix things.",
    "checker": "Senior sign-off on high-risk and fraud-flagged cases. Sees everything, including the full bank account of active vendors for payment.",
}

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _fmt_dt(d: datetime | str | None) -> str:
    if not d:
        return ""
    if isinstance(d, str):  # ISO timestamps stored in JSON (bill audit trails)
        try:
            d = datetime.fromisoformat(d)
        except ValueError:
            return d
    ist = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    return ist.strftime("%d %b, %H:%M IST")


def _mask(name: str, value) -> str:
    """Mask PAN and account numbers wherever extracted fields are displayed."""
    if not isinstance(value, str):
        return value
    n = (name or "").lower()
    if "pan" in n and len(V.normalise_id(value)) == 10:
        return V.mask_pan(value)
    if "account" in n and sum(c.isdigit() for c in value) >= 6:
        return V.mask_account(value)
    return value


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["sigdate"] = lambda v: (f"{v[6:8]}/{v[4:6]}/{v[:4]} {v[8:10]}:{v[10:12]}" if isinstance(v, str) and len(v) >= 12 and v[:12].isdigit() else v)
templates.env.filters["mask"] = lambda value, name="": _mask(name, value)
def signal_text(s) -> dict:
    """How an authenticity signal reads on screen. Older checks stored development wording for known files."""
    get = (lambda k: s.get(k, "")) if isinstance(s, dict) else (lambda k: getattr(s, k, ""))
    title, detail = get("title") or "", get("detail") or ""
    if get("code") == "SPECIMEN":
        title, detail = "Known file: matched by fingerprint to a registered reference copy", "This exact file is on record, so visual authenticity checks are not applied. What it says is document evidence only: not independently confirmed."
    return dict(title=title, detail=detail.replace("[not applied: known test specimen]", "[not applied: known file]"))


from onboarding.i18n import t as _t  # noqa: E402
templates.env.filters["t"] = _t
templates.env.globals.update(signal_text=signal_text)
# One palette everywhere: amber = still in progress, red = invalid / blocked / rejected, green = verified / done.
# The old tone names map onto it so every page reads the same way.
COLOR = {"slate": "text-slate-600", "green": "text-emerald-700", "red": "text-rose-700",
         "emerald": "text-emerald-700", "amber": "text-amber-700", "orange": "text-amber-700", "indigo": "text-amber-700", "violet": "text-amber-700", "rose": "text-rose-700"}
templates.env.globals.update(COLOR=COLOR)
from onboarding import pincode as _pincode  # noqa: E402
from onboarding import countries as _countries
templates.env.globals.update(PIN_SPECIFIC=_pincode.SPECIFIC, PIN_TWO=_pincode.TWO, COUNTRIES=_countries.COUNTRIES, SWIFT_CODES=_countries.CODE_NAME)
templates.env.globals.update(STATUS_LABEL=STATUS_LABEL, LEVEL_NAMES=LEVEL_NAMES, SLOT_TITLE=SLOT_TITLE, SLOT_LABEL=SLOT_LABEL,
                             ROLE_LABEL=ROLE_LABEL, ROLE_HINT=ROLE_HINT, inr=inr, money=money, BUYER=BUYER, BUSINESS_TYPES=V.BUSINESS_TYPES, mask_pan=V.mask_pan, mask_account=V.mask_account,
                             tone=lambda s: sum(map(ord, s or "")) % 6)


# --- shared helpers ------------------------------------------------------------------------------
async def _employees(s) -> list[Employee]:
    return await staff_cache.employees(s)


async def staff_member(request: Request, s) -> Employee | None:
    """The employee logged in to the company console (signed company_session cookie), if any."""
    emp_id = auth.read_session(request.cookies.get(auth.COMPANY_COOKIE), purpose="company")
    return next((e for e in await _employees(s) if e.id == emp_id), None) if emp_id else None


async def _actor(request: Request, s) -> Employee | None:
    """Who is using the console: the logged-in employee. Only with DEMO_TOOLS on (development) can the person
    switcher act as someone else."""
    staff_id, actor_id = auth.actor_ids(request)   # the switcher's cookie is signed and bound to this login
    if not actor_id:
        return None
    emps = await _employees(s)
    return next((e for e in emps if e.id == actor_id), None) or next((e for e in emps if e.id == staff_id), None)


async def render(request: Request, s, name: str, **ctx) -> HTMLResponse:
    from onboarding import captcha, google_auth, i18n
    ctx.update(request=request, actor=await _actor(request, s), employees=await _employees(s), path=request.url.path,
               staff=await staff_member(request, s), DEMO_TOOLS=get_settings().demo_tools, FEATURES=features(),
               lang=i18n.lang_of(request), LANGS=i18n.LANGS, captcha_key=captcha.site_key(), google_on=google_auth.configured())
    if "vendor_account" not in ctx:
        ctx["vendor_account"] = await vendor_account(request, s)
    return templates.TemplateResponse(request, name, ctx)


# --- vendor portal sessions ---------------------------------------------------------------------
async def vendor_account(request: Request, s) -> VendorAccount | None:
    acct_id = auth.read_session(request.cookies.get(auth.COOKIE))
    return await s.get(VendorAccount, acct_id) if acct_id else None


def safe_next(nxt: str | None, default: str = "/vendor") -> str:
    """Only local paths: never redirect a vendor to another site after login."""
    return nxt if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt else default


async def _needs_login(s, app: Application | None) -> bool:
    """A new invite needs an account. An application already tied to an account needs that login.
    One submitted as a guest (demo shortcut) stays reachable with its private link, as before."""
    if app is None:
        return True
    return (await s.execute(select(VendorLink).where(VendorLink.application_id == app.id))).scalar_one_or_none() is not None


def login_redirect(nxt: str, register: bool = False) -> RedirectResponse:
    return RedirectResponse(f"/vendor/{'register' if register else 'login'}?next={quote(nxt)}", status_code=303)


async def claim(s, acct: VendorAccount, *, invite: Invite | None = None, app: Application | None = None) -> VendorLink:
    """Tie an invite and/or an application to the vendor's account (first account wins)."""
    if app is not None:
        link = (await s.execute(select(VendorLink).where(VendorLink.application_id == app.id))).scalar_one_or_none()
        if link and link.account_id != acct.id:
            raise HTTPException(403, "This registration belongs to another vendor account. Log in with that account.")
        if link:
            return link
    if invite is not None:
        link = (await s.execute(select(VendorLink).where(VendorLink.invite_id == invite.id))).scalars().first()
        if link and link.account_id != acct.id:
            raise HTTPException(403, "This invitation was already opened with another vendor account. Log in with that account.")
        if link:
            if app is not None and link.application_id is None:
                link.application_id = app.id
            return link
    link = VendorLink(account_id=acct.id, invite_id=invite.id if invite else None, application_id=app.id if app else None)
    s.add(link)
    return link


def demo_key(demo: str) -> str:
    """The `demo` form/query value, honoured only in demo mode and only when it names a known scenario. It pre-fills
    the form and supplies sample files; it never replaces the vendor login or the invite token check."""
    return demo if demo and get_settings().demo_tools and demo in demo_catalog() else ""


def demo_catalog() -> dict[str, dict]:
    """Demo scenarios the UI can pre-fill: form values + files (fixtures, or private inputs locally)."""
    out = {}
    for key, sc in SCENARIOS.items():
        files = {p.stem: p for p in sorted((DOCS / key).glob("*"))}
        out[key] = dict(title=sc["title"], expected=sc["expected"], form=sc["form"], files=files, invite_scenario=None if sc.get("bill") else key,
                        resubmission_of=sc.get("resubmission_of"), private=False, bill=bool(sc.get("bill")))
    variants = {
        "handwritten_nilgiri": ("Hand-written PAN on plain paper (phone photo)", "PENDING_VENDOR", {"pan_card": "handwritten_pan.jpg"}),
        "ai_pan_nilgiri": ("AI-generated PAN card image", "PENDING_REVIEW", {"pan_card": "ai_pan.jpg"}),
        "screenshot_gst_nilgiri": ("Screenshot instead of the GST certificate PDF", "PENDING_VENDOR", {"gst_certificate": "screenshot_gst.png"}),
        "ai_cheque_nilgiri": ("AI-generated cancelled cheque", "PENDING_REVIEW", {"bank_proof": "web_cheque_kotak_ai_generated.png"}),
    }
    base = out["happy_nilgiri"]
    for key, (title, expected, swap) in variants.items():
        paths = {slot: PRIVATE / fn for slot, fn in swap.items()}
        if all(p.exists() for p in paths.values()):  # private inputs exist only on Shubham's laptop
            out[key] = dict(base, title=title, expected=expected, files={**base["files"], **paths}, private=True)
    out["unsolicited_nilgiri"] = dict(base, title="Registers for future work (no invite)", expected="PENDING_REVIEW", invite_scenario=None, bill=False,
                                      form={**base["form"], "supply_note": "Corrugated boxes and export packaging, about 20 tonnes a month from our Bengaluru plant"})
    from onboarding.demo_data import PUBLISHED_SCENARIOS
    for key, sc in PUBLISHED_SCENARIOS.items():   # real, self-published documents: only where the files are on this machine
        paths = {slot: PRIVATE / "published" / fn for slot, fn in sc["files"].items()}
        if all(p.exists() for p in paths.values()):
            out[key] = dict(title=sc["title"], expected=sc["expected"], form=sc["form"], files=paths, invite_scenario=key,
                            resubmission_of=None, private=True, bill=False)
    return out


LAUNCHER = "demo:"   # Invite.scenario_key prefix of invites made by the scenario launcher (/demo/{key}, staff only)


def _new_invite_from(tpl: Invite, launcher_key: str = "") -> Invite:
    return Invite(token=secrets.token_urlsafe(18), sponsor_id=tpl.sponsor_id, company_name=tpl.company_name, contact_email=tpl.contact_email,
                  business_reason=tpl.business_reason, spend_category=tpl.spend_category, spend_band=tpl.spend_band,
                  high_spend=tpl.high_spend, scenario_key=f"{LAUNCHER}{launcher_key}" if launcher_key else "",
                  expires_at=now() + timedelta(days=14))


def _launcher_guest(inv: Invite | None, demo: str) -> bool:
    """A scenario-launcher invite opened for its own scenario: the demo vendor may fill it in without a vendor login.
    Needs demo mode and a known scenario (demo_key), and the invite must have been made by the launcher for that same
    scenario. A real invite with ?demo= still needs the vendor login (S1)."""
    if not (demo and demo_key(demo) == demo and inv is not None and inv.scenario_key.startswith(LAUNCHER)):
        return False
    launched = inv.scenario_key[len(LAUNCHER):]
    # ... or the scenario that resubmits it (wrongdoc_tejas_resubmit on a wrongdoc_tejas launcher invite)
    return demo == launched or SCENARIOS.get(demo, {}).get("resubmission_of") == launched


async def _latest_run(s, app_id: int) -> Run | None:
    return (await s.execute(select(Run).where(Run.application_id == app_id).order_by(Run.id.desc()))).scalars().first()


_read_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()  # one per event loop


async def _reads(**queries):
    """Run independent read-only queries at the same time, each on its own pooled connection.
    Every query is a network round trip to the database; sent together they cost about one.
    At most db.WARM_CONNECTIONS at once (so they reuse open connections instead of opening new
    ones), and a query whose connection drops is simply asked again: it only reads."""
    slots = _read_slots.setdefault(asyncio.get_running_loop(), asyncio.Semaphore(WARM_CONNECTIONS))

    async def one(fn):
        for attempt in range(3):
            try:
                async with slots, read_sessions()() as s:
                    return await fn(s)
            except Exception as e:
                if attempt == 2 or not is_dropped_connection(e):
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
    keys = list(queries)
    return dict(zip(keys, await asyncio.gather(*(one(queries[k]) for k in keys))))


def _all(stmt):
    return lambda s: _scalars(s, stmt)


async def _scalars(s, stmt) -> list:
    return list((await s.execute(stmt)).scalars().all())


def _rows(stmt):
    async def go(s):
        return list((await s.execute(stmt)).all())
    return go


# --- dashboard ----------------------------------------------------------------------------------
@router.get("/console")
async def dashboard():
    """Home is drawn by the browser app from GET /api/v1/console/home."""
    from onboarding.appshell import app_shell
    return app_shell()


async def _dashboard_ctx(request: Request, s) -> dict:
    actor = await _actor(request, s)
    full = access.full_view(actor)
    emps = {e.id: e for e in await _employees(s)}
    q = dict(rows=_rows(select(Run, Application).join(Application, Application.id == Run.application_id).order_by(Run.id.desc()).limit(200)),
             invites=_all(select(Invite)),
             docs=_rows(select(Document.run_id, Document.read["origin"].as_string())),  # just where each reading came from
             bills=_all(select(Bill)),
             acted=_rows(select(HumanAction.run_id, HumanAction.action)),
             open_vbills=_all(select(VendorBill).where(VendorBill.status.in_(("awaiting_confirmation", "for_review", "vendor_fix", "ready_for_approval", "blocked", "approved")))))
    if full:
        q["alerts"] = _rows(select(RiskEvent, Vendor).join(Vendor, Vendor.id == RiskEvent.vendor_pk).where(RiskEvent.status == "open").order_by(RiskEvent.opened_at))
        q["vnames"] = _rows(select(Vendor.id, Vendor.vendor_id, Vendor.display_name))
    if actor and not full:
        q["vbills"] = _all(select(VendorBill).where(VendorBill.engaged_employee_id == actor.id, VendorBill.status == "awaiting_confirmation"))
    r = await _reads(**q)
    rows = r["rows"]
    sponsors = {i.id: i for i in r["invites"]}
    origin: dict[int, list[str]] = {}
    for run_id, org in r["docs"]:
        origin.setdefault(run_id, []).append(org or "")
    bills = {b.application_id: b for b in r["bills"]}
    runs = []
    for run, app in rows:
        inv = sponsors.get(app.invite_id)
        b = bills.get(app.id)
        secs = (run.finished_at - run.started_at).total_seconds() if run.finished_at and run.started_at else None
        o = origin.get(run.id, [])
        who = (emps[inv.sponsor_id].name if inv and inv.sponsor_id in emps else
               ((emps[b.engaged_employee_id].name if b.engaged_employee_id in emps else "unknown") + " · bill" if b else ""))
        runs.append(dict(run=run, app=app, sponsor=who, bill=b, owned=access.owns_application(actor, inv, b),
                         seconds=secs, fraud=(run.summary or {}).get("fraud"), resubmission=bool(run.parent_run_id),
                         reads="live" if o and all(x == "live" for x in o) else ("saved" if o else "")))
    if not full:  # a requester sees only what they asked for
        runs = [r for r in runs if r["owned"]]
    apps = {r["app"].id: r["app"] for r in runs}
    counts = {k: sum(1 for a in apps.values() if a.current_status == k) for k in ("ACTIVE", "APPROVED", "PENDING_VENDOR", "PENDING_REVIEW", "REJECTED")}
    done = [r for r in runs if r["seconds"] is not None]
    stats = dict(applications=len(apps), runs=len(runs), avg_seconds=round(sum(r["seconds"] for r in done) / len(done), 1) if done else None,
                 fraud=sum(1 for r in runs if r["fraud"]), first_pass=sum(1 for r in runs if not r["resubmission"] and r["run"].status == "APPROVED"))
    to_confirm = 0
    if actor and not full:
        to_confirm = sum(1 for r in runs if r["bill"] and r["bill"].engaged_employee_id == actor.id and r["bill"].confirmation == "awaiting"
                         and r["app"].current_status not in ("REJECTED", "ACTIVE"))
        to_confirm += len(r["vbills"])
    from onboarding.ap.models import InvoiceCase
    bill_cases = {c.bill_id: c for c in (await _reads(c=_all(select(InvoiceCase))))["c"]}
    todo = _todo(actor, runs, sponsors, emps, r["acted"], r["open_vbills"], bill_cases)
    if actor:   # invoices a teammate tagged me on come first: someone is waiting for my answer
        from onboarding.ap.models import BillTag
        mine = (await _reads(t=_rows(select(BillTag, VendorBill).join(VendorBill, VendorBill.id == BillTag.bill_id)
                                    .where(BillTag.to_employee_id == actor.id, BillTag.done_at.is_(None)).order_by(BillTag.id))))["t"]
        names = {x["app"].id: x["app"].legal_name for x in runs}
        tagged = [dict(href=f"/bills/{vb.id}#team", ref=vb.ref, name=names.get(vb.application_id, vb.vendor_id), verb="Answer",
                       detail=f"{emps[tg.from_employee_id].name.split()[0] if tg.from_employee_id in emps else 'A teammate'} tagged you: {tg.note[:70]}",
                       status="BILL", risk=vb.risk_tier, fraud=False, since=tg.created_at, amount=vb.amount, waiting=_waiting(tg.created_at))
                  for tg, vb in mine]
        todo = tagged + [t for t in todo if t["href"] not in {x["href"].split("#")[0] for x in tagged}]
    if full:    # a vendor asked to change its bank account or contact: Finance decides bank accounts, reviewers the rest
        from onboarding.ap.models import ChangeRequest
        from onboarding.models import VendorMaster
        cr = await _reads(c=_all(select(ChangeRequest).where(ChangeRequest.status == "submitted").order_by(ChangeRequest.id)),
                          m=_rows(select(VendorMaster.vendor_id, VendorMaster.legal_name)))
        vm_names = dict(cr["m"])
        todo = [dict(href="/review#changes", ref=c.erp_vendor_id, name=vm_names.get(c.erp_vendor_id, c.erp_vendor_id), verb="Decide",
                     detail="Bank account change" if c.kind == "bank_account" else "Contact change", status="CHANGE",
                     risk="high" if c.kind == "bank_account" else "low", fraud=False, since=c.created_at, waiting=_waiting(c.created_at))
                for c in cr["c"] if c.kind != "bank_account" or actor.role == "checker"] + todo
    if not feature("payables"):   # no bills or change requests on the to-do list (or the menu counts) when Payables is off
        todo = [t for t in todo if t["status"] not in ("BILL", "CHANGE")]
    work =await _work_summary(s, actor, full, counts, todo)
    vnames = {pk: (vid, name) for pk, vid, name in r.get("vnames", [])}
    alerts = [dict(ev=ev, vendor=vend, related=vnames.get(ev.related_vendor_pk)) for ev, vend in r.get("alerts", [])]
    alerts.sort(key=lambda a: a["ev"].severity != "fraud")
    if not feature("intel"):
        alerts = []   # risk flags come from Vendor Intelligence
    from onboarding import followups
    chasing = ([w for w in await followups.waiting(s) if full or (actor and w.requester and w.requester.id == actor.id)]
               if feature("followups") else [])
    open_invites = sum(1 for i in r["invites"] if i.status == "open" and (full or (actor and i.sponsor_id == actor.id))
                       and (not i.expires_at or _utc(i.expires_at) > now()))
    return dict(runs=runs, counts=counts, stats=stats, catalog=demo_catalog(), full=full, open_invites=open_invites,
                to_confirm=to_confirm, todo=todo, alerts=alerts, work=work, chasing=chasing, FU=followups)


async def _work_summary(s, actor, full, counts, todo) -> dict:
    """Actionable work for the dashboard, from stored records only."""
    from onboarding import bills as BL
    from onboarding.ap.models import AuditEvent, InvoiceCase
    r = await _reads(vbills=_all(select(VendorBill)), cases=_all(select(InvoiceCase)),
                     risks=_all(select(RiskEvent).where(RiskEvent.status == "open")),
                     audit=_all(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(8)) if full else _none,
                     decisions=_rows(select(HumanAction, Employee, Application).join(Employee, Employee.id == HumanAction.employee_id)
                                     .join(Run, Run.id == HumanAction.run_id).join(Application, Application.id == Run.application_id)
                                     .order_by(HumanAction.id.desc()).limit(8)) if full else _none)
    cases = {c.bill_id: c for c in r["cases"]}
    bills = [b for b in r["vbills"] if full or access.can_open_bill(actor, b)]
    st = [(b, BL.invoice_status(b, cases.get(b.id))) for b in bills]
    amt = lambda rows: sum(money(b.amount) or 0 for b, _ in rows)  # noqa: E731
    review = [(b, x) for b, x in st if x in ("Needs internal review", "Blocked for investigation")]
    holds = [(b, x) for b, x in st if x == "Payment on hold"]
    unpaid = [(b, x) for b, x in st if x in ("Approved for payment", "Payment in progress")]
    recent = [dict(at=e.at, who=e.actor_label, what=BL.BILL_ACTION_LABEL.get(e.action, e.action.replace("_", " ")), label=e.entity_label,
                   href=f"/bills/{e.entity_id}" if e.entity == "invoice" else "", override=e.override) for e in r["audit"]]
    recent += [dict(at=a.at, who=f"{emp.name} ({ROLE_LABEL.get(emp.role, emp.role)})", what=ACTIONS.get(a.action, a.action.replace("_", " ")), label=app.ref,
                    href=f"/runs/{a.run_id}", override=a.action in ("override_reject", "review_approve")) for a, emp, app in r["decisions"]]
    recent.sort(key=lambda x: x["at"].replace(tzinfo=None), reverse=True)
    return dict(reviews=len(todo), waiting=counts.get("PENDING_VENDOR", 0) + sum(1 for _, x in st if x == "Needs vendor information"),
                high_risk=sum(1 for x in r["risks"] if x.severity == "fraud"), inv_review=len(review), inv_review_amt=amt(review),
                holds=len(holds), holds_amt=amt(holds), unpaid=len(unpaid), unpaid_amt=amt(unpaid), recent=recent[:8])


_TODO_VERB = {"activate": "Activate vendor", "review_approve": "Review and decide", "ask_vendor": "Review and decide", "review_reject": "Review and decide",
              "confirm_reject": "Confirm the rejection", "override_reject": "Confirm the rejection",
              "confirm_engagement": "Confirm you engaged them", "deny_engagement": "Confirm you engaged them"}
_TODO_BILL_VERB = {"confirm_engagement": "Confirm the work was done", "deny_engagement": "Confirm the work was done",
                   "approve_payment": "Approve the bill", "ask_vendor": "Approve the bill", "reject_bill": "Approve the bill"}


def _todo(actor, runs, invites, emps, acted, vbills, cases: dict | None = None) -> list[dict]:
    """What this person can act on right now, using the same rules as the buttons (segregation of duties,
    high risk to the Finance controller): the latest run of each application, and open vendor bills."""
    from onboarding.bills import allowed_bill_actions

    if not actor:
        return []
    done = {(run_id, a) for run_id, a in acted}
    latest: dict[int, dict] = {}
    for x in runs:  # newest first
        latest.setdefault(x["app"].id, x)
    names = {x["app"].id: x["app"].legal_name for x in runs}
    out = []
    for x in latest.values():
        run, app, b = x["run"], x["app"], x["bill"]
        if app.current_status == "REJECTED" and any((run.id, a) in done for a in ("confirm_reject", "review_reject", "override_reject")):
            continue  # already decided
        acts = _allowed_actions(run, app, invites.get(app.invite_id), actor, b, emps.get(b.engaged_employee_id) if b else None)
        open_ = [a for a, v in acts.items() if not v["blocked"]]
        if open_:
            out.append(dict(href=f"/runs/{run.id}", ref=app.ref, name=app.legal_name, verb=_TODO_VERB.get(open_[0], "Open"),
                            status=app.current_status, risk=run.risk_tier, fraud=x["fraud"], since=run.finished_at or run.started_at))
    from onboarding import bills as BL
    cases = cases or {}
    for b in vbills:
        case = cases.get(b.id)
        acts = allowed_bill_actions(b, actor, emps.get(b.engaged_employee_id), case)
        open_ = [a for a, v in acts.items() if not v["blocked"] and a not in ("block", "hold_payment")]   # a real next step, not a safety valve
        if open_:
            verb = BL.next_action(b, case)[0] or _TODO_BILL_VERB.get(open_[0], "Open")
            out.append(dict(href=f"/bills/{b.id}", ref=b.ref, name=names.get(b.application_id, b.vendor_id), detail=f"Invoice {b.invoice_number}", verb=verb,
                            status="BILL", risk=b.risk_tier, fraud=b.fraud, since=getattr(b, "created_at", None), amount=b.amount))
    for t in out:
        t["waiting"] = _waiting(t["since"])
    # most urgent first: fraud signals, then high risk, then whatever has waited longest
    out.sort(key=lambda t: (not t["fraud"], t["risk"] != "high", _utc(t["since"]) or now()))
    return out


def _utc(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _waiting(dt) -> str:
    """'waiting 3 h' / 'waiting 2 days', for the action queue."""
    if dt is None:
        return ""
    mins = max(0, int((now() - _utc(dt)).total_seconds() // 60))
    if mins < 60:
        return f"waiting {mins} min"
    if mins < 48 * 60:
        return f"waiting {mins // 60} h"
    return f"waiting {mins // (24 * 60)} days"


@router.post("/act-as")
async def act_as(request: Request, employee_id: int = Form(...)):
    if not get_settings().demo_tools:
        raise HTTPException(404, "Not found")
    back = request.headers.get("referer") or "/console"
    resp = RedirectResponse(back, status_code=303)
    staff_id = auth.read_session(request.cookies.get(auth.COMPANY_COOKIE), purpose="company")
    resp.set_cookie(auth.ACTOR_COOKIE, auth.make_actor(employee_id, staff_id), max_age=auth.MAX_AGE, httponly=True, samesite="lax")
    return resp


# --- invites (sponsor) -------------------------------------------------------------------------
@router.get("/invites")
async def invites_page():
    """Drawn by the browser app from GET /api/v1/invites."""
    from onboarding.appshell import app_shell
    return app_shell()


async def invites(request: Request) -> dict:
    """Recent invites this person may see (requesters: their own), with the application each one led to."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        emps = {e.id: e for e in await _employees(s)}
        r = await _reads(invites=_all(select(Invite).order_by(Invite.id.desc()).limit(100)),
                         apps=_all(select(Application).where(Application.invite_id.is_not(None))))
        rows = r["invites"]
        if not access.full_view(actor):
            rows = [i for i in rows if actor and i.sponsor_id == actor.id]
        apps = {a.invite_id: a for a in r["apps"]}
        return dict(invites=rows, emps=emps, apps=apps, actor=actor)


@router.post("/invites")
async def create_invite(request: Request, company_name: str = Form(...), contact_email: str = Form(...), business_reason: str = Form(...),
                        spend_category: str = Form(...), spend_band: str = Form(...)):
    token = await create_invite_core(request, company_name, contact_email, business_reason, spend_category, spend_band)
    return RedirectResponse(f"/invites?created={token}", status_code=303)


async def create_invite_core(request: Request, company_name: str, contact_email: str, business_reason: str, spend_category: str, spend_band: str) -> str:
    """A requester invites a vendor. Returns the invite token. Used by the form route and POST /api/v1/invites."""
    if spend_band not in SPEND_BANDS:
        raise HTTPException(400, "Choose the expected yearly spend.")
    if not company_name.strip() or "@" not in contact_email or not spend_category.strip():
        raise HTTPException(400, "Fill in the vendor's name, contact email and spend category.")
    async with sessions()() as s:
        actor = await _actor(request, s)
        if not actor or actor.role != "sponsor":
            raise HTTPException(403, "Only a requester (the employee who needs the vendor) can send an invite.")
        if len(business_reason.strip()) < 10:
            raise HTTPException(400, "Please give a business reason (at least a sentence): it's shown to the approver.")
        inv = Invite(token=secrets.token_urlsafe(18), sponsor_id=actor.id, company_name=company_name.strip(), contact_email=contact_email.strip(),
                     business_reason=business_reason.strip(), spend_category=spend_category.strip(), spend_band=spend_band,
                     high_spend=spend_band in HIGH_SPEND, expires_at=now() + timedelta(days=14))
        s.add(inv)
        await s.commit()
        return inv.token


# --- vendor form ---------------------------------------------------------------------------------
@router.get("/demo/{key}")
async def demo_start(key: str):
    """Start a demo scenario as a vendor would: a fresh invite (cloned from the seeded one), then the form."""
    if not get_settings().demo_tools:
        raise HTTPException(404, "Not found")
    cat = demo_catalog()
    if key not in cat or not scenario_on(cat[key]):
        raise HTTPException(404, "Unknown scenario")
    sc = cat[key]
    if sc.get("bill"):
        return RedirectResponse(f"/bill?demo={key}", status_code=303)
    if sc["invite_scenario"] is None:
        return RedirectResponse(f"/apply?demo={key}", status_code=303)
    async with sessions()() as s:
        tpl = (await s.execute(select(Invite).where(Invite.scenario_key == sc["invite_scenario"]).order_by(Invite.id))).scalars().first()
        if not tpl:
            raise HTTPException(409, "Reference data not loaded. Use 'Reset data' on the System page.")
        inv = _new_invite_from(tpl, launcher_key=key)
        s.add(inv)
        await s.commit()
        return RedirectResponse(f"/apply/{inv.token}?demo={key}", status_code=303)


async def _invite_or_404(s, token: str) -> Invite:
    inv = (await s.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "This invite link isn't valid. Please contact the person who invited you.")
    await s.refresh(inv, ["sponsor"])
    return inv


async def _vendor_link(s, token: str) -> tuple[Invite | None, Bill | None, Application | None]:
    """A vendor's private link is an invite token or, for bill-first registrations, a bill token."""
    bill = (await s.execute(select(Bill).where(Bill.token == token))).scalar_one_or_none()
    if bill:
        return None, bill, await s.get(Application, bill.application_id)
    inv = await _invite_or_404(s, token)
    app = (await s.execute(select(Application).where(Application.invite_id == inv.id))).scalars().first()
    return inv, None, app


async def _resolve_employee(s, text: str) -> Employee | None:
    """Match 'Priya Nair', 'priya', 'priya.nair@parakh.tech' to one employee (None if unknown or ambiguous)."""
    t = " ".join((text or "").lower().replace(".", " ").split())
    if not t:
        return None
    emps = await _employees(s)
    exact = [e for e in emps if (text or "").strip().lower() in (e.name.lower(), e.email.lower())]
    if exact:
        return exact[0]
    words = set(t.replace("@", " ").split())
    hits = [e for e in emps if set(e.name.lower().split()) <= words or (len(words) == 1 and words <= set(e.name.lower().split()))]
    return hits[0] if len(hits) == 1 else None


@router.get("/apply/{token}", response_class=HTMLResponse)
async def apply_form(request: Request, token: str, demo: str = ""):
    demo = demo_key(demo)
    async with sessions()() as s:
        inv, bill, app = await _vendor_link(s, token)
        acct = await vendor_account(request, s)
        if not acct and not _launcher_guest(inv, demo) and await _needs_login(s, app):
            return login_redirect(f"/apply/{token}", register=app is None)
        if acct:
            await claim(s, acct, invite=inv, app=app)
            await s.commit()
        prev, message = None, None
        if app:
            prev = await _latest_run(s, app.id)
            if not _vendor_may_resubmit(app, prev):
                return RedirectResponse(f"/status/{token}", status_code=303)
            message = (await s.execute(select(Message).where(Message.run_id == prev.id, Message.audience == "vendor"))).scalars().first()
        prev_docs = {d.slot: d for d in (await s.execute(select(Document).where(Document.run_id == prev.id))).scalars()} if prev else {}
        start = {"legal_name": inv.company_name, "contact_email": inv.contact_email} if inv else {}
        if acct and not prev:
            start = {"legal_name": start.get("legal_name") or acct.company_name, "contact_name": acct.contact_name, "contact_email": acct.email}
        return await render(request, s, "apply.html", invite=inv, bill=bill, token=token, app=app, prev=prev, prev_docs=prev_docs, message=message,
                            **_form_context(demo, prev.form if prev else start))


@router.get("/apply", response_class=HTMLResponse)
async def apply_unsolicited(request: Request, demo: str = ""):
    demo = demo_key(demo)
    async with sessions()() as s:
        if not await vendor_account(request, s):
            return login_redirect("/apply")
        return await render(request, s, "apply.html", invite=None, bill=None, token="", app=None, prev=None, prev_docs={}, message=None, **_form_context(demo, {}))


@router.get("/bill", response_class=HTMLResponse)
async def bill_form(request: Request, demo: str = ""):
    """Self-registration for a vendor who already did work for us and wants to be paid."""
    demo = demo_key(demo)
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return login_redirect("/bill", register=True)
        start = {"bill_mode": True}
        if acct:
            start |= {"legal_name": acct.company_name, "contact_name": acct.contact_name, "contact_email": acct.email}
        return await render(request, s, "apply.html", invite=None, bill=None, bill_mode=True, token="", app=None, prev=None, prev_docs={},
                            message=None, **_form_context(demo, start))


def _form_context(demo: str, values: dict) -> dict:
    cat = demo_catalog()
    sc = cat.get(demo)
    if sc:
        values = dict(sc["form"])
    states = sorted({v for k, v in V.GST_STATE_CODES.items() if "legacy" not in v and k not in ("97", "99")})
    return dict(values=values, submit_token=secrets.token_urlsafe(16), demo=demo if sc else "", demo_files={k: p.name for k, p in sc["files"].items()} if sc else {},
                demo_title=sc["title"] if sc else "", states=states, catalog=cat)


async def _collect_form(request: Request, rate_limit: bool = True) -> tuple[dict, dict[str, tuple[str, bytes]], str]:
    """rate_limit False: the caller checks SUBMIT_PER_IP itself (apply_submit exempts scenario-launcher invites)."""
    if rate_limit:
        security.SUBMIT_PER_IP.check(security.client_ip(request))   # each submission sends documents to Gemini
    data = await request.form()
    f = {k: (str(data.get(k) or "")).strip() for k in ("business_type", "legal_name", "proprietor_name", "gstin", "pan", "cin", "llpin", "address",
                                                       "city", "state", "pin", "contact_name", "contact_email", "contact_phone", "alt_contact_name", "alt_contact_email", "alt_contact_phone", "bank_holder",
                                                       "bank_account", "ifsc", "udyam_no", "country",
                                                       "tax_id", "swift", "postal_code", "supply_note")}
    for k in ("gstin", "pan", "cin", "llpin", "ifsc", "udyam_no", "tax_id", "swift"):
        f[k] = f[k].upper().replace(" ", "")
    f["bank_account"] = f["bank_account"].replace(" ", "").replace("-", "")
    f["country"] = f["country"] or "India"
    f["msme"] = data.get("msme") == "on"
    f["gst_registered"] = data.get("gst_registered", "on") == "on"
    # keep only the fields for the country chosen (the form hides the others, but they may still be filled in)
    if _countries.is_india(f["country"]):
        f["country"] = "India"
        for k in ("tax_id", "swift", "postal_code"):
            f[k] = ""
    else:
        for k in ("gstin", "pan", "cin", "llpin", "state", "pin", "ifsc", "udyam_no"):
            f[k] = ""
        f["msme"] = False
    from onboarding.prefill import parse_record
    rec = parse_record(str(data.get("prefill") or ""))
    if rec:
        f["prefill"] = rec          # what we read from the documents and suggested (R-PF-01 compares)
    if data.get("bill_mode") == "1":
        f["bill_mode"] = True
        f["bill_engaged_by"] = str(data.get("bill_engaged_by") or "").strip()   # the rest is read from the bill itself
    files: dict[str, tuple[str, bytes]] = {}
    for slot in SLOTS:
        up = data.get(slot)
        if up is not None and hasattr(up, "read") and getattr(up, "filename", ""):
            raw = await security.read_upload(up, SLOT_TITLE[slot])   # stops reading past 10 MB
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, f"{SLOT_TITLE[slot]} is larger than 10 MB. Please upload a smaller file.")
            if raw:
                security.require_document(raw, f"The {SLOT_TITLE[slot].lower()}")
                files[slot] = (up.filename, raw)
    f["_submit_token"] = str(data.get("submit_token") or "")[:100]   # popped by _submit_token(); never stored
    return f, files, demo_key(str(data.get("demo") or ""))


def _require_basics(form: dict) -> None:
    """The fields every registration needs, checked on the server too: a direct POST can skip the browser's check."""
    missing = [label for key, label in (("legal_name", "the legal name"), ("contact_email", "a contact email"))
               if not str(form.get(key) or "").strip()]
    if missing:
        raise HTTPException(400, f"Please enter {' and '.join(missing)}, then submit again.")


def _submit_token(form: dict) -> str | None:
    """The form's one-time submit token (apply.html sets a random one per page load): a double submit makes one run."""
    return form.pop("_submit_token", "") or None


def _fill_files(files: dict, demo: str, prev_files: dict[str, tuple[str, bytes]], form: dict) -> dict:
    """Uploaded file > demo scenario file > the file sent last time (resubmissions)."""
    sc = demo_catalog().get(demo)
    needed = SLOTS[:3] + (["udyam_certificate"] if form.get("msme") else []) + (["invoice"] if form.get("bill_mode") else [])
    for slot in needed:
        if slot in files:
            continue
        if sc and slot in sc["files"]:
            p = sc["files"][slot]
            files[slot] = (p.name, p.read_bytes())
        elif slot in prev_files:
            files[slot] = prev_files[slot]
    return files


@router.get("/prequalified")
async def prequalified_page():
    """Drawn by the browser app from GET /api/v1/prequalified."""
    from onboarding.appshell import app_shell
    return app_shell()


async def prequalified(request: Request, q: str = "") -> list[dict]:
    """Suppliers who registered for future work and passed the checks. Not payable until an employee asks for one."""
    from onboarding.models import ReliabilityCheck
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        if not actor:
            raise access.forbid("Pre-qualified suppliers")
        apps = (await s.execute(select(Application).where(Application.current_status == "PREQUALIFIED").order_by(Application.id.desc()))).scalars().all()
        runs = {a.id: await _latest_run(s, a.id) for a in apps}
        checks = {}
        for c in (await s.execute(select(ReliabilityCheck).where(ReliabilityCheck.application_id.in_([a.id for a in apps] or [-1]))
                                  .order_by(ReliabilityCheck.id))).scalars():
            checks[c.application_id] = c
        rows = [dict(app=a, run=runs[a.id], form=(runs[a.id].form or {}) if runs[a.id] else {}, check=checks.get(a.id)) for a in apps]
        if q:
            rows = [x for x in rows if q.lower() in f"{x['app'].legal_name} {x['form'].get('supply_note', '')} {x['form'].get('city', '')} {x['form'].get('state', '')}".lower()]
        return rows


@router.post("/prequalified/{app_id}/request")
async def prequalified_request(request: Request, app_id: int, business_reason: str = Form(""), spend_category: str = Form(""), spend_band: str = Form("")):
    run_id = await prequalified_request_core(request, app_id, business_reason, spend_category, spend_band)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


async def prequalified_request_core(request: Request, app_id: int, business_reason: str, spend_category: str, spend_band: str) -> int:
    """A requester needs a pre-qualified supplier: that's the business need. The supplier is invited on the spot and
    every check runs again on what they sent (bank, registries, documents), so nothing stale becomes payable.
    Returns the new run's id. Used by the form route and POST /api/v1/prequalified/{id}/request."""
    async with sessions()() as s:
        actor = await _actor(request, s)
        if not actor or actor.role != "sponsor":
            raise HTTPException(403, "Only a requester (the employee who needs the supplier) can ask for one.")
        app = await s.get(Application, app_id)
        if not app or app.current_status != "PREQUALIFIED":
            raise HTTPException(409, "This supplier isn't on the pre-qualified list any more.")
        if len(business_reason.strip()) < 10:
            raise HTTPException(400, "Please give a business reason (at least a sentence): it's shown to the approver.")
        if spend_band not in SPEND_BANDS:
            raise HTTPException(400, "Choose the expected spend.")
        prev = await _latest_run(s, app.id)
        f = dict(prev.form or {})
        inv = Invite(token=secrets.token_urlsafe(18), sponsor_id=actor.id, company_name=app.legal_name, contact_email=f.get("contact_email", ""),
                     business_reason=business_reason.strip(), spend_category=spend_category.strip() or (f.get("supply_note") or "")[:100],
                     spend_band=spend_band, high_spend=spend_band in HIGH_SPEND, expires_at=now() + timedelta(days=14))
        s.add(inv)
        await s.flush()
        app.invite_id, app.current_status = inv.id, "IN_PROGRESS"
        files = {}
        for d in (await s.execute(select(Document).where(Document.run_id == prev.id))).scalars():
            files[d.slot] = (d.filename, (await s.get(StoredFile, d.sha256)).data)
        f.pop("prefill", None)
        run = await create_run(s, f, files, invite_token=inv.token, parent_run_id=prev.id)
        await s.commit()
    runner.start(run.id)
    return run.id


@router.post("/runs/{run_id}/reliability")
async def reliability_again(request: Request, run_id: int):
    """Run the reliability check again (news and watch lists change)."""
    from onboarding import reliability
    async with read_sessions()() as s:
        access.require_full(await _actor(request, s), "The reliability check")
    await reliability.check_run(run_id)
    return RedirectResponse(f"/runs/{run_id}#reliability", status_code=303)




@router.post("/apply/read")
async def apply_read(request: Request, slot: str = Form(...), file: UploadFile = File(...)):
    """Upload first: read one document and suggest form values (onboarding/prefill.py). Suggests only; the
    pipeline reads every document again after submission. Limited per visitor so the reader can't be abused."""
    from onboarding.ai.read import read_with_cache
    from onboarding.prefill import suggestions
    if slot not in ("gst_certificate", "pan_card", "bank_proof", "udyam_certificate"):
        raise HTTPException(400, "Unknown document")
    if get_settings().rate_limits and not security.READ_PER_IP.allow(security.client_ip(request)):
        return JSONResponse({"ok": False, "message": security.READ_PER_IP.message}, status_code=429)
    try:
        raw = await security.read_upload(file)   # stops reading past 10 MB
    except HTTPException:
        return JSONResponse({"ok": False, "message": "Please upload a PDF, JPG or PNG under 10 MB."}, status_code=413)
    if not raw or len(raw) > MAX_BYTES:
        return JSONResponse({"ok": False, "message": "Please upload a PDF, JPG or PNG under 10 MB."}, status_code=400)
    mime = security.sniff(raw) or ""                      # what the file really is, not what its name says
    if mime not in security.ALLOWED_MIME:
        return JSONResponse({"ok": False, "message": "Please upload a PDF, JPG or PNG."}, status_code=400)
    try:
        res, _ = await asyncio.wait_for(read_with_cache(raw, mime, prefer="cache"), timeout=45)
    except asyncio.TimeoutError:
        res = None
    if not res or not res.ok or not res.read:
        return JSONResponse({"ok": False, "message": "We couldn't read this file just now. Please type the details below; we'll still check the file after you submit."})
    return JSONResponse({"ok": True, **suggestions(slot, res.read)})


@router.post("/apply/{token}")
async def apply_submit(request: Request, token: str):
    form, files, demo = await _collect_form(request, rate_limit=False)
    submit_token = _submit_token(form)
    _require_basics(form)
    async with sessions()() as s:
        inv, bill, app = await _vendor_link(s, token)
        guest = _launcher_guest(inv, demo)
        if not guest:   # scenario-launcher invites are exempt in demo mode, so rehearsals and recordings don't hit the limit
            security.SUBMIT_PER_IP.check(security.client_ip(request))
        acct = await vendor_account(request, s)
        if not acct and not guest and await _needs_login(s, app):
            return login_redirect(f"/apply/{token}")
        if acct:
            await claim(s, acct, invite=inv, app=app)
        if bill and bill.confirmation == "awaiting":
            emp = await _resolve_employee(s, form.get("bill_engaged_by", ""))
            bill.engaged_by_text, bill.engaged_employee_id = form.get("bill_engaged_by", ""), emp.id if emp else None
        prev_files, parent = {}, None
        if app:
            prev = await _latest_run(s, app.id)
            if not _vendor_may_resubmit(app, prev):
                return RedirectResponse(f"/status/{token}", status_code=303)
            parent = prev.id
            for d in (await s.execute(select(Document).where(Document.run_id == prev.id))).scalars():
                sf = await s.get(StoredFile, d.sha256)
                prev_files[d.slot] = (d.filename, sf.data)
        files = _fill_files(files, demo, prev_files, form)
        run = await create_run(s, form, files, invite_token=token if inv else None, parent_run_id=parent, submit_token=submit_token)
        if acct:
            await claim(s, acct, invite=inv, app=await s.get(Application, run.application_id))
        ref = (await s.get(Application, run.application_id)).ref
        await s.commit()
    runner.start(run.id)
    return _after_submit(request, run, acct, demo, ref, "update" if parent else "registration")


def _after_submit(request: Request, run: Run, acct: VendorAccount | None, demo: str, ref: str = "",
                  kind: str = "registration") -> RedirectResponse:
    """A vendor sees the thank-you page. The internal live view only for a demo shortcut taken by someone who is also
    logged in to the company console (the staff scenario launcher); a vendor-only browser never lands on a staff page."""
    staff = auth.read_session(request.cookies.get(auth.COMPANY_COOKIE), purpose="company") is not None
    if acct and not (demo and staff):
        return RedirectResponse(f"/thanks?for={kind}&ref={ref}", status_code=303)
    return RedirectResponse(f"/runs/{run.id}?from=vendor", status_code=303)


@router.post("/bill")
async def bill_submit(request: Request):
    form, files, demo = await _collect_form(request)
    submit_token = _submit_token(form)
    _require_basics(form)
    form["bill_mode"] = True
    for k in BILL_FIELDS:
        form.setdefault(k, "")
    files = _fill_files(files, demo, {}, form)
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return login_redirect("/bill")
        run = await create_run(s, form, files, invite_token=None, submit_token=submit_token)
        if not (await s.execute(select(Bill.id).where(Bill.application_id == run.application_id))).first():   # a double submit: one bill
            emp = await _resolve_employee(s, form.get("bill_engaged_by", ""))
            s.add(Bill(application_id=run.application_id, token=secrets.token_urlsafe(18), engaged_by_text=form.get("bill_engaged_by", ""),
                       engaged_employee_id=emp.id if emp else None))
        if acct:
            await claim(s, acct, app=await s.get(Application, run.application_id))
        ref = (await s.get(Application, run.application_id)).ref
        await s.commit()
    runner.start(run.id)
    return _after_submit(request, run, acct, demo, ref, "bill")


@router.post("/apply")
async def apply_unsolicited_submit(request: Request):
    form, files, demo = await _collect_form(request)
    submit_token = _submit_token(form)
    _require_basics(form)
    files = _fill_files(files, demo, {}, form)
    async with sessions()() as s:
        acct = await vendor_account(request, s)
        if not acct:
            return login_redirect("/apply")
        run = await create_run(s, form, files, invite_token=None, submit_token=submit_token)
        ref = (await s.get(Application, run.application_id)).ref
        if acct:
            await claim(s, acct, app=await s.get(Application, run.application_id))
            await s.commit()
    runner.start(run.id)
    return _after_submit(request, run, acct, demo, ref, "future")


@router.get("/status/{token}", response_class=HTMLResponse)
async def vendor_status(request: Request, token: str):
    """What the vendor sees: their reference, status and the messages sent to them."""
    async with sessions()() as s:
        inv, bill, app = await _vendor_link(s, token)
        msgs, run = [], None
        if app:
            run = await _latest_run(s, app.id)
            run_ids = [r for (r,) in (await s.execute(select(Run.id).where(Run.application_id == app.id))).all()]
            msgs = (await s.execute(select(Message).where(Message.run_id.in_(run_ids), Message.audience == "vendor", Message.state == "sent")
                                    .order_by(Message.id.desc()))).scalars().all()
        company = inv.company_name if inv else (run.form.get("legal_name") if run else "")
        return await render(request, s, "status.html", invite=inv, bill=bill, company=company, app=app, run=run, msgs=msgs, token=token)


# --- run view ------------------------------------------------------------------------------------
def _event_dict(e: RunEvent, full: bool = True) -> dict:
    """What the browser gets: rule titles and results only. Raw evidence (which can hold a PAN or an
    account number) stays server-side and is shown masked on the decision page. A requester gets the
    stages and their one-line summaries, not the individual checks."""
    ev = dict(e.evidence or {})
    if not full:
        ev.pop("rules", None)
    if "rules" in ev:
        ev["rules"] = [{k: r.get(k) for k in ("rule_id", "result", "title")} for r in ev["rules"]]
    ev = {k: v for k, v in ev.items() if k in ("rules", "slot", "origin", "form", "status")}
    return dict(seq=e.seq, stage=e.stage, state=e.state, summary=e.summary, evidence=ev, at=_fmt_dt(e.at))


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_view(request: Request, run_id: int):
    async with read_sessions()() as s:
        row = (await s.execute(select(Run, Application, Invite, Bill).join(Application, Application.id == Run.application_id)
                               .outerjoin(Invite, Invite.id == Application.invite_id).outerjoin(Bill, Bill.application_id == Application.id)
                               .where(Run.id == run_id))).first()
        if not row:
            raise HTTPException(404, "No such run")
        run, app, inv, bill = row
        actor = await _actor(request, s)
        if not access.can_open_application(actor, inv, bill):
            raise access.forbid("This application")
        full = access.full_view(actor)
        emps = {e.id: e for e in await _employees(s)}
        sponsor = emps.get(inv.sponsor_id) if inv else None
        bill_emp = emps.get(bill.engaged_employee_id) if bill and bill.engaged_employee_id else None
        app_runs = select(Run.id).where(Run.application_id == app.id)
        r = await _reads(
            events=_all(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)),
            docs=_all(select(Document).where(Document.run_id == run_id)),
            rules=_all(select(RuleResult).where(RuleResult.run_id == run_id).order_by(RuleResult.id)),
            facts=_all(select(Fact).where(Fact.run_id == run_id).order_by(Fact.id)),
            msgs=_all(select(Message).where(Message.run_id == run_id).order_by(Message.id)),
            actions=_rows(select(HumanAction, Employee).join(Employee, Employee.id == HumanAction.employee_id)
                          .where(HumanAction.run_id.in_(app_runs)).order_by(HumanAction.id)),
            history=_all(select(Run).where(Run.application_id == app.id).order_by(Run.id)),
            vendor=_all(select(VendorMaster).where(VendorMaster.source_run_id.in_(app_runs)).order_by(VendorMaster.id).limit(1)),
            profile=_rows(select(Vendor.vendor_id).join(VendorApplication, VendorApplication.vendor_pk == Vendor.id).where(VendorApplication.application_id == app.id)),
            snap=_rows(select(DecisionSnapshot.replay_ok, DecisionSnapshot.replay_note, DecisionSnapshot.reconstructed).where(DecisionSnapshot.run_id == run_id)),
        )
        events = [_event_dict(e, full) for e in r["events"]]
        docs = sorted(r["docs"], key=lambda d: SLOTS.index(d.slot) if d.slot in SLOTS else 99)
        msgs = {m.audience: m for m in r["msgs"]}  # the latest message per audience
        history = r["history"]
        latest = history[-1].id == run.id
        return await render(request, s, "run.html", run=run, app=app, invite=inv, sponsor=sponsor, bill=bill, bill_emp=bill_emp, full=full,
                            fact_issues=_fact_issues(r["rules"]) if full else {}, profile_id=(r["profile"] or [[None]])[0][0] if feature("intel") else None, snap=(r["snap"] or [None])[0],
                            rights=_decision_rights(run, app, inv, bill, bill_emp, list(emps.values())) if latest else [],
                            vendor_token=inv.token if inv else (bill.token if bill else ""), events=events, stages=stages_for(run.form), docs=docs,
                            finished_ago=(now() - _utc(run.finished_at)).total_seconds() if run.finished_at else None,
                            rules=r["rules"], facts=r["facts"], vendor_msg=msgs.get("vendor"),
                            all_vendor_msgs=[m for m in r["msgs"] if m.audience == "vendor"], internal=msgs.get("internal"),
                            actions=r["actions"], history=history, latest=latest, vendor=(r["vendor"] or [None])[0],
                            allowed=_allowed_actions(run, app, inv, actor, bill, bill_emp), from_vendor=request.query_params.get("from") == "vendor",
                            reliab=await _reliability(s, app.id) if full and feature("reliability") else None)


async def _reliability(s, application_id: int):
    from onboarding import reliability
    return await reliability.latest(s, application_id)


def _fact_of(rule: RuleResult) -> str | None:
    """Which key fact a check is about, so a failed check shows next to the fact it puts in doubt."""
    rid, t = rule.rule_id, f" {(rule.title or '').lower()}"
    if "ifsc" in t:
        return "Bank branch"
    if rid in ("R-SRC-BANK", "R-BANK-01", "R-RISK-02", "R-NAME-03", "R-XD-04") or " account" in t or "cheque" in t:
        return "Bank account"
    if rid.startswith("R-MSME") or "udyam" in t:
        return "MSME (Udyam)"
    if rid in ("R-SRC-GST", "R-XD-01", "R-XD-03") or "gstin" in t:
        return "GSTIN"
    if rid in ("R-SRC-PAN", "R-SRC-PAN2", "R-XD-02") or " pan" in t:
        return "PAN"
    if rid.startswith("R-NAME") or " name" in t:
        return "Legal name"
    return None


def _fact_issues(rules: list[RuleResult]) -> dict[str, list[dict]]:
    """Failed or warning checks per fact, worst first: 'conflict' (a person must decide or it's rejected),
    'fix' (the vendor must fix it) or 'warn'."""
    out: dict[str, list[dict]] = {}
    for r in rules:
        if r.result not in ("FAIL", "WARN"):
            continue
        fact = _fact_of(r)
        if not fact:
            continue
        kind = "warn" if r.result == "WARN" else ("fix" if r.outcome_if_fail == "VENDOR" else "conflict")
        out.setdefault(fact, []).append(dict(rule=r.rule_id, title=r.title, kind=kind))
    for v in out.values():
        v.sort(key=lambda i: ("conflict", "fix", "warn").index(i["kind"]))
    return out


_RIGHT_VERB = {"activate": "activate", "review_approve": "approve", "ask_vendor": "ask the vendor", "review_reject": "reject",
               "confirm_reject": "confirm the rejection", "override_reject": "send it to review", "confirm_engagement": "confirm the work",
               "deny_engagement": "deny the work", "rerun": "re-run the checks"}


def _decision_rights(run, app, inv, bill, bill_emp, employees) -> list[dict]:
    """For each employee: what they may decide on this application now, and why not (segregation of duties,
    high risk to the Finance controller). Same function as the buttons, so the panel can't disagree with them."""
    order = {"sponsor": 0, "maker": 1, "checker": 2}
    out = []
    for e in sorted(employees, key=lambda e: (order.get(e.role, 9), e.name)):
        acts = _allowed_actions(run, app, inv, e, bill, bill_emp)
        if not acts:
            return []
        can = [_RIGHT_VERB.get(a, a) for a, v in acts.items() if not v["blocked"]]
        decisive = [v["blocked"] for a, v in acts.items() if v["blocked"] and a in ("activate", "review_approve", "review_reject", "confirm_reject")]
        why = (decisive or [v["blocked"] for v in acts.values() if v["blocked"]] or [""])[0]
        requester_id = inv.sponsor_id if inv else (bill.engaged_employee_id if bill else None)
        if e.role == "sponsor" and e.id != requester_id and why.startswith("Segregation"):
            why = "Requesters don't approve vendors: Procurement or Finance decides."
        elif e.id == requester_id and why.startswith("Segregation"):
            why = "Requested this vendor, so can't approve, activate or reject it."
        out.append(dict(emp=e, can=can, why=why))
    return out


async def _guard_run(request: Request, s, run_id: int) -> bool:
    """Can the person acting open this run? (used by the live-view feeds)"""
    run = await s.get(Run, run_id)
    if not run:
        return True
    app = await s.get(Application, run.application_id)
    inv = await s.get(Invite, app.invite_id) if app.invite_id else None
    bill = (await s.execute(select(Bill).where(Bill.application_id == app.id))).scalar_one_or_none()
    actor = await _actor(request, s)
    if not access.can_open_application(actor, inv, bill):
        raise access.forbid("This application")
    return access.full_view(actor)


@router.get("/runs/{run_id}/events")
async def run_events(request: Request, run_id: int, after: int = 0):
    async with read_sessions()() as s:
        full = await _guard_run(request, s, run_id)
        evs = (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after).order_by(RunEvent.seq))).scalars().all()
        run = await s.get(Run, run_id)
        return JSONResponse({"events": [_event_dict(e, full) for e in evs], "state": run.state if run else "missing"})


@router.get("/runs/{run_id}/stream")
async def run_stream(request: Request, run_id: int, after: int = 0):
    """Server-sent events, tailing run_events in the database (so a refresh or a second viewer sees the same thing)."""
    async with read_sessions()() as s:
        full = await _guard_run(request, s, run_id)

    async def gen():
        last, started, quiet = after, time.monotonic(), 0
        while time.monotonic() - started < 300:
            async with read_sessions()() as s:
                evs = (await s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > last).order_by(RunEvent.seq))).scalars().all()
                run = await s.get(Run, run_id)
            finished = False
            for e in evs:
                last = e.seq
                yield f"id: {e.seq}\ndata: {json.dumps(_event_dict(e, full))}\n\n"
                finished = finished or (e.stage == "decision" and e.state in ("done", "failed"))
            if finished or run is None or (run.state == "interrupted" and not evs):
                yield "event: end\ndata: {}\n\n"
                return
            quiet = 0 if evs else quiet + 1
            if quiet and quiet % 20 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.4)
        yield "event: end\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/files/{sha}")
async def file_view(request: Request, sha: str):
    async with sessions()() as s:
        access.require_full(await _actor(request, s), "Vendors' documents")
        sf = await s.get(StoredFile, sha)
        if not sf:
            raise HTTPException(404, "No such file")
        return security.file_response(sf.data, sf.mime)


# --- human actions ---------------------------------------------------------------------------------
ACTIONS = {
    "activate": "Activate vendor",
    "confirm_reject": "Confirm rejection and notify the vendor",
    "override_reject": "Don't reject: send to internal review",
    "review_approve": "Approve and activate",
    "ask_vendor": "Ask the vendor for something",
    "review_reject": "Reject",
    "confirm_engagement": "Yes, I engaged this vendor",
    "deny_engagement": "No, I didn't engage them",
}


def _vendor_may_resubmit(app: Application, prev: Run | None) -> bool:
    """The vendor may send the form again when we asked them to fix something, or when the last run failed or was
    interrupted (nothing was decided)."""
    if prev is not None and prev.state in ("failed", "interrupted"):
        return app.current_status in ("IN_PROGRESS", "PENDING_REVIEW", "PENDING_VENDOR")
    return app.current_status == "PENDING_VENDOR" and (prev is None or prev.state == "done")


def _allowed_actions(run: Run, app: Application, inv: Invite | None, actor: Employee | None, bill: Bill | None = None,
                     bill_emp: Employee | None = None) -> dict:
    """Which actions apply now, and for each, whether the current person may take it (and why not)."""
    if run.state in ("failed", "interrupted") and app.current_status not in ("ACTIVE", "REJECTED", "PREQUALIFIED"):
        why = ("Sign in as an employee first." if not actor else
               "" if actor.role in ("maker", "checker") else "Only Procurement or Finance can re-run the checks.")
        return {"rerun": dict(label="Re-run checks", blocked=why, needs_comment=False)}
    if run.state != "done":
        return {}
    status = app.current_status
    applicable = {"APPROVED": ["activate"], "REJECTED": ["confirm_reject", "override_reject"],
                  "PENDING_REVIEW": ["review_approve", "ask_vendor", "review_reject"]}.get(status, [])
    if bill and bill_emp and bill.confirmation == "awaiting" and status not in ("REJECTED", "ACTIVE"):
        applicable = ["confirm_engagement", "deny_engagement"] + applicable
    requester_id = inv.sponsor_id if inv else (bill.engaged_employee_id if bill else None)
    out = {}
    high = run.risk_tier == "high" or (run.summary or {}).get("fraud") or (bill is not None and bill.confirmation == "denied")
    for a in applicable:
        why = ""
        if a in ("confirm_engagement", "deny_engagement"):
            if not actor or actor.id != bill.engaged_employee_id:
                why = f"Only {bill_emp.name}, who the vendor named, can answer this."
            out[a] = dict(label=ACTIONS[a], blocked=why, needs_comment=a == "deny_engagement")
            continue
        if not actor:
            why = "Sign in as an employee first."
        elif actor.role == "sponsor" or (requester_id and requester_id == actor.id):
            why = "Segregation of duties: the employee who requested this vendor can't approve, activate or reject it."
        elif a in ("activate", "review_approve") and bill and bill.confirmation == "awaiting":
            why = (f"Waiting for {bill_emp.name} to confirm they engaged this vendor." if bill_emp
                   else "Nobody has confirmed engaging this vendor: find out who did before approving.")
        elif a in ("activate", "review_approve") and bill and bill.confirmation == "denied":
            why = f"{bill_emp.name if bill_emp else 'The named employee'} says they didn't engage this vendor."
        elif a in ("review_reject",) and actor.role != "checker":
            why = "Only the Finance controller can reject after review."
        elif a in ("activate", "review_approve") and high and actor.role != "checker":
            why = "High-risk or fraud-flagged: needs the Finance controller."
        label = "Add to pre-qualified suppliers" if a in ("activate", "review_approve") and not inv and not bill else ACTIONS[a]
        out[a] = dict(label=label, blocked=why, needs_comment=a in ("override_reject", "review_approve", "ask_vendor", "review_reject"))
    return out


async def _activate(s, run: Run, app: Application) -> VendorMaster:
    n = (await s.execute(select(func.count(VendorMaster.id)).where(VendorMaster.source_run_id.is_not(None)))).scalar() or 0
    f = run.form
    k = 1001 + n
    while (await s.execute(select(VendorMaster.id).where(VendorMaster.vendor_id == f"V-{k}"))).first():   # never reuse a taken ID
        k += 1
    vm = VendorMaster(vendor_id=f"V-{k}", legal_name=f.get("legal_name", ""), pan=f.get("pan", "").upper(), gstin=f.get("gstin", "").upper(),
                      account=f.get("bank_account", ""), ifsc=f.get("ifsc", "").upper(), status="Active", source_run_id=run.id)
    s.add(vm)
    app.current_status = "ACTIVE"
    hi = f"Hi {f.get('contact_name') or 'there'},"
    bill_note = (f"\n\nYour bill {f.get('bill_invoice_number')} for {inr(money(f.get('bill_amount')))} has been passed to accounts payable. "
                 "It is paid once a purchase order is raised for the work and the receipt is recorded." if f.get("bill_mode") else "")
    s.add(Message(run_id=run.id, audience="vendor", subject=f"Your vendor account is active (Ref {app.ref})", state="sent",
                  body=f"{hi}\n\n{f.get('legal_name')} is now an active vendor. Your vendor ID is {vm.vendor_id}. Please quote it on every invoice; "
                       f"invoices are paid after the purchase order and goods receipt are matched.{bill_note}\n\nVendor Onboarding Team"))
    return vm


@router.post("/runs/{run_id}/action")
async def run_action(request: Request, run_id: int, action: str = Form(...), comment: str = Form(""), reliability_ack: str = Form("")):
    async with sessions()() as s:
        run = await s.get(Run, run_id)
        if not run:
            raise HTTPException(404, "No such run")
        app = (await s.execute(select(Application).where(Application.id == run.application_id).with_for_update())).scalar_one()  # one decision at a time
        latest = await _latest_run(s, app.id)
        if latest.id != run.id:
            raise HTTPException(409, "A newer submission exists; act on that one.")
        inv = await s.get(Invite, app.invite_id) if app.invite_id else None
        actor = await _actor(request, s)
        comment = comment.strip()
        bill =(await s.execute(select(Bill).where(Bill.application_id == app.id))).scalar_one_or_none()
        if not access.can_open_application(actor, inv, bill):
            raise access.forbid("This application")
        bill_emp = await s.get(Employee, bill.engaged_employee_id) if bill and bill.engaged_employee_id else None
        allowed = _allowed_actions(run, app, inv, actor, bill, bill_emp)
        if action not in allowed:
            raise HTTPException(409, "That action doesn't apply to this application right now.")
        if allowed[action]["blocked"]:
            raise HTTPException(403, allowed[action]["blocked"])
        if allowed[action]["needs_comment"] and len(comment.strip()) < 5:
            raise HTTPException(400, "Please write a short reason: it goes on the audit trail.")
        if action == "rerun":   # a new run from the stored form and documents; the failed one stays as it was
            s.add(HumanAction(run_id=run.id, employee_id=actor.id, action=action, comment=auth.audit_comment(request, comment)))
            from onboarding.pipeline import rerun
            new = await rerun(s, run)
            runner.start(new.id)
            return RedirectResponse(f"/runs/{new.id}", status_code=303)
        if feature("reliability") and action in ("activate", "review_approve") and reliability_ack != "1":
            rc = await _reliability(s, app.id)
            if rc and rc.level == "high":
                raise HTTPException(400, "This vendor's reliability check found serious concerns. Read the warning on the page before approving.")
        prequalify = action in ("activate", "review_approve") and not inv and not bill
        held = (await s.execute(select(Message).where(Message.run_id == run.id, Message.audience == "vendor", Message.state == "held"))).scalars().first()
        hi = f"Hi {run.form.get('contact_name') or 'there'},"
        if action == "confirm_engagement":
            bill.confirmation, bill.decided_at = "confirmed", now()
        elif action == "deny_engagement":
            bill.confirmation, bill.decided_at = "denied", now()
            if app.current_status in ("APPROVED", "PENDING_VENDOR"):
                app.current_status = "PENDING_REVIEW"  # a person who never engaged them: the Finance controller decides
        elif prequalify:   # no business need yet: checked and listed, not payable (no vendor ID, no bank account in the vendor master)
            app.current_status = "PREQUALIFIED"
            s.add(Message(run_id=run.id, audience="vendor", subject=f"You're on our pre-qualified supplier list (Ref {app.ref})", state="sent",
                          body=f"{hi}\n\nThank you for registering. We've checked your details and added {run.form.get('legal_name')} to our pre-qualified "
                               "suppliers. When one of our teams needs what you supply, they'll contact you; we'll confirm your details again then and "
                               "give you a vendor ID.\n\nVendor Onboarding Team"))
        elif action == "activate":
            if held:
                held.state = "sent"
            await _activate(s, run, app)
        elif action == "confirm_reject":
            if held:
                held.state = "sent"
            app.current_status = "REJECTED"
        elif action == "override_reject":
            app.current_status = "PENDING_REVIEW"
            if held:
                held.state = "draft"
        elif action == "review_approve":
            await _activate(s, run, app)
        elif action == "ask_vendor":
            app.current_status = "PENDING_VENDOR"
            s.add(Message(run_id=run.id, audience="vendor", subject=f"Action needed: your vendor registration (Ref {app.ref})", state="sent",
                          body=f"{hi}\n\n{comment}\n\nUpdate your submission using the same link you received from us.\n\nVendor Onboarding Team"))
        elif action == "review_reject":
            app.current_status = "REJECTED"
            s.add(Message(run_id=run.id, audience="vendor", subject=f"Your vendor registration (Ref {app.ref}): unable to proceed", state="sent",
                          body=f"{hi}\n\nThank you for your interest. After review, we're unable to proceed with your registration at this time.\n\nVendor Onboarding Team"))
        ha = HumanAction(run_id=run.id, employee_id=actor.id, action=action, comment=auth.audit_comment(request, comment))
        s.add(ha)
        await s.commit()
    if feature("intel"):
        from onboarding.intel.project import on_decision
        await on_decision(ha.id)   # Vendor Intelligence: evidence of the decision, closes the risk flags it addressed; never raises
    from onboarding import mailer
    mailer.start(run.id)       # email the vendor the message this decision released, in the background
    return RedirectResponse(f"/runs/{run_id}#actions", status_code=303)


# --- outbox, document check, assumptions, system -----------------------------------------------------
@router.get("/outbox")
async def outbox_page():
    """Drawn by the browser app from GET /api/v1/outbox."""
    from onboarding.appshell import app_shell
    return app_shell()


async def outbox(request: Request) -> dict:
    """Every message to vendors, follow-up notes to requesters, and the Contact us inbox (reviewers and Finance only)."""
    async with read_sessions()() as s:
        access.require_full(await _actor(request, s), "The outbox")
        from onboarding.models import FollowUp
        steps = (await s.execute(select(FollowUp))).scalars().all()
        notes = [f.note_id for f in steps if f.note_id]
        kind = {f.message_id: f.kind for f in steps if f.message_id} | {f.note_id: "note" for f in steps if f.note_id}
        emp_by_note = {f.note_id: f.to_employee_id for f in steps if f.note_id}
        emps = {e.id: e for e in await _employees(s)}
        rows = (await s.execute(select(Message, Run, Application).join(Run, Run.id == Message.run_id).join(Application, Application.id == Run.application_id)
                                .where(or_(Message.audience == "vendor", Message.id.in_(notes or [-1]))).order_by(Message.id.desc()).limit(100))).all()
        from onboarding.models import EmailDelivery
        mails = {d.message_id: d for d in (await s.execute(select(EmailDelivery).where(EmailDelivery.message_id.in_([m.id for m, _, _ in rows] or [-1])))).scalars()}
        from onboarding.models import ContactMessage
        inbox = (await s.execute(select(ContactMessage).order_by(ContactMessage.id.desc()).limit(50))).scalars().all()
        return dict(rows=rows, mails=mails, kind=kind, inbox=inbox, note_to={k: emps.get(v) for k, v in emp_by_note.items()})


@router.get("/check")
async def doc_check():
    """Drawn by the browser app; it posts files to /api/v1/check."""
    from onboarding.appshell import app_shell
    return app_shell()


def _check_one(filename: str, raw: bytes, label: str = "") -> dict:
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    a = assess(raw, mime, None)
    d = a.as_dict()
    d["facts"] = {k: v for k, v in d["facts"].items() if k != "text"}
    return dict(filename=filename + (f" ({label})" if label else ""), size=len(raw), mime=mime, auth=d)


async def check_files(request: Request, files: list, with_sample: bool) -> list[dict]:
    """Forensic check of up to two files, without the AI (reviewers and Finance only)."""
    async with sessions()() as s:
        access.require_full(await _actor(request, s), "The document check")
    results = []
    if with_sample and PUBLIC_SAMPLE.exists():
        results.append(_check_one(PUBLIC_SAMPLE.name, PUBLIC_SAMPLE.read_bytes(), "genuine sample"))
    for up in files:
        if up is not None and getattr(up, "filename", ""):
            raw = await security.read_upload(up)   # stops reading past 10 MB
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, "File larger than 10 MB")
            security.require_document(raw)
            results.append(_check_one(up.filename, raw))
    return results


@router.get("/assumptions")
async def assumptions():
    """Help: drawn by the browser app (its table comes from GET /api/v1/help)."""
    from onboarding.appshell import app_shell
    return app_shell()


@router.get("/system")
async def system_page():
    """Drawn by the browser app from GET /api/v1/system."""
    from onboarding.appshell import app_shell
    return app_shell()


async def system(request: Request) -> dict:
    """Live health of everything the process depends on, and the follow-up job's state (reviewers and Finance only)."""
    st = get_settings()
    checks = []
    t = time.monotonic()
    async with read_sessions()() as s:
        access.require_full(await _actor(request, s), "The system page")
        from onboarding.sources import ifsc_lookup
        models = (Employee, Invite, Application, Run, VendorMaster)

        async def db_counts():
            try:  # one query for all the counts, sent while the bank lookup is in flight
                row = (await s.execute(select(*(select(func.count()).select_from(m).scalar_subquery() for m in models)))).one()
                return (db_label(st.database_url), True, f"connected in {round((time.monotonic() - t) * 1000)} ms; "
                        + ", ".join(f"{m.__tablename__}: {v}" for m, v in zip(models, row)))
            except Exception as e:
                return ("Database", False, type(e).__name__)
        db_check, r = await asyncio.gather(db_counts(), ifsc_lookup("HDFC0000009"))
        checks.append(db_check)
        checks.append(("Gemini API key", bool(st.gemini_api_key), f"models: {st.gemini_model} (fallback {st.gemini_fallback_model})" if st.gemini_api_key else "missing: documents can only be read from saved readings"))
        checks.append(("Bank branch lookup (Razorpay IFSC, live)", r.live and r.status == "FOUND", r.source + (f": {r.data.get('BANK')}, {r.data.get('BRANCH')}" if r.data else "")))
        checks.append(("Registry connectors", True, "GST registry, PAN registry, penny-drop, MCA (CIN), Udyam"))
        checks.append(("Background runs", True, f"{runner.busy()} running now (max 2 at a time)"))
        from onboarding import followups
        from onboarding.models import FollowUp
        last = (await s.execute(select(FollowUp).order_by(FollowUp.id.desc()).limit(1))).scalar()
        chasing = await followups.waiting(s) if feature("followups") else []
        return dict(checks=checks, chasing=chasing, last_fu=last)


@router.post("/system/followups")
async def followups_now(request: Request):
    """Run the follow-up job now (it also runs by itself every few hours)."""
    async with sessions()() as s:
        access.require_full(await _actor(request, s), "Running follow-ups")
    r = await run_followups(request)
    return RedirectResponse(f"/system?done=followups&r={r['reminders']}&e={r['escalations']}&w={r['waiting']}", status_code=303)


async def run_followups(request: Request) -> dict:
    """Run the follow-up job now. Used by the form route and POST /api/v1/system/followups."""
    async with sessions()() as s:
        access.require_full(await _actor(request, s), "Running follow-ups")
    from onboarding import followups
    return await followups.run_once()


@router.post("/system/reset")
async def reset(request: Request, passcode: str = Form(...)):
    await reset_data(request, passcode)
    return RedirectResponse("/system?done=reset", status_code=303)


async def reset_data(request: Request, passcode: str) -> None:
    """Delete every run and reload the reference data. Needs a reviewer and the admin passcode."""
    async with sessions()() as s:
        access.require_full(await _actor(request, s), "Resetting the demo")
    from onboarding.config import reset_passcode
    code = reset_passcode()   # no default: blank, short or "change-me" means reset is off
    if not code:
        raise HTTPException(403, "Reset is switched off: set ADMIN_PASSCODE (at least 12 characters) on the server first.")
    who = security.client_ip(request)
    if not security.RESET_WRONG.allow_more(who):
        raise HTTPException(429, security.RESET_WRONG.message)
    if not secrets.compare_digest(passcode.encode(), code.encode()):
        security.RESET_WRONG.allow(who)   # count the wrong try
        raise HTTPException(403, "Wrong passcode")
    if runner.busy():
        raise HTTPException(409, "A run is in progress; try again in a minute.")
    from onboarding.seeding import seed
    await seed(reset=True, dispose=False, allow_remote=True)   # the passcode is the confirmation here


# --- Vendor Intelligence: vendor directory and Vendor 360 ------------------------------------------------------------
from sqlalchemy.orm import aliased  # noqa: E402

from onboarding.intel import vendor360 as V360  # noqa: E402
from onboarding.intel.crypto import decrypt  # noqa: E402
from onboarding.intel.models import (DecisionSnapshot, EvidenceItem, FactObservation, GraphEdge, GraphNode, RiskEvent, Vendor,  # noqa: E402
                                     VendorApplication, VendorIdentifier)


async def _none(_s) -> list:
    return []


def _owned_app_ids(actor, apps, invites: dict, bills: dict) -> set[int]:
    return {a.id for a in apps if access.owns_application(actor, invites.get(a.invite_id), bills.get(a.id))}


@router.get("/vendors")
async def vendor_directory_page():
    """Drawn by the browser app from GET /api/v1/vendors."""
    from onboarding.appshell import app_shell
    return app_shell()


async def vendor_directory(request: Request, q: str = "", status: str = "", risk: str = "", pay: str = "", inv: str = "", sort: str = "") -> dict:
    """Every canonical vendor: one row per legal entity, however many applications it made (for the API)."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        full = access.full_view(actor)
        r = await _reads(vendors=_all(select(Vendor).order_by(Vendor.id)),
                         links=_rows(select(VendorApplication.vendor_pk, Application).join(Application, Application.id == VendorApplication.application_id)),
                         pans=_rows(select(VendorIdentifier.vendor_pk, VendorIdentifier.display).where(VendorIdentifier.kind == "PAN", VendorIdentifier.status == "current")),
                         risks=_rows(select(RiskEvent.vendor_pk, RiskEvent.related_vendor_pk, RiskEvent.severity, RiskEvent.kind).where(RiskEvent.status == "open")),
                         gst=_rows(select(VendorIdentifier.vendor_pk, VendorIdentifier.display).where(VendorIdentifier.kind == "GSTIN", VendorIdentifier.status == "current")),
                         invites=_all(select(Invite)), bills=_all(select(Bill)), vbills=_all(select(VendorBill)))
        from onboarding import bills as BL
        from onboarding.ap.models import InvoiceCase
        cases = {c.bill_id: c for c in (await _reads(c=_all(select(InvoiceCase))))["c"]}
        vb_by_erp: dict[str, list] = {}
        for b in r["vbills"]:
            vb_by_erp.setdefault(b.vendor_id, []).append(b)
        apps_by_v: dict[int, list] = {}
        for vpk, app in r["links"]:
            apps_by_v.setdefault(vpk, []).append(app)
        owned = _owned_app_ids(actor, [a for _, a in r["links"]], {i.id: i for i in r["invites"]}, {b.application_id: b for b in r["bills"]}) if not full else set()
        pan = dict(r["pans"])
        gst: dict[int, list] = {}
        for vpk, g in r["gst"]:
            gst.setdefault(vpk, []).append(g)
        flags: dict[int, list] = {}
        kinds: dict[int, list] = {}
        for vpk, rel, sev, kind in r["risks"]:
            flags.setdefault(vpk, []).append(sev)
            kinds.setdefault(vpk, []).append(kind)
            if rel:
                flags.setdefault(rel, []).append("linked")
        rows = []
        for v in r["vendors"]:
            apps = sorted(apps_by_v.get(v.id, []), key=lambda a: a.id)
            if not full and not any(a.id in owned for a in apps):
                continue
            if q and q.lower() not in f"{v.display_name} {v.vendor_id} {v.erp_vendor_id}".lower():
                continue
            vb = vb_by_erp.get(v.erp_vendor_id, []) if v.erp_vendor_id else []
            if not full:
                vb = [b for b in vb if access.can_open_bill(actor, b)]
            msum = V360.money_summary(vb, cases, money)
            own = [f for f in flags.get(v.id, []) if f != "linked"]
            payel = "not_yet" if v.status != "active" else ("blocked" if "fraud" in own else "eligible")
            needs = [b for b in vb if BL.invoice_status(b, cases.get(b.id)) in ("Needs internal review", "Blocked for investigation", "Matched and ready for approval")]
            stamps = [a.created_at for a in apps] + [b.created_at for b in vb] + [v.updated_at]
            last = max((x for x in stamps if x), key=lambda d: d.replace(tzinfo=None), default=None)
            pending_app = next((a for a in reversed(apps) if a.current_status in ("PENDING_REVIEW", "APPROVED", "PENDING_VENDOR")), None)
            if own and full:
                nxt = {"shared_bank_account": "Investigate the shared bank account", "reused_document": "Review the reused document",
                       "identity_conflict": "Resolve the identity conflict", "blocklist": "Confirm the blocklist rejection",
                       "duplicate_registration": "Check for a duplicate record"}.get(kinds.get(v.id, [""])[0], "Review the open flag")
            elif needs:
                nxt = BL.next_action(needs[0], cases.get(needs[0].id))[0]
            elif pending_app:
                nxt = {"PENDING_REVIEW": f"Review {pending_app.ref}", "APPROVED": f"Activate ({pending_app.ref} approved)", "PENDING_VENDOR": "Waiting for the vendor"}[pending_app.current_status]
            elif msum["approved_unpaid"]:
                nxt = "Release approved payments"
            else:
                nxt = ""
            row = dict(v=v, apps=apps, pan=pan.get(v.id, "") if full else "", gstins=gst.get(v.id, []), flags=flags.get(v.id, []) if full else [],
                       pay=payel, msum=msum, needs=len(needs), last=last, next=nxt)
            if status and v.status != status:
                continue
            if risk == "flagged" and not own:
                continue
            if pay and payel != pay:
                continue
            if inv == "needs_review" and not needs:
                continue
            if inv == "unpaid" and not msum["approved_unpaid"]:
                continue
            rows.append(row)
        if sort == "activity":
            rows.sort(key=lambda x: x["last"].replace(tzinfo=None) if x["last"] else datetime.min, reverse=True)
        elif sort == "awaiting":
            rows.sort(key=lambda x: -x["msum"]["awaiting_review"])
        elif sort == "unpaid":
            rows.sort(key=lambda x: -x["msum"]["approved_unpaid"])
        else:
            rows.sort(key=lambda x: (not x["next"], x["v"].display_name.lower()))
        return dict(rows=rows, full=full)


@router.get("/vendors/{vendor_key}")
async def vendor_profile_page(vendor_key: str):
    """Drawn by the browser app from GET /api/v1/vendors/{id}."""
    from onboarding.appshell import app_shell
    return app_shell()


async def vendor_profile(request: Request, vendor_key: str) -> dict:
    """Vendor 360: who the vendor is, what proves it, who it's connected to, what's risky and what to do next."""
    async with read_sessions()() as s:
        actor = await _actor(request, s)
        full = access.full_view(actor)
        found = (await _reads(v=_all(select(Vendor).where(Vendor.vendor_id == vendor_key))))["v"]
        if not found:
            raise HTTPException(404, "No such vendor")
        v = found[0]
        src, dst = aliased(GraphNode), aliased(GraphNode)
        r = await _reads(
            apps=_all(select(Application).join(VendorApplication, VendorApplication.application_id == Application.id)
                      .where(VendorApplication.vendor_pk == v.id).order_by(Application.id)),
            runs=_all(select(Run).join(VendorApplication, VendorApplication.application_id == Run.application_id)
                      .where(VendorApplication.vendor_pk == v.id).order_by(Run.id)),
            idents=_all(select(VendorIdentifier).where(VendorIdentifier.vendor_pk == v.id).order_by(VendorIdentifier.id)),
            obs=_all(select(FactObservation).where(FactObservation.vendor_pk == v.id)),
            my_edges=_rows(select(GraphEdge, dst).join(src, src.id == GraphEdge.src_id).join(dst, dst.id == GraphEdge.dst_id)
                           .where(src.kind == "VENDOR", src.vendor_pk == v.id).order_by(GraphEdge.id)),
            risks=_all(select(RiskEvent).where(or_(RiskEvent.vendor_pk == v.id, RiskEvent.related_vendor_pk == v.id)).order_by(RiskEvent.opened_at)),
            evidence=_all(select(EvidenceItem).where(EvidenceItem.vendor_pk == v.id).order_by(EvidenceItem.id)),
            actions=_rows(select(HumanAction, Employee).join(Employee, Employee.id == HumanAction.employee_id).join(Run, Run.id == HumanAction.run_id)
                          .join(VendorApplication, VendorApplication.application_id == Run.application_id)
                          .where(VendorApplication.vendor_pk == v.id).order_by(HumanAction.id)),
            snaps=_rows(select(DecisionSnapshot.run_id, DecisionSnapshot.replay_ok, DecisionSnapshot.reconstructed)
                        .join(Run, Run.id == DecisionSnapshot.run_id).join(VendorApplication, VendorApplication.application_id == Run.application_id)
                        .where(VendorApplication.vendor_pk == v.id)),
            invites=_all(select(Invite)), bills=_all(select(Bill)), allv=_all(select(Vendor)),
            vbills=_all(select(VendorBill).where(VendorBill.vendor_id == v.erp_vendor_id).order_by(VendorBill.id.desc())) if v.erp_vendor_id else _none,
            docs=_all(select(Document).join(Run, Run.id == Document.run_id).join(VendorApplication, VendorApplication.application_id == Run.application_id)
                      .where(VendorApplication.vendor_pk == v.id)))
        invites, bills = {i.id: i for i in r["invites"]}, {b.application_id: b for b in r["bills"]}
        owned = _owned_app_ids(actor, r["apps"], invites, bills)
        if not full and not owned:
            raise access.forbid("This vendor's profile")
        dst_ids = [n.id for _, n in r["my_edges"]]
        r2 = await _reads(shared=_rows(select(GraphEdge, src, dst).join(src, src.id == GraphEdge.src_id).join(dst, dst.id == GraphEdge.dst_id)
                                       .where(GraphEdge.dst_id.in_(dst_ids), src.kind == "VENDOR", src.vendor_pk != v.id)) if dst_ids and full else _none)
        vendors_by_pk = {x.id: x for x in r["allv"]}
        conns = V360.connections(r["my_edges"], r2["shared"], vendors_by_pk, r["risks"]) if full else []
        other_ev_ids = [i["theirs"].evidence_item_id for c in conns for i in c["shared"] if i["theirs"].evidence_item_id]
        other_ev = (await _reads(e=_all(select(EvidenceItem).where(EvidenceItem.id.in_(other_ev_ids))) if other_ev_ids else _none))["e"]
        evidence = {e.id: e for e in [*r["evidence"], *other_ev]}
        runs_by_app: dict[int, list] = {}
        for run in r["runs"]:
            runs_by_app.setdefault(run.application_id, []).append(run)
        emps = await _employees(s)
        apps, rights_by_app = [], {}
        for a in r["apps"]:
            rs = runs_by_app.get(a.id, [])
            latest = rs[-1] if rs else None
            inv, bill = invites.get(a.invite_id), bills.get(a.id)
            if latest is not None:
                bill_emp = next((e for e in emps if bill and e.id == bill.engaged_employee_id), None)
                rights_by_app[a.id] = _decision_rights(latest, a, inv, bill, bill_emp, emps)
            apps.append(dict(app=a, runs=rs, latest=latest, invite=inv, bill=bill, owned=a.id in owned,
                             sponsor=next((e for e in emps if inv and e.id == inv.sponsor_id), None)))
        facts = V360.fact_history(r["obs"])
        risks = r["risks"] if full else []
        nba = V360.next_actions(v, [a for a in apps if full or a["owned"]], risks, facts if full else [], rights_by_app, evidence)
        full_bank = {}
        if access.sees_full_bank(actor) and v.status == "active":   # Finance releases payments: the real number, decrypted on demand
            full_bank = {i.id: decrypt(i.value_enc) for i in r["idents"] if i.kind == "BANK_ACCOUNT" and i.value_enc}
        doubts = V360.fact_doubts(v, r["my_edges"], risks) if full else {}
        # the supplier record: invoices, payments, purchase orders, documents
        from onboarding import bills as BL
        from onboarding.ap.models import InvoiceCase, PurchaseOrder
        gstins = [i.display for i in r["idents"] if i.kind == "GSTIN"]
        shas = list({d.sha256 for d in r["docs"]})
        app_ids = [a.id for a in r["apps"]]
        r3 = await _reads(cases=_all(select(InvoiceCase).where(InvoiceCase.bill_id.in_([b.id for b in r["vbills"]]))) if r["vbills"] else _none,
                          pos=_all(select(PurchaseOrder).where(PurchaseOrder.vendor_gstin.in_(gstins)).order_by(PurchaseOrder.id.desc())) if gstins and full else _none,
                          sizes=_rows(select(StoredFile.sha256, StoredFile.size).where(StoredFile.sha256.in_(shas))) if shas and full else _none,
                          reused=_rows(select(Document.sha256, Application.ref).join(Run, Run.id == Document.run_id).join(Application, Application.id == Run.application_id)
                                       .where(Document.sha256.in_(shas), Application.id.not_in(app_ids))) if shas and full else _none)
        cases = {c.bill_id: c for c in r3["cases"]}
        visible_bills = [b for b in r["vbills"] if full or access.can_open_bill(actor, b)]
        invoices = [dict(b=b, case=cases.get(b.id), status=BL.invoice_status(b, cases.get(b.id)), next=BL.next_action(b, cases.get(b.id))) for b in visible_bills]
        reused: dict[str, list] = {}
        for sha, ref in r3["reused"]:
            reused.setdefault(sha, []).append(ref)
        ev_by_sha: dict = {}
        for e in r["evidence"]:
            if e.kind == "document" and e.content_sha256:
                ev_by_sha.setdefault((e.content_sha256, e.run_id), []).append(e)
        documents = V360.document_rows(r["docs"], {x.id: x for x in r["runs"]}, {a.id: a for a in r["apps"]}, dict(r3["sizes"]), reused, ev_by_sha, r["obs"]) if full else []
        pay = V360.payment_eligibility(v, risks, facts) if full else ("", "")
        msum = V360.money_summary(visible_bills, cases, money)
        for x in invoices:   # invoice work joins the next-best-action list
            if x["next"][0] and x["status"] not in ("Paid", "Rejected", "Being checked", "Draft"):
                urgent = x["status"] == "Blocked for investigation"
                nba.insert(0 if urgent else len([a for a in nba if a["priority"] == "urgent"]),
                           dict(priority="urgent" if urgent else ("high" if x["status"] in ("Needs internal review", "Matched and ready for approval", "Approved for payment", "Payment on hold") else "normal"),
                                title=x["next"][0] + (f" ({x['b'].invoice_number or x['b'].ref})" if x["b"].invoice_number and x["b"].invoice_number not in x["next"][0] else "") + ".",
                                why=x["next"][1], detail="", evidence=[], who=["Finance"] if x["status"] in ("Approved for payment", "Payment in progress", "Payment on hold") else ["Procurement or Finance"],
                                href=f"/bills/{x['b'].id}", kind="invoice"))
        nba = [a for a in nba if a["kind"] != "none"] or nba
        return dict(v=v, apps=apps, idents=r["idents"], facts=facts, conns=conns, risks=risks, doubts=doubts,
                    invoices=invoices, pos=r3["pos"], documents=documents, pay=pay, msum=msum,
                    evidence=evidence, actions=r["actions"] if full else [], nba=nba, full=full, vendors_by_pk=vendors_by_pk,
                    lay=V360.layout(v, r["my_edges"], conns) if full else None, my_edges=r["my_edges"] if full else [],
                    snaps={rid: (ok, rec) for rid, ok, rec in r["snaps"]}, full_bank=full_bank)


@router.post("/runs/{run_id}/simulate", response_class=HTMLResponse)
async def simulate_run(request: Request, run_id: int, scenario: str = Form(...), rule_id: str = Form("")):
    """A counterfactual on this check's saved decision input. Writes only a simulation_runs row."""
    from onboarding.intel.models import SimulationRun
    from onboarding.intel.simulate import SimulationRefused, simulate
    async with sessions()() as s:
        actor = await _actor(request, s)
        if not actor or actor.role not in ("maker", "checker"):
            raise HTTPException(403, "Simulations are for the Procurement reviewer and the Finance controller.")
        run = await s.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "No such run")
        app = await s.get(Application, run.application_id)
        snap = (await s.execute(select(DecisionSnapshot).where(DecisionSnapshot.run_id == run_id))).scalars().first()
        try:
            res, refused = simulate(snap, scenario, rule_id, ref=app.ref), ""
        except SimulationRefused as e:
            res, refused = None, str(e)
        s.add(SimulationRun(run_id=run_id, actor_id=actor.id, scenario=scenario, params={"rule_id": rule_id}, result=res or {"refused": refused}))
        await s.commit()
    return templates.TemplateResponse(request, "_simulation.html", {"res": res, "refused": refused})
