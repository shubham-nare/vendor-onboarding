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

## Phase 3: reliability (merge b8bcf80) and lean security (merge e32113d)
**Reliability (agent E):**
- **Saved readings first:** a document already read (same SHA-256) reuses its saved reading.
- **Reading deadline:** one per run, 60 s after review (was 20 s). When it runs out, the saved reading is used, or the document is marked "please upload a clearer copy" and goes to review, never to rejection.
- **Reading errors:** every reading error is caught; there are no retries on a missing key, a 401/403 or a 400; there is one lazy Gemini client and a pacing lock.
- **CPU work:** image, PDF and authenticity work runs on worker threads.
- **Failed and interrupted runs:** they move the application to PENDING_REVIEW. On restart, a run cut off less than 1 h ago is re-queued once, as a new run linked by `parent_run_id`; older ones are parked for review. Procurement and Finance get "Re-run checks"; the vendor can resubmit after a failed or interrupted run.
- **Steps after the decision:** intelligence, mail and reliability are isolated. Their failures are logged and never flip a finished run. A run is claimed `queued → running` in one UPDATE.
- **Approval invariant:** it no longer asserts. The application goes to PENDING_REVIEW with an `INTERNAL-INVARIANT` card.
- **Refs and vendor IDs:** refs come from the primary key, and vendor IDs skip taken numbers.
- **Concurrent submits:** row locks on the invite and application, plus a one-time submit token. Four concurrent submits give one run.

**Security (agent F, lean):**
- **S1, demo parameter:** honoured only with `DEMO_TOOLS=true` and a known scenario, and never instead of the vendor login.
- **S2, visitor address:** the right-most `X-Forwarded-For` hop (`TRUSTED_PROXY_HOPS`).
- **S3, secrets:** `SESSION_SECRET` is required unless the app runs in demo mode on a local database.
- **S4, demo logins:** created only from `DEMO_PASSWORD`.
- **S5, API docs:** `/docs`, `/redoc` and `/openapi.json` are off in every mode.
- **S6, person switcher:** a signed actor cookie bound to the login.
- **S8, upload size:** 25 MB per request and 10 MB per file (chunked reads).
- **Reset passcode:** no default (at least 12 characters), and 5 wrong tries lock it for an hour.
- **Startup:** the steps are independent, so an empty database no longer crashes it.
- **Seeding from the command line:** `seed --reset` refuses a remote database without `--production` and the host typed back.
- **Remote-database warning:** one warning when demo tools are on against a remote database.
- **Tests:** the IFSC and PIN lookups are stubbed, and a missing `fixtures/read_cache` fails instead of skipping.

**Follow-ups after review (this commit):**
- **Scenario launcher:** its invites are marked `scenario_key="demo:<key>"`. A guest may open and submit such an invite only for its own scenario, in demo mode. Real invites with `?demo=` still need the vendor login. `/demo/{key}` already required a staff login (it is in `COMPANY_AREAS`); a test now pins that.
- **Submit limit:** launcher submits are exempt from `SUBMIT_PER_IP`, so rehearsals and recordings don't hit it.
- **Audit:** `run_action` writes `auth.audit_comment(request, comment)`, so an action taken through the person switcher records both people. The length check stays on the raw comment, and the vendor message uses the raw comment.
- **Submit token:** the form's `submit_token` is generated on the server per page load, and `/apply` and `/bill` pass it through. A double submit on `/bill` doesn't add a second Bill row.
- **Visitor-address log:** one WARNING per process with the X-Forwarded-For entry count and the hop used (no addresses), so `TRUSTED_PROXY_HOPS` can be checked after a deploy.
- **Clean-ups:** `main._sweep` calls `recover_interrupted` directly, and two formatting nits are fixed.
- **Parked, not merged:** PAN/account encryption with a blind index, on branch `parked/s9-encryption`.

## Lean phase (merges b2535f9 docs, 99c9499 code) and demo fixes
- **Docs:** `docs/DEMO_SCRIPT.md` (5-minute recording plan), `docs/DEPLOY.md` (every env var, the submission settings, cold start), `docs/ARCHITECTURE.md` (Mermaid flow, invariants).
- **Code:**
  - The `FEATURE_PAYABLES/INTEL/RELIABILITY/FOLLOWUPS/UNSOLICITED` flags (all off by default) hide the out-of-scope features. Their routes return 404, they leave the navigation, and their background work stops. Nothing is deleted.
  - `STAGE_PACE_SECONDS`, default 0.4.
  - `/readyz` (`select 1`).
  - `/history` redirects to `/applications`.
  - The "waiting for you" toast no longer covers run pages or phone screens.
  - Why cards lead with the problem.
  - The `/system` database label comes from the URL.
- **Golden change (own commit ce903c4):** with `FEATURE_RELIABILITY` off there is no reliability gate, so Kavita's Rangoli approval no longer needs `reliability_ack`. Every other Rangoli assertion stays: fraud, high risk, the neutral vendor message, Arjun's 403 ("needs the Finance controller") and Kavita's approval. The gate itself stays covered with the flag on (`test_web.py::test_a_serious_reliability_finding_must_be_read_before_approving`).
- **Demo fixes (after review):**
  - A second demo vendor login is seeded in demo mode, `anitha@nilgiripack.example.com` (Nilgiri's contact person), for beat 1 of the video. It is not the invite's `accounts@` address, which the golden tests register.
  - A launcher invite also accepts its scenario's own resubmission (`wrongdoc_tejas_resubmit` on a `demo:wrongdoc_tejas` invite).
  - After submitting, a vendor-only browser always lands on `/thanks`. Only someone who is also logged in as staff (the scenario launcher) goes to the live view. `test_portal` now finds the run from the ref and asserts the `/thanks` landing.
  - **Run page replay:** the stored stage events play back in order, about 0.5 s per stage. It starts automatically when the page is opened mid-run or within 2 minutes of the run finishing, labelled with the real run duration. A "▶ Replay the checks" button is always available. The result appears only when the replay reaches the decision. It plays once per tab session and writes nothing.
