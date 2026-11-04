"""Identifier validators for the vendor onboarding review.

These check the *shape* of an identifier (format, check digit, what its parts
encode). They never prove that an identifier is issued, active, or belongs to
the business that submitted it. Sources: docs/agents/02-compliance-validation.md.
"""

from __future__ import annotations

import re
from typing import Optional


# Current codes plus historic codes that may occur in an older GSTIN.  Code 25
# was folded into 26 in 2020 and 28 was replaced by 36/37 after bifurcation.
GST_STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu (legacy; merged into 26)",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (legacy, pre-bifurcation)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

PAN_HOLDER_TYPES = {
    "P": "Individual",
    "C": "Company",
    "H": "Hindu Undivided Family (HUF)",
    "F": "Firm / Limited Liability Partnership (LLP)",
    "A": "Association of Persons (AOP)",
    "T": "Trust",
    "B": "Body of Individuals (BOI)",
    "L": "Local Authority",
    "J": "Artificial Juridical Person",
    "G": "Government Agency",
}

# These are deliberately format-only country-routing patterns, not existence
# checks.  Each jurisdiction can have exceptional registration forms.
TAX_ID_PATTERNS = {
    "IN_GSTIN": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]{3}$",
    "GB_VAT": r"^(?:GB)?[0-9]{9}$",
    "US_EIN": r"^[0-9]{2}-?[0-9]{7}$",
    "SG_UEN": r"^(?:[0-9]{8}[A-Z]|[0-9]{9}[A-Z]|[ST][0-9]{2}[A-Z]{2}[0-9]{4}[A-Z])$",
    "AE_TRN": r"^[0-9]{15}$",
}

_GSTIN_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_TAN_RE = re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def _normalise(value: object) -> str:
    """Return an upper-case, whitespace-free identifier without repairing it."""
    return "" if value is None else str(value).strip().upper()


def gstin_check_char(first_fourteen: str) -> str:
    """Return the GSTIN mod-36 check character for exactly 14 characters.

    Factors alternate 1, 2 beginning at the left.  For each product, quotient
    and remainder after division by 36 are added to the running total.
    """
    value = _normalise(first_fourteen)
    if len(value) != 14 or any(char not in _GSTIN_CHARSET for char in value):
        raise ValueError("GSTIN checksum input must be 14 characters from 0-9A-Z")
    total = 0
    for index, char in enumerate(value):
        product = _GSTIN_CHARSET.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _GSTIN_CHARSET[(36 - (total % 36)) % 36]


def validate_gstin(gstin: str, *, regular_only: bool = False) -> bool:
    """Validate GSTIN structure and checksum, never registry existence.

    ``regular_only=True`` is appropriate for this demo's domestic regular
    taxpayer scope: it requires an embedded PAN and a ``Z`` in position 14.
    The default also permits the TAN-shaped middle section used by TDS/TCS
    registrations and does not guess special-registration entity codes.
    """
    value = _normalise(gstin)
    if len(value) != 15 or value[:2] not in GST_STATE_CODES:
        return False
    embedded_tax_id = value[2:12]
    if not (_PAN_RE.fullmatch(embedded_tax_id) or _TAN_RE.fullmatch(embedded_tax_id)):
        return False
    if value[12] not in _GSTIN_CHARSET or value[13] not in _GSTIN_CHARSET:
        return False
    if regular_only and (value[13] != "Z" or not _PAN_RE.fullmatch(embedded_tax_id)):
        return False
    return value[14] == gstin_check_char(value[:14])


def validate_pan(pan: str) -> bool:
    """Validate public PAN structure and a known fourth-character holder code.

    PAN's final character is a check character, but its calculation algorithm
    is not published by the Income Tax Department; this cannot validate it.
    """
    value = _normalise(pan)
    return bool(_PAN_RE.fullmatch(value) and value[3] in PAN_HOLDER_TYPES)


def pan_holder_type(pan: str) -> Optional[str]:
    """Return the official holder category encoded at PAN position four."""
    value = _normalise(pan)
    return PAN_HOLDER_TYPES.get(value[3]) if len(value) == 10 else None


def validate_ifsc(ifsc: str) -> bool:
    """Validate the RBI IFSC shape; it does not establish branch existence."""
    return bool(_IFSC_RE.fullmatch(_normalise(ifsc)))


def validate_tax_id(country_pattern: str, tax_id: str) -> bool:
    """Validate one of ``TAX_ID_PATTERNS`` by key (for country-routing only)."""
    pattern = TAX_ID_PATTERNS.get(country_pattern)
    if pattern is None:
        raise KeyError(f"Unknown tax-ID pattern: {country_pattern}")
    return bool(re.fullmatch(pattern, _normalise(tax_id)))


def generate_fictional_pan(
    holder_code: str = "C", *, name_initial: str = "X", sequence: int = 1
) -> str:
    """Make a clearly synthetic, *format-only* PAN with a chosen holder code.

    The last character is intentionally a placeholder: public sources describe
    it as a check character but do not publish a calculation algorithm.
    Never submit generated PANs to a government or commercial verification API.
    """
    code = _normalise(holder_code)
    initial = _normalise(name_initial)
    if code not in PAN_HOLDER_TYPES or len(initial) != 1 or not initial.isalpha():
        raise ValueError("Use a known one-letter holder code and name initial")
    if not isinstance(sequence, int) or not 1 <= sequence <= 9999:
        raise ValueError("sequence must be an integer from 1 to 9999")
    return f"ZZZ{code}{initial}{sequence:04d}X"


def generate_fictional_gstin(
    state_code: str,
    *,
    holder_code: str = "C",
    name_initial: str = "X",
    sequence: int = 1,
    entity_code: str = "1",
) -> str:
    """Make a checksum-valid GSTIN from a fictional, format-only PAN.

    This is safe for local fixtures only.  It is not a claim that the embedded
    PAN exists, and it must never be sent to a registry lookup service.
    """
    state = _normalise(state_code).zfill(2)
    entity = _normalise(entity_code)
    if state not in GST_STATE_CODES or len(entity) != 1 or entity not in _GSTIN_CHARSET:
        raise ValueError("Use a known state code and one base-36 entity character")
    first_fourteen = f"{state}{generate_fictional_pan(holder_code, name_initial=name_initial, sequence=sequence)}{entity}Z"
    return first_fourteen + gstin_check_char(first_fourteen)




# --- Helpers used by the rules (added on top of the reference module) ---

BUSINESS_TYPES = {
    "PVT_LTD": "Private Limited Company",
    "PUBLIC_LTD": "Public Limited Company",
    "LLP": "Limited Liability Partnership",
    "PARTNERSHIP": "Partnership Firm",
    "PROPRIETORSHIP": "Sole Proprietorship",
    "INSTITUTION": "Government body, university or trust",
}

# PAN 4th character expected for each business type.
EXPECTED_PAN_CODE = {
    "PVT_LTD": "C",
    "PUBLIC_LTD": "C",
    "LLP": "F",
    "PARTNERSHIP": "F",
    "PROPRIETORSHIP": "P",
    "INSTITUTION": "JGTAL",   # artificial juridical person (IITs, universities), government, trust, AOP/society, local authority
}

_GSTIN_SHAPE_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CIN_RE = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
_LLPIN_RE = re.compile(r"^[A-Z]{3}-[0-9]{4}$")
_ACCOUNT_RE = re.compile(r"^[0-9]{9,18}$")
_UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$")


def normalise_id(value: object) -> str:
    """Upper-case and drop spaces; never 'repairs' characters."""
    return _normalise(value).replace(" ", "")


def gstin_format_ok(gstin: str) -> bool:
    """R-ID-01: regular-taxpayer GSTIN shape (no checksum)."""
    return bool(_GSTIN_SHAPE_RE.fullmatch(normalise_id(gstin)))


def gstin_checksum_ok(gstin: str) -> bool:
    """R-ID-02: the 15th character matches the official mod-36 check character."""
    value = normalise_id(gstin)
    if len(value) != 15 or any(c not in _GSTIN_CHARSET for c in value):
        return False
    return value[14] == gstin_check_char(value[:14])


def gstin_embedded_pan(gstin: str) -> Optional[str]:
    """Characters 3-12 of a GSTIN: the holder's PAN."""
    value = normalise_id(gstin)
    return value[2:12] if len(value) == 15 else None


def gstin_state(gstin: str) -> tuple[Optional[str], Optional[str]]:
    """(state code, state name) from the first two digits."""
    value = normalise_id(gstin)
    code = value[:2] if len(value) >= 2 else None
    return code, GST_STATE_CODES.get(code or "")


def pan_code(pan: str) -> Optional[str]:
    value = normalise_id(pan)
    return value[3] if len(value) == 10 else None


def cin_ok(cin: str, business_type: str) -> bool:
    """R-ID-07: CIN shape, and the ownership code fits the business type."""
    value = normalise_id(cin)
    if not _CIN_RE.fullmatch(value):
        return False
    ownership = value[12:15]
    if business_type == "PVT_LTD":
        return ownership == "PTC"
    if business_type == "PUBLIC_LTD":
        return ownership == "PLC"
    return True


def llpin_ok(llpin: str) -> bool:
    return bool(_LLPIN_RE.fullmatch(normalise_id(llpin)))


def account_number_ok(account: str) -> bool:
    """R-ID-09: 9-18 digits (assumption; banks vary)."""
    return bool(_ACCOUNT_RE.fullmatch(normalise_id(account)))


def udyam_ok(udyam: str) -> bool:
    return bool(_UDYAM_RE.fullmatch(normalise_id(udyam)))


def state_code_for_name(state_name: str) -> Optional[str]:
    """Reverse lookup used to compare a declared state with a GSTIN state code."""
    target = _normalise(state_name)
    for code, name in GST_STATE_CODES.items():
        if "legacy" in name:
            continue
        if _normalise(name) == target:
            return code
    return None


def mask_account(account: str) -> str:
    value = normalise_id(account)
    return ("•" * 4 + value[-4:]) if len(value) >= 4 else value


def mask_pan(pan: str) -> str:
    value = normalise_id(pan)
    return value[:4] + "•" * 4 + value[-2:] if len(value) == 10 else value
