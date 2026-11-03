"""Vendor Intelligence end to end: real pipeline runs (cached AI readings), then identity, evidence, fact history,
relationships, risk flags, decision snapshots, Vendor 360 pages and access rules. Throwaway SQLite database."""

import asyncio
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".read_cache"
pytestmark = pytest.mark.skipif(not CACHE.exists() or not any(CACHE.iterdir()), reason="no cached AI readings")

KEYS = ["happy_nilgiri", "wrongdoc_tejas", "wrongdoc_tejas_resubmit", "borrowed_gstin_kaveri", "shared_bank_rangoli", "proprietor_shinde",
        "unsolicited_nilgiri"]


@pytest.fixture(scope="module")
def intel(tmp_path_factory):
    db = tmp_path_factory.mktemp("inteldb") / "intel.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    import onboarding.config as cfg
    import onboarding.db as dbm
    cfg.get_settings.cache_clear()
    dbm._engine = None
    import httpx
    from sqlalchemy import func, select

    from onboarding.demo_data import SCENARIOS
    from onboarding.intel.crypto import decrypt
    from onboarding.intel.models import (DecisionSnapshot, DomainEvent, EvidenceItem, FactObservation, GraphEdge, GraphNode, RiskEvent, Vendor,
                                         VendorApplication, VendorIdentifier)
    from onboarding.intel.project import backfill, on_run_completed
    from onboarding.intel.snapshot import reconstruct
    from onboarding.main import app
    from onboarding.intel.models import SimulationRun
    from onboarding.models import Application, Employee, HumanAction, Message, Run, RuleResult
    from onboarding.models import Fact as RunFact
    from onboarding.pipeline import sessions
    from onboarding.seeding import DEMO_COMPANY_EMAIL, DEMO_PASSWORD, seed
    from scripts.run_scenario import run_one

    tables = (Vendor, VendorApplication, VendorIdentifier, EvidenceItem, FactObservation, GraphNode, GraphEdge, RiskEvent, DecisionSnapshot, DomainEvent)
    out: dict = {}

    async def counts():
        async with sessions()() as s:
            return {t.__tablename__: (await s.execute(select(func.count()).select_from(t))).scalar() for t in tables}

    async def go():
        await seed(reset=True, dispose=False)
        parents: dict = {}
        for key in KEYS:
            await run_one(key, False, parents)
            await on_run_completed(parents[key])
        out["runs"] = dict(parents)
        out["counts"] = await counts()
        out["backfill"] = await backfill()            # nothing left to do
        for rid in parents.values():                  # and projecting again changes nothing
            await on_run_completed(rid)
        out["counts_again"] = await counts()

        async with sessions()() as s:
            def pan_of(key):
                return SCENARIOS["happy_nilgiri" if key == "unsolicited_nilgiri" else key]["form"]["pan"]
            v_of = {}
            for key, rid in parents.items():
                run = await s.get(Run, rid)
                va = (await s.execute(select(VendorApplication).where(VendorApplication.application_id == run.application_id))).scalar_one()
                v_of[key] = await s.get(Vendor, va.vendor_pk)
            out["vendor_of"] = {k: (v.vendor_id, v.display_name, v.status) for k, v in v_of.items()}
            out["deccan"] = (await s.execute(select(Vendor).where(Vendor.erp_vendor_id == "V-0042"))).scalar_one()
            out["risks"] = [(r.rule_id, r.kind, r.status, r.vendor_pk, r.related_vendor_pk, r.reviewer_action, r.evidence_item_id)
                            for r in (await s.execute(select(RiskEvent))).scalars()]
            out["v_pk"] = {k: v.id for k, v in v_of.items()}
            out["snaps"] = {rid: (sn.replay_ok, sn.reconstructed, sn.replay_note) for rid, sn in
                            ((sn.run_id, sn) for sn in (await s.execute(select(DecisionSnapshot))).scalars())}
            tej = v_of["wrongdoc_tejas"]
            out["tejas_obs"] = [(o.fact, o.run_id, o.supersedes_id, o.level) for o in
                                (await s.execute(select(FactObservation).where(FactObservation.vendor_pk == tej.id).order_by(FactObservation.id))).scalars()]
            out["edges_no_evidence"] = (await s.execute(select(func.count()).select_from(GraphEdge).where(GraphEdge.evidence_item_id.is_(None),
                                                                                                         GraphEdge.type.not_in(("GSTIN_OF_PAN", "ACCOUNT_AT"))))).scalar()
            out["kaveri_edges"] = [(e.type, e.status, e.rule_id) for e in (await s.execute(
                select(GraphEdge).join(GraphNode, GraphNode.id == GraphEdge.src_id).where(GraphNode.vendor_pk == v_of["borrowed_gstin_kaveri"].id))).scalars()]
            raw = [SCENARIOS[k]["form"][f] for k in ("shared_bank_rangoli", "happy_nilgiri") for f in ("pan", "bank_account")]
            # GSTINs are public business data (they embed the PAN by design), as on the run page; everything else must be masked
            keys = [n.lookup_key + " " + ("" if n.kind == "GSTIN" else n.display) for n in (await s.execute(select(GraphNode))).scalars()]
            out["raw_in_graph"] = [r for r in raw if any(r in k for k in keys)]
            ident = (await s.execute(select(VendorIdentifier).where(VendorIdentifier.vendor_pk == v_of["shared_bank_rangoli"].id,
                                                                   VendorIdentifier.kind == "BANK_ACCOUNT"))).scalars().first()
            out["decrypted_account"] = decrypt(ident.value_enc)
            out["rangoli_account"] = SCENARIOS["shared_bank_rangoli"]["form"]["bank_account"]
            out["pan_of"] = pan_of
            # a run's input rebuilt from stored data (as for runs from before snapshots) must reproduce its decision
            rebuilt = await reconstruct(s, await s.get(Run, parents["shared_bank_rangoli"]))
            out["rebuilt"] = (rebuilt.replay_ok, rebuilt.replay_note)
            emp = {e.name if e.role == "sponsor" else e.role: e.id for e in (await s.execute(select(Employee))).scalars()}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            await c.post("/company/login", data={"email": DEMO_COMPANY_EMAIL, "password": DEMO_PASSWORD})
            rangoli, deccan = out["vendor_of"]["shared_bank_rangoli"][0], out["deccan"].vendor_id
            c.cookies.set("actor", str(emp["maker"]))
            out["dir"] = (await c.get("/vendors")).text
            out["rangoli_page"] = (await c.get(f"/vendors/{rangoli}")).text
            out["deccan_page"] = (await c.get(f"/vendors/{deccan}")).text
            out["dash"] = (await c.get("/console")).text
            out["run_page"] = (await c.get(f"/runs/{parents['shared_bank_rangoli']}")).text
            out["missing"] = (await c.get("/vendors/VND-9999")).status_code
            out["accounts"] = (await c.get("/supplier-accounts")).status_code
            c.cookies.set("actor", str(emp["Priya Nair"]))          # didn't request Rangoli
            out["priya_rangoli"] = (await c.get(f"/vendors/{rangoli}")).status_code
            out["priya_dir"] = (await c.get("/vendors")).text
            c.cookies.set("actor", str(emp["Rahul Desai"]))         # requested Rangoli
            out["rahul_rangoli"] = (await c.get(f"/vendors/{rangoli}")).text
            # counterfactuals: same rules, a copy of the saved input, nothing real touched
            real = (Run, RuleResult, RunFact, Message, HumanAction, RiskEvent, EvidenceItem, DecisionSnapshot, Application, VendorApplication)
            async def real_counts():
                async with sessions()() as s2:
                    n = {m.__tablename__: (await s2.execute(select(func.count()).select_from(m))).scalar() for m in real}
                    n["statuses"] = sorted((await s2.execute(select(Application.id, Application.current_status))).all())
                    n["run_status"] = sorted((await s2.execute(select(Run.id, Run.status))).all())
                    return n
            before = await real_counts()
            c.cookies.set("actor", str(emp["checker"]))
            out["sim_policy"] = (await c.post(f"/runs/{parents['happy_nilgiri']}/simulate", data={"scenario": "policy_bank_a4"})).text
            out["sim_clear"] = (await c.post(f"/runs/{parents['shared_bank_rangoli']}/simulate", data={"scenario": "clear_flag", "rule_id": "R-SRC-BANK"})).text
            out["sim_clear_conflict"] = (await c.post(f"/runs/{parents['borrowed_gstin_kaveri']}/simulate", data={"scenario": "clear_flag", "rule_id": "R-XD-03"})).text
            out["sim_bad_rule"] = (await c.post(f"/runs/{parents['happy_nilgiri']}/simulate", data={"scenario": "clear_flag", "rule_id": "R-XD-03"})).text
            out["sim_panel"] = (await c.get(f"/runs/{parents['shared_bank_rangoli']}")).text
            out["real_unchanged"] = (before == await real_counts())
            async with sessions()() as s2:
                out["sim_rows"] = (await s2.execute(select(func.count()).select_from(SimulationRun))).scalar()
                snap = (await s2.execute(select(DecisionSnapshot).where(DecisionSnapshot.run_id == parents["proprietor_shinde"]))).scalar_one()
                snap.replay_ok, snap.replay_note = False, "test: pretend it doesn't reproduce"
                await s2.commit()
            out["sim_refused"] = (await c.post(f"/runs/{parents['proprietor_shinde']}/simulate", data={"scenario": "policy_bank_a4"})).text
            out["sim_refused_panel"] = (await c.get(f"/runs/{parents['proprietor_shinde']}")).text
            c.cookies.set("actor", str(emp["Rahul Desai"]))
            out["sim_requester"] = (await c.post(f"/runs/{parents['shared_bank_rangoli']}/simulate", data={"scenario": "policy_bank_a4"})).status_code
            # a person's decision closes the flags it addressed; activation makes the vendor active
            nil_run = parents["happy_nilgiri"]
            c.cookies.set("actor", str(emp["maker"]))
            out["activate"] = (await c.post(f"/runs/{nil_run}/action", data={"action": "activate"})).status_code
            kav_run = parents["borrowed_gstin_kaveri"]
            c.cookies.set("actor", str(emp["checker"]))
            out["kaveri_page_before"] = (await c.get(f"/runs/{kav_run}")).text
            out["confirm"] = (await c.post(f"/runs/{kav_run}/action", data={"action": "confirm_reject"})).status_code
            out["kaveri_page_after"] = (await c.get(f"/runs/{kav_run}")).text
        async with sessions()() as s:
            out["nilgiri_after"] = (await s.get(Vendor, out["v_pk"]["happy_nilgiri"])).status
            out["kaveri_flags_after"] = [(r.status, r.resolution) for r in (await s.execute(select(RiskEvent).where(RiskEvent.vendor_pk == out["v_pk"]["borrowed_gstin_kaveri"]))).scalars()]
            out["decision_events"] = (await s.execute(select(func.count()).select_from(DomainEvent).where(DomainEvent.type == "decision.recorded"))).scalar()
            out["apps_of_nilgiri"] = (await s.execute(select(func.count()).select_from(VendorApplication).where(VendorApplication.vendor_pk == out["v_pk"]["happy_nilgiri"]))).scalar()
            out["app_count"] = (await s.execute(select(func.count()).select_from(Application))).scalar()
        await dbm.engine().dispose()

    asyncio.run(go())
    os.environ.pop("DATABASE_URL", None)
    cfg.get_settings.cache_clear()
    dbm._engine = None
    return out


def test_projection_is_idempotent(intel):
    assert intel["counts"]["vendors"] > 0 and intel["counts"]["evidence_items"] > 0
    assert intel["backfill"] == {"runs": 0, "decisions": 0}
    assert intel["counts_again"] == intel["counts"]


def test_vendor_identity_pan_matches_and_ids_are_ours(intel):
    vo = intel["vendor_of"]
    assert all(re.fullmatch(r"VND-\d{4}", vid) for vid, _, _ in vo.values())
    assert vo["happy_nilgiri"][0] == vo["unsolicited_nilgiri"][0]          # same PAN: one vendor, two applications
    assert intel["apps_of_nilgiri"] == 2
    assert vo["wrongdoc_tejas"][0] == vo["wrongdoc_tejas_resubmit"][0]    # resubmission: same application, same vendor
    assert len({vo[k][0] for k in ("happy_nilgiri", "wrongdoc_tejas", "borrowed_gstin_kaveri", "shared_bank_rangoli", "proprietor_shinde")}) == 5


def test_shared_bank_account_is_a_relationship_not_a_merge(intel):
    rangoli_pk, deccan = intel["v_pk"]["shared_bank_rangoli"], intel["deccan"]
    assert rangoli_pk != deccan.id
    flags = [r for r in intel["risks"] if r[0] == "R-RISK-02"]
    assert flags and flags[0][3] == rangoli_pk and flags[0][4] == deccan.id
    assert flags[0][5] and flags[0][6]                                     # a reviewer action and evidence provenance
    page = intel["rangoli_page"]
    assert "Shared bank account" in page and "Deccan Office Supplies" in page and "Needs a reviewer (1)" in page
    assert "In doubt despite its level" in page                            # a good evidence level never hides an open conflict
    assert "Verify who owns the shared bank account" in page


def test_identity_conflict_is_unresolved_and_flagged(intel):
    assert ("IDENTITY_CONFLICT", "unresolved", "R-XD-03") in intel["kaveri_edges"]
    assert ("HAS_GSTIN", "unresolved", "R-XD-03") in intel["kaveri_edges"]
    assert any(r[0] == "R-XD-03" and r[3] == intel["v_pk"]["borrowed_gstin_kaveri"] for r in intel["risks"])


def test_every_relationship_and_flag_has_provenance(intel):
    assert intel["edges_no_evidence"] == 0
    assert all(r[5] for r in intel["risks"])                               # every flag says what the reviewer does


def test_fact_history_keeps_earlier_observations(intel):
    obs = intel["tejas_obs"]
    r1, r2 = intel["runs"]["wrongdoc_tejas"], intel["runs"]["wrongdoc_tejas_resubmit"]
    later = [o for o in obs if o[1] == r2]
    assert later and all(o[2] is not None for o in later)                  # each supersedes the first submission's observation
    assert any(o[1] == r1 for o in obs)                                    # and the first one is kept


def test_decisions_replay_exactly(intel):
    snaps = intel["snaps"]
    assert set(intel["runs"].values()) <= set(snaps)
    assert all(ok for ok, rec, note in snaps.values()), snaps            # new runs: exact snapshots that replay
    assert not any(rec for ok, rec, note in snaps.values())
    assert intel["rebuilt"][0] is True, intel["rebuilt"]                  # rebuilt from stored data: still reproduces


def test_sensitive_identifiers_are_hmacd_and_encrypted(intel):
    assert intel["raw_in_graph"] == []
    assert intel["decrypted_account"] == intel["rangoli_account"]
    from onboarding.demo_data import SCENARIOS
    f = SCENARIOS["shared_bank_rangoli"]["form"]
    page = intel["rangoli_page"].replace(f["gstin"], "")   # the GSTIN embeds the PAN and is public business data
    assert f["pan"] not in page and f["bank_account"] not in page


def test_registry_sources_are_labelled(intel):
    page = intel["rangoli_page"]
    assert "Registry" in page and "SIMULATED" not in page


def test_pages_and_navigation(intel):
    assert "Rangoli Print House" in intel["dir"] and "Deccan Office Supplies" in intel["dir"]
    assert "Waiting for you" in intel["dash"] and "Open vendor profile" in intel["run_page"]
    assert intel["missing"] == 404 and intel["accounts"] == 200
    assert "What to do next" in intel["rangoli_page"] and "Who:" in intel["rangoli_page"]
    assert "On record (vendor master)" in intel["deccan_page"] and "Rangoli Print House" in intel["deccan_page"]   # seen from the other side too


def test_requesters_see_only_their_vendors_and_less(intel):
    assert intel["priya_rangoli"] == 403
    assert "Rangoli" not in intel["priya_dir"]
    rahul = intel["rahul_rangoli"]
    assert "Requester view" in rahul and "Relationships" not in rahul and "Evidence register" not in rahul


def test_human_decisions_close_flags_and_activate(intel):
    assert intel["activate"] == 303 and intel["confirm"] == 303
    assert intel["nilgiri_after"] == "active"
    assert intel["kaveri_flags_after"] and all(st == "resolved" and "Rejection confirmed" in res for st, res in intel["kaveri_flags_after"])
    assert intel["decision_events"] == 2


def test_simulation_bank_a4_policy_and_simulated_sources(intel):
    page = intel["sim_policy"]
    assert "nothing real was changed" in page
    assert "Approved → Pending: internal review" in page and "R-POL-BANK-A4" in page
    assert "waits for internal review" in page


def test_simulation_explains_what_still_decides(intel):
    page = intel["sim_clear"]                       # clearing the penny-drop doesn't clear the shared account
    assert "No change: still Pending: internal review" in page and "R-RISK-02" in page
    assert "Rejected →" in intel["sim_clear_conflict"]
    assert "did not fail in this check" in intel["sim_bad_rule"]
    assert "What would change the decision?" in intel["sim_panel"]


def test_simulation_never_touches_real_data(intel):
    assert intel["real_unchanged"] is True
    assert intel["sim_rows"] == 4                   # the only thing written: one simulation record each


def test_simulation_refused_when_replay_is_not_exact(intel):
    assert "Simulation is off for this check" in intel["sim_refused"]
    assert "Simulation is off for this check" in intel["sim_refused_panel"]
    assert intel["sim_requester"] == 403


def test_a_rejection_waits_for_a_person_to_confirm_it(intel):
    """Until someone confirms, the rejected check offers 'confirm' and 'send to review'; afterwards it says it was confirmed."""
    before, after = intel["kaveri_page_before"], intel["kaveri_page_after"]
    assert 'value="confirm_reject"' in before and 'value="override_reject"' in before
    assert "Rejection confirmed" not in before
    assert "Rejection confirmed" in after and 'value="confirm_reject"' not in after

