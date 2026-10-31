"""Run Gemini document reading on every test file and save the results.

Run: uv run python scripts/read_all.py [fixtures|private|all]
Saves JSON next to the inputs: fixtures/reads/*.json (fictional) and private_inputs/reads/*.json (git-ignored).
Uses one Gemini request per file.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from onboarding.ai.read import read_document  # noqa: E402

KEY_FIELDS = ("gstin", "pan", "legal_name", "name_on_card", "account_number", "ifsc", "account_holder_name", "udyam_number")


def targets(which: str) -> list[tuple[Path, Path]]:
    out = []
    if which in ("fixtures", "all"):
        docs = ROOT / "fixtures" / "documents"
        manifest = json.loads((docs / "manifest.json").read_text(encoding="utf-8"))
        for key, m in manifest.items():
            for slot, info in m["files"].items():
                out.append((docs / info["file"], ROOT / "fixtures" / "reads" / f"{key}__{slot}.json"))
        out.append((ROOT / "fixtures" / "public" / "gst_certificate_signed_igr_maharashtra.pdf",
                    ROOT / "fixtures" / "reads" / "public__gst_signed.json"))
    if which in ("private", "all"):
        for f in sorted((ROOT / "private_inputs").glob("*")):
            if f.is_file():
                out.append((f, ROOT / "private_inputs" / "reads" / f"{f.stem}.json"))
    return out


async def main(which: str, only: list[str]) -> None:
    jobs = [j for j in targets(which) if not only or any(o in j[0].name for o in only)]
    print(f"Reading {len(jobs)} files with Gemini...")

    async def one(src: Path, dst: Path):
        mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        res = await read_document(src.read_bytes(), mime)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(res.model_dump_json(indent=2), encoding="utf-8")
        return src, res

    results = await asyncio.gather(*(one(s, d) for s, d in jobs))
    for src, r in results:
        if not r.ok:
            print(f"FAIL {src.name:45} {r.error}")
            continue
        d = r.read
        f = {x.name: f"{x.value}[{x.legibility[0]}]" for x in d.fields if x.name in KEY_FIELDS and x.value}
        print(f"{src.name:45} {d.doc_type:18} {d.document_form:27} {r.seconds:5.1f}s {r.model}")
        print(f"{'':45} fields: {f}")
        for label, items in (("garbled", d.garbled_or_misspelled_text), ("marks", d.visible_watermarks_or_logos),
                             ("obscured", d.obscured_regions), ("notes", d.integrity_notes)):
            if items:
                print(f"{'':45} {label}: {items[:4]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "all", sys.argv[2:]))
