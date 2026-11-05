"""Fill the registration form from the vendor's own documents (upload first, then confirm), as Stripe does.

The vendor uploads a document; we read it (the same reader the checks use) and suggest values for the form.
The vendor checks them and submits. Guard rails:
- Only clear or partly legible values are suggested; partly legible ones are marked "check this".
- Nothing here decides anything. After submission the pipeline reads every document again on its own and the
  usual checks compare the form with the documents, the registries and the bank.
- What we suggested is sent back with the form (`prefill`), so a value the vendor changed after we read it is
  visible to the reviewer (rule R-PF-01). The record is only a signal: the independent checks don't trust it.
"""

from __future__ import annotations

import json
import re

from onboarding import validators as V
from onboarding.ai.read import DocRead
from onboarding.rules import SLOT_TYPES, constitution_type

# form fields a document can fill, and the ones that matter most if the vendor changes them
FILLABLE = ("business_type", "legal_name", "proprietor_name", "gstin", "pan", "address", "city", "state", "pin",
            "bank_holder", "bank_account", "ifsc", "udyam_no", "msme")
KEY_FIELDS = ("legal_name", "gstin", "pan", "bank_account", "ifsc", "bank_holder")
SOURCE_LABEL = {"gst_certificate": "GST certificate", "pan_card": "PAN card", "bank_proof": "cheque", "udyam_certificate": "Udyam certificate"}
DOC_LABEL = {"GST_CERTIFICATE": "a GST certificate", "PAN_CARD": "a PAN card", "CANCELLED_CHEQUE": "a cheque", "BANK_LETTER": "a bank letter",
             "UDYAM_CERTIFICATE": "a Udyam certificate", "TAX_INVOICE": "an invoice", "AADHAAR": "an Aadhaar card", "OTHER": "another kind of document"}
_STATES = sorted({v for k, v in V.GST_STATE_CODES.items() if "legacy" not in v and k not in ("97", "99")})
_LABELS = ("Building No./Flat No.", "Name Of Premises/Building", "Road/Street", "Locality/Sub Locality", "City/Town/Village",
           "District", "State", "PIN Code")


def _get(read: DocRead, name: str) -> tuple[str, str]:
    f = next((x for x in read.fields if x.name == name and x.value and x.legibility in ("clear", "partial")), None)
    return ((f.value or "").strip(), f.legibility) if f else ("", "")


def split_address(text: str, state_hint: str = "") -> dict:
    """A GST certificate address -> street address, city, state and PIN. Handles the labelled REG-06 layout
    ("City/Town/Village: X District: Y State: Z PIN Code: N") and the plain comma-separated one."""
    t = " ".join((text or "").split())
    out = {"address": "", "city": "", "state": "", "pin": ""}
    if "City/Town/Village:" in t or "PIN Code:" in t:
        pat = "(" + "|".join(re.escape(x) for x in _LABELS) + "):"
        bits = re.split(pat, t)
        parts = {bits[i]: bits[i + 1].strip(" ,") for i in range(1, len(bits) - 1, 2)}
        out["address"] = ", ".join(v for k in _LABELS[:4] if (v := parts.get(k)))
        out["city"] = parts.get("City/Town/Village") or parts.get("District", "")
        out["state"] = parts.get("State", "")
        out["pin"] = re.sub(r"\D", "", parts.get("PIN Code", ""))[:6]
    else:
        parts = [p.strip() for p in t.split(",") if p.strip()]
        if parts and re.fullmatch(r"[1-8]\d{5}", parts[-1].replace(" ", "")):
            out["pin"] = parts.pop().replace(" ", "")
        if parts and parts[-1].lower() in {s.lower() for s in _STATES}:
            out["state"] = parts.pop()
        if parts:
            out["city"] = parts.pop()
            while parts and parts[-1].lower() == out["city"].lower():   # "PUNE, Pune": the same place twice
                parts.pop()
        out["address"] = ", ".join(parts)
    st = out["state"] or state_hint
    out["state"] = next((s for s in _STATES if s.lower() == st.lower()), "")
    return out


def suggestions(slot: str, read: DocRead) -> dict:
    """What this document suggests for the form: {field: {"value", "check"}} plus whether it's in the right slot."""
    right = read.doc_type in SLOT_TYPES.get(slot, set())
    source = "bank letter" if read.doc_type == "BANK_LETTER" else SOURCE_LABEL.get(slot, "document")
    res = {"slot": slot, "doc_type": read.doc_type, "right_slot": right, "fields": {}, "source": source}
    if not right:
        res["message"] = f"This looks like {DOC_LABEL.get(read.doc_type, 'a different document')}, not your {SOURCE_LABEL.get(slot, 'document')}. Please check the file."
        return res
    fields = res["fields"]

    def put(name: str, value: str, leg: str = "clear") -> None:
        if value:
            fields[name] = {"value": value, "check": leg == "partial"}

    if slot == "gst_certificate":
        g, gl = _get(read, "gstin")
        g = V.normalise_id(g)
        put("gstin", g, gl)
        if len(g) == 15:
            put("pan", g[2:12], gl)                                  # the PAN is characters 3 to 12 of the GSTIN
        put("legal_name", *_get(read, "legal_name"))
        bt = constitution_type(_get(read, "constitution")[0])
        if bt:
            put("business_type", bt)
        addr, al = _get(read, "principal_address")
        for k, v in split_address(addr, _get(read, "state")[0]).items():
            put(k, v, al)
    elif slot == "pan_card":
        p, pl = _get(read, "pan")
        put("pan", V.normalise_id(p), pl)
        n, nl = _get(read, "name_on_card")
        if n and V.pan_code(V.normalise_id(p)) == "P":                 # a person's PAN: the proprietor
            put("proprietor_name", n, nl)
    elif slot == "bank_proof":
        a, al = _get(read, "account_number")
        put("bank_account", re.sub(r"[\s-]", "", a), al)
        i, il = _get(read, "ifsc")
        put("ifsc", V.normalise_id(i), il)
        put("bank_holder", *_get(read, "account_holder_name"))
    elif slot == "udyam_certificate":
        u, ul = _get(read, "udyam_number")
        put("udyam_no", V.normalise_id(u), ul)
        if u:
            put("msme", "on")
    if not fields:
        res["message"] = f"We couldn't read the details on your {SOURCE_LABEL.get(slot, 'document')}. Please type them below."
    return res


def _norm(field: str, v) -> str:
    s = str(v or "").strip()
    if field in ("gstin", "pan", "ifsc", "udyam_no"):
        return V.normalise_id(s)
    if field == "bank_account":
        return re.sub(r"[\s-]", "", s)
    return " ".join(s.lower().split())


def parse_record(raw: str) -> dict:
    """The record the browser sends back: {field: {"value", "from"}}. Anything malformed is dropped."""
    try:
        d = json.loads(raw or "{}")
    except ValueError:
        return {}
    if not isinstance(d, dict):
        return {}
    return {k: {"value": str(v.get("value", ""))[:300], "from": str(v.get("from", ""))[:40]}
            for k, v in d.items() if k in FILLABLE and isinstance(v, dict)}


def changes(form: dict) -> tuple[list[str], list[str]]:
    """(fields filled from documents, fields the vendor then changed)."""
    rec = form.get("prefill") or {}
    filled = [k for k in rec if k != "msme"]
    changed = [k for k in filled if _norm(k, form.get(k)) != _norm(k, rec[k]["value"])]
    return filled, changed


def _words(s) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split())


def completed(field: str, form: dict) -> bool:
    """A name the reader cut short (a line that wraps on the certificate) that the vendor finished: the read text
    is still all there, at the start. That's a completion, not a change. Identifiers never get this allowance."""
    if field not in ("legal_name", "bank_holder", "proprietor_name", "address"):
        return False
    read, sent = _words((form.get("prefill") or {}).get(field, {}).get("value")), _words(form.get(field))
    return bool(read) and len(read) >= 8 and sent.startswith(read)
