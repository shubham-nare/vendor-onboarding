"""Business and person name matching (method: docs/agents/01-business-process.md §4.2).

Score bands: >= 90 MATCH, 75-89 PARTIAL, < 75 MISMATCH.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

MATCH = "MATCH"
PARTIAL = "PARTIAL"
MISMATCH = "MISMATCH"

MATCH_AT = 90
PARTIAL_AT = 75

_HONORIFICS = {"M/S", "MS", "M/S.", "MESSRS", "SHRI", "SMT", "MR", "MRS", "DR"}
# Every spelling of a common business word maps to one canonical (short) form, so
# "Private Limited", "Pvt. Ltd." and a cheque's truncated "PVT LT" line up.
_CANON = {
    "PRIVATE": "PVT", "PVT": "PVT", "LIMITED": "LTD", "LTD": "LTD", "COMPANY": "CO", "CO": "CO",
    "CORPORATION": "CORPN", "CORPN": "CORPN", "CORP": "CORPN", "ENTERPRISES": "ENT", "ENTERPRISE": "ENT",
    "ENTS": "ENT", "ENT": "ENT", "INDUSTRIES": "INDS", "INDS": "INDS", "MANUFACTURING": "MFG", "MFG": "MFG",
    "INTERNATIONAL": "INTL", "INTL": "INTL", "BROTHERS": "BROS", "BROS": "BROS", "SERVICES": "SVCS",
    "SVCS": "SVCS", "TRADING": "TRDG", "TRDG": "TRDG", "AND": "AND",
    "SHREE": "SRI", "SRI": "SRI", "SREE": "SRI",  # common transliteration variants in business names
}
# Checked longest first (after canonicalisation).
_SUFFIXES = [
    ("PVT LTD", "PVT"),
    ("LTD", "LTD"),
    ("LLP", "LLP"),
]
TRUNCATION_MIN = 20  # characters of agreement needed before a truncated name counts


@dataclass(frozen=True)
class NameMatch:
    score: int
    band: str
    a_stem: str
    b_stem: str
    note: str = ""


def normalise(name: str) -> tuple[str, str | None]:
    """Return (stem, suffix class) for a name."""
    text = (name or "").upper().replace("&", " AND ")
    tokens = [t for t in re.split(r"\s+", text) if t]
    tokens = [t for t in tokens if t not in _HONORIFICS]
    text = " ".join(tokens)
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = " ".join(_CANON.get(t, t) for t in text.split())
    suffix = None
    for phrase, cls in _SUFFIXES:
        if text == phrase or text.endswith(" " + phrase):
            suffix = cls
            text = text[: -len(phrase)].strip()
            break
    return text, suffix


def band_for(score: int) -> str:
    if score >= MATCH_AT:
        return MATCH
    if score >= PARTIAL_AT:
        return PARTIAL
    return MISMATCH


def compare(a: str, b: str, *, individual: bool = False) -> NameMatch:
    """Compare two names.

    individual=True enables the middle-name tolerance, used only when the PAN
    holder type is P (a person).
    """
    a_stem, a_suf = normalise(a)
    b_stem, b_suf = normalise(b)
    score = int(round(fuzz.token_sort_ratio(a_stem, b_stem)))
    note = ""

    # Truncation: printers cut long names (e.g. "NILGIRI PACKAGING SOLUTIONS PV").
    a_full, b_full = full_form(a), full_form(b)
    short_f, long_f = sorted([a_full, b_full], key=len)
    if score < 100 and len(short_f) >= TRUNCATION_MIN and long_f.startswith(short_f) and short_f != long_f:
        score, note = max(score, 95), "name truncated on the document"

    # Initials for people: "R V SHINDE" vs "RAMESH VITTHAL SHINDE".
    if individual and score < MATCH_AT and initials_match(a_stem.split(), b_stem.split()):
        score, note = 92, "initials match the full name"

    if individual and score < MATCH_AT:
        short, long_ = sorted([a_stem.split(), b_stem.split()], key=len)
        if len(short) >= 2 and all(t in long_ for t in short) and len(long_) - len(short) <= 1:
            score = 95
            note = "middle name omitted"

    # Institutions write themselves in initials and bank in a designated account:
    # "IIT (BHU) RESEARCH & DEVELOPMENT ACCOUNT" is "Indian Institute of Technology (Banaras Hindu University)".
    # Never a full match: a person confirms the designated account belongs to the institution.
    if not individual and score < PARTIAL_AT:
        hit = designated_account(a_stem, b_stem)
        if hit:
            score, note = 85, hit

    if a_suf and b_suf and a_suf != b_suf and score > 89:
        score = 89
        note = f"legal form differs ({a_suf} vs {b_suf})"

    return NameMatch(score=score, band=band_for(score), a_stem=a_stem, b_stem=b_stem, note=note)


_STOP = {"OF", "AND", "THE", "FOR"}
# words a bank adds after the holder's name for a designated account ("... RESEARCH & DEVELOPMENT ACCOUNT")
_DESIGNATION = {"ACCOUNT", "AC", "A", "C", "CURRENT", "SAVINGS", "FUND", "FUNDS", "PROJECT", "PROJECTS", "RESEARCH", "AND",
                "DEVELOPMENT", "R", "D", "RND", "CONSULTANCY", "SPONSORED", "CORPUS", "GRANT", "GRANTS", "REVENUE", "COLLECTION",
                "MAIN", "GENERAL", "RECEIPT", "RECEIPTS"}


def _expand(short: list[str], long_: list[str]) -> tuple[list[str], int]:
    """Replace initials in `short` ("IIT", "BHU") with the words they stand for in `long_`."""
    out, hits = [], 0
    for t in short:
        found = None
        if 2 <= len(t) <= 6 and t.isalpha() and t not in long_:
            for i in range(len(long_)):
                run, ini = [], ""
                for w in long_[i:]:
                    run.append(w)
                    if w not in _STOP:
                        ini += w[0]
                    if len(ini) >= len(t):
                        break
                if ini == t and run[-1] not in _STOP:
                    found = run
                    break
        if found:
            out += found
            hits += 1
        else:
            out.append(t)
    return out, hits


def designated_account(a_stem: str, b_stem: str) -> str:
    """'' unless one name is the other written in initials, optionally followed by an account designation.
    Returns a note for the reviewer when it is."""
    a, b = a_stem.split(), b_stem.split()
    for short, long_ in ((a, b), (b, a)):
        core = list(short)
        tail = []
        while core and core[-1] in _DESIGNATION:
            tail.insert(0, core.pop())
        exp, hits = _expand(core, long_)
        if hits and exp and fuzz.token_sort_ratio(" ".join(exp), " ".join(long_)) >= MATCH_AT:
            what = " ".join(short[:len(core)])
            return (f"'{what}' is the initials of the same name" + (f"; the account is designated '{' '.join(tail)}'" if tail else "")
                    + ": confirm the account belongs to this vendor")
    return ""


def full_form(name: str) -> str:
    """Canonical text including the legal suffix, used for truncation checks."""
    stem, suffix = normalise(name)
    tail = {"PVT": "PVT LTD", "LTD": "LTD", "LLP": "LLP"}.get(suffix or "", "")
    return f"{stem} {tail}".strip()


def initials_match(a: list[str], b: list[str]) -> bool:
    """True if one name is the other with some tokens reduced to initials (same order,
    at most one middle token omitted). At least one full token must agree."""
    # "short" = the side written with initials
    short, long_ = sorted([a, b], key=lambda toks: (-sum(len(t) == 1 for t in toks), len(toks)))
    if not short or len(long_) < len(short) or len(long_) - len(short) > 1 or not any(len(t) == 1 for t in short):
        return False
    i, full_hits = 0, 0
    for t in short:
        while i < len(long_):
            lt = long_[i]
            i += 1
            if t == lt:
                full_hits += 1
                break
            if len(t) == 1 and lt.startswith(t):
                break
        else:
            return False
    return full_hits >= 1
