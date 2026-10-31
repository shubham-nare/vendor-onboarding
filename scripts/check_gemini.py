"""One-request check that the Gemini key in .env works. Uses 1 of the day's free requests.

Run: uv run python scripts/check_gemini.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai  # noqa: E402

from onboarding.config import get_settings  # noqa: E402

s = get_settings()
if not s.gemini_api_key:
    sys.exit("GEMINI_API_KEY is empty. Open vendor-onboarding/.env and paste your key after GEMINI_API_KEY=")

client = genai.Client(api_key=s.gemini_api_key)
start = time.perf_counter()
try:
    r = client.models.generate_content(model=s.gemini_model, contents="Reply with exactly: OK")
except Exception as e:  # show the reason plainly, never the key
    sys.exit(f"Gemini call failed for model {s.gemini_model}: {type(e).__name__}: {e}")
print(f"model: {s.gemini_model}")
print(f"reply: {r.text!r}")
print(f"time:  {time.perf_counter() - start:.1f}s")
