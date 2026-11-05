"""Is the address the vendor typed their real business address?

1. compare(): the typed address against the principal place of business printed on their GST certificate
   (a government document we already read). PIN code and state must agree; the street is compared word by word.
2. validate(): Google's Address Validation API (India is in preview there) says whether the address exists,
   how precisely it could place it, and which PIN code it belongs to. Off until GOOGLE_MAPS_API_KEY is set.
"""

import re
from dataclasses import dataclass, field

import httpx


from onboarding.config import get_settings

MATCH, PARTIAL, MISMATCH, UNREADABLE = "match", "partial", "mismatch", "unreadable"

ABBR = {"rd": "road", "st": "street", "mg": "mahatma gandhi", "opp": "opposite", "nr": "near", "bldg": "building", "blvd": "boulevard",
        "ave": "avenue", "apt": "apartment", "apts": "apartments", "ind": "industrial", "indl": "industrial", "estt": "estate", "est": "estate",
        "sec": "sector", "ph": "phase", "flr": "floor", "fl": "floor", "mkt": "market", "nagr": "nagar", "clny": "colony", "dist": "district",
        "tal": "taluka", "tq": "taluka", "vill": "village", "po": "post", "ps": "police", "hsg": "housing", "soc": "society", "co": "",
        "plot": "plot", "no": "", "num": "", "near": "near"}
# words that say little about where a place is
STOP = {"", "the", "of", "and", "near", "opposite", "behind", "beside", "post", "office", "district", "taluka", "village", "india", "floor",
        "ground", "first", "second", "third", "building", "road", "street", "lane", "area", "city", "town", "pin", "code", "state", "nagar"}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    out = []
    for w in words:
        w = ABBR.get(w, w)
        out.extend(w.split())
    return out


def _distinct(text: str) -> set[str]:
    return {w for w in _tokens(text) if w not in STOP and (len(w) > 1 or w.isdigit())}


def _same_place(a: str, b: str) -> bool:
    ta, tb = _distinct(a), _distinct(b)
    return bool(ta and tb and (ta <= tb or tb <= ta or len(ta & tb) / min(len(ta), len(tb)) >= .5))


@dataclass
class AddressMatch:
    status: str                       # match | partial | mismatch | unreadable
    reasons: list[str] = field(default_factory=list)
    certificate: dict = field(default_factory=dict)   # the certificate address split into address/city/state/pin
    score: float = 0.0                # share of the shorter street's distinctive words found in the other


def compare(form: dict, certificate_address: str) -> AddressMatch:
    """The vendor's address (form: address, city, state, pin) against the GST certificate's principal place of business."""
    from onboarding import prefill   # here, not at the top: prefill imports the rules, which import this module
    cert = prefill.split_address(certificate_address or "", form.get("state", ""))
    if not (certificate_address or "").strip() or not (cert.get("pin") or cert.get("address")):
        return AddressMatch(UNREADABLE, ["The address on the GST certificate couldn't be read."], cert)
    reasons, hard = [], False
    pin, cpin = (form.get("pin") or "").strip(), (cert.get("pin") or "").strip()
    if pin and cpin and pin != cpin:
        reasons.append(f"PIN code {pin} differs from the certificate's {cpin}")
        hard = True
    st, cst = (form.get("state") or "").strip().lower(), (cert.get("state") or "").strip().lower()
    if st and cst and st != cst and not (st in cst or cst in st):
        reasons.append(f"state {form.get('state')} differs from the certificate's {cert.get('state')}")
        hard = True
    if form.get("city") and cert.get("city") and not _same_place(form["city"], cert["city"]) \
            and not _same_place(form["city"], certificate_address):
        reasons.append(f"city {form.get('city')} differs from the certificate's {cert.get('city')}")
    mine = _distinct(f"{form.get('address', '')} {form.get('city', '')}")
    theirs = _distinct(f"{cert.get('address', '')} {cert.get('city', '')}") or _distinct(certificate_address)
    score = len(mine & theirs) / min(len(mine), len(theirs)) if mine and theirs else 0.0
    nums_theirs = {w for w in theirs if any(ch.isdigit() for ch in w)} - {cpin}
    nums_mine = {w for w in mine if any(ch.isdigit() for ch in w)} - {pin}
    if nums_theirs and nums_mine and not nums_theirs & nums_mine:
        reasons.append(f"building or plot number differs ({', '.join(sorted(nums_mine))} vs {', '.join(sorted(nums_theirs))})")
    if score < .5:
        reasons.append("the street address has little in common with the certificate's")
    if hard or score < .3:
        status = MISMATCH
    elif reasons:
        status = PARTIAL
    else:
        status = MATCH
    return AddressMatch(status, reasons, cert, round(score, 2))


# --- Google Address Validation -------------------------------------------------------------------------------
URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
LEVELS = {"SUB_PREMISE": "the exact unit", "PREMISE": "the building", "PREMISE_PROXIMITY": "near the building", "BLOCK": "the block",
          "ROUTE": "the street", "LOCALITY": "the area only", "OTHER": "nowhere precise"}


def configured() -> bool:
    return bool(get_settings().google_maps_api_key)


async def validate(form: dict, *, timeout: float = 6.0):
    """Google's verdict on the typed address, as a SourceResult (FOUND with the verdict, or ERROR). None when not configured."""
    from onboarding.sources import SourceResult
    if not configured() or not (form.get("address") or form.get("pin")):
        return None
    body = {"address": {"regionCode": "IN", "addressLines": [form.get("address", "")], "locality": form.get("city", ""),
                        "administrativeArea": form.get("state", ""), "postalCode": form.get("pin", "")}}
    label = "Google Address Validation (live)"
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(URL, params={"key": get_settings().google_maps_api_key}, json=body)
        r.raise_for_status()
        return SourceResult(label, "FOUND", True, summarize(r.json()))
    except Exception as e:
        return SourceResult(label, "ERROR", False, note=f"{type(e).__name__}"[:80])


def summarize(resp: dict) -> dict:
    """The parts of Google's answer the rule uses."""
    res = resp.get("result") or {}
    v, addr, geo = res.get("verdict") or {}, res.get("address") or {}, res.get("geocode") or {}
    comps = addr.get("addressComponents") or []
    postal = next((c for c in comps if c.get("componentType") == "postal_code"), {})
    loc = geo.get("location") or {}
    return {
        "granularity": v.get("validationGranularity", "OTHER"),
        "complete": bool(v.get("addressComplete")),
        "formatted": addr.get("formattedAddress", ""),
        "postal_code": (postal.get("componentName") or {}).get("text", ""),
        "postal_status": postal.get("confirmationLevel", ""),
        "postal_replaced": bool(postal.get("replaced")),
        "unconfirmed": [c.get("componentType") for c in comps if c.get("confirmationLevel") == "UNCONFIRMED_AND_SUSPICIOUS"],
        "lat": loc.get("latitude"), "lng": loc.get("longitude"),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={loc.get('latitude')},{loc.get('longitude')}" if loc else "",
    }


def judge(form: dict, data: dict) -> tuple[str, str]:
    """('PASS' | 'WARN', title) for Google's verdict."""
    level = data.get("granularity", "OTHER")
    pin = (form.get("pin") or "").strip()
    gpin = (data.get("postal_code") or "").strip()
    if level == "OTHER":
        return "WARN", "Google couldn't place this address"
    if pin and gpin and gpin != pin:
        return "WARN", f"Google places this address in PIN code {gpin}, not {pin}"
    if "UNCONFIRMED_AND_SUSPICIOUS" in (data.get("postal_status") or "") or data.get("unconfirmed"):
        return "WARN", "Google found the area but doubts part of the address: " + ", ".join(x.replace("_", " ") for x in data.get("unconfirmed") or ["postal code"])
    return "PASS", f"Google found this address (to {LEVELS.get(level, level.lower())})"
