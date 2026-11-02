"""Counterfactual decisions: "what would the decision be if ...?", using the unchanged rules and decision code on a
copy of a saved decision input. Nothing real is touched: the only row written is a simulation_runs record.

Refused when the saved input doesn't replay to the original decision exactly (snapshot.replay_ok is False, or the
replay done here differs), because a counterfactual on a decision we can't reproduce would be fiction.

Scenarios:
  policy_bank_a4   Hypothetical policy: the bank account must be confirmed at source (A4). Applied as an extra
                   policy gate after the rules. A SIMULATED SOURCE never confers A4, so in this build the gate
                   fails for every vendor until a real penny-drop provider is connected.
  confirm_warning  A reviewer agrees with a warning: that rule counts as a review failure.
  clear_flag       A reviewer resolves a failed check (e.g. after calling the bank): that rule counts as passed.
                   Shows which other rules would still decide.
"""

from __future__ import annotations

import copy

from onboarding import decision as D
from onboarding.intel.snapshot import load_context, outcome_of, replay, same_outcome
from onboarding.rules import FAIL, PASS, WARN, R

SCENARIOS = {
    "policy_bank_a4": "Policy: the bank account must be confirmed at source (A4)",
    "confirm_warning": "A reviewer confirms a warning",
    "clear_flag": "A reviewer clears a failed check",
}
STATUS = {"APPROVED": "Approved", "PENDING_VENDOR": "Pending: vendor to fix", "PENDING_REVIEW": "Pending: internal review", "REJECTED": "Rejected"}


class SimulationRefused(Exception):
    pass


def simulate(snap, scenario: str, rule_id: str = "", ref: str = "") -> dict:
    if scenario not in SCENARIOS:
        raise SimulationRefused("Unknown scenario.")
    if snap is None:
        raise SimulationRefused("This check has no saved decision input, so it can't be simulated.")
    if not snap.replay_ok:
        raise SimulationRefused("Simulation is off for this check: its saved input doesn't reproduce the original decision exactly"
                                + (f" ({snap.replay_note})" if snap.replay_note else "") + ".")
    ctx = load_context(snap)
    base_rules, base_dec = replay(ctx, ref)
    ok, why = same_outcome(snap.outcome, outcome_of(base_rules, base_dec))
    if not ok:
        raise SimulationRefused(f"Simulation is off for this check: replaying it today gives a different result ({why}).")

    rules = copy.deepcopy(base_rules)
    note = ""
    if scenario == "policy_bank_a4":
        bank = next((f for f in base_dec.facts if f.name == "Bank account"), None)
        level = bank.level if bank else "A0"
        src = ctx.sources.get("bank")
        simulated = bool(src and not src.live)
        if level == "A4":
            rules.append(R("R-POL-BANK-A4", "policy", PASS, "Hypothetical policy met: the bank account is confirmed at source (A4)"))
        else:
            rules.append(R("R-POL-BANK-A4", "policy", FAIL, f"Hypothetical policy: the bank account must be confirmed at source (A4); it is {level}", "REVIEW",
                           internal="Needs an independent confirmation of the account holder (penny-drop through a bank or KYB provider)."))
        if simulated:
            note = ("The penny-drop in this build is a SIMULATED SOURCE, which can never confer A4. Under this policy every vendor would wait "
                    "for internal review until a real penny-drop provider is connected.")
    else:
        target = next((r for r in rules if r.rule_id == rule_id), None)
        if target is None:
            raise SimulationRefused("Pick a rule from this check.")
        if scenario == "confirm_warning":
            if target.result != WARN:
                raise SimulationRefused(f"{rule_id} is not a warning in this check.")
            target.result, target.outcome = FAIL, "REVIEW"
            note = f"Treats {rule_id} as a confirmed concern that needs a decision by a person."
        else:
            if target.result != FAIL:
                raise SimulationRefused(f"{rule_id} did not fail in this check.")
            target.result = PASS
            note = f"Assumes a reviewer resolved {rule_id} (for example by checking with the issuer). The other rules are unchanged."
    try:
        dec = D.decide(rules, ctx, ref=ref)
    except AssertionError:
        # the approval safety check: a required rule didn't pass, so the decision can't be "approved"
        raise SimulationRefused("That change would break the approval safety check (a required rule didn't pass), so it can't be approved.")

    before, after = outcome_of(base_rules, base_dec), outcome_of(rules, dec)
    b_rules = {r.rule_id: (r.result, r.outcome) for r in base_rules}
    changed = []
    for r in rules:
        old = b_rules.get(r.rule_id)
        if old != (r.result, r.outcome):
            changed.append({"rule": r.rule_id, "title": r.title, "before": old[0] if old else "not in policy", "after": r.result})
    deciding = [{"rule": c["rule"], "title": c["title"]} for c in dec.cards]
    if dec.status == base_dec.status:
        explanation = f"No change: still {STATUS.get(dec.status, dec.status)}."
    else:
        explanation = f"{STATUS.get(base_dec.status, base_dec.status)} → {STATUS.get(dec.status, dec.status)}."
    explanation += (" Decided by " + ", ".join(d["rule"] for d in deciding) + ".") if deciding else " No rule stands in the way."
    return {"scenario": scenario, "label": SCENARIOS[scenario], "rule_id": rule_id,
            "before": {"status": before["status"], "risk_tier": before["risk_tier"]},
            "after": {"status": after["status"], "risk_tier": after["risk_tier"]},
            "changed": changed, "deciding": deciding, "explanation": explanation, "note": note,
            "facts_changed": [[a[0], b[1], a[1]] for a, b in zip(after["facts"], before["facts"]) if a != b]}
