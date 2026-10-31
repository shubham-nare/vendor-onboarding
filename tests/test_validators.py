import pytest

from onboarding import validators as v

# The demo fixtures (all fictional) and one published real example.
FIXTURE_GSTINS = {
    "29AAHCN4821K1Z4": ("AAHCN4821K", "29", "Karnataka"),        # Nilgiri, happy path
    "36AAJCT9052D1Z7": ("AAJCT9052D", "36", "Telangana"),        # Tejas, wrong document
    "27AAHCK5590L1ZX": ("AAHCK5590L", "27", "Maharashtra"),      # Kaveri Agro Foods (borrowed)
    "36AAQCR6188B1ZZ": ("AAQCR6188B", "36", "Telangana"),        # Rangoli, shared bank
    "27BVKPS5274R1ZE": ("BVKPS5274R", "27", "Maharashtra"),      # Shinde, proprietor
    "27AAPFU0939F1ZV": ("AAPFU0939F", "27", "Maharashtra"),      # published example
}


@pytest.mark.parametrize("gstin", FIXTURE_GSTINS)
def test_fixture_gstins_pass_format_and_checksum(gstin):
    assert v.gstin_format_ok(gstin)
    assert v.gstin_checksum_ok(gstin)


@pytest.mark.parametrize("gstin,expected", FIXTURE_GSTINS.items())
def test_gstin_parts(gstin, expected):
    pan, code, state = expected
    assert v.gstin_embedded_pan(gstin) == pan
    assert v.gstin_state(gstin) == (code, state)


def test_one_character_typo_fails_checksum():
    # The "pocket" demo: mistype one digit.
    assert not v.gstin_checksum_ok("29AAHCN4831K1Z4")
    assert v.gstin_format_ok("29AAHCN4831K1Z4")  # still looks right


def test_lowercase_and_spaces_are_normalised():
    assert v.gstin_checksum_ok(" 29aahcn4821k1z4 ")


def test_pan_format_and_holder_type():
    assert v.validate_pan("AAHCN4821K")
    assert v.pan_code("AAHCN4821K") == "C"
    assert v.pan_code("BVKPS5274R") == "P"
    assert v.pan_code("AAKFK7316M") == "F"
    assert not v.validate_pan("AAHCN482K")


def test_expected_pan_codes_cover_all_business_types():
    assert set(v.EXPECTED_PAN_CODE) == set(v.BUSINESS_TYPES)


def test_ifsc():
    assert v.validate_ifsc("HDFC0000001")
    assert not v.validate_ifsc("HDFC1000001")  # 5th char must be zero


def test_cin_and_llpin():
    assert v.cin_ok("U22220KA2015PTC081234", "PVT_LTD")
    assert not v.cin_ok("U22220KA2015PLC081234", "PVT_LTD")
    assert v.llpin_ok("AAB-1234")


def test_account_and_udyam():
    assert v.account_number_ok("50200012345678")
    assert not v.account_number_ok("12345")
    assert v.udyam_ok("UDYAM-TS-02-0012345")


def test_state_reverse_lookup():
    assert v.state_code_for_name("Telangana") == "36"
    assert v.state_code_for_name("karnataka") == "29"
    assert v.state_code_for_name("Narnia") is None


def test_masking():
    assert v.mask_account("50200012345678").endswith("5678")
    assert "•" in v.mask_pan("AAHCN4821K")
