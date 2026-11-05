"""The two front doors and the supplier portal, through HTTP: accounts (register, login, logout, bad
passwords, tampered cookies), a bill-first registration linked to the account, activation, and later
bills (clean, and one asking for a new bank account). Throwaway SQLite, saved AI readings, no API calls."""

import asyncio
import html
import os
import json
import re
import secrets
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".read_cache"
pytestmark = pytest.mark.skipif(not CACHE.exists() or not any(CACHE.iterdir()), reason="no cached AI readings")
PW = "Ks@9" + secrets.token_urlsafe(10)   # meets the policy: upper, lower, number, symbol, 8+

from pathlib import Path  # noqa: E402

APP_JS = (Path(__file__).resolve().parent.parent / "onboarding" / "static" / "app.js").read_text(encoding="utf-8")
APP_CSS = (Path(__file__).resolve().parent.parent / "onboarding" / "static" / "app.css").read_text(encoding="utf-8")


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
    os.environ["SMTP_HOST"], os.environ["MAIL_FROM"] = "smtp.test", "vendors@mamoni.in"   # email on, to a fake server
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    import httpx

    from onboarding import bills, runner
    from onboarding.demo_data import SCENARIOS
    from onboarding.main import app
    from onboarding.seeding import seed

    runner.PACE = 0
    from onboarding import mailer
    sent_mail: list = []
    mailer._smtp_send = lambda em: sent_mail.append(dict(to=em["To"], cc=em["Cc"] or "", subject=em["Subject"], body=em.get_content()))
    pending: list[asyncio.Task] = []
    runner.start = lambda run_id, prefer_cache=False: pending.append(asyncio.create_task(runner._run(run_id, True)))
    bills.start_check = lambda bill_id, prefer_cache=False: pending.append(asyncio.create_task(bills._guarded(bill_id, True)))
    out: dict = {"mails": sent_mail}
    mailer.start = lambda run_id: pending.append(asyncio.create_task(mailer.deliver_for_run(run_id)))

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
            out["console_page"] = (await staff.get("/api/v1/console/home")).text
            out["pending"] = (await staff.get("/api/v1/console/pending")).json()
            out["pending_anon"] = (await other.get("/api/v1/console/pending")).status_code
            out["applications_page"] = (await staff.get("/outbox")).text   # a staff page still drawn by the server
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
            out["dup"] = (await other.post("/vendor/register", data=reg | {"password": "Diff3rent!pw"})).text
            out["home_new"] = (await v.get("/vendor")).text
            out["bill_form_page"] = (await v.get("/bill")).text
            out["weak_pw"] = (await other.post("/vendor/register", data={"company_name": "X", "contact_name": "Y", "email": "y@x.example.com",
                                                                          "password": "demo_pass"})).text

            f = SCENARIOS["bill_kesari"]["form"]
            data = {k: str(x) for k, x in f.items() if not isinstance(x, bool)} | {"bill_mode": "1", "gst_registered": "on", "demo": "bill_kesari"}
            r = await v.post("/bill", data=data)
            run_id = int(re.search(r"/runs/(\d+)", r.headers["location"]).group(1))
            out["home_submitted"] = (await v.get(f"/vendor?submitted={run_id}")).text
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
            for path in ("/invoices", "/purchase-orders", "/audit", "/invoices?status=Paid"):   # invoices come from the API
                out[path] = await staff.get("/api/v1" + path if path.startswith(("/invoices", "/purchase-orders")) else path.replace("/audit", "/api/v1/history"))
            for path in ("/invoices?sort=amount_desc", "/invoices?sort=amount_asc", "/invoices?amin=41000", "/invoices?amax=30000", "/invoices?vendor=V-9999"):
                out["filter " + path] = (await staff.get("/api/v1" + path)).json()
            po3 = re.search(r'href="/purchase-orders/(\d+)"', out["over_page"]).group(1)
            staff.cookies.set("actor", "1")                      # Priya, the requester on the order, records the third shift
            out["receipt"] = (await staff.post(f"/purchase-orders/{po3}/receipts", data={"kind": "service", "qty_x": ""} |
                                               {k: "1" for k in re.findall(r'name="(qty_\d+)"', (await staff.get(f"/purchase-orders/{po3}")).text)})).status_code
            staff.cookies.set("actor", "3")
            out["po3_page"] = (await staff.get(f"/purchase-orders/{po3}")).text
            out["vendor_dir"] = (await staff.get("/api/v1/vendors")).text
            vnd = next(v["id"] for v in json.loads(out["vendor_dir"])["vendors"] if v["name"].startswith("Kesari"))
            out["kesari_360"] = (await staff.get(f"/vendors/{vnd}")).text
            out["vendor_dir_unpaid"] = (await staff.get("/api/v1/vendors?inv=needs_review")).text

            # bank-account change request: the vendor asks, Finance (only) approves after an independent check
            out["profile"] = (await v.get("/vendor/profile")).text
            r = await v.post("/vendor/profile/change", data={"kind": "bank_account", "account": "50200099887766", "ifsc": "HDFC0000123",
                                                            "holder": "Kesari Facility Services Private Limited", "reason": "Moved our main account"},
                             files={"proof": ("new_cheque.pdf", b"%PDF-1.4 test cheque", "application/pdf")})
            out["cr_post"] = r.status_code
            out["profile_after"] = (await v.get("/vendor/profile")).text
            staff.cookies.set("actor", "3")
            out["review_maker"] = (await staff.get("/api/v1/review")).json()
            out["pending_maker_cr"] = (await staff.get("/api/v1/console/pending")).json()
            staff.cookies.set("actor", "4")
            out["review_finance"] = (await staff.get("/api/v1/review")).json()
            out["pending_finance_cr"] = (await staff.get("/api/v1/console/pending")).json()
            out["applications_finance"] = (await staff.get("/api/v1/applications")).json()
            cr_id = out["review_finance"]["changes"][0]["id"]
            staff.cookies.set("actor", "3")
            out["cr_maker"] = (await staff.post(f"/change-requests/{cr_id}/decide", data={"decision": "approve", "note": "looks fine"})).status_code
            out["cr_maker_api"] = await staff.post(f"/api/v1/change-requests/{cr_id}/decision", json={"decision": "approve", "note": "looks fine"})
            staff.cookies.set("actor", "4")
            out["cr_nonote"] = (await staff.post(f"/change-requests/{cr_id}/decide", data={"decision": "approve", "note": ""})).status_code
            out["cr_checker"] = (await staff.post(f"/change-requests/{cr_id}/decide", data={"decision": "approve", "note": "Called the number on record; Sneha confirmed"})).status_code
            out["profile_done"] = (await v.get("/vendor/profile")).text
            out["documents"] = (await staff.get("/documents")).text
            out["documents_bills"] = (await staff.get("/documents?kind=invoice&show=all")).text
            for path in ("/review", "/applications", "/relationships", "/audit?entity=change_request"):
                out[path] = await staff.get(path.replace("/audit", "/api/v1/history"))
            out["kesari_360_after_change"] = (await staff.get(f"/vendors/{vnd}")).text

            # who sees what: Priya (1) is named on the bills, Rahul (2) isn't, Arjun (3) reviews, Kavita (4) is Finance
            sha = re.search(r'href="/files/([0-9a-f]+)"', out["newbank_page"]).group(1)
            seen = {}
            for who in (1, 2, 3, 4):
                staff.cookies.set("actor", str(who))
                seen[who] = dict(bills=(await staff.get("/bills")).text, bill=await staff.get(f"/bills/{bid2}"), run=await staff.get(f"/runs/{run_id}"),
                                 events=(await staff.get(f"/runs/{run_id}/events")).status_code, file=(await staff.get(f"/files/{sha}")).status_code,
                                 outbox=(await staff.get("/outbox")).status_code, console=(await staff.get("/api/v1/console/home")).text,
                                 vendors=(await staff.get("/supplier-accounts")).text)
            out["seen"] = seen
            staff.cookies.set("actor", "2")
            out["rahul_action"] = (await staff.post(f"/bills/{bid2}/action", data={"action": "confirm_engagement"})).status_code
            staff.cookies.set("actor", "3")
            # tag a teammate: Arjun asks Rahul about the invoice; Rahul sees it, opens it, answers
            out["rahul_bill_before_tag"] = seen[2]["bill"].status_code
            out["tag"] = (await staff.post(f"/bills/{bid2}/tag", data={"to_employee_id": "2", "note": "Did the team ask Kesari for this extra cleaning?"})).status_code
            out["tag_self"] = (await staff.post(f"/bills/{bid2}/tag", data={"to_employee_id": "3", "note": "me"})).status_code
            staff.cookies.set("actor", "2")
            out["rahul_console_tagged"] = (await staff.get("/api/v1/console/home")).text
            page = await staff.get(f"/bills/{bid2}")
            out["rahul_bill_tagged"] = page
            tag_id = re.search(r'/bills/\d+/tag/(\d+)/done', page.text).group(1)
            staff.cookies.set("actor", "1")
            out["tag_wrong_person"] = (await staff.post(f"/bills/{bid2}/tag/{tag_id}/done", data={"reply": "x"})).status_code
            staff.cookies.set("actor", "2")
            out["tag_done"] = (await staff.post(f"/bills/{bid2}/tag/{tag_id}/done", data={"reply": "Yes, I asked them on 2 Nov."})).status_code
            out["rahul_console_after"] = (await staff.get("/api/v1/console/home")).text
            staff.cookies.set("actor", "3")
            out["bill_after_tag"] = (await staff.get(f"/bills/{bid2}")).text

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
            await drain()
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SMTP_HOST", None)
    os.environ.pop("MAIL_FROM", None)
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
    assert "Arjun Mehta" in flows["console_page"] and "Log out" in APP_JS


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
    assert "R-BILL-10" not in page and "fraud-class" not in page and "/files/" not in page
    assert KESARI["pan"] not in page and "Pays into" not in page
    run = priya["run"].text
    assert "Every rule that ran" not in run and "Internal note" not in run and "How well each fact is proven" not in run
    assert priya["file"] == 403 and priya["outbox"] == 403 and 'href="/outbox"' not in priya["console"]
    # Rahul has nothing to do with Kesari: he can't open it at all
    assert rahul["bill"].status_code == 403 and rahul["run"].status_code == 403 and rahul["events"] == 403
    assert "BILL-0002" not in rahul["bills"] and "Kesari" not in rahul["console"] and flows["rahul_action"] == 403
    assert "accounts@kesarifacility" not in rahul["vendors"] and '/bills/' not in rahul["vendors"]


def test_reviewers_see_everything_and_only_finance_sees_the_full_account(flows):
    arjun, kavita = flows["seen"][3], flows["seen"][4]
    acct = "50200099887766"   # Kesari's account after the approved bank change earlier in the flow
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


def test_vendor_360_is_the_supplier_record(flows):
    page = flows["kesari_360"]
    for text in ("Invoices and payments", "KFS/2026-27/0207", "UTR HDFC261103000417", "Supplier master", "Payment eligibility", "Documents",
                 "Cancelled cheque", "Blocked for investigation"):
        assert text in page or text.lower() in page.lower(), text
    assert "Investigate before anything is paid" in page          # the blocked duplicate leads the next actions
    assert "Kesari" in flows["vendor_dir"] and ('"eligible"' in flows["vendor_dir"] or '"blocked"' in flows["vendor_dir"])
    assert "Kesari" in flows["vendor_dir_unpaid"]


def test_bank_change_needs_finance_and_an_independent_check(flows):
    assert "Company and tax details" in flows["profile"] and "never inherits" in flows["profile"]
    assert flows["cr_post"] == 303 and "Being checked" in flows["profile_after"]
    assert flows["cr_maker"] == 403 and flows["cr_nonote"] == 400 and flows["cr_checker"] == 303
    assert [c["mine"] for c in flows["review_maker"]["changes"]] == [False]          # the reviewer sees it, Finance decides
    assert flows["cr_maker_api"].status_code == 403 and "Finance controller" in flows["cr_maker_api"].json()["error"]
    assert "••••7766" in flows["profile_done"] and "Approved" in flows["profile_done"]
    for path in ("/review", "/applications", "/relationships", "/audit?entity=change_request"):
        assert flows[path].status_code == 200, path
    assert "Called the number on record" in flows["/audit?entity=change_request"].text


def test_new_bank_account_does_not_inherit_the_old_level(flows):
    page = flows["kesari_360_after_change"]
    facts = page.split("Evidence and fact history", 1)[1].split("Relationships", 1)[0]
    assert "7766" in facts and "change request" in facts and "Not confirmed at source" in facts
    bank = facts.split("Bank account", 1)[1][:1500]
    assert "A1" in bank and "7766" in bank      # the current bank fact is the new account, at its own (lower) level



def test_vendor_360_reads_as_a_product(flows):
    """Supplier record and latest application are separate cards; known files and registration bills say what they are."""
    page = flows["kesari_360_after_change"]
    assert "Supplier master" in page and "Latest application" in page and "Payment eligibility" in page
    assert "demo specimen" not in page and "fictional" not in page.lower()
    if "Onboarding bill" in page:
        assert "not a payable invoice" in page


def test_old_development_wording_is_not_shown_for_known_files():
    from onboarding.web import signal_text
    old = {"code": "SPECIMEN", "title": "Known fictional test document (generated for this demo)", "detail": "x"}
    shown = signal_text(old)
    assert "fictional" not in shown["title"].lower() and "demo" not in shown["title"].lower()
    assert "not independently confirmed" in shown["detail"]
    assert "known file" in signal_text({"code": "AU-1", "title": "t", "detail": "[not applied: known test specimen] y"})["detail"]


def test_registration_form_marks_required_fields_and_checks_the_pin(flows):
    page = flows["bill_form_page"]
    assert "are required, and so are the documents" in page and page.count('text-rose-600 ml-0.5') >= 10
    assert 'id="pin-msg"' in page and "PIN_SPECIFIC" in page and "R-ID-10" in page
    assert 'name="alt_contact_email"' in page and "Alternate contact" in page
    assert "under review" in page and "email the contact above" in page


def test_weak_passwords_are_refused(flows):
    assert "needs" in html.unescape(flows["weak_pw"]) and "an uppercase letter" in html.unescape(flows["weak_pw"])


def test_after_submitting_the_vendor_sees_under_review_not_thank_you(flows):
    page = html.unescape(flows["home_submitted"])
    assert "Submitted · under review" in page and "Thank you" not in page and "bg-amber-50" in page
    assert "isn't final until our team confirms it" in page


def test_the_vendor_is_emailed_when_a_decision_is_released(flows):
    mails = flows["mails"]
    activated = [m for m in mails if "active" in m["subject"].lower()]
    assert activated, [m["subject"] for m in mails]
    assert "kesarifacility" in activated[0]["to"]


def test_invoices_filter_by_amount_vendor_and_sort(flows):
    def order(d):
        return [x["invoice_number"] for x in d["invoices"] if (x["invoice_number"] or "").startswith("KFS/2026-27/0")]
    desc, asc = order(flows["filter /invoices?sort=amount_desc"]), order(flows["filter /invoices?sort=amount_asc"])
    assert desc[0] == "KFS/2026-27/0219" and asc[0] == "KFS/2026-27/0211"          # 42,480 is the largest, 23,600 the smallest
    assert set(order(flows["filter /invoices?amin=41000"])) == {"KFS/2026-27/0219"}
    assert set(order(flows["filter /invoices?amax=30000"])) == {"KFS/2026-27/0211"}
    assert flows["filter /invoices?vendor=V-9999"]["invoices"] == []
    assert flows["filter /invoices?amin=41000"]["filters"]["amin"] == "41000"
    assert 'name="vendor"' in APP_JS and "Amount: high to low" in APP_JS and "No invoices match" in APP_JS and "Clear</a>" in APP_JS


def test_navigation_uses_short_names_and_help_replaces_sources(flows):
    page = APP_JS                                                     # the menu is drawn by the app
    for label in ("'Review'", "'Invoices'", "'Orders'", "'History'", "}Help<"):
        assert label in page, label
    assert "Verification sources" not in page and "Decisions and audit" not in page and "Invoice verification" not in page


def test_home_is_only_what_needs_approving(flows):
    page = flows["console_page"]                                      # GET /api/v1/console/home
    assert '"todo"' in page and "Vendors to approve" in page and "Invoices to approve" in page
    for gone in ("Where applications stand", "Recent decisions", "Recent checks", "Relationship alerts"):
        assert gone not in page and gone not in APP_JS, gone
    assert "Waiting for you" in APP_JS and "'Approvals'" in APP_JS and "'In depth'" in APP_JS and "'Documents'" in APP_JS


def test_documents_page_lists_every_upload(flows):
    page = flows["documents"]
    assert "Documents" in page and "GST certificate" in page and "/files/" in page and "Kesari" in page
    assert "Onboarding bill" in flows["documents_bills"] and "GST certificate</div>" not in flows["documents_bills"]



def test_pending_reminder_feed_and_house_style(flows):
    assert flows["pending_anon"] == 401                                          # signed out: the API says so
    assert isinstance(flows["pending"]["count"], int) and len(flows["pending"]["items"]) <= 4
    page = flows["applications_page"]
    assert 'id="pending-note"' in page and "/api/v1/console/pending" in page     # reminder on other pages
    assert "path === '/console'" in APP_JS                                        # ... not on Home, which already lists them
    assert "/static/app.css" in page and "-apple-system" in APP_CSS and "Verdana" not in APP_CSS and "#F5F5F7" in APP_CSS
    assert "html.js .sr" in APP_CSS and "IntersectionObserver" in page            # blocks rise in as they scroll into view


def test_order_rows_turn_red_on_a_mismatch():
    from types import SimpleNamespace as NS
    from onboarding.ap.web import _po_issues
    bill = lambda rules, status="for_review": NS(ref="BILL-9", status=status, rules=rules)  # noqa: E731
    case = NS(payment_status="unpaid")
    base = dict(receipts=[1], delivered_value=100.0, total=100.0)
    issues, tone = _po_issues(base | dict(invoices=[(bill([{"rule_id": "R-PO-05", "result": "FAIL"}]), case)]))
    assert tone == "red" and issues == ["BILL-9: unit price mismatch"]
    assert _po_issues(base | dict(invoices=[(bill([{"rule_id": "R-PO-05", "result": "FAIL"}], "rejected"), case)]))[1] == "green"   # a rejected invoice no longer counts
    assert _po_issues(base | dict(invoices=[(bill([{"rule_id": "R-PO-05", "result": "PASS"}]), case)]))[1] == "amber"
    assert _po_issues(base | dict(invoices=[(bill([]), NS(payment_status="paid"))]))[1] == "green"
    assert _po_issues(dict(receipts=[], delivered_value=0, total=100.0, invoices=[]))[1] == "amber"


def test_ready_replies_carry_the_right_figures():
    from types import SimpleNamespace as NS
    from onboarding.ap.replies import suggested_replies
    from onboarding.demo_data import BUYER
    b = NS(ref="BILL-9", invoice_number="KFS/101", po_number="PO-1", rules=[
        {"rule_id": "R-PO-06", "result": "FAIL", "evidence": {"expected": 118000.0, "billed": 177000.0}},
        {"rule_id": "R-PO-04", "result": "FAIL", "evidence": {}},
        {"rule_id": "R-BILL-02", "result": "FAIL", "evidence": {"seller_gstin": "27AAAAA0000A1Z5"}},
        {"rule_id": "R-PO-05", "result": "PASS"}])
    case = NS(match={"lines": [{"description": "Guard shift", "po_desc": "Security guard shift", "billed_qty": 3, "received": 2,
                                "billed_before": 0, "unit": "shift", "billed_price": 50000, "po_price": 50000}]})
    replies = {r["key"]: r for r in suggested_replies(b, case, NS(po_number="PO-1"), NS(gstin="27AAKCK4417F1ZJ", account="123456789012"), BUYER)}
    assert "₹1,18,000.00" in replies["total"]["text"] and "₹1,77,000.00" in replies["total"]["text"]
    assert "delivered 2 shift, billed 3" in replies["quantity"]["text"]
    assert "27AAKCK4417F1ZJ" in replies["gstin"]["text"]
    assert "price" not in replies                                    # rates matched: no reply about them
    assert {"clear_copy", "addressed"} <= set(replies)               # the general ones are always there


def test_tag_a_teammate_on_an_invoice(flows):
    assert flows["rahul_bill_before_tag"] == 403                      # not his bill ...
    assert flows["tag"] == 303 and flows["tag_self"] == 400
    assert "tagged you" in flows["rahul_console_tagged"]              # ... until he is tagged on it
    assert flows["rahul_bill_tagged"].status_code == 200 and "Mark done" in flows["rahul_bill_tagged"].text
    assert flows["tag_wrong_person"] == 403 and flows["tag_done"] == 303
    assert "tagged you" not in flows["rahul_console_after"]
    page = flows["bill_after_tag"]
    assert "@Rahul Desai" in page and "Yes, I asked them on 2 Nov." in page and "Tag a teammate" in page


def test_review_badge_home_and_review_count_the_same_things(flows):
    fin, mk = flows["pending_finance_cr"], flows["pending_maker_cr"]
    assert any(i["href"] == "/review#changes" for i in fin["items"])           # a bank change waits for Finance ...
    assert not any(i["href"] == "/review#changes" for i in mk["items"])        # ... not for the reviewer
    assert flows["review_finance"]["counts"]["review"] == fin["count"]                # Review and the badge count the same things
    rv = flows["review_finance"]
    assert len(rv["changes"]) + len(rv["invoices"]) + len(rv["apps"]) >= 1
    page = APP_JS
    assert 'id="invite-box"' in page and 'review-count' in page
    nav = page[page.index("const NAV"):page.index("const REVIEWER_ONLY")]
    assert "'/invites'" not in nav                                              # Invites lives on Home, not in the menu


def test_applications_is_a_main_tab_with_its_own_count(flows):
    apps, fin = flows["applications_finance"], flows["pending_finance_cr"]
    nav = APP_JS[APP_JS.index("const NAV"):]
    assert nav.index("'/applications'") < nav.index("'/review'") < nav.index("'/invoices'")
    assert "apps" in fin and fin["apps"] <= fin["count"]
    waiting = [a for a in apps["applications"] if a["waiting"]]
    assert len(waiting) == fin["apps"] and apps["applications"][:len(waiting)] == waiting       # waiting ones first
