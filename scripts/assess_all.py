"""Run the authenticity layer on every test file using the saved Gemini reads (no new API calls).

Run: uv run python scripts/assess_all.py
"""

from __future__ import annotations

import json
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from onboarding.ai.read import ReadResult  # noqa: E402
from onboarding.authenticity.assess import assess  # noqa: E402
from scripts.read_all import targets  # noqa: E402


def main() -> None:
    for src, read_path in targets("all"):
        read = None
        if read_path.exists():
            rr = ReadResult.model_validate_json(read_path.read_text(encoding="utf-8"))
            read = rr.read if rr.ok else None
        mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        a = assess(src.read_bytes(), mime, read)
        label = f"{src.parent.name}/{src.name}"
        form = read.document_form if read else "(no read)"
        print(f"{label:58} {a.level}  worst={a.worst or '-':7} form={form}")
        for s in a.signals:
            if s.severity != "info" or s.code in ("AU-4", "AU-14"):
                print(f"{'':60}[{s.severity:6}] {s.code}: {s.title}")


if __name__ == "__main__":
    main()
