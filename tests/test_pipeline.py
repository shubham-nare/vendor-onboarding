"""End-to-end: every scenario through a throwaway SQLite database, using cached AI readings
(no API calls). Skipped if the reading cache hasn't been built (it's git-ignored)."""

import asyncio
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".read_cache"
pytestmark = pytest.mark.skipif(not CACHE.exists() or not any(CACHE.iterdir()), reason="no cached AI readings")


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    cfg.get_settings.cache_clear()
    import onboarding.db as dbm
    dbm._engine = None
    sys.path.insert(0, str(ROOT))
    seed = importlib.import_module("scripts.seed")
    rs = importlib.import_module("scripts.run_scenario")

    async def go():
        await seed.seed(reset=True)
        import onboarding.db as dbm2
        dbm2._engine = None
        parents, out = {}, {}
        for key in rs.ORDER:
            res = await rs.run_one(key, False, parents)
            if res[1] != "SKIPPED":
                out[key] = res
        return out

    out = asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


@pytest.mark.parametrize("key", ["happy_nilgiri", "wrongdoc_tejas", "wrongdoc_tejas_resubmit", "borrowed_gstin_kaveri",
                                 "shared_bank_rangoli", "proprietor_shinde", "unsolicited_nilgiri"])
def test_scenario_outcome(results, key):
    _, status, expected, _ = results[key]
    assert status == expected


def test_rejection_message_is_held_for_a_human(results):
    dec = results["borrowed_gstin_kaveri"][3]
    assert dec.vendor_state == "held" and "different legal entity" in dec.vendor_body


def test_fraud_signals_produce_a_neutral_vendor_message(results):
    dec = results["shared_bank_rangoli"][3]
    assert dec.fraud and "DECCAN" not in dec.vendor_body and "under review" in dec.vendor_subject


def test_vendor_gets_one_complete_list(results):
    dec = results["wrongdoc_tejas"][3]
    assert "tax invoice" in dec.vendor_body and "Udyam" in dec.vendor_body and dec.vendor_state == "sent"


def test_borrowed_gstin_fact_drops_to_a0(results):
    facts = {f.name: f.level for f in results["borrowed_gstin_kaveri"][3].facts}
    assert facts["GSTIN"] == "A0"


def test_bank_branch_confirmed_live_reaches_a4(results):
    facts = {f.name: f for f in results["happy_nilgiri"][3].facts}
    assert facts["Bank branch"].level in ("A4", "A1")  # A1 only if the live lookup was unreachable (snapshot)
