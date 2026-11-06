"""Move a registration's history back in time, to rehearse the follow-up schedule on staging data.

Shifts the application, its checks, the messages and the reviewer actions back by N days, so "waiting on
the vendor for 4 days" can be shown without waiting 4 days. It doesn't send anything: run the follow-up job
afterwards (System page, "Run follow-ups now").

Run: uv run python scripts/backdate.py VOB-0002 4
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from onboarding.models import Application, FollowUp, HumanAction, Message, Run  # noqa: E402
from onboarding.pipeline import sessions  # noqa: E402


async def main(ref: str, days: int) -> None:
    d = timedelta(days=days)
    async with sessions()() as s:
        app = (await s.execute(select(Application).where(Application.ref == ref))).scalar_one_or_none()
        if not app:
            sys.exit(f"No application {ref}")
        app.created_at -= d
        runs = (await s.execute(select(Run).where(Run.application_id == app.id))).scalars().all()
        ids = [r.id for r in runs]
        for r in runs:
            r.started_at -= d
            if r.finished_at:
                r.finished_at -= d
        for m in (await s.execute(select(Message).where(Message.run_id.in_(ids)))).scalars():
            m.created_at -= d
        for a in (await s.execute(select(HumanAction).where(HumanAction.run_id.in_(ids)))).scalars():
            a.at -= d
        for f in (await s.execute(select(FollowUp).where(FollowUp.run_id.in_(ids)))).scalars():
            f.at -= d
        await s.commit()
    print(f"{ref}: moved {len(ids)} check(s) back {days} day(s)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--production"]
    if len(args) != 2:
        sys.exit(__doc__)
    from onboarding.seeding import confirm_target
    confirm_target()   # a non-local database needs --production and the host typed back
    asyncio.run(main(args[0], int(args[1])))
