"""The India Post comparison: wrong state is a problem for the vendor; a city name that differs from the district is only a note."""
from onboarding.pincode import live_pin_problem

PEENYA = {"districts": ["Bangalore"], "states": ["Karnataka"], "offices": ["Laggere", "Peenya I Stage"], "blocks": ["Bangalore North"]}


def test_old_and_new_city_names_match():
    assert live_pin_problem("560058", "Karnataka", "Bengaluru", PEENYA) == ("", "")
    assert live_pin_problem("560058", "Karnataka", "Peenya", PEENYA) == ("", "")


def test_wrong_state_is_a_problem():
    why, note = live_pin_problem("560058", "Maharashtra", "Pune", PEENYA)
    assert "Karnataka, not Maharashtra" in why and "Bangalore" in why and not note


def test_other_city_is_only_a_note():
    why, note = live_pin_problem("560058", "Karnataka", "Mysuru", PEENYA)
    assert not why and "Bangalore district" in note and "Mysuru" in note
