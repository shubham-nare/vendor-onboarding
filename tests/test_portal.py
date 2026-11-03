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
            from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD, DEMO_VENDOR
            out["landing"] = (await v.get("/")).text
            out["console_anon"] = (await staff.get("/console")).headers.get("location", "")
            out["action_anon"] = (await staff.post("/runs/1/action", data={"action": "activate"})).status_code
            out["staff_bad"] = (await staff.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": "not-it"})).text
            out["staff_login"] = (await staff.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD, "next": "/bills"})).headers.get("location", "")
            out["console"] = (await staff.get("/console")).status_code
            out["console_page"] = (await staff.get("/console")).text
            r = await other.post("/vendor/login", data={"email": DEMO_VENDOR["email"], "password": DEMO_PASSWORD})
            out["demo_vendor"] = (r.status_code, (await other.get("/vendor")).text)
            out["vendor_cookie_on_console"] = (await other.get("/console")).headers.get("location", "")
            other.cookies.clear()
            out["portal_anon"] = (await v.get("/vendor")).headers.get("location", "")
            out["bill_anon"] = (await v.get("/bill")).headers.get("location", "")
            reg = {"company_name": "Kesari Facility Services Private Limited", "contact_name": "Sneha Kulkarni", "email": "accounts@kesarifacility.example.com"}
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
                review = (await v.get(f"/vendor/bills/{bid}")).text
                out.setdefault("review_" + key, review)
                po = re.search(r'<option value="(PO-[^"]+)" selected', review)
                await v.post(f"/vendor/bills/{bid}/send", data={"po_number": po.group(1) if po else "", "engaged_by": vals.get("engaged_by", "")})
                await drain()
                return bid

            bid = await bill("clean")
            out["clean_page"] = (await staff.get(f"/bills/{bid}")).text
            codes = []
            # Priya engaged them (can't approve); Arjun approves; only Finance releases; payment needs its bank reference
            for actor, action, comment in ((1, "approve_payment", ""), (3, "approve_payment", ""), (3, "release_payment", ""),
                                           (4, "release_payment", ""), (4, "mark_paid", ""), (4, "mark_paid", "UTR HDFC261103000417")):
                staff.cookies.set("actor", str(actor))
                codes.append((await staff.post(f"/bills/{bid}/action", data={"action": action, "comment": comment})).status_code)
            out["clean_codes"] = codes
            out["clean_paid_page"] = (await staff.get(f"/bills/{bid}")).text
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

            # three-way match journeys
            bid3 = await bill("overbilled")                     # bills 3 shifts; delivery recorded for 2
            staff.cookies.set("actor", "3")
            out["over_page"] = (await staff.get(f"/bills/{bid3}")).text
            out["over_vendor"] = (await v.get(f"/vendor/bills/{bid3}")).text
            staff.cookies.set("actor", "4")                      # Finance approves over the discrepancy, with a reason ...
            out["over_override_no_reason"] = (await staff.post(f"/bills/{bid3}/action", data={"action": "approve_payment"})).status_code
            out["over_override"] = (await staff.post(f"/bills/{bid3}/action", data={"action": "approve_payment", "comment": "Third shift done on 3 Nov, confirmed by phone"})).status_code
            out["over_release_self"] = (await staff.post(f"/bills/{bid3}/action", data={"action": "release_payment"})).status_code   # ... but can't release it
            bid4 = await bill("clean")                          # the paid invoice, sent again
            out["dup_page"] = (await staff.get(f"/bills/{bid4}")).text
            out["dup_vendor"] = (await v.get(f"/vendor/bills/{bid4}")).text
            out["review_clean"] = out.get("review_clean", "")
            for path in ("/invoices", "/purchase-orders", "/audit", "/invoices?status=Paid"):
                out[path] = await staff.get(path)
            po3 = re.search(r'href="/purchase-orders/(\d+)"', out["over_page"]).group(1)
            staff.cookies.set("actor", "1")                      # Priya, the requester on the order, records the third shift
            out["receipt"] = (await staff.post(f"/purchase-orders/{po3}/receipts", data={"kind": "service", f"qty_x": ""} |
                                               {k: "1" for k in re.findall(r'name="(qty_\d+)"', (await staff.get(f"/purchase-orders/{po3}")).text)})).status_code
            staff.cookies.set("actor", "3")
            out["po3_page"] = (await staff.get(f"/purchase-orders/{po3}")).text

            # who sees what: Priya (1) is named on the bills, Rahul (2) isn't, Arjun (3) reviews, Kavita (4) is Finance
            sha = re.search(r'href="/files/([0-9a-f]+)"', out["newbank_page"]).group(1)
            seen = {}
            for who in (1, 2, 3, 4):
                staff.cookies.set("actor", str(who))
                seen[who] = dict(bills=(await staff.get("/bills")).text, bill=await staff.get(f"/bills/{bid2}"), run=await staff.get(f"/runs/{run_id}"),
                                 events=(await staff.get(f"/runs/{run_id}/events")).status_code, file=(await staff.get(f"/files/{sha}")).status_code,
                                 outbox=(await staff.get("/outbox")).status_code, console=(await staff.get("/console")).text,
                                 vendors=(await staff.get("/supplier-accounts")).text)
            out["seen"] = seen
            staff.cookies.set("actor", "2")
            out["rahul_action"] = (await staff.post(f"/bills/{bid2}/action", data={"action": "confirm_engagement"})).status_code
            staff.cookies.set("actor", "3")

            await other.post("/vendor/register", data={"company_name": "Someone Else", "contact_name": "A B", "email": "a@else.example.com", "password": PW})
            out["other_bill"] = (await other.get(f"/vendor/bills/{bid}")).status_code
            out["bills_list"] = (await staff.get("/bills")).text
            out["vendors_list"] = (await staff.get("/supplier-accounts")).text
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


def test_company_pages_need_an_employee_login(flows):
    assert flows["console_anon"].startswith("/company/login?next=")
    assert flows["action_anon"] == 401
    assert "match an employee login" in flows["staff_bad"]
    assert flows["staff_login"] == "/bills"
    assert "Arjun Mehta" in flows["console_page"] and "Log out" in flows["console_page"]


def test_demo_vendor_account_and_cookies_dont_cross_over(flows):
    code, home = flows["demo_vendor"]
    assert code == 303 and "Hello, Sneha" in home and "demo=bill_kesari" in home
    assert flows["vendor_cookie_on_console"].startswith("/company/login")    # a vendor's cookie is not an employee's


def test_cookie_purposes_are_separate():
    from onboarding import auth
    c = auth.make_session(3)                     # a vendor cookie for account 3
    assert auth.read_session(c) == 3 and auth.read_session(c, purpose="company") is None


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


def test_clean_bill_matches_its_po_and_payment_needs_finance(flows):
    page = flows["clean_page"]
    assert "Matched and ready for approval" in page and "PO-2026-0141" in page and "SC-2026-0141" in page
    assert flows["clean_codes"] == [403, 303, 403, 303, 400, 303]
    paid = flows["clean_paid_page"]
    assert "Paid" in paid and "UTR HDFC261103000417" in paid
    assert "Paid" in flows["clean_vendor"] or "Approved for payment" in flows["clean_vendor"]


def test_bank_change_bill_is_caught_and_kept_from_the_vendor(flows):
    page = flows["newbank_page"]
    assert "R-BILL-10" in page and "different bank account" in page and "fraud-class signal" in page
    assert "Under review" in flows["newbank_vendor"] and "different bank account" not in flows["newbank_vendor"]
    assert flows["newbank_maker"] == 403 and flows["newbank_checker"] == 303


def test_vendors_only_see_their_own_bills(flows):
    assert flows["other_bill"] == 404


def test_company_lists_and_login_again(flows):
    assert "BILL-0001" in flows["bills_list"] and "BILL-0002" in flows["bills_list"]
    assert "Kesari Facility Services" in flows["vendors_list"] and "V-1001" in flows["vendors_list"]
    assert "match" in flows["badlogin"] and flows["login"] == 303 and "V-1001" in flows["home_again"]


def test_requester_sees_only_their_own_and_no_evidence(flows):
    from onboarding.demo_data import KESARI
    priya, rahul = flows["seen"][1], flows["seen"][2]
    # Priya is named on the bills: she sees them, without the checks, documents, ID numbers or fraud flag
    assert "BILL-0002" in priya["bills"] and priya["bill"].status_code == 200 and priya["run"].status_code == 200
    page = priya["bill"].text
    assert "Requester view" in page and "R-BILL-10" not in page and "fraud-class" not in page and "/files/" not in page
    assert KESARI["pan"] not in page and "Pays into" not in page
    run = priya["run"].text
    assert "Every rule that ran" not in run and "Internal note" not in run and "How well each fact is proven" not in run
    assert priya["file"] == 403 and priya["outbox"] == 403 and 'href="/outbox"' not in priya["console"]
    # Rahul has nothing to do with Kesari: he can't open it at all
    assert rahul["bill"].status_code == 403 and rahul["run"].status_code == 403 and rahul["events"] == 403
    assert "BILL-0002" not in rahul["bills"] and "Kesari" not in rahul["console"] and flows["rahul_action"] == 403
    assert "accounts@kesarifacility" not in rahul["vendors"] and f'/bills/' not in rahul["vendors"]


def test_reviewers_see_everything_and_only_finance_sees_the_full_account(flows):
    from onboarding.demo_data import KESARI
    arjun, kavita = flows["seen"][3], flows["seen"][4]
    acct = KESARI["bank"]["account"]
    for who in (arjun, kavita):
        assert who["bill"].status_code == 200 and "R-BILL-10" in who["bill"].text and who["file"] == 200 and who["outbox"] == 200
        assert "Every rule that ran" in who["run"].text
    assert acct not in arjun["bill"].text and acct in kavita["bill"].text and "Finance only" in kavita["bill"].text


def test_vendor_checks_what_was_read_before_sending(flows):
    review = flows["review_clean"]
    assert "Check what we read from your bill" in review and "KFS/2026-27/0207" in review and "PO-2026-0141" in review
    assert 'name="invoice_number"' not in review


def test_overbilled_invoice_goes_to_review_with_the_exact_discrepancy(flows):
    page = flows["over_page"]
    assert "Needs internal review" in page and "R-PO-04" in page and "billed 3" in page and "confirmed for 2" in page
    assert "billed quantity exceeds confirmed receipt" in page.lower()
    assert "Under review" in flows["over_vendor"] and "R-PO-04" not in flows["over_vendor"] and "confirmed for 2" not in flows["over_vendor"]


def test_finance_override_needs_a_reason_and_approver_cannot_release(flows):
    assert flows["over_override_no_reason"] == 400 and flows["over_override"] == 303
    assert flows["over_release_self"] == 403


def test_duplicate_of_a_paid_invoice_is_blocked(flows):
    page = flows["dup_page"]
    assert "Blocked for investigation" in page and "already paid" in page
    assert "Under review" in flows["dup_vendor"] and "already paid" not in flows["dup_vendor"]


def test_payables_pages_and_delivery_recording(flows):
    for path in ("/invoices", "/purchase-orders", "/audit", "/invoices?status=Paid"):
        assert flows[path].status_code == 200, path
    assert "UTR HDFC261103000417" in flows["/audit"].text or "mark_paid" in flows["/audit"].text or "Record the payment" in flows["/audit"].text
    assert "PO-2026-0141" in flows["/purchase-orders"].text and "Blocked for investigation" in flows["/invoices"].text
    assert flows["receipt"] == 303 and "SC-" in flows["po3_page"]

