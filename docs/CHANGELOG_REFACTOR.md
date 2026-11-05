# Refactor changelog (`refactor/ps2-lean`)

This records what changed, why, and any behaviour a user would notice. The baseline is the `pre-refactor` tag (`3a22559`).

## Production guard (f524177)
- **What:** the tests run on a throwaway SQLite file. It is seeded once and restored after each test module.
- **Why:** test modules used to pop `DATABASE_URL` when they finished, so later tests fell back to `.env`, which held production's Neon URL.
- **Safeguards:**
  - `pytest_configure` aborts the session if the database URL is not local;
  - `onboarding.db.engine()` refuses any non-local URL while pytest is loaded.
- **User-visible:** none.

## Phase 2: safety net (merge 2dce240)
- **Cached readings:** the end-to-end tests use the committed `fixtures/read_cache/`. A fresh clone no longer skips 92 tests; the only skips left are tests that need Shubham's private files.
- **`tests/test_decide.py`:** a table-driven test of the `decide()` precedence, held versus sent messages, and the risk tier. The approval invariant is pinned as it behaves today (it raises `AssertionError`); phase 3 changes it.
- **`tests/test_scenarios.py`:** the golden scenarios through the real invite path, covering status, risk tier, reason codes, stage events, activation, the resubmission diff, a rejection held until a person confirms, and Finance-only approval.

  | Scenario | Status | Risk | Reason codes |
  |---|---|---|---|
  | happy_nilgiri | APPROVED | low | — |
  | wrongdoc_tejas | PENDING_VENDOR | low | R-COMP-02, R-DOC-01 |
  | wrongdoc_tejas_resubmit | APPROVED | medium | — (R-MSME-02 is a WARN) |
  | borrowed_gstin_kaveri | REJECTED | low | R-XD-03 |
  | shared_bank_rangoli | PENDING_REVIEW, fraud | high | R-RISK-02, R-SRC-BANK |
  | proprietor_shinde | APPROVED | medium | — |

- **Suite:** 281 passed, 0 skipped on this machine. 276 passed and 5 skipped (private files) on a fresh clone.
- **Noticed and not changed yet:** Kaveri is rejected at risk tier "low", because six FAILs don't raise the tier. Finance has to acknowledge the reliability warning on Rangoli; that goes away with C3.
