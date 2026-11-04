import pytest

from onboarding.names import MATCH, MISMATCH, PARTIAL, compare, normalise

# Calibration pairs from docs/agents/01-business-process.md §4.2.
@pytest.mark.parametrize(
    "a,b,individual,band",
    [
        ("Shree Ganesh Enterprises", "Sri Ganesh Enterprises", False, MATCH),
        ("Rangoli Print House", "Rangoli Prints House", False, MATCH),
        ("Ramesh Shinde", "Ramesh Vitthal Shinde", True, MATCH),       # middle name rule
        ("Kaveri Agro Traders", "Kaveri Agro Foods", False, MISMATCH),
        ("Shinde Electricals", "Ramesh Vitthal Shinde", False, MISMATCH),
    ],
)
def test_calibration_pairs(a, b, individual, band):
    assert compare(a, b, individual=individual).band == band


def test_middle_name_rule_only_for_individuals():
    assert compare("Ramesh Shinde", "Ramesh Vitthal Shinde", individual=False).band != MATCH


def test_suffix_variants_are_the_same_company():
    m = compare("Nilgiri Packaging Solutions Private Limited", "NILGIRI PACKAGING SOLUTIONS PVT LTD")
    assert m.band == MATCH and m.score == 100


def test_honorifics_and_ampersand():
    assert normalise("M/S Shah & Sons")[0] == "SHAH AND SONS"


def test_different_legal_forms_never_auto_match():
    m = compare("Kaveri Agro Private Limited", "Kaveri Agro LLP")
    assert m.score <= 89 and m.band == PARTIAL


def test_institution_initials_and_designated_account_need_a_person():
    from onboarding import names as N
    m = N.compare("Indian Institute of Technology (Banaras Hindu University)", "IIT (BHU) RESEARCH & DEVELOPMENT ACCOUNT")
    assert m.band == N.PARTIAL and "initials" in m.note and "RESEARCH AND DEVELOPMENT ACCOUNT" in m.note
    assert N.compare("Rangoli Print House Private Limited", "DECCAN OFFICE SUPPLIES").band == N.MISMATCH
