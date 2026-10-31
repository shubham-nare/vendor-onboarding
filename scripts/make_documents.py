"""Render the fictional demo documents (PDF, and PNG where a scenario asks for an image).

Run: uv run python scripts/make_documents.py
Output: fixtures/documents/<scenario>/<slot>.pdf|png  +  fixtures/documents/manifest.json
Needs Google Chrome (or set CHROME=path). Uses a throwaway Chrome profile.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: E402

from onboarding.demo_data import EXTRA_DOCUMENTS, SCENARIOS  # noqa: E402

TEMPLATES = ROOT / "fixtures" / "doc_templates"
OUT = ROOT / "fixtures" / "documents"

CHROME_CANDIDATES = [
    os.environ.get("CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]

# Image size (CSS px at 96 dpi) for documents rendered as PNG; scaled 3x for legibility.
IMAGE_SIZE = {"pan_card": (410, 290), "cancelled_cheque": (785, 400)}


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome not found. Set CHROME=<path to chrome.exe>.")


def render(env: Environment, doc: dict, out_base: Path, profile: str) -> Path:
    html = env.get_template(f"{doc['kind']}.html").render(d=doc)
    if doc.get("as_image"):
        # Chrome won't open a window narrower than ~500px, so render 3x larger via CSS zoom.
        html = html.replace("</head>", "<style>html { zoom: 3; } body { padding: 4px; }</style></head>")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        src = Path(f.name)
    common = [chrome(), "--headless=new", "--disable-gpu", f"--user-data-dir={profile}", "--hide-scrollbars"]
    try:
        if doc.get("as_image"):
            w, h = IMAGE_SIZE[doc["kind"]]
            out = out_base.with_suffix(".png")
            cmd = common + [f"--screenshot={out}", f"--window-size={w * 3},{h * 3}", src.as_uri()]
        else:
            out = out_base.with_suffix(".pdf")
            cmd = common + ["--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    finally:
        src.unlink(missing_ok=True)
    if not out.exists() or out.stat().st_size == 0:
        sys.exit(f"Rendering failed for {out}")
    return out


def main() -> None:
    """No arguments: re-render everything. With scenario keys: render only those and keep the rest
    (re-rendering changes the files' bytes, which invalidates their saved AI readings)."""
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined, autoescape=True)
    only = set(sys.argv[1:])
    unknown = only - set(SCENARIOS) - {"extra"}
    if unknown:
        sys.exit(f"Unknown scenario(s): {', '.join(sorted(unknown))}")
    manifest: dict[str, dict] = {}
    if only:
        manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    else:
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as profile:
        for key, sc in SCENARIOS.items():
            if only and key not in only:
                continue
            folder = OUT / key
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir()
            files = {}
            for slot, doc in sc["documents"].items():
                path = render(env, doc, folder / slot, profile)
                files[slot] = {"file": str(path.relative_to(OUT)).replace("\\", "/"), "actual_kind": doc["kind"]}
                print(f"  {key:26} {slot:18} -> {path.name} ({path.stat().st_size // 1024} KB, really a {doc['kind']})")
            manifest[key] = {"expected": sc["expected"], "files": files}
        if not only or "extra" in only:  # loose documents (e.g. later bills), one folder
            folder = OUT / "extra"
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir()
            files = {}
            for name, doc in EXTRA_DOCUMENTS.items():
                path = render(env, doc, folder / name, profile)
                files[name] = {"file": str(path.relative_to(OUT)).replace("\\", "/"), "actual_kind": doc["kind"]}
                print(f"  extra                      {name:18} -> {path.name}")
            manifest["extra"] = {"expected": "", "files": files}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Done: {sum(len(m['files']) for m in manifest.values())} documents in {OUT}")


if __name__ == "__main__":
    main()
