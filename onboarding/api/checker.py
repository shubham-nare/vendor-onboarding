"""The forensic document checker: digital signature, file facts and tampering signals, without the AI."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile

from onboarding.api.common import staff_or_401
from onboarding.pipeline import read_sessions

router = APIRouter()
FACTS = [("producer", "Producer"), ("creator", "Creator"), ("author", "Author"), ("created", "Created"), ("modified", "Modified"),
         ("saves", "Times saved"), ("pages", "Pages"), ("exif_software", "Image software"), ("exif_camera", "Camera")]


def _sigdate(v):
    return f"{v[6:8]}/{v[4:6]}/{v[:4]} {v[8:10]}:{v[10:12]}" if isinstance(v, str) and len(v) >= 12 and v[:12].isdigit() else v


def _result(r: dict) -> dict:
    from onboarding.web import LEVEL_NAMES, signal_text
    a, sig = r["auth"], r["auth"]["signature"]
    facts = a["facts"]
    verified = bool(sig.get("present") and sig.get("intact") and sig.get("valid"))
    if verified:
        stamp = "verified"
    elif sig.get("present"):
        stamp = "broken"
    elif a.get("worst") == "fraud":
        stamp = "edited"
    else:
        stamp = "unsigned_pdf" if facts.get("kind") == "pdf" else "image"
    return {
        "file": r["filename"], "mime": r["mime"], "size_kb": round(r["size"] / 1024, 1), "stamp": stamp, "kind": facts.get("kind"),
        "proof": {"level": a["level"], "name": LEVEL_NAMES.get(a["level"], "")},
        "signature": {"present": bool(sig.get("present")), "verified": verified, "intact": sig.get("intact"), "signer": sig.get("signer"),
                      "signer_org": sig.get("signer_org"), "signed_at": _sigdate(sig.get("signed_at")), "format": sig.get("sub_filter"),
                      "covers_whole_file": sig.get("covers_whole_file"), "chain": sig.get("chain") or [], "error": sig.get("error")},
        "facts": [{"label": label, "value": str(facts[k])} for k, label in FACTS if facts.get(k)]
                 + ([{"label": "Size", "value": f"{facts['width']} × {facts['height']} px"}] if facts.get("width") else []),
        "signals": [{"severity": s["severity"]} | signal_text(s) for s in a.get("signals", [])],
    }


@router.get("/check/sample")
async def sample(request: Request):
    """The genuine, GSTN-signed public sample certificate, checked."""
    from onboarding.web import PUBLIC_SAMPLE, _check_one, access, _actor
    async with read_sessions()() as s:
        await staff_or_401(request, s)
        access.require_full(await _actor(request, s), "The document check")
    return {"results": [_result(_check_one(PUBLIC_SAMPLE.name, PUBLIC_SAMPLE.read_bytes()))] if PUBLIC_SAMPLE.exists() else []}


@router.post("/check")
async def check(request: Request, file_a: UploadFile = File(None), file_b: UploadFile = File(None), with_sample: str = Form("")):
    """Up to two PDFs, JPGs or PNGs (10 MB each), optionally next to the genuine sample."""
    from onboarding.web import check_files
    async with read_sessions()() as s:
        await staff_or_401(request, s)
    return {"results": [_result(r) for r in await check_files(request, [file_a, file_b], bool(with_sample))]}
