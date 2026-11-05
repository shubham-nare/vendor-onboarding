"""decision.decide(): the fixed precedence (scope -> reject -> review/errors -> vendor -> approved), the risk tier and
the approval invariant, on hand-built rule results. Pure: no database, no documents, no AI."""

import pytest

from onboarding import decision as D
from onboarding.rules import ERROR, FAIL, PASS, SKIPPED, WARN, Context, R


def r(rule_id, result=PASS, outcome="", fraud=False, title=""):
    return R(rule_id, "test", result, title or f"{rule_id} {result}", outcome, vendor_text=f"fix {rule_id}" if outcome == "VENDOR" else f"text {rule_id}",
             fraud=fraud)


ALL_REQUIRED_PASS = [r(rid) for rid in sorted(D.REQUIRED)]


def ctx(**kw):
    return Context(form={"legal_name": "Test Traders Private Limited", "contact_name": "Asha"}, docs={}, **kw)


CASES = [
    # id, extra rule results (on top of every required rule passing), expected status, expected reason codes
    ("scope fail wins over everything", [r("R-SCOPE-01", FAIL, "REVIEW"), r("R-XD-03", FAIL, "REJECT"), r("R-COMP-03", FAIL, "VENDOR")],
     D.PENDING_REVIEW, ["R-SCOPE-01"]),
    ("reject beats review and vendor", [r("R-XD-03", FAIL, "REJECT"), r("R-RISK-03", FAIL, "REVIEW"), r("R-COMP-03", FAIL, "VENDOR")],
     D.REJECTED, ["R-XD-03"]),
    ("review beats vendor", [r("R-RISK-03", FAIL, "REVIEW"), r("R-COMP-03", FAIL, "VENDOR")], D.PENDING_REVIEW, ["R-RISK-03"]),
    ("an error beats vendor", [r("R-SRC-PAN", ERROR), r("R-COMP-03", FAIL, "VENDOR")], D.PENDING_REVIEW, ["R-SRC-PAN"]),
    ("review and errors are listed together", [r("R-RISK-03", FAIL, "REVIEW"), r("R-SRC-PAN", ERROR)], D.PENDING_REVIEW, ["R-RISK-03", "R-SRC-PAN"]),
    ("vendor only", [r("R-COMP-03", FAIL, "VENDOR"), r("R-COMP-04", FAIL, "VENDOR")], D.PENDING_VENDOR, ["R-COMP-03", "R-COMP-04"]),
    ("all pass", [], D.APPROVED, []),
    ("a warning does not change the status", [r("R-ADDR-01", WARN)], D.APPROVED, []),
    ("a skipped optional rule does not block approval", [r("R-MSME-01", SKIPPED)], D.APPROVED, []),
]


@pytest.mark.parametrize("extra,status,codes", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_precedence(extra, status, codes):
    d = D.decide(ALL_REQUIRED_PASS + extra, ctx(), ref="VOB-0001")
    assert d.status == status
    assert d.reason_codes == codes
    assert [c["rule"] for c in d.cards] == codes


def test_vendor_message_state_follows_the_status():
    """Rejections and approvals wait for a person; vendor fixes and reviews are sent at once."""
    states = {}
    for extra, want in (([r("R-XD-03", FAIL, "REJECT")], D.REJECTED), ([r("R-RISK-03", FAIL, "REVIEW")], D.PENDING_REVIEW),
                        ([r("R-COMP-03", FAIL, "VENDOR")], D.PENDING_VENDOR), ([], D.APPROVED)):
        d = D.decide(ALL_REQUIRED_PASS + extra, ctx(), ref="VOB-0001")
        assert d.status == want
        states[want] = d.vendor_state
    assert states == {D.REJECTED: "held", D.PENDING_REVIEW: "sent", D.PENDING_VENDOR: "sent", D.APPROVED: "held"}


def test_vendor_message_lists_every_vendor_fix_once():
    d = D.decide(ALL_REQUIRED_PASS + [r("R-COMP-03", FAIL, "VENDOR"), r("R-COMP-04", FAIL, "VENDOR")], ctx(), ref="VOB-0001")
    assert "2 things" in d.vendor_body and "fix R-COMP-03" in d.vendor_body and "fix R-COMP-04" in d.vendor_body


def test_risk_tier():
    assert D.decide(ALL_REQUIRED_PASS, ctx(), "X").risk_tier == "low"
    assert D.decide(ALL_REQUIRED_PASS + [r("R-ADDR-01", WARN)], ctx(), "X").risk_tier == "medium"
    assert D.decide(ALL_REQUIRED_PASS, ctx(invite={"high_spend": True}), "X").risk_tier == "high"
    fraud = D.decide(ALL_REQUIRED_PASS + [r("R-SRC-BANK", FAIL, "REVIEW", fraud=True)], ctx(), "X")
    assert fraud.fraud and fraud.risk_tier == "high" and fraud.status == D.PENDING_REVIEW
    # a fraud flag on a rule that did not fail is not a fraud signal
    assert not D.decide(ALL_REQUIRED_PASS + [r("R-SRC-BANK", PASS, fraud=True)], ctx(), "X").fraud


def test_a_required_rule_that_does_not_apply_is_not_needed():
    """REQUIRED rules count only if present: a rule that was never evaluated does not block approval."""
    rules = [x for x in ALL_REQUIRED_PASS if x.rule_id != "R-ID-06"]
    assert D.decide(rules, ctx(), "X").status == D.APPROVED


# --- the approval invariant ---------------------------------------------------------------------------
# CURRENT BEHAVIOUR, pinned on purpose: decision.py checks "every applicable required rule passed" with a bare
# `assert`, so a required rule that did not pass but recorded no FAIL with a status-changing outcome crashes
# decide() with AssertionError (the run is then marked failed by the runner). PHASE 3 WILL CHANGE THIS: decide()
# should return PENDING_REVIEW with an internal-error card instead of raising. When that lands, replace the
# pytest.raises below with assertions on that status and card. What must never change: such a run is NOT approved.
INVARIANT_CASES = [
    ("required rule skipped", r("R-XD-02", SKIPPED)),
    ("required rule failed with a non-status outcome", r("R-XD-02", FAIL, "WARN")),
    ("required rule failed with no outcome", r("R-BANK-01", FAIL, "")),
]


@pytest.mark.parametrize("bad", [c[1] for c in INVARIANT_CASES], ids=[c[0] for c in INVARIANT_CASES])
def test_approval_invariant_never_approves(bad):
    rules = [x for x in ALL_REQUIRED_PASS if x.rule_id != bad.rule_id] + [bad]
    with pytest.raises(AssertionError, match="approval invariant broken"):
        D.decide(rules, ctx(), "X")
