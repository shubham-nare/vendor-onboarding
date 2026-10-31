"""Compare what the vendor typed with what a document shows, tolerating misreads only where
that's provably safe (docs/PRODUCT.md §6.4).

Rule: "couldn't read clearly" is never treated as "read and different".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from onboarding import names
from onboarding.validators import gstin_checksum_ok, normalise_id

MATCH = "MATCH"                      # identical
MATCH_CORRECTED = "MATCH_CORRECTED"  # identical after a provable misread correction
MISMATCH = "MISMATCH"                # clearly read, and different
UNREADABLE = "UNREADABLE"            # couldn't read reliably -> ask for a clearer copy
MISSING = "MISSING"                  # the document doesn't show it
PARTIAL = "PARTIAL"                  # names only: close but not close enough

# Common OCR confusions, by the character class a position requires.
TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G", "4": "A", "7": "T"}
TO_DIGIT = {v: k for k, v in TO_LETTER.items()} | {"D": "0", "Q": "0", "L": "1", "|": "1"}

PAN_CLASSES = "LLLLLDDDDL"                     # L = letter, D = digit
GSTIN_CLASSES = "DDLLLLLDDDDLAAA"              # A = any
IFSC_CLASSES = "LLLL0AAAAAA"                   # 5th character is always zero


@dataclass(frozen=True)
class IdMatch:
    status: str
    form_value: str
    doc_value: str
    detail: str = ""


def correct(value: str, classes: str) -> tuple[str, list[str]]:
    """Fix confusable characters where the position's class is fixed. Returns (value, changes)."""
    v = normalise_id(value)
    if len(v) != len(classes):
        return v, []
    out, changes = [], []
    for i, (ch, cls) in enumerate(zip(v, classes)):
        new = ch
        if cls == "L" and not ch.isalpha():
            new = TO_LETTER.get(ch, ch)
        elif cls in ("D", "0") and not ch.isdigit():
            new = TO_DIGIT.get(ch, ch)
        if new != ch:
            changes.append(f"position {i + 1}: read '{ch}', must be a {'letter' if cls == 'L' else 'digit'} -> '{new}'")
        out.append(new)
    return "".join(out), changes


def _unclear(legibility: str) -> bool:
    return legibility in ("partial", "unreadable")


def compare_id(kind: str, form_value: str, doc_value: str | None, legibility: str = "clear") -> IdMatch:
    """kind: pan | gstin | ifsc. Structure-aware; for GSTIN the check digit arbitrates."""
    f = normalise_id(form_value)
    if not doc_value or legibility in ("not_present",):
        return IdMatch(MISSING if legibility == "not_present" else UNREADABLE, f, "", "not shown on the document")
    if legibility == "unreadable":
        return IdMatch(UNREADABLE, f, doc_value, "the document couldn't be read clearly")
    d = normalise_id(doc_value)
    if d == f:
        return IdMatch(MATCH, f, d)
    classes = {"pan": PAN_CLASSES, "gstin": GSTIN_CLASSES, "ifsc": IFSC_CLASSES}[kind]
    fixed, changes = correct(d, classes)
    if fixed == f and changes:
        if kind == "gstin" and not gstin_checksum_ok(f):
            return IdMatch(UNREADABLE, f, d, "correction possible but the check digit doesn't confirm it")
        proof = "; the GSTIN check digit confirms the corrected value" if kind == "gstin" else ""
        return IdMatch(MATCH_CORRECTED, f, d, "; ".join(changes) + proof)
    if _unclear(legibility):
        return IdMatch(UNREADABLE, f, d, "partly readable and different; a clearer copy is needed")
    return IdMatch(MISMATCH, f, d, "clearly read and different")


def compare_account(form_value: str, doc_value: str | None, legibility: str = "clear") -> IdMatch:
    """Strict: a one-digit difference is a different account. No correction, ever."""
    f = re.sub(r"[\s-]", "", form_value or "")
    if not doc_value or legibility == "not_present":
        return IdMatch(MISSING if legibility == "not_present" else UNREADABLE, f, "", "account number not shown")
    d = re.sub(r"[\s-]", "", doc_value)
    if legibility == "unreadable" or not d.isdigit():
        return IdMatch(UNREADABLE, f, d, "account number covered or unreadable (e.g. masked with X)")
    if d == f:
        return IdMatch(MATCH, f, d)
    if _unclear(legibility):
        return IdMatch(UNREADABLE, f, d, "partly readable and different; a clearer copy is needed")
    return IdMatch(MISMATCH, f, d, "clearly read and different: this would be a different account")


@dataclass(frozen=True)
class NameResult:
    status: str        # MATCH | PARTIAL | MISMATCH | UNREADABLE | MISSING
    score: int
    note: str
    form_value: str
    doc_value: str


def compare_name(form_value: str, doc_value: str | None, *, individual: bool = False, legibility: str = "clear") -> NameResult:
    if not doc_value or legibility == "not_present":
        return NameResult(MISSING if legibility == "not_present" else UNREADABLE, 0, "name not shown", form_value, "")
    if legibility == "unreadable":
        return NameResult(UNREADABLE, 0, "name couldn't be read", form_value, doc_value)
    m = names.compare(form_value, doc_value, individual=individual)
    if m.band == names.PARTIAL and _unclear(legibility):
        return NameResult(UNREADABLE, m.score, "partial match on an unclear reading; a clearer copy is needed", form_value, doc_value)
    if m.band == names.MISMATCH and _unclear(legibility):
        return NameResult(UNREADABLE, m.score, "unclear reading", form_value, doc_value)
    return NameResult(m.band, m.score, m.note, form_value, doc_value)
