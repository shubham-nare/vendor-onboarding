"""Which tax ID a vendor's country uses, what it looks like, and whether the bank fits the country.

The form shows the chosen country's tax ID with a grey sample in the box and a one-line format hint, and
checks the format as the vendor types. The rules (R-ID-11, R-ID-12) repeat the same checks on the server.

These are format checks only. A well-formed VAT number or EIN can still be unregistered; confirming that
needs the country's own registry (HMRC, IRS, ACRA, FTA), which our team does when it onboards a vendor
from outside India.
"""

from __future__ import annotations

import re

from onboarding.validators import TAX_ID_PATTERNS

INDIA = "India"

# name shown in the form -> what that country's tax ID is called and looks like
COUNTRIES: dict[str, dict] = {
    INDIA: dict(code="IN", tax_label="GSTIN", example="27ABCDE1234F1Z5",
                hint="15 characters: state code, PAN, entity number, Z, check character",
                pattern=TAX_ID_PATTERNS["IN_GSTIN"]),
    "United Kingdom": dict(code="GB", tax_label="VAT registration number", example="GB123456789",
                           hint="GB followed by 9 digits", pattern=TAX_ID_PATTERNS["GB_VAT"]),
    "United States": dict(code="US", tax_label="EIN (Employer Identification Number)", example="12-3456789",
                          hint="9 digits, usually written 12-3456789", pattern=TAX_ID_PATTERNS["US_EIN"]),
    "Singapore": dict(code="SG", tax_label="UEN (Unique Entity Number)", example="201912345K",
                      hint="9 or 10 characters ending in a letter", pattern=TAX_ID_PATTERNS["SG_UEN"]),
    "United Arab Emirates": dict(code="AE", tax_label="TRN (Tax Registration Number)", example="100123456700003",
                                 hint="15 digits", pattern=TAX_ID_PATTERNS["AE_TRN"]),
}

# two-letter codes inside SWIFT/BIC codes, for saying which country a bank is really in
CODE_NAME = {c["code"]: name for name, c in COUNTRIES.items()} | {
    "DE": "Germany", "FR": "France", "NL": "the Netherlands", "CH": "Switzerland", "HK": "Hong Kong",
    "CN": "China", "JP": "Japan", "AU": "Australia", "CA": "Canada", "IE": "Ireland", "LU": "Luxembourg"}

_SWIFT = re.compile(r"^[A-Z]{4}([A-Z]{2})[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")


def is_india(country: str | None) -> bool:
    return (country or INDIA).strip().lower() in ("india", "in")


def code_for(country: str | None) -> str:
    if is_india(country):
        return "IN"
    return COUNTRIES.get((country or "").strip(), {}).get("code", "")


def normalise(value: str | None) -> str:
    return re.sub(r"\s", "", value or "").upper()


def looks_like(tax_id: str) -> list[str]:
    """Countries whose tax ID format this value fits."""
    v = normalise(tax_id)
    return [name for name, c in COUNTRIES.items() if v and re.fullmatch(c["pattern"], v)]


def tax_id_problem(country: str, tax_id: str) -> str:
    """'' if the tax ID fits the country's format, otherwise what's wrong in words a vendor understands."""
    c = COUNTRIES.get(country)
    v = normalise(tax_id)
    if not c or not v:
        return ""
    if re.fullmatch(c["pattern"], v):
        return ""
    others = [n for n in looks_like(v) if n != country]
    if others:
        return (f"{v} looks like a {COUNTRIES[others[0]]['tax_label'].split(' (')[0]} from {others[0]}, not a "
                f"{c['tax_label']}. Check the country you chose, or enter your {country} tax ID.")
    return f"A {c['tax_label']} in {country} looks like {c['example']} ({c['hint']}). You entered {v}."


def swift_problem(country: str, swift: str) -> str:
    """'' if the SWIFT/BIC code is well formed and belongs to a bank in the vendor's country."""
    v = normalise(swift)
    if not v:
        return ""
    m = _SWIFT.fullmatch(v)
    if not m:
        return f"A SWIFT/BIC code has 8 or 11 characters, like BARCGB22XXX. You entered {v}."
    want = code_for(country)
    if want and m.group(1) != want:
        where = CODE_NAME.get(m.group(1), f"country code {m.group(1)}")
        return f"SWIFT code {v} is for a bank in {where}, but you told us you're in {country}. Check the bank details or the country."
    return ""
