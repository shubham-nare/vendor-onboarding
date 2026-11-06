"""Layer 3: is this document genuine? Combines Gemini's visual judgement, file facts and the
signature check into plain-English signals (AU-1..AU-14, see docs/PRODUCT.md §6.2).

Severity, lowest to highest:
  info   - shown to the reviewer, no effect
  warn   - shown to the reviewer, caps the document at A1 ("evidenced, not shown genuine")
  vendor - the vendor must upload a better document (handwritten, screen photo, screenshot)
  review - a person must look before anything proceeds
  fraud  - review, fraud class: neutral vendor message, specifics stay internal
Never "reject": authenticity signals route; they never decide alone (principle 3).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from onboarding.ai.read import DocRead
from onboarding.authenticity.metadata import FileFacts, inspect_file
from onboarding.authenticity.signature import SignatureCheck, check_pdf_signature

SEVERITY = ["info", "warn", "vendor", "review", "fraud"]
# Our own fictional fixtures carry this banner ("SPECIMEN · FICTIONAL TEST DATA · NOT A REAL DOCUMENT"); so does any
# sample/specimen someone downloads and uploads. Either way it is not the vendor's real document.
SPECIMEN_MARK = re.compile(r"SPECIMEN|FICTIONAL TEST DATA|NOT A REAL DOCUMENT|SAMPLE (?:DOCUMENT|CERTIFICATE|ONLY)", re.I)
CERTIFICATES = {"GST_CERTIFICATE", "UDYAM_CERTIFICATE"}
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Signal:
    code: str
    severity: str
    title: str          # plain English, shown to the reviewer
    detail: str = ""
    vendor_text: str = ""   # what to tell the vendor (only for severity == "vendor")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Authenticity:
    level: str                      # A1 evidenced | A2 genuine | A3 cryptographically proven
    worst: str                      # highest severity among signals ("" if none)
    specimen: bool = False          # one of our own fictional test fixtures
    signals: list[Signal] = field(default_factory=list)
    signature: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["signals"] = [s.as_dict() for s in self.signals]
        return d


@lru_cache
def specimen_hashes() -> frozenset[str]:
    """SHA-256 of our generated fictional documents (they carry a SPECIMEN banner)."""
    manifest = ROOT / "fixtures" / "documents" / "manifest.json"
    if not manifest.exists():
        return frozenset()
    hashes = set()
    for m in json.loads(manifest.read_text(encoding="utf-8")).values():
        for info in m["files"].values():
            p = ROOT / "fixtures" / "documents" / info["file"]
            if p.exists():
                hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
    return frozenset(hashes)


def _field(read: DocRead | None, name: str) -> str:
    if not read:
        return ""
    for f in read.fields:
        if f.name == name and f.value:
            return f.value
    return ""


def _parse_date(s: str) -> datetime | None:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


async def assess_async(raw: bytes, mime: str, read: DocRead | None) -> Authenticity:
    """assess() on a worker thread: PIL, pypdf and the signature check are CPU-bound and would stall every other
    request (and the live run view) while they work."""
    return await asyncio.to_thread(assess, raw, mime, read)


def assess(raw: bytes, mime: str, read: DocRead | None) -> Authenticity:
    facts: FileFacts = inspect_file(raw, mime)
    sig: SignatureCheck = check_pdf_signature(raw) if facts.kind == "pdf" else SignatureCheck(present=False)
    from onboarding.config import get_settings
    specimen = hashlib.sha256(raw).hexdigest() in specimen_hashes()
    marked = specimen or bool(SPECIMEN_MARK.search(facts.text or "")) or bool(
        read and any(SPECIMEN_MARK.search(w or "") for w in [*read.visible_watermarks_or_logos, *read.integrity_notes]))
    accept_specimens = get_settings().accept_specimen_documents   # tests only; never on the live site
    out: list[Signal] = []
    add = lambda *a, **k: out.append(Signal(*a, **k))  # noqa: E731

    doc_type = read.doc_type if read else ""
    form = read.document_form if read else "UNSURE"

    # --- AU-1: not an original (Gemini's visual judgement) -----------------------------
    if form == "HANDWRITTEN_OR_PLAIN_PAPER":
        add("AU-1", "vendor", "Details are hand-written or typed on plain paper, not an official document",
            read.document_form_evidence,
            "The file you uploaded shows the details written on plain paper. Please upload the original document (a photo or scan of the actual card or certificate).")
    elif form == "PHOTO_OF_SCREEN":
        add("AU-1", "vendor", "Photo of a document shown on a screen", read.document_form_evidence,
            "The file you uploaded is a photo of a screen. Please upload the original file, or a direct photo or scan of the physical document.")
    # Certificates are issued as PDFs: an image of one is a copy, whatever it looks like.
    if doc_type in CERTIFICATES and facts.kind == "image":
        if form in ("SCREENSHOT", "ORIGINAL_DIGITAL", "DIGITALLY_COMPOSED", "UNSURE"):
            add("AU-1", "vendor", "Certificate uploaded as a screenshot or image, not the original PDF",
                f"{facts.width}x{facts.height} image; the portal issues this certificate as a PDF",
                "Please upload the original PDF downloaded from the government portal (for GST: Services > User Services > View/Download Certificates), without printing or re-saving it.")
        elif form != "PHOTO_OF_SCREEN":
            add("AU-1", "warn", "Certificate provided as a photo of a printout", "The government's digital signature can only be checked on the original PDF")

    # --- AU-2: fabricated or AI-generated (Gemini) -------------------------------------
    if form in ("DIGITALLY_COMPOSED", "AI_GENERATED") and not (doc_type in CERTIFICATES and facts.kind == "image" and form == "DIGITALLY_COMPOSED"):
        what = "AI-generated" if form == "AI_GENERATED" else "assembled or edited in software"
        # The AI's visual verdict alone varies between runs (robustness harness), so on its own it
        # only asks for a human look. Corroborating signals below raise it to the fraud class.
        add("AU-2", "review", f"Document appears {what} (AI visual judgement, needs a human look)", read.document_form_evidence)
    if read and read.garbled_or_misspelled_text and form != "HANDWRITTEN_OR_PLAIN_PAPER":
        if doc_type == "BANK_LETTER" and form != "AI_GENERATED":
            # a mandate or letter is typed by the vendor's own office and stamped by the bank: typos happen
            add("AU-2", "warn", "Typing errors in the letter", ", ".join(read.garbled_or_misspelled_text[:5]))
        else:
            add("AU-2", "fraud", "Printed text is garbled or misspelled (genuine bank/government printing never is)",
                ", ".join(read.garbled_or_misspelled_text[:5]))
    if read and any(re.search(r"sparkle|gemini|dall-?e|midjourney|stable diffusion|\bai[- ](?:generated|generator|watermark|logo|icon)|made with ai", w, re.I) for w in read.visible_watermarks_or_logos):
        add("AU-2", "fraud", "An AI generator's watermark is visible", ", ".join(read.visible_watermarks_or_logos[:3]))
    if read and read.obscured_regions:
        add("AU-2", "warn", "Parts of the document are covered or redacted", "; ".join(read.obscured_regions[:3]))

    # --- AU-3 / AU-4: digital signature --------------------------------------------------
    if sig.present:
        if sig.intact and sig.valid:
            add("AU-4", "info", f"Digital signature verified: signed by {sig.signer}, content unchanged since signing",
                f"chain: {' > '.join(sig.chain)}; signed {sig.signed_at}")
        else:
            add("AU-3", "fraud", "Digital signature is BROKEN: the document was changed after it was signed",
                f"signer: {sig.signer or 'unknown'}; content intact: {sig.intact}; signature maths valid: {sig.valid}. {sig.error}")

    # --- AU-5 / AU-12 / AU-13 / AU-14: file history -------------------------------------
    editor = facts.editor
    claims = facts.signature_claimed_in_text and not sig.present
    issue = _parse_date(_field(read, "issue_date"))
    late = bool(facts.created and issue and (facts.created - issue).days > 365)
    if editor:
        add("AU-5", "warn", f"File was created or saved with {editor}",
            f"producer: {facts.producer or '-'}; creator: {facts.creator or '-'}; software: {facts.exif_software or '-'}")
    if claims:
        how = f"re-saved by {facts.resaver}" if facts.resaver else "signature removed"
        add("AU-12", "warn", "Page says 'Digitally signed', but the file contains no signature",
            f"{how}. Honest browser re-saves do this too; on its own it's only a warning.",
            )
    if late and (editor or not facts.resaver):
        add("AU-13", "warn", "File was created long after the document's own issue date",
            f"issued {issue:%d %b %Y}, file created {facts.created:%d %b %Y}" + (f" in {editor}" if editor else ""))
    if editor and (claims or late):
        add("AU-12", "fraud", "Likely edited: signature missing, editing software, and/or rebuilt years after issue",
            "Combination of AU-5 with AU-12/AU-13")
    if facts.author and facts.author.lower() not in ("", "unknown", "administrator", "admin"):
        add("AU-14", "info", f"File metadata names a person: Author = '{facts.author}'", "Shown to reviewers only")
    if facts.saves > 1 and not sig.present:
        add("AU-6", "info", f"File was saved {facts.saves} times", "Normal for scanners and signing; meaningful only with other signals")

    # --- AU-8 / AU-11: hidden instructions, provenance markers ---------------------------
    if facts.injection_text or (read and any("instruction" in n.lower() for n in read.integrity_notes)):
        add("AU-8", "fraud", "Document contains instruction-like text aimed at automated checks", facts.injection_text)
    if facts.ai_markers:
        add("AU-11", "review", "File carries AI/content-provenance markers", ", ".join(facts.ai_markers))

    # --- Specimens: an absolute flag on the live site ------------------------------------------
    if marked and not accept_specimens:
        out.append(Signal("AU-15", "fraud", "Not a real document: it is marked as a specimen / fictional test data",
                          "The page or the file says SPECIMEN / FICTIONAL TEST DATA / NOT A REAL DOCUMENT"
                          + (" (also matched by fingerprint to a known specimen file)" if specimen else ""),
                          "The file you uploaded is a sample or specimen, not your actual document. Please upload your own original document."))
    # --- Our own fictional fixtures, accepted ONLY when the tests ask for it (ACCEPT_SPECIMEN_DOCUMENTS) ----------
    if specimen and accept_specimens:
        for s in out:
            if s.code in ("AU-1", "AU-2") and s.severity != "info":
                s.detail = f"[not applied: known file] {s.detail}"
                s.severity = "info"
        out.append(Signal("SPECIMEN", "info", "Known file: matched by fingerprint to a registered reference copy",
                          "This exact file is on record, so visual authenticity checks are not applied. What it says is document evidence only: not independently confirmed."))

    worst = max((s.severity for s in out), key=SEVERITY.index, default="")
    if sig.present and sig.intact and sig.valid and worst in ("", "info"):
        level = "A3"
    elif worst in ("", "info") and form in ("ORIGINAL_DIGITAL", "SCAN_OR_PHOTOCOPY", "PHOTO_OF_PHYSICAL_ORIGINAL"):
        level = "A2"
    elif specimen and accept_specimens and worst in ("", "info"):
        level = "A2"
    else:
        level = "A1"
    return Authenticity(level=level, worst=worst, specimen=specimen and accept_specimens, signals=out,
                        signature=sig.as_dict(), facts=facts.as_dict())
