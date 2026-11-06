"""Build the browser app: onboarding/frontend/*.js (in name order) -> onboarding/static/app.js, one compact file.

Comments, indentation and blank lines are removed and everything is wrapped in one function, so nothing leaks
into the page's global scope. No source map is written. Run after changing anything in onboarding/frontend:

    uv run python scripts/build_frontend.py
(a test fails if app.js is out of date)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "onboarding" / "frontend"
OUT = ROOT / "onboarding" / "static" / "app.js"


def compact(js: str) -> str:
    js = re.sub(r"^\s*/\*.*?\*/\s*$", "", js, flags=re.S | re.M)      # block comments on their own lines
    out = []
    for line in js.split("\n"):
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        s = re.sub(r"\s{2,}//\s.*$", "", s)                            # comments at the end of a line
        out.append(s)
    return "\n".join(out)


def build() -> str:
    parts = [compact(p.read_text(encoding="utf-8")) for p in sorted(SRC.glob("*.js"))]
    return "/* Parakh Vendor Onboarding */\n(()=>{'use strict';\n" + "\n".join(parts) + "\n})();\n"


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} KB")
    sys.exit(0)
