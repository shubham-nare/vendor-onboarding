"""Run demo scenarios end to end (database, documents, AI reading, rules, decision) from the
command line, and check each outcome against what we expect.

Run: uv run python scripts/run_scenario.py all            (uses cached AI readings: no API calls)
     uv run python scripts/run_scenario.py happy_nilgiri --live
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from onboarding.demo_data import SCENARIOS  # noqa: E402
from onboarding.models import Invite, Message, Run  # noqa: E402
from onboarding.pipeline import create_run, run_pipeline, sessions  # noqa: E402

DOCS = ROOT / "fixtures" / "documents"
PRIVATE = ROOT / "private_inputs"

# Variants built from Shubham's real-world test inputs (skipped if the files are absent).
VARIANTS = {
    "handwritten_nilgiri": dict(base="happy_nilgiri", expected="PENDING_VENDOR", swap={"pan_card": PRIVATE / "handwritten_pan.jpg"}),
    "ai_pan_nilgiri": dict(base="happy_nilgiri", expected="PENDING_REVIEW", swap={"pan_card": PRIVATE / "ai_pan.jpg"}),
    "screenshot_gst_nilgiri": dict(base="happy_nilgiri", expected="PENDING_VENDOR", swap={"gst_certificate": PRIVATE / "screenshot_gst.png"}),
    "ai_cheque_nilgiri": dict(base="happy_nilgiri", expected="PENDING_REVIEW", swap={"bank_proof": PRIVATE / "web_cheque_kotak_ai_generated.png"}),
    "unsolicited_nilgiri": dict(base="happy_nilgiri", expected="PENDING_REVIEW", no_invite=True),
}
ORDER = ["happy_nilgiri", "wrongdoc_tejas", "wrongdoc_tejas_resubmit", "borrowed_gstin_kaveri", "shared_bank_rangoli",
         "proprietor_shinde", *VARIANTS]


def files_for(key: str, swap: dict | None = None) -> dict[str, tuple[str, bytes]]:
    base = key
    out = {}
    for p in sorted((DOCS / base).glob("*")):
        out[p.stem] = (p.name, p.read_bytes())
    for slot, path in (swap or {}).items():
        out[slot] = (path.name, path.read_bytes())
    return out


async def fresh_invite(s, scenario_key: str) -> str:
    """A new invite cloned from the scenario's seeded invite (so each test run is a new application)."""
    tpl = (await s.execute(select(Invite).where(Invite.scenario_key == scenario_key).order_by(Invite.id))).scalars().first()
    inv = Invite(token=secrets.token_urlsafe(18), sponsor_id=tpl.sponsor_id, company_name=tpl.company_name, contact_email=tpl.contact_email,
                 business_reason=tpl.business_reason, spend_category=tpl.spend_category, spend_band=tpl.spend_band,
                 high_spend=tpl.high_spend, expires_at=tpl.expires_at + timedelta(days=0))
    s.add(inv)
    await s.commit()
    return inv.token


async def run_one(key: str, live: bool, parents: dict) -> tuple[str, str, str]:
    S = sessions()
    if key in VARIANTS:
        v = VARIANTS[key]
        if any(not p.exists() for p in v.get("swap", {}).values()):
            return key, "SKIPPED", "private input missing"
        base, expected = v["base"], v["expected"]
        form, files = SCENARIOS[base]["form"], files_for(base, v.get("swap"))
    else:
        sc = SCENARIOS[key]
        base, expected, form = key, sc["expected"], sc["form"]
        files = files_for(key)
    async with S() as s:
        parent = parents.get(SCENARIOS.get(key, {}).get("resubmission_of", ""))
        token = None
        if not parent and not VARIANTS.get(key, {}).get("no_invite"):
            token = await fresh_invite(s, base)
        run = await create_run(s, form, files, invite_token=token, parent_run_id=parent)
    dec = await run_pipeline(run.id, prefer_cache=not live)
    parents[key] = run.id
    return key, dec.status, expected, dec


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    live = "--live" in sys.argv
    keys = ORDER if not args or args == ["all"] else args
    parents: dict[str, int] = {}
    if "wrongdoc_tejas_resubmit" in keys and "wrongdoc_tejas" not in keys:
        keys = ["wrongdoc_tejas", *keys]
    ok = 0
    for key in keys:
        res = await run_one(key, live, parents)
        if res[1] == "SKIPPED":
            print(f"SKIP  {key}: {res[2]}")
            continue
        _, status, expected, dec = res
        mark = "PASS" if status == expected else "FAIL"
        ok += mark == "PASS"
        print(f"{mark}  {key:26} -> {status:15} (expected {expected}) tier={dec.risk_tier}{' FRAUD-CLASS' if dec.fraud else ''}")
        for c in dec.cards[:4]:
            print(f"        {c['rule']}: {c['title']}")
        print("        facts: " + ", ".join(f"{f.name}={f.level}" for f in dec.facts))
    print(f"\n{ok}/{len([k for k in keys])} scenarios as expected")


if __name__ == "__main__":
    asyncio.run(main())
