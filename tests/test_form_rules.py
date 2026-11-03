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
