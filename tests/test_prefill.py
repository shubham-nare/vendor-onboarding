"""Upload first: documents fill the form, the vendor confirms, and a changed value is a signal to the reviewer."""

import json

from onboarding.ai.read import DocRead, FieldReading, ReadResult
from onboarding.prefill import changes, parse_record, split_address, suggestions
from onboarding.rules import PASS, WARN, Context, evaluate


def doc(doc_type, **fields):
    return DocRead(doc_type=doc_type, doc_type_evidence="", document_form="ORIGINAL_DIGITAL", document_form_evidence="",
                   fields=[FieldReading(name=k, value=v[0] if isinstance(v, tuple) else v,
                                        legibility=v[1] if isinstance(v, tuple) else "clear") for k, v in fields.items()])


def test_addresses_split_into_street_city_state_and_pin():
    a = split_address("Plot 47, 2nd Phase, Peenya Industrial Area, Bengaluru, Karnataka, 560058")
    assert a == {"address": "Plot 47, 2nd Phase, Peenya Industrial Area", "city": "Bengaluru", "state": "Karnataka", "pin": "560058"}
    b = split_address("GROUND FLOOR, NEW ADMIN BUILDING, CAMP ROAD, PUNE, Pune, Maharashtra, 411001")
    assert b["city"] == "Pune" and b["address"] == "GROUND FLOOR, NEW ADMIN BUILDING, CAMP ROAD"     # "PUNE, Pune" once
    c = split_address("Building No./Flat No.: WARD NO. 2 BUILDING NUMBER 1356 Name Of Premises/Building: THE REGISTRAR Road/Street: PUDUSSERY "
                      "Locality/Sub Locality: Kanjikkod City/Town/Village: Pudussery District: Palakkad State: Kerala PIN Code: 678623")
    assert c == {"address": "WARD NO. 2 BUILDING NUMBER 1356, THE REGISTRAR, PUDUSSERY, Kanjikkod", "city": "Pudussery", "state": "Kerala", "pin": "678623"}


def test_a_gst_certificate_fills_the_business_and_address():
    s = suggestions("gst_certificate", doc("GST_CERTIFICATE", gstin="29aabcn1234k1z5", legal_name="NILGIRI PACKAGING PRIVATE LIMITED",
                                           constitution="Private Limited Company",
                                           principal_address="Plot 47, Peenya Industrial Area, Bengaluru, Karnataka, 560058", state="Karnataka"))
    f = {k: v["value"] for k, v in s["fields"].items()}
    assert s["right_slot"] and f["gstin"] == "29AABCN1234K1Z5" and f["pan"] == "AABCN1234K"       # PAN from inside the GSTIN
    assert f["business_type"] == "PVT_LTD" and f["city"] == "Bengaluru" and f["state"] == "Karnataka" and f["pin"] == "560058"


def test_only_legible_values_are_suggested_and_doubtful_ones_are_marked():
    s = suggestions("bank_proof", doc("CANCELLED_CHEQUE", account_number=("0123 0500 4321", "partial"), ifsc="icic0000008",
                                      account_holder_name=("", "unreadable")))
    assert s["fields"]["bank_account"] == {"value": "012305004321", "check": True}
    assert s["fields"]["ifsc"] == {"value": "ICIC0000008", "check": False} and "bank_holder" not in s["fields"]


def test_a_document_in_the_wrong_slot_fills_nothing():
    s = suggestions("gst_certificate", doc("PAN_CARD", pan="AABCN1234K"))
    assert not s["right_slot"] and not s["fields"] and "PAN card" in s["message"]


def test_a_persons_pan_card_names_the_proprietor():
    s = suggestions("pan_card", doc("PAN_CARD", pan="ABCPD1234E", name_on_card="RAVI DESHMUKH"))
    assert s["fields"]["proprietor_name"]["value"] == "RAVI DESHMUKH"
    assert "proprietor_name" not in suggestions("pan_card", doc("PAN_CARD", pan="AABCN1234K", name_on_card="NILGIRI PACKAGING"))["fields"]


def test_the_record_from_the_browser_is_sanitised():
    rec = parse_record(json.dumps({"gstin": {"value": "29AABCN1234K1Z5", "from": "GST certificate"}, "evil": {"value": "x"}, "pan": "not a dict"}))
    assert list(rec) == ["gstin"]
    assert parse_record("not json") == {} and parse_record("[1, 2]") == {}


def _rule(form):
    base = {"country": "India", "gst_registered": True, "business_type": "PVT_LTD"}
    return next(r for r in evaluate(Context(form=base | form, docs={})) if r.rule_id == "R-PF-01")


def test_changing_a_key_value_after_we_read_it_warns_the_reviewer():
    rec = {"gstin": {"value": "29AABCN1234K1Z5", "from": "GST certificate"}, "city": {"value": "Bengaluru", "from": "GST certificate"}}
    same = _rule({"gstin": "29aabcn1234k1z5", "city": "bengaluru ", "prefill": rec})
    assert same.result == PASS and "2 details filled" in same.title
    moved = _rule({"gstin": "29AABCN1234K1Z5", "city": "Bangalore", "prefill": rec})
    assert moved.result == PASS and "adjusted: City" in moved.title                       # a city spelling isn't a red flag
    changed = _rule({"gstin": "27AABCN1234K1Z9", "city": "Bengaluru", "prefill": rec})
    assert changed.result == WARN and "GSTIN" in changed.title
    assert changed.evidence["read"]["gstin"] == "29AABCN1234K1Z5" and changed.evidence["submitted"]["gstin"] == "27AABCN1234K1Z9"
    assert changes({"gstin": "X", "prefill": rec}) == (["gstin", "city"], ["gstin", "city"])


def test_without_prefill_there_is_no_signal():
    assert not any(r.rule_id == "R-PF-01" for r in evaluate(Context(form={"country": "India", "gst_registered": True}, docs={})))


def test_the_read_endpoint_suggests_values_and_is_limited(monkeypatch):
    from fastapi.testclient import TestClient

    import onboarding.ai.read as reader
    from onboarding.main import app

    async def fake(data, mime, prefer="live"):
        return ReadResult(ok=True, read=doc("CANCELLED_CHEQUE", account_number="50200088412375", ifsc="HDFC0000007",
                                           account_holder_name="KESARI FACILITY SERVICES PVT LTD")), "cache"
    monkeypatch.setattr(reader, "read_with_cache", fake)
    from onboarding import security
    import onboarding.config as cfg
    monkeypatch.setenv("RATE_LIMITS", "true")
    cfg.get_settings.cache_clear()
    security.READ_PER_IP.reset()
    c = TestClient(app, raise_server_exceptions=False)  # no lifespan: no database needed
    files = {"file": ("cheque.pdf", b"%PDF-1.4 cheque", "application/pdf")}
    r = c.post("/apply/read", data={"slot": "bank_proof"}, files=files).json()
    assert r["ok"] and r["fields"]["ifsc"]["value"] == "HDFC0000007" and r["source"] == "cheque"
    assert c.post("/apply/read", data={"slot": "bank_proof"}, files={"file": ("x.exe", b"MZ", "application/x-msdownload")}).status_code == 400
    assert c.post("/apply/read", data={"slot": "secrets"}, files=files).status_code == 400
    for _ in range(security.READ_PER_IP.limit):
        c.post("/apply/read", data={"slot": "bank_proof"}, files=files)
    assert c.post("/apply/read", data={"slot": "bank_proof"}, files=files).status_code == 429
    monkeypatch.setenv("RATE_LIMITS", "false")
    cfg.get_settings.cache_clear()


def test_the_form_starts_with_the_documents(monkeypatch):
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "onboarding" / "templates" / "apply.html").read_text(encoding="utf-8")
    assert page.index("Start with your documents") < page.index("Check your business details")
    assert 'name="prefill"' in page and "/apply/read" in page and "Changed by you" in page


def test_finishing_a_name_the_reader_cut_short_is_not_a_change():
    rec = {"legal_name": {"value": "INDIAN INSTITUTE OF TECHNOLOGY (BANARAS HINDU", "from": "GST certificate"},
           "ifsc": {"value": "SBIN0011445", "from": "bank letter"}}
    done = _rule({"legal_name": "Indian Institute of Technology (Banaras Hindu University) Varanasi", "ifsc": "SBIN0011445", "prefill": rec})
    assert done.result == PASS and "adjusted: Legal name" in done.title
    other = _rule({"legal_name": "Deccan Office Supplies", "ifsc": "SBIN0011445", "prefill": rec})
    assert other.result == WARN and "Legal name" in other.title
    assert _rule({"legal_name": rec["legal_name"]["value"], "ifsc": "SBIN0011446", "prefill": rec}).result == WARN   # identifiers: any change


def test_a_bank_letter_is_named_as_one():
    assert suggestions("bank_proof", doc("BANK_LETTER", ifsc="SBIN0011445"))["source"] == "bank letter"
