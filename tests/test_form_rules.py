"""Strong passwords, PIN code vs state, and the alternate contact."""

from onboarding import rules
from onboarding.auth import password_problem
from onboarding.demo_data import SCENARIOS
from onboarding.pincode import pin_problem, states_for_pin


def test_passwords_need_upper_lower_number_symbol_and_length():
    assert password_problem("Kesari@2026") == ""
    for weak, missing in (("Ab@1", "at least 8 characters"), ("kesari@2026", "an uppercase letter"),
                          ("KESARI@2026", "a lowercase letter"), ("Kesari@abcd", "a number"), ("Kesari2026", "a symbol"),
                          ("demo_pass", "an uppercase letter")):
        problem = password_problem(weak)
        if missing:
            assert missing in problem, (weak, problem)
    assert "too easy" in password_problem("P@ssw0rd")


def test_pin_codes_belong_to_their_state():
    assert pin_problem("560058", "Karnataka") == ""          # Bengaluru
    assert pin_problem("411037", "Maharashtra") == ""        # Pune
    assert pin_problem("500034", "Telangana") == ""          # Hyderabad
    assert pin_problem("403001", "Goa") == ""                # Panaji: inside Maharashtra's 40-44 circle
    assert pin_problem("737101", "Sikkim") == ""             # Gangtok: inside West Bengal's 70-74
    assert "Karnataka, not Maharashtra" in pin_problem("560058", "Maharashtra")
    assert "Goa" in pin_problem("403001", "Maharashtra")
    assert "valid PIN" in pin_problem("56005", "Karnataka") and "valid PIN" in pin_problem("060058", "Karnataka")
    assert states_for_pin("990001") is None and "valid PIN" in pin_problem("990001", "Delhi")   # 9: army postal service, not a state
    for key, sc in SCENARIOS.items():                         # every demo vendor's address is consistent
        assert pin_problem(sc["form"]["pin"], sc["form"]["state"]) == "", key


def test_the_checks_send_a_wrong_pin_back_to_the_vendor():
    form = dict(SCENARIOS["happy_nilgiri"]["form"])
    ok = {r.rule_id: r for r in rules.evaluate(rules.Context(form=form, docs={}))}
    assert ok["R-ID-10"].result == rules.PASS
    form["state"] = "Maharashtra"
    bad = {r.rule_id: r for r in rules.evaluate(rules.Context(form=form, docs={}))}
    assert bad["R-ID-10"].result == rules.FAIL and bad["R-ID-10"].outcome == "VENDOR"
    assert "Karnataka" in bad["R-ID-10"].vendor_text
    form["pin"] = ""
    missing = {r.rule_id: r for r in rules.evaluate(rules.Context(form=form, docs={}))}
    assert "pin" in missing["R-COMP-01"].evidence["missing"]


def test_alternate_contact_is_optional_and_labelled():
    form = dict(SCENARIOS["happy_nilgiri"]["form"])
    assert not any(k.startswith("alt_") for k in rules.required_fields(form))
    assert rules.FIELD_LABEL["alt_contact_email"] == "Alternate contact email"


# --- vendors outside India: the tax ID must fit the country; the bank must be in it ---------------
from onboarding import countries as C  # noqa: E402
from onboarding.decision import decide  # noqa: E402


def _abroad(**over):
    form = dict(SCENARIOS["happy_nilgiri"]["form"]) | dict(country="United Kingdom", tax_id="GB123456789", swift="BARCGB22XXX",
                                                          postal_code="EC1A 1BB", gstin="", pan="", state="", pin="", ifsc="")
    return form | over


def test_tax_id_formats_by_country():
    assert C.tax_id_problem("United Kingdom", "GB123456789") == "" and C.tax_id_problem("United Kingdom", "GB 123 4567 89") == ""
    assert C.tax_id_problem("United States", "12-3456789") == "" and C.tax_id_problem("Singapore", "201912345K") == ""
    assert C.tax_id_problem("United Arab Emirates", "100123456700003") == ""
    assert "looks like GB123456789" in C.tax_id_problem("United Kingdom", "GB12345")
    assert "from India" in C.tax_id_problem("United Kingdom", "29AAHCN4821K1Z4")         # a GSTIN typed for a UK vendor
    assert "from United Kingdom" in C.tax_id_problem("United States", "GB123456789")
    assert C.swift_problem("United Kingdom", "BARCGB22") == ""
    assert "India" in C.swift_problem("United Kingdom", "HDFCINBBXXX") and "8 or 11" in C.swift_problem("Singapore", "DBS")


def test_abroad_bad_tax_id_goes_back_to_the_vendor_then_to_our_team():
    bad = rules.evaluate(rules.Context(form=_abroad(tax_id="12345"), docs={}))
    by = {r.rule_id: r for r in bad}
    assert by["R-ID-11"].result == rules.FAIL and by["R-ID-11"].outcome == "VENDOR" and "GB123456789" in by["R-ID-11"].vendor_text
    assert by["R-SCOPE-01"].result == rules.WARN
    assert "bank_proof" in by["R-COMP-02"].evidence["missing"] and "gst_certificate" not in by["R-COMP-02"].evidence["missing"]
    inv = {"status": "open", "company_name": _abroad()["legal_name"], "sponsor": "Priya Nair", "reason": "test"}
    ctx = rules.Context(form=_abroad(tax_id="12345"), docs={"bank_proof": object()}, invite=inv)
    assert decide(rules.evaluate(ctx), ctx).status == "PENDING_VENDOR"
    swift = {r.rule_id: r for r in rules.evaluate(rules.Context(form=_abroad(swift="HDFCINBBXXX"), docs={}))}
    assert swift["R-ID-12"].result == rules.FAIL and "India" in swift["R-ID-12"].vendor_text
    missing = {r.rule_id: r for r in rules.evaluate(rules.Context(form=_abroad(tax_id="", postal_code=""), docs={}))}
    assert {"tax_id", "postal_code"} <= set(missing["R-COMP-01"].evidence["missing"]) and "gstin" not in missing["R-COMP-01"].evidence["missing"]


def test_abroad_correct_details_go_to_our_team():
    docs = {"bank_proof": object()}
    good = rules.evaluate(rules.Context(form=_abroad(), docs=docs))
    by = {r.rule_id: r for r in good}
    assert by["R-ID-11"].result == rules.PASS and by["R-ID-12"].result == rules.PASS
    assert by["R-SCOPE-01"].result == rules.FAIL and by["R-SCOPE-01"].outcome == "REVIEW"
