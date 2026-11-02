"""Create tables and load demo data. Idempotent. Used by scripts/seed.py and the app's "Reset demo"."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from onboarding import demo_data as dd
from onboarding.db import engine
from onboarding import auth
from onboarding.models import Base, Blocklist, Employee, Invite, SimRegistry, StaffLogin, VendorAccount, VendorMaster, now

EMPLOYEES = [
    dict(name="Priya Nair", department="Operations, Plant 2", role="sponsor", email="priya.nair@nareenterprises.example.com"),
    dict(name="Rahul Desai", department="Plant Head, Pune", role="sponsor", email="rahul.desai@nareenterprises.example.com"),
    dict(name="Arjun Mehta", department="Procurement", role="maker", email="arjun.mehta@nareenterprises.example.com"),
    dict(name="Kavita Rao", department="Finance", role="checker", email="kavita.rao@nareenterprises.example.com"),
]

# Demo logins (fictional people, shown on the login pages so anyone reviewing the demo can sign in).
# Every employee logs in with their own email; one vendor account is ready, with no registration yet.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "vardhan-demo-26")
DEMO_COMPANY_EMAIL = "arjun.mehta@nareenterprises.example.com"
DEMO_VENDOR = dict(email=dd.KESARI["contact"]["email"], company_name=dd.KESARI["legal_name"], contact_name=dd.KESARI["contact"]["name"])

INVITES = {  # scenario_key -> (sponsor, company, reason, category, band, high)
    "happy_nilgiri": ("Priya Nair", dd.NILGIRI["legal_name"], "Corrugated boxes and protective packaging for Plant 2, replacing a supplier with late deliveries", "Packaging", "10-25 lakh", False),
    "wrongdoc_tejas": ("Rahul Desai", dd.TEJAS["legal_name"], "Pneumatic spares for line maintenance", "MRO spares", "5-10 lakh", False),
    "borrowed_gstin_kaveri": ("Priya Nair", dd.KAVERI_TRADERS["legal_name"], "Agri produce for the canteen contract", "Food & catering", "1-5 lakh", False),
    "shared_bank_rangoli": ("Rahul Desai", dd.RANGOLI["legal_name"], "Printed labels and operator manuals", "Printing", "5-10 lakh", False),
    "proprietor_shinde": ("Priya Nair", dd.SHINDE["trade_name"], "Electrical maintenance at the Pune office", "Facility services", "1-5 lakh", False),
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
    ]
    for pan, name in pans:
        recs.append(dict(kind="pan", key=pan, data=dict(name=name.upper(), status="VALID", aadhaar_linked=True)))
    banks = [dd.NILGIRI, dd.TEJAS, dd.KAVERI_TRADERS, dd.SHINDE, dd.KESARI, dd.BRINDAVAN]
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


async def seed(reset: bool = False, dispose: bool = True) -> dict:
    from onboarding import staff_cache
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
            contact = dd.SCENARIOS[key]["form"]["contact_email"]
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



async def ensure_demo_logins(s: AsyncSession) -> None:
    """Give every seeded employee a console login and create the demo vendor account, if missing.
    Called by seed() and at app start (so a fresh deploy can always be logged into)."""
    have = {sl.employee_id for sl in (await s.execute(select(StaffLogin))).scalars()}
    seeded_email = {d["name"]: d["email"] for d in EMPLOYEES}
    for e in (await s.execute(select(Employee))).scalars():
        if e.name in seeded_email and e.email != seeded_email[e.name]:
            e.email = seeded_email[e.name]  # the demo company was renamed: keep logins on the current domain
        if e.id not in have:
            s.add(StaffLogin(employee_id=e.id, password_hash=await auth.hash_password_async(DEMO_PASSWORD)))
    if not (await s.execute(select(VendorAccount).where(VendorAccount.email == DEMO_VENDOR["email"]))).scalar_one_or_none():
        s.add(VendorAccount(password_hash=await auth.hash_password_async(DEMO_PASSWORD), **DEMO_VENDOR))
    await s.flush()


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

