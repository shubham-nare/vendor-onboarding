"""The address checks: typed address vs the GST certificate, and Google's Address Validation verdict (faked here)."""

import asyncio

from onboarding import address as A

CERT = "Gat No. 418, Chakan Industrial Area Phase I, Pune, Maharashtra, 410501"


def form(**kw):
    return {"address": "Gat No. 418, Chakan Industrial Area Phase I", "city": "Pune", "state": "Maharashtra", "pin": "410501"} | kw


def test_same_address_matches_even_written_differently():
    assert A.compare(form(), CERT).status == A.MATCH
    assert A.compare(form(address="Gat 418, Chakan Indl Area Ph I"), CERT).status == A.MATCH


def test_labelled_certificate_layout():
    cert = "Building No./Flat No.: 418 Road/Street: Chakan Industrial Area Phase I City/Town/Village: Pune District: Pune State: Maharashtra PIN Code: 410501"
    assert A.compare(form(address="418, Chakan Industrial Area Phase I"), cert).status == A.MATCH


def test_different_pin_or_state_is_a_mismatch():
    m = A.compare(form(pin="411037"), CERT)
    assert m.status == A.MISMATCH and any("PIN code 411037" in r for r in m.reasons)
    assert A.compare(form(state="Karnataka"), CERT).status == A.MISMATCH


def test_another_street_in_the_same_pin_is_a_mismatch_and_a_different_plot_is_partial():
    assert A.compare(form(address="Shop 14, Market Yard, Gultekdi"), CERT).status == A.MISMATCH
    m = A.compare(form(address="Gat No. 420, Chakan Industrial Area Phase I"), CERT)
    assert m.status == A.PARTIAL and any("plot number" in r for r in m.reasons)


def test_unreadable_certificate_address():
    assert A.compare(form(), "").status == A.UNREADABLE


GOOGLE_OK = {"result": {
    "verdict": {"validationGranularity": "PREMISE", "addressComplete": True},
    "address": {"formattedAddress": "Gat No. 418, Chakan Industrial Area Phase I, Pune, Maharashtra 410501, India",
                "addressComponents": [{"componentType": "postal_code", "componentName": {"text": "410501"}, "confirmationLevel": "CONFIRMED"}]},
    "geocode": {"location": {"latitude": 18.76, "longitude": 73.86}}}}


def test_google_verdicts():
    d = A.summarize(GOOGLE_OK)
    assert d["granularity"] == "PREMISE" and d["postal_code"] == "410501" and "18.76,73.86" in d["maps_url"]
    assert A.judge(form(), d) == ("PASS", "Google found this address (to the building)")
    assert A.judge(form(pin="411037"), d)[0] == "WARN"
    assert A.judge(form(), A.summarize({"result": {"verdict": {"validationGranularity": "OTHER"}}}))[0] == "WARN"


def test_google_is_off_without_a_key():
    assert not A.configured()
    assert asyncio.run(A.validate(form())) is None
