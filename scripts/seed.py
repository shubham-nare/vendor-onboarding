"""Create tables and load demo data. Idempotent.

Run: uv run python scripts/seed.py            # create missing tables, upsert seed data
     uv run python scripts/seed.py --reset    # drop everything and start clean (demo reset)
     uv run python scripts/seed.py --payables # add sample purchase orders to an existing database (no reset)
A non-local DATABASE_URL is refused unless you add --production and type the host when asked.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from onboarding.seeding import EMPLOYEES, INVITES, confirm_target, load_payables_sample, seed, sim_records  # noqa: E402,F401

if __name__ == "__main__":
    remote_ok = confirm_target()   # prints the host; a non-local database needs --production and the host typed back
    if "--payables" in sys.argv:
        print(asyncio.run(load_payables_sample()))
    else:
        print(asyncio.run(seed(reset="--reset" in sys.argv, allow_remote=remote_ok)))
