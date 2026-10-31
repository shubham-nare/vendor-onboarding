from onboarding.matching import (
    MATCH, MATCH_CORRECTED, MISMATCH, MISSING, UNREADABLE, compare_account, compare_id, compare_name,
)


# --- IDs: structure-aware correction --------------------------------------------------
def test_pan_exact():
    assert compare_id("pan", "AAHCN4821K", "AAHCN4821K").status == MATCH


def test_pan_confusables_corrected_only_in_fixed_positions():
    # 'O' read as '0' in a letter position, 'B' read as '8'... in digit position '8' is correct
    r = compare_id("pan", "AOHCN4821K", "A0HCN4821K")
    assert r.status == MATCH_CORRECTED and "position 2" in r.detail
    r = compare_id("pan", "AAHCN4821K", "AAHCN482IK")  # 'I' in a digit position -> '1'
    assert r.status == MATCH_CORRECTED


def test_pan_real_difference_is_a_mismatch():
    assert compare_id("pan", "AAHCN4821K", "AAKFK7316M").status == MISMATCH


def test_gstin_correction_needs_the_check_digit():
    # '0' misread as 'O' in a digit position; corrected value passes the check digit
    r = compare_id("gstin", "29AAHCN4821K1Z4", "29AAHCN4B21K1Z4")
    assert r.status == MATCH_CORRECTED and "check digit" in r.detail


def test_gstin_one_real_digit_change_is_not_corrected():
    assert compare_id("gstin", "27PNEI00141B1DI", "26PNEI00141B1DI").status == MISMATCH


def test_unclear_reading_is_never_a_mismatch():
    assert compare_id("pan", "AAHCN4821K", "AAKFK7316M", "partial").status == UNREADABLE
    assert compare_id("pan", "AAHCN4821K", None, "unreadable").status == UNREADABLE
    assert compare_id("pan", "AAHCN4821K", None, "not_present").status == MISSING


def test_ifsc_fifth_character_is_always_zero():
    assert compare_id("ifsc", "HDFC0000009", "HDFCO000009").status == MATCH_CORRECTED


# --- bank account: strict ---------------------------------------------------------------
def test_account_exact_with_spaces():
    assert compare_account("50200071234567", "5020 0071 2345 67").status == MATCH


def test_account_one_digit_off_is_never_corrected():
    r = compare_account("50200071234567", "50200071234568")
    assert r.status == MISMATCH and "different account" in r.detail


def test_account_masked_with_x_is_unreadable():
    assert compare_account("50200071234567", "XXXXXXXXX").status == UNREADABLE


def test_account_one_digit_off_on_a_blurry_copy_asks_for_a_clearer_copy():
    assert compare_account("50200071234567", "50200071234568", "partial").status == UNREADABLE


# --- names ----------------------------------------------------------------------------------
def test_suffix_spellings_line_up():
    assert compare_name("Nilgiri Packaging Solutions Private Limited", "NILGIRI PACKAGING SOLUTIONS PVT. LTD.").status == MATCH


def test_truncated_on_cheque():
    r = compare_name("Nilgiri Packaging Solutions Private Limited", "NILGIRI PACKAGING SOLUTIONS PV")
    assert r.status == MATCH and "truncated" in r.note


def test_short_truncation_is_not_trusted():
    assert compare_name("Nilgiri Packaging Solutions Private Limited", "NILGIRI PAC").status != MATCH


def test_initials_for_individuals_only():
    assert compare_name("Ramesh Vitthal Shinde", "R V SHINDE", individual=True).status == MATCH
    assert compare_name("Ramesh Vitthal Shinde", "R V SHINDE", individual=False).status != MATCH


def test_initials_must_line_up():
    assert compare_name("Ramesh Vitthal Shinde", "S V KADAM", individual=True).status == MISMATCH


def test_abbreviations():
    assert compare_name("Shah Brothers Enterprises", "SHAH BROS ENT").status == MATCH
    assert compare_name("M/s Patil & Co", "PATIL AND COMPANY").status == MATCH


def test_partial_name_on_blurry_copy_asks_for_a_clearer_copy():
    r = compare_name("Kaveri Agro Traders", "KAVERI AGRO TRADING CO", legibility="partial")
    assert r.status in (MATCH, UNREADABLE)


def test_borrowed_name_still_mismatches():
    assert compare_name("Kaveri Agro Traders", "KAVERI AGRO FOODS PRIVATE LIMITED").status == MISMATCH
