"""The two front doors and the supplier portal, through HTTP: accounts (register, login, logout, bad
passwords, tampered cookies), a bill-first registration linked to the account, activation, and later
bills (clean, and one asking for a new bank account). Throwaway SQLite, saved AI readings, no API calls."""

import asyncio
import os
import re
import secrets
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".read_cache"
pytestmark = pytest.mark.skipif(not CACHE.exists() or not any(CACHE.iterdir()), reason="no cached AI readings")
PW = secrets.token_urlsafe(12)


def test_password_hashing_and_cookie_signing():
    from onboarding import auth
    h = auth.hash_password("correct horse battery")
    assert h.startswith("scrypt$") and "correct" not in h
    assert auth.verify_password("correct horse battery", h) and not auth.verify_password("wrong", h)
    cookie = auth.make_session(42)
    assert auth.read_session(cookie) == 42
    acct, issued, sig = cookie.split(".")
    assert auth.read_session(f"43.{issued}.{sig}") is None          # someone else's id
    assert auth.read_session("42.1.deadbeef") is None and auth.read_session("junk") is None


def test_safe_next_only_allows_local_paths():
    from onboarding.web import safe_next
    assert safe_next("/apply/abc") == "/apply/abc"
    assert safe_next("//evil.example.com") == "/vendor" and safe_next("https://evil.example.com") == "/vendor"


@pytest.fixture(scope="module")
def flows(tmp_path_factory):
    db = tmp_path_factory.mktemp("portaldb") / "portal.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    import httpx

    from onboarding import bills, runner, web
    from onboarding.demo_data import SCENARIOS
    from onboarding.main import app
    from onboarding.seeding import seed

    runner.PACE = 0
    pending: list[asyncio.Task] = []
    runner.start = lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True)))
    bills.start_check = lambda bill_id, prefer_cache=False: pending.append(asyncio.create_task(bills._guarded(bill_id, True)))
    out: dict = {}

    async def drain():
        await asyncio.gather(*pending)
        pending.clear()

    async def go():
        await seed(reset=True, dispose=False)
        t = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=t, base_url="http://t") as v, httpx.AsyncClient(transport=t, base_url="http://t") as staff, \
                httpx.AsyncClient(transport=t, base_url="http://t") as other:
            out["landing"] = (await v.get("/")).text
            out["console"] = (await staff.get("/console")).status_code
            out["portal_anon"] = (await v.get("/vendor")).headers.get("location", "")
            out["bill_anon"] = (await v.get("/bill")).headers.get("location", "")
            reg = {"company_name": "Kesari Facility Services Private Limited", "contact_name": "Sneha Kulkarni", "email": "billing@kesarifacility.example.com"}
            out["weak"] = (await v.post("/vendor/register", data=reg | {"password": "short"})).text
            r = await v.post("/vendor/register", data=reg | {"password": PW})
            out["registered"] = (r.status_code, r.headers.get("set-cookie", ""))
            out["dup"] = (await other.post("/vendor/register", data=reg | {"password": PW})).text
            out["home_new"] = (await v.get("/vendor")).text

            f = SCENARIOS["bill_kesari"]["form"]
            data = {k: str(x) for k, x in f.items() if not isinstance(x, bool)} | {"bill_mode": "1", "gst_registered": "on", "demo": "bill_kesari"}
            r = await v.post("/bill", data=data)
            run_id = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            await drain()
            out["home_reg"] = (await v.get("/vendor")).text
            for actor, action in ((1, "confirm_engagement"), (3, "activate")):
                staff.cookies.set("actor", str(actor))
                await staff.post(f"/runs/{run_id}/action", data={"action": action})
            out["home_active"] = (await v.get("/vendor")).text

            async def bill(key):
                page = (await v.get(f"/vendor/bills/new?demo={key}")).text
                vals = dict(re.findall(r'name="(invoice_number|invoice_date|amount|description|engaged_by|po_number)"[^>]*value="([^"]*)"', page))
                r = await v.post("/vendor/bills/new", data=vals | {"demo": key})
                bid = int(r.headers["location"].rsplit("/", 1)[1])
                await drain()
                return bid

            bid = await bill("clean")
            out["clean_page"] = (await staff.get(f"/bills/{bid}")).text
            codes = []
            for actor, action in ((3, "approve_payment"), (1, "confirm_engagement"), (1, "approve_payment"), (3, "approve_payment")):
                staff.cookies.set("actor", str(actor))
                codes.append((await staff.post(f"/bills/{bid}/action", data={"action": action})).status_code)
            out["clean_codes"] = codes
            out["clean_vendor"] = (await v.get(f"/vendor/bills/{bid}")).text
            bid2 = await bill("newbank")
            out["newbank_page"] = (await staff.get(f"/bills/{bid2}")).text
            out["newbank_vendor"] = (await v.get(f"/vendor/bills/{bid2}")).text
            staff.cookies.set("actor", "1")
            await staff.post(f"/bills/{bid2}/action", data={"action": "confirm_engagement"})
            staff.cookies.set("actor", "3")
            out["newbank_maker"] = (await staff.post(f"/bills/{bid2}/action", data={"action": "approve_payment"})).status_code
            staff.cookies.set("actor", "4")
            out["newbank_checker"] = (await staff.post(f"/bills/{bid2}/action", data={"action": "reject_bill", "comment": "Bank change not confirmed by phone."})).status_code

            await other.post("/vendor/register", data={"company_name": "Someone Else", "contact_name": "A B", "email": "a@else.example.com", "password": PW})
            out["other_bill"] = (await other.get(f"/vendor/bills/{bid}")).status_code
            out["bills_list"] = (await staff.get("/bills")).text
            out["vendors_list"] = (await staff.get("/vendors")).text
            v.cookies.set("vendor_session", "1.1.forged")
            out["forged"] = (await v.get("/vendor")).headers.get("location", "")
            v.cookies.clear()
            out["badlogin"] = (await v.post("/vendor/login", data={"email": reg["email"], "password": "not-it"})).text
            r = await v.post("/vendor/login", data={"email": reg["email"], "password": PW})
            out["login"] = r.status_code
            out["home_again"] = (await v.get("/vendor")).text
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


def test_two_doors(flows):
    assert "I work at" in flows["landing"] and "vendor or supplier" in flows["landing"] and flows["console"] == 200


def test_vendor_pages_need_an_account(flows):
    assert flows["portal_anon"].startswith("/vendor/login")
    assert flows["bill_anon"].startswith("/vendor/register")
    assert flows["forged"].startswith("/vendor/login")


def test_register_validates_and_logs_in(flows):
    assert "at least 8" in flows["weak"]
    code, cookie = flows["registered"]
    assert code == 303 and "vendor_session=" in cookie and "httponly" in cookie.lower()
    assert "already exists" in flows["dup"]
    assert "I have an invitation link" in flows["home_new"]


def test_registration_is_linked_and_activation_unlocks_bills(flows):
    assert "VOB-0001" in flows["home_reg"]
    assert "V-1001" in flows["home_active"] and "Submit a new bill" in flows["home_active"]


def test_clean_bill_needs_confirmation_and_a_second_person(flows):
    assert "Awaiting confirmation" in flows["clean_page"] and "Every check on the bill passed" in flows["clean_page"]
    assert flows["clean_codes"] == [409, 303, 403, 303]
    assert "Approved for payment" in flows["clean_vendor"]


def test_bank_change_bill_is_caught_and_kept_from_the_vendor(flows):
    page = flows["newbank_page"]
    assert "R-BILL-10" in page and "different bank account" in page and "fraud-class signal" in page
    assert "being reviewed" in flows["newbank_vendor"] and "different bank account" not in flows["newbank_vendor"]
    assert flows["newbank_maker"] == 403 and flows["newbank_checker"] == 303


def test_vendors_only_see_their_own_bills(flows):
    assert flows["other_bill"] == 404


def test_company_lists_and_login_again(flows):
    assert "BILL-0001" in flows["bills_list"] and "BILL-0002" in flows["bills_list"]
    assert "Kesari Facility Services" in flows["vendors_list"] and "V-1001" in flows["vendors_list"]
    assert "match" in flows["badlogin"] and flows["login"] == 303 and "V-1001" in flows["home_again"]
