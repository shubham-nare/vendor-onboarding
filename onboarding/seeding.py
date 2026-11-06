"""Create tables and load demo data. Idempotent. Used by scripts/seed.py and the app's "Reset demo"."""

from __future__ import annotations

import secrets
import sys
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from onboarding import demo_data as dd
from onboarding.db import engine
from onboarding import auth
from onboarding.config import database_host, get_settings, local_database
from onboarding.models import Base, Blocklist, Employee, Invite, SimRegistry, StaffLogin, VendorAccount, VendorMaster, now

EMPLOYEES = [
    dict(name="Priya Nair", department="Operations, Plant 2", role="sponsor", email="priya.nair@parakh.tech"),
    dict(name="Rahul Desai", department="Plant Head, Pune", role="sponsor", email="rahul.desai@parakh.tech"),
    dict(name="Arjun Mehta", department="Procurement", role="maker", email="arjun.mehta@parakh.tech"),
    dict(name="Kavita Rao", department="Finance", role="checker", email="kavita.rao@parakh.tech"),
]

# Demo logins (fictional people, shown on the login pages so anyone reviewing the demo can sign in): only in demo mode
# and only when DEMO_PASSWORD is set, with that password. Every employee logs in with their own email; one vendor
# account is ready, with no registration yet.
DEMO_PASSWORD = get_settings().demo_password
LEGACY_PUBLIC_PASSWORD = "demo_pass"   # was the default in the public repo: logins still using it are switched off
DEMO_COMPANY_EMAIL = "arjun.mehta@parakh.tech"
DEMO_VENDOR = dict(email=dd.KESARI["contact"]["email"], company_name=dd.KESARI["legal_name"], contact_name=dd.KESARI["contact"]["name"])
# The live happy-path beat of the demo video: Nilgiri's own contact person signs in to Nilgiri's invite. Not the
# invite's accounts@ address, which the golden tests register from the invite link.
DEMO_VENDOR_NILGIRI = dict(email="anitha@nilgiripack.example.com", company_name=dd.NILGIRI["legal_name"], contact_name=dd.NILGIRI["contact"]["name"])
DEMO_VENDORS = (DEMO_VENDOR, DEMO_VENDOR_NILGIRI)

INVITES = {  # scenario_key -> (sponsor, company, reason, category, band, high)
    "happy_nilgiri": ("Priya Nair", dd.NILGIRI["legal_name"], "Corrugated boxes and protective packaging for Plant 2, replacing a supplier with late deliveries", "Packaging", "10-25 lakh", False),
    "wrongdoc_tejas": ("Rahul Desai", dd.TEJAS["legal_name"], "Pneumatic spares for line maintenance", "MRO spares", "5-10 lakh", False),
    "borrowed_gstin_kaveri": ("Priya Nair", dd.KAVERI_TRADERS["legal_name"], "Agri produce for the canteen contract", "Food & catering", "1-5 lakh", False),
    "shared_bank_rangoli": ("Rahul Desai", dd.RANGOLI["legal_name"], "Printed labels and operator manuals", "Printing", "5-10 lakh", False),
    "proprietor_shinde": ("Priya Nair", dd.SHINDE["trade_name"], "Electrical maintenance at the Pune office", "Facility services", "1-5 lakh", False),
    "real_iitbhu": ("Rahul Desai", dd.IITBHU["legal_name"], "Sponsored R&D consultancy: vibration analysis of the Plant 2 press line", "Consultancy / R&D", "10-25 lakh", False),
}


def sim_records() -> list[dict]:
    recs = []
    gst = [
        (dd.NILGIRI, dd.NILGIRI["legal_name"], ""),
        (dd.TEJAS, dd.TEJAS["legal_name"], ""),
        (dd.KAVERI_FOODS, dd.KAVERI_FOODS["legal_name"], ""),
        (dd.RANGOLI, dd.RANGOLI["legal_name"], ""),
        (dd.SHINDE, dd.SHINDE["proprietor"], dd.SHINDE["trade_name"]),
        (dd.KESARI, dd.KESARI["legal_name"], ""),
        (dd.BRINDAVAN, dd.BRINDAVAN["legal_name"], ""),
        (dd.IITBHU, "INDIAN INSTITUTE OF TECHNOLOGY (BANARAS HINDU UNIVERSITY)", dd.IITBHU["trade_name"]),
        (dd.NITRR, dd.NITRR["legal_name"], dd.NITRR["trade_name"]),   # a real institute's public GST record
    ]
    for b, legal, trade in gst:
        recs.append(dict(kind="gst", key=b["gstin"], data=dict(
            legal_name=legal.upper(), trade_name=trade.upper(), status="Active", state=b["state"],
            constitution=b["constitution"], registered_on=b["liability_date"], return_filing="Regular")))
    for m in dd.VENDOR_MASTER:
        recs.append(dict(kind="gst", key=m["gstin"], data=dict(legal_name=m["legal_name"].upper(), trade_name="", status="Active",
                                                             state="", constitution="", registered_on="", return_filing="Regular")))
    pans = [
        (dd.NILGIRI["pan"], dd.NILGIRI["legal_name"]), (dd.TEJAS["pan"], dd.TEJAS["legal_name"]),
        (dd.KAVERI_TRADERS["pan"], dd.KAVERI_TRADERS["legal_name"]), (dd.KAVERI_FOODS["pan"], dd.KAVERI_FOODS["legal_name"]),
        (dd.RANGOLI["pan"], dd.RANGOLI["legal_name"]), (dd.SHINDE["pan"], dd.SHINDE["proprietor"]),
        (dd.KESARI["pan"], dd.KESARI["legal_name"]), (dd.BRINDAVAN["pan"], dd.BRINDAVAN["legal_name"]),
        (dd.IITBHU["pan"], "INDIAN INSTITUTE OF TECHNOLOGY BANARAS HINDU UNIVERSITY"),
        (dd.NITRR["pan"], dd.NITRR["legal_name"]),
    ]
    for pan, name in pans:
        recs.append(dict(kind="pan", key=pan, data=dict(name=name.upper(), status="VALID", aadhaar_linked=True)))
    banks = [dd.NILGIRI, dd.TEJAS, dd.KAVERI_TRADERS, dd.SHINDE, dd.KESARI, dd.BRINDAVAN, dd.IITBHU, dd.NITRR]
    for b in banks:
        recs.append(dict(kind="bank", key=f"{b['bank']['account']}@{b['bank']['ifsc']}",
                         data=dict(holder_name=b["bank"]["holder"], status="VALID")))
    # Rangoli's account really belongs to vendor V-0042: a penny-drop returns that holder.
    recs.append(dict(kind="bank", key=f"{dd.RANGOLI['bank']['account']}@{dd.RANGOLI['bank']['ifsc']}",
                     data=dict(holder_name="DECCAN OFFICE SUPPLIES", status="VALID")))
    for b in (dd.NILGIRI, dd.TEJAS, dd.RANGOLI, dd.KESARI, dd.BRINDAVAN):
        recs.append(dict(kind="cin", key=b["cin"], data=dict(name=b["legal_name"].upper(), status="Active", incorporated=b["incorporated"])))
    recs.append(dict(kind="udyam", key=dd.TEJAS["udyam"]["number"], data=dict(
        name=dd.TEJAS["legal_name"].upper(), type=dd.TEJAS["udyam"]["type"], status="Active")))
    return recs


async def ensure_sim_registry(s) -> int:
    """Demo mode: add any simulated-registry record that is missing (an older database seeded before a record was added).
    Never changes or removes existing rows. Returns how many were added."""
    have = {(k, key) for k, key in (await s.execute(select(SimRegistry.kind, SimRegistry.key))).all()}
    added = 0
    for r in sim_records():
        if (r["kind"], r["key"]) not in have:
            s.add(SimRegistry(**r))
            have.add((r["kind"], r["key"]))
            added += 1
    return added


async def seed(reset: bool = False, dispose: bool = True, allow_remote: bool = False) -> dict:
    """Load the demo data. reset=True drops every table first: refused on a non-local database unless allow_remote
    (the in-app reset passes it after checking the passcode; the command line after confirm_target)."""
    from onboarding import staff_cache
    if reset:
        refuse_remote_reset(allow_remote)
    staff_cache.clear()
    eng = engine()
    async with eng.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    async with Session() as s:  # type: AsyncSession
        emp = {e.name: e for e in (await s.execute(select(Employee))).scalars()}
        for e in EMPLOYEES:
            if e["name"] not in emp:
                obj = Employee(**e)
                s.add(obj)
                emp[e["name"]] = obj
            else:
                emp[e["name"]].email, emp[e["name"]].department = e["email"], e["department"]
        await s.flush()
        await ensure_demo_logins(s)

        existing = {i.scenario_key for i in (await s.execute(select(Invite))).scalars() if i.scenario_key}
        for key, (sponsor, company, reason, cat, band, high) in INVITES.items():
            if key in existing:
                continue
            contact = (dd.SCENARIOS.get(key) or dd.PUBLISHED_SCENARIOS[key])["form"]["contact_email"]
            s.add(Invite(token=secrets.token_urlsafe(18), sponsor_id=emp[sponsor].id, company_name=company,
                         contact_email=contact, business_reason=reason, spend_category=cat, spend_band=band,
                         high_spend=high, scenario_key=key, expires_at=now() + timedelta(days=14)))

        await s.execute(delete(VendorMaster).where(VendorMaster.source_run_id.is_(None)))
        for m in dd.VENDOR_MASTER:
            s.add(VendorMaster(**m))
        await seed_purchase_orders(s, emp)
        await s.execute(delete(Blocklist))
        for b in dd.BLOCKLIST:
            s.add(Blocklist(**b))
        await s.execute(delete(SimRegistry))
        for r in sim_records():
            s.add(SimRegistry(**r))
        await s.commit()

        counts = {}
        for model in (Employee, StaffLogin, VendorAccount, Invite, VendorMaster, Blocklist, SimRegistry):
            counts[model.__tablename__] = len((await s.execute(select(model))).scalars().all())
    staff_cache.clear()  # again, in case a page refilled it mid-seed
    if dispose:
        await eng.dispose()
    return counts



async def load_payables_sample(dispose: bool = True) -> dict:
    """Make payables testable on an existing database without a reset:
    - the sample purchase orders and service confirmations (added once);
    - the demo vendor login linked to its own ACTIVE registration, when that registration has no login yet
      (registrations made before vendor accounts existed) and was made with the same contact email.
    It never links a login to a registration made by another login, and never by PAN alone."""
    from onboarding.models import Application, Run, VendorLink
    from onboarding.ap.models import PurchaseOrder
    eng = engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    out = {}
    async with Session() as s:
        before = len((await s.execute(select(PurchaseOrder))).scalars().all())
        await seed_purchase_orders(s, {e.name: e for e in (await s.execute(select(Employee))).scalars()})
        out["purchase_orders_added"] = len((await s.execute(select(PurchaseOrder))).scalars().all()) - before
        acct = (await s.execute(select(VendorAccount).where(VendorAccount.email == DEMO_VENDOR["email"]))).scalar_one_or_none()
        linked = []
        if acct:
            taken = {ln.application_id for ln in (await s.execute(select(VendorLink))).scalars() if ln.application_id}
            for app in (await s.execute(select(Application).where(Application.current_status == "ACTIVE"))).scalars():
                if app.id in taken:
                    continue
                run = (await s.execute(select(Run).where(Run.application_id == app.id).order_by(Run.id.desc()).limit(1))).scalar_one_or_none()
                if run and str((run.form or {}).get("contact_email", "")).strip().lower() == acct.email.lower():
                    s.add(VendorLink(account_id=acct.id, application_id=app.id))
                    linked.append(app.ref)
        out["registrations_linked_to_demo_vendor_login"] = linked
        await s.commit()
    if dispose:
        await eng.dispose()
    return out


_VERIFIED: set[tuple[str, str]] = set()   # (hash, password) pairs already checked in this process (scrypt is slow)


async def _matches(stored: str, password: str) -> bool:
    if (stored, password) in _VERIFIED:
        return True
    ok = bool(password) and await auth.verify_password_async(password, stored)
    if ok:
        _VERIFIED.add((stored, password))
    return ok


async def _hash(password: str) -> str:
    h = await auth.hash_password_async(password)
    _VERIFIED.add((h, password))
    return h


DISABLED = "disabled"   # a password hash nothing verifies against


async def ensure_demo_logins(s: AsyncSession) -> None:
    """Demo mode with DEMO_PASSWORD set: every seeded employee has a console login and the demo vendor account exists,
    all with that password (an older password, such as the public "demo_pass", is replaced). Otherwise no demo login is
    created, and seeded demo logins still using the public "demo_pass" (or DEMO_PASSWORD outside demo mode) are
    switched off. Called by seed() and at app start."""
    st = get_settings()
    pw = st.demo_password if st.demo_tools else ""
    retired = {p for p in (LEGACY_PUBLIC_PASSWORD, st.demo_password) if p and p != pw}
    logins = {sl.employee_id: sl for sl in (await s.execute(select(StaffLogin))).scalars()}
    seeded_email = {d["name"]: d["email"] for d in EMPLOYEES}
    for e in (await s.execute(select(Employee))).scalars():
        if e.name in seeded_email and e.email != seeded_email[e.name]:
            e.email = seeded_email[e.name]  # the demo company was renamed: keep logins on the current domain
        sl = logins.get(e.id)
        if pw and sl is None:
            s.add(StaffLogin(employee_id=e.id, password_hash=await _hash(pw)))
        elif sl is not None and e.name in seeded_email:
            await _refresh(sl, pw, retired)
    for vendor in DEMO_VENDORS:
        acct = (await s.execute(select(VendorAccount).where(VendorAccount.email == vendor["email"]))).scalar_one_or_none()
        if acct is None and pw:
            s.add(VendorAccount(password_hash=await _hash(pw), **vendor))
        elif acct is not None:
            await _refresh(acct, pw, retired)
    await s.flush()


async def _refresh(row, pw: str, retired: set[str]) -> None:
    """A seeded login: on the current demo password, or switched off if it still uses a retired one."""
    if pw:
        if not await _matches(row.password_hash, pw):
            row.password_hash = await _hash(pw)
    elif row.password_hash != DISABLED:
        for old in retired:
            if await _matches(row.password_hash, old):
                row.password_hash = DISABLED
                break


class RemoteDatabaseRefused(RuntimeError):
    pass


def refuse_remote_reset(allow_remote: bool) -> None:
    """seed(reset=True) wipes every table: on a non-local database only with explicit permission (the in-app reset,
    after its passcode, or a CLI run confirmed with confirm_target)."""
    if not allow_remote and not local_database():
        raise RemoteDatabaseRefused(f"Refusing to reset a non-local database ({database_host(get_settings().database_url)}). "
                                    "From the command line, run with --production and type the host to confirm.")


def confirm_target(argv: list[str] | None = None, ask=input) -> bool:
    """Command-line guard for scripts that write to the database. Prints the target host (never the URL or its
    credentials). A non-local database needs --production AND the host typed back exactly; otherwise exit.
    Returns True when the target is remote and was confirmed (pass it on as allow_remote)."""
    argv = sys.argv if argv is None else argv
    host = database_host(get_settings().database_url)
    print(f"Target database: {host}")
    if local_database():
        return False
    if "--production" not in argv:
        sys.exit(f"Refusing to write to a non-local database ({host}). Re-run with --production to be asked for confirmation.")
    if ask(f"Type the database host ({host}) to confirm: ").strip() != host:
        sys.exit("The host you typed doesn't match. Nothing was changed.")
    return True


async def seed_purchase_orders(s: AsyncSession, emp: dict) -> None:
    """The company's own purchase orders and service confirmations (dd.PURCHASE_ORDERS), added once."""
    from onboarding.ap.models import GoodsReceipt, POLine, PurchaseOrder, ReceiptLine
    from onboarding.intel.crypto import lookup_key, mask
    for spec in dd.PURCHASE_ORDERS:
        if (await s.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == spec["po_number"]))).scalar_one_or_none():
            continue
        v = spec["vendor"]
        acct = v["bank"]["account"]
        po = PurchaseOrder(po_number=spec["po_number"], vendor_gstin=v["gstin"], vendor_name=v["legal_name"], cost_centre=spec["cost_centre"],
                           requester_id=emp[spec["requester"]].id, approver_id=emp[spec["approver"]].id, service_from=spec["service_from"],
                           service_to=spec["service_to"], payee_account_key=lookup_key("BANK_ACCOUNT", acct), payee_account_display=mask("BANK_ACCOUNT", acct),
                           payee_ifsc=v["bank"]["ifsc"], source="seed")
        s.add(po)
        await s.flush()
        lines = []
        for i, ln in enumerate(spec["lines"], 1):
            pl = POLine(po_id=po.id, line_no=i, description=ln["desc"], quantity=ln["qty"], unit=ln["unit"], unit_price=ln["rate"], tax_rate=ln["tax"])
            s.add(pl)
            lines.append(pl)
        await s.flush()
        for rc in spec.get("receipts", []):
            g = GoodsReceipt(po_id=po.id, number=rc["number"], kind="service", received_on=rc["on"], confirmed_by=emp[rc["by"]].id)
            s.add(g)
            await s.flush()
            for pl, q in zip(lines, rc["qty"]):
                s.add(ReceiptLine(receipt_id=g.id, po_line_id=pl.id, quantity=q))
    await s.flush()


if __name__ == "__main__":   # python -m onboarding.seeding [--reset] [--production]
    import asyncio
    remote_ok = confirm_target()
    print(asyncio.run(seed(reset="--reset" in sys.argv, allow_remote=remote_ok)))

