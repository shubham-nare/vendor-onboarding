"""Robustness harness: degrade GENUINE documents and measure how reading + matching hold up.

For each document x degradation: render -> degrade -> Gemini read -> compare each key field
with the known value -> exact / corrected / unreadable / wrong; plus the authenticity verdict.
Pass criterion: no degraded genuine document gets a fraud-class flag, and no field is "wrong"
(a misread must land in "corrected" or "unreadable", never silently accepted as different).

Run: uv run python scripts/robustness.py        (~30 Gemini requests)
Writes docs/research/robustness.md (fictional/public docs only; private results stay in private_inputs/).
"""

from __future__ import annotations

import asyncio
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402  (PyMuPDF)
from PIL import Image, ImageFilter  # noqa: E402

from onboarding import demo_data as dd  # noqa: E402
from onboarding.ai.read import ReadResult, read_document  # noqa: E402
from onboarding.authenticity.assess import assess  # noqa: E402
from onboarding.matching import MATCH, MATCH_CORRECTED, MISMATCH, compare_account, compare_id, compare_name  # noqa: E402

DOCS = ROOT / "fixtures" / "documents"


def expected_docs() -> list[dict]:
    n, t, r = dd.NILGIRI, dd.TEJAS, dd.RANGOLI
    out = [
        dict(name="Nilgiri GST certificate", path=DOCS / "happy_nilgiri/gst_certificate.pdf", private=False,
             expect={"gstin": ("id:gstin", n["gstin"]), "legal_name": ("name", n["legal_name"])}),
        dict(name="Nilgiri cancelled cheque", path=DOCS / "happy_nilgiri/bank_proof.pdf", private=False,
             expect={"account_number": ("account", n["bank"]["account"]), "ifsc": ("id:ifsc", n["bank"]["ifsc"]),
                     "account_holder_name": ("name", n["bank"]["holder"])}),
        dict(name="Tejas Udyam certificate", path=DOCS / "wrongdoc_tejas_resubmit/udyam_certificate.pdf", private=False,
             expect={"udyam_number": ("id:raw", t["udyam"]["number"]), "enterprise_name": ("name", t["legal_name"])}),
        dict(name="Rangoli cheque (image)", path=DOCS / "shared_bank_rangoli/bank_proof.png", private=False,
             expect={"account_number": ("account", r["bank"]["account"]), "ifsc": ("id:ifsc", r["bank"]["ifsc"])}),
        dict(name="Real GSTN-signed certificate", path=ROOT / "fixtures/public/gst_certificate_signed_igr_maharashtra.pdf", private=False,
             expect={"gstin": ("id:raw", "27PNEI00141B1DI")}, genuine_visual=True),
    ]
    own = ROOT / "private_inputs" / "own_pan_card.jpg"
    ref = ROOT / "private_inputs" / "reads" / "own_pan_card.json"
    if own.exists() and ref.exists():  # expected values come from the clear read; never hard-coded
        rr = ReadResult.model_validate_json(ref.read_text(encoding="utf-8"))
        vals = {f.name: f.value for f in rr.read.fields if f.value}
        out.append(dict(name="Real PAN card (Shubham's)", path=own, private=True, genuine_visual=True,
                        expect={"pan": ("id:pan", vals["pan"]), "name_on_card": ("name", vals["name_on_card"])}))
    return out


def render(path: Path) -> Image.Image:
    if path.suffix.lower() == ".pdf":
        page = fitz.open(path)[0]
        pix = page.get_pixmap(dpi=150)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    from PIL import ImageOps
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def jpeg(im: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def noise(im: Image.Image, amount: int = 18) -> Image.Image:
    rnd = random.Random(7)
    px = im.load()
    w, h = im.size
    for _ in range(w * h // 12):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]
        d = rnd.randint(-amount, amount)
        px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)))
    return im


DEGRADATIONS = {
    "blur": lambda im: im.filter(ImageFilter.GaussianBlur(1.6)),
    "jpeg_q20": lambda im: jpeg(im, 20),
    "low_res_40pct": lambda im: im.resize((int(im.width * 0.4), int(im.height * 0.4)), Image.LANCZOS),
    "tilt_3deg": lambda im: im.rotate(3, expand=True, fillcolor=(235, 235, 235)),
    "combo_phone": lambda im: jpeg(noise(im.rotate(-2, expand=True, fillcolor=(225, 225, 225)).filter(ImageFilter.GaussianBlur(1.0))), 35),
}


def outcome(kind: str, expected: str, f) -> str:
    val = f.value if f else None
    leg = f.legibility if f else "not_present"
    if kind == "account":
        r = compare_account(expected, val, leg).status
    elif kind == "name":
        r = compare_name(expected, val, legibility=leg).status
        r = {"PARTIAL": "UNREADABLE"}.get(r, r) if leg != "clear" else r
    elif kind == "id:raw":
        r = MATCH if (val or "").replace(" ", "").upper() == expected else ("UNREADABLE" if leg != "clear" or not val else MISMATCH)
    else:
        r = compare_id(kind.split(":")[1], expected, val, leg).status
    return {MATCH: "exact", MATCH_CORRECTED: "corrected", MISMATCH: "WRONG", "PARTIAL": "WRONG"}.get(r, "unreadable")


async def main() -> None:
    rows, private_rows = [], []
    jobs = []
    for doc in expected_docs():
        base = render(doc["path"])
        for dname, fn in DEGRADATIONS.items():
            im = fn(base.copy())
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
            jobs.append((doc, dname, buf.getvalue()))

    async def run(doc, dname, data):
        res = await read_document(data, "image/jpeg")
        return doc, dname, data, res

    for doc, dname, data, res in await asyncio.gather(*(run(*j) for j in jobs)):
        if not res.ok:
            row = dict(doc=doc["name"], degradation=dname, error=res.error)
        else:
            fields = {f.name: f for f in res.read.fields}
            outs = {k: outcome(kind, exp, fields.get(k)) for k, (kind, exp) in doc["expect"].items()}
            a = assess(data, "image/jpeg", res.read)
            row = dict(doc=doc["name"], degradation=dname, form=res.read.document_form, fields=outs,
                       authenticity=a.worst or "-", fraud_flag=(a.worst == "fraud"), genuine_visual=doc.get("genuine_visual", False))
        (private_rows if doc["private"] else rows).append(row)
        print(json.dumps(row))

    def table(rs: list[dict]) -> str:
        lines = ["| Document | Degradation | Read as | Fields | Authenticity |", "|---|---|---|---|---|"]
        for r in rs:
            if "error" in r:
                lines.append(f"| {r['doc']} | {r['degradation']} | ERROR | {r['error'][:60]} | |")
                continue
            f = ", ".join(f"{k}: {v}" for k, v in r["fields"].items())
            lines.append(f"| {r['doc']} | {r['degradation']} | {r['form']} | {f} | {r['authenticity']} |")
        return "\n".join(lines)

    def stats(rs: list[dict]) -> str:
        cells = [v for r in rs if "fields" in r for v in r["fields"].values()]
        n = len(cells) or 1
        c = {k: cells.count(k) for k in ("exact", "corrected", "unreadable", "WRONG")}
        fraud_genuine = sum(1 for r in rs if r.get("fraud_flag") and r.get("genuine_visual"))
        fraud_any = sum(1 for r in rs if r.get("fraud_flag"))
        return (f"Field readings: {len(cells)} | exact {c['exact']} ({100*c['exact']//n}%) | corrected {c['corrected']} | "
                f"unreadable (re-upload) {c['unreadable']} | **wrong {c['WRONG']}**\n\n"
                f"Fraud-class flags on degraded genuine documents with real visuals: **{fraud_genuine}**; on any degraded copy: {fraud_any}")

    md = ["# Robustness harness results", "", "Genuine documents rendered, degraded, read by Gemini, matched against known values.", "",
          stats(rows), "", table(rows)]
    (ROOT.parent / "docs" / "research" / "robustness.md").write_text("\n".join(md), encoding="utf-8")
    if private_rows:
        (ROOT / "private_inputs" / "reads" / "robustness_private.md").write_text("\n".join([stats(private_rows), "", table(private_rows)]), encoding="utf-8")
    print("\n" + stats(rows + private_rows))


if __name__ == "__main__":
    asyncio.run(main())
