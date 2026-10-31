"""File-level facts: PDF info dictionary, save count, text layer, image EXIF, AI provenance markers."""

from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from PIL import ExifTags, Image

# Software that creates or edits documents. Seeing one of these is a flag, not proof:
# honest people also re-save files.
EDITORS = {
    "canva": "Canva", "photoshop": "Adobe Photoshop", "illustrator": "Adobe Illustrator",
    "ilovepdf": "iLovePDF", "sejda": "Sejda", "smallpdf": "Smallpdf", "pdfescape": "PDFescape",
    "pdf-xchange": "PDF-XChange", "foxit phantom": "Foxit PhantomPDF", "nitro": "Nitro PDF",
    "gimp": "GIMP", "inkscape": "Inkscape", "microsoft word": "Microsoft Word",
    "libreoffice": "LibreOffice", "pixlr": "Pixlr", "snapseed": "Snapseed", "picsart": "PicsArt",
    "midjourney": "Midjourney", "dall": "DALL-E", "stable diffusion": "Stable Diffusion",
}
# Producers that merely re-render (browser print / viewer save): they strip signatures but don't edit.
RESAVERS = {"pdfium": "PDFium (browser save)", "skia": "Skia/Chrome (print to PDF)", "quartz": "macOS Quartz", "microsoft: print to pdf": "Microsoft Print to PDF"}
AI_MARKERS = [b"c2pa", b"jumbf", b"trainedAlgorithmicMedia", b"SynthID", b"Made with Google AI", b"DALL-E", b"OpenAI"]
SIGNATURE_CLAIM = re.compile(r"digitally\s+signed\s+by|signature\s+(?:not\s+)?verified", re.I)
INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|disregard (?:the )?(?:previous|above)|"
    r"you are (?:now )?an? (?:ai|assistant|model)|system prompt|mark (?:this|the) (?:vendor|application) as approved|"
    r"approve this (?:vendor|application)|return (?:status|decision)\s*[:=]",
    re.I,
)


@dataclass
class FileFacts:
    kind: str                       # pdf | image | other
    producer: str = ""
    creator: str = ""
    author: str = ""
    created: datetime | None = None
    modified: datetime | None = None
    saves: int = 0                  # %%EOF markers
    pages: int = 0
    text: str = ""                  # text layer (PDF only)
    width: int = 0
    height: int = 0
    exif_software: str = ""
    exif_camera: str = ""
    ai_markers: list[str] = field(default_factory=list)
    editor: str = ""                # name if producer/creator/software is a known editor
    resaver: str = ""
    signature_claimed_in_text: bool = False
    injection_text: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["text"] = self.text[:300]
        d["created"] = self.created.isoformat() if self.created else None
        d["modified"] = self.modified.isoformat() if self.modified else None
        return d


def _pdf_date(v) -> datetime | None:
    if not v:
        return None
    m = re.search(r"(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", str(v))
    if not m:
        return None
    parts = [int(x) if x else 0 for x in m.groups()]
    try:
        return datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
    except ValueError:
        return None


def _match(table: dict, *values: str) -> str:
    blob = " ".join(v.lower() for v in values if v)
    for key, name in table.items():
        if key in blob:
            return name
    return ""


def inspect_file(raw: bytes, mime: str) -> FileFacts:
    markers = [m.decode() for m in AI_MARKERS if m in raw]
    if mime == "application/pdf" or raw[:5] == b"%PDF-":
        from pypdf import PdfReader
        f = FileFacts(kind="pdf", saves=raw.count(b"%%EOF"), ai_markers=markers)
        try:
            r = PdfReader(io.BytesIO(raw), strict=False)
            info = r.metadata or {}
            f.producer = str(info.get("/Producer", "") or "").strip()
            f.creator = str(info.get("/Creator", "") or "").strip()
            f.author = str(info.get("/Author", "") or "").strip()
            f.created = _pdf_date(info.get("/CreationDate"))
            f.modified = _pdf_date(info.get("/ModDate"))
            f.pages = len(r.pages)
            f.text = "\n".join((p.extract_text() or "") for p in r.pages[:4])
        except Exception:
            pass
        f.editor = _match(EDITORS, f.producer, f.creator)
        f.resaver = _match(RESAVERS, f.producer, f.creator)
        f.signature_claimed_in_text = bool(SIGNATURE_CLAIM.search(f.text))
        inj = INJECTION.search(f.text)
        f.injection_text = inj.group(0) if inj else ""
        return f
    if mime.startswith("image/"):
        f = FileFacts(kind="image", ai_markers=markers)
        try:
            im = Image.open(io.BytesIO(raw))
            f.width, f.height = im.size
            ex = {ExifTags.TAGS.get(k, k): v for k, v in im.getexif().items()}
            f.exif_software = str(ex.get("Software", "") or "")
            f.exif_camera = " ".join(str(ex.get(k, "")) for k in ("Make", "Model")).strip()
        except Exception:
            pass
        f.editor = _match(EDITORS, f.exif_software)
        return f
    return FileFacts(kind="other", ai_markers=markers)
