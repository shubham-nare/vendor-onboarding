"""The demo scenarios must stay internally consistent, or the live demo breaks."""

import json
from pathlib import Path

from onboarding import validators as v
from onboarding.demo_data import BLOCKLIST, SCENARIOS, VENDOR_MASTER

DOCS = Path(__file__).resolve().parent.parent / "fixtures" / "documents"


def test_expected_gstins_unchanged():
    expected = {
        "happy_nilgiri": "29AAHCN4821K1Z4",
        "wrongdoc_tejas": "36AAJCT9052D1Z7",
        "borrowed_gstin_kaveri": "27AAHCK5590L1ZX",
        "shared_bank_rangoli": "36AAQCR6188B1ZZ",
        "proprietor_shinde": "27BVKPS5274R1ZE",
    }
    for key, g in expected.items():
        assert SCENARIOS[key]["form"]["gstin"] == g


def test_all_ids_are_well_formed():
    for key, sc in SCENARIOS.items():
        f = sc["form"]
        assert v.gstin_format_ok(f["gstin"]) and v.gstin_checksum_ok(f["gstin"]), key
        assert v.validate_pan(f["pan"]), key
        assert v.validate_ifsc(f["ifsc"]), key
        assert v.account_number_ok(f["bank_account"]), key
        assert v.state_code_for_name(f["state"]) == f["gstin"][:2], key
        assert v.pan_code(f["pan"]) == v.EXPECTED_PAN_CODE[f["business_type"]], key


def test_only_kaveri_has_a_pan_gstin_conflict():
    for key, sc in SCENARIOS.items():
        f = sc["form"]
        conflict = v.gstin_embedded_pan(f["gstin"]) != f["pan"]
        assert conflict == (key == "borrowed_gstin_kaveri"), key


def test_rangoli_account_is_already_on_file_for_another_vendor():
    f = SCENARIOS["shared_bank_rangoli"]["form"]
    owners = [m for m in VENDOR_MASTER if m["account"] == f["bank_account"] and m["ifsc"] == f["ifsc"]]
    assert len(owners) == 1 and owners[0]["pan"] != f["pan"]


def test_no_other_scenario_collides_with_vendor_master_or_blocklist():
    taken = {(m["account"], m["ifsc"]) for m in VENDOR_MASTER}
    ids = {m["pan"] for m in VENDOR_MASTER} | {m["gstin"] for m in VENDOR_MASTER}
    ids |= {b["pan"] for b in BLOCKLIST} | {b["gstin"] for b in BLOCKLIST}
    for key, sc in SCENARIOS.items():
        f = sc["form"]
        if key != "shared_bank_rangoli":
            assert (f["bank_account"], f["ifsc"]) not in taken, key
        assert f["pan"] not in ids and f["gstin"] not in ids, key


def test_master_and_blocklist_ids_valid():
    for m in VENDOR_MASTER + BLOCKLIST:
        assert v.gstin_checksum_ok(m["gstin"]) and v.gstin_embedded_pan(m["gstin"]) == m["pan"]


def test_generated_documents_exist_for_every_scenario():
    manifest = json.loads((DOCS / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == set(SCENARIOS)
    for key, m in manifest.items():
        for slot, info in m["files"].items():
            assert (DOCS / info["file"]).stat().st_size > 10_000, (key, slot)
