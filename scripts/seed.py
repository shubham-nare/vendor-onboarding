"""Create tables and load demo data. Idempotent.

Run: uv run python scripts/seed.py            # create missing tables, upsert seed data
     uv run python scripts/seed.py --reset    # drop everything and start clean (demo reset)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from onboarding.seeding import EMPLOYEES, INVITES, seed, sim_records  # noqa: E402,F401

if __name__ == "__main__":
    print(asyncio.run(seed(reset="--reset" in sys.argv)))
