# Refactor plan: PS-2 lean

**Branch:** `refactor/ps2-lean`, cut from `main` at `3a22559`. That commit is tagged `pre-refactor`.
**Inputs:**
- the four phase-1 discovery reports (A: re-checking `TEST_REPORT.md`; B: module map and cuts; C: UI inventory; D: baseline benchmark), summarised here;
- `TEST_REPORT.md` and `COMPETITOR_RESEARCH.md`.

**Status:** waiting for approval of the cut list (§3) and the UI decision (§4). Nothing has been deleted yet.

## 1. What the discovery found

### Re-checking `TEST_REPORT.md` against today's code (agent A)
Every P0 and S item that could be checked locally is **still present** at `3a22559`. Most were reproduced on a throwaway SQLite database.

| Item | Verdict | Where |
|---|---|---|
| P0-1 | Reproduced. A failed or interrupted run leaves the application `IN_PROGRESS`: the vendor is bounced, reviewers get no actions, and `run.html:71` falsely says "you can resubmit". | `pipeline.py:291-318`, `web.py:579,797,1079` |
| P0-2 | Reproduced. With no Gemini key, one fixture document takes 17 s before it falls back to the saved reading. | `runner.py:31`, `ai/read.py:152,184-205` |
| P0-3 | Reproduced. An injected `httpx.ConnectError` fails the whole run. | `ai/read.py:200`, `pipeline.py:141` |
| P0-4 | Present: a bare `assert` holds the approval invariant. | `decision.py:69` |
| P0-5 | Not checked. It needs production. | — |
| S1 | Reproduced. Anonymous runs via `demo=x` with `DEMO_TOOLS=false`, and the full PAN and account number are shown on a pre-filled page. | `web.py:571,591,604,790,829,849` |
| S2 | Reproduced. A spoofed `X-Forwarded-For` resets the limits, including the Gemini-spend limit. | `security.py:12-18` |
| S3 | Reproduced. The Finance controller can log in with `demo_pass` while `DEMO_TOOLS=false`. | `seeding.py:26,169-180`, `main.py:31` |
| S4 | Present. Keys are derived from `DATABASE_URL`. | `auth.py:64-67`, `intel/crypto.py:28-30` |
| S5 | Reproduced: `/docs`, `/redoc` and `/openapi.json` are open, with 95 paths. | `main.py:67` |
| S6 | Present, demo mode only: the actor falls back to the maker. | `web.py:122-139` |
| S7 | Reproduced. 4 concurrent submits gave 1 run and 3 × 500 (`IntegrityError` on `ref`). | `pipeline.py:69-70`, `web.py:1116` |
| S8 | Present. | `web.py:655,766,1257`, `portal.py:442,795` |
| S9 | Present. | `models.py:88,245,247` |
| UX items | All present. The reminder toast, a Why card that leads with a pass-like line, `/history` returning 404, the "Neon Postgres" label, and the visibilitychange refresh without a debounce. The sidebar is now 14 items. | |
| Tests | Present. A fresh clone gets **141 passed / 97 skipped**: 92 skip for "no cached AI readings" (`CACHE = ROOT/".read_cache"` in 4 files). Pointed at `fixtures/read_cache`, all 92 pass. `test_api.py:92` depends on `ADMIN_PASSCODE` in `.env`. | |

**New, and more serious than the report:**
1. **The tests can reach the production database.** Module teardowns call `os.environ.pop("DATABASE_URL")` and clear the settings cache. Later tests then read `.env`, which holds the Neon URL. Today an in-memory employee cache hides this, but `pytest tests/test_security.py` run on its own would query production. **This is the first fix in phase 2.**
2. Locally, with no `SESSION_SECRET` and the default SQLite URL, the cookie-signing key is effectively public, so session cookies can be forged.
3. The reset passcode has no rate limit.
4. **Startup crashes on an empty database** in demo mode: `KeyError` in `seed_purchase_orders`, `main.py:42`. The crash is swallowed, so `sweep_interrupted` and the backfill never run (found by agent D).

### Baseline (agent D; local SQLite, 12 runs)
| | Today |
|---|---|
| Scenario run from saved readings | 2.4–3.8 s. All 6 scenarios reach the right status. |
| Scenario run as the app runs it today, with no Gemini key | 23.5–32.7 s, almost all of it reading retries |
| `/api/v1/session`, `/console/home`, `/console/pending` | 18 SQL each, 80–115 ms. `_dashboard_ctx` is rebuilt on every call. |
| `/api/v1/applications` | 23 SQL, 225 ms |
| `/api/v1/system` | 620–660 ms: a live Razorpay call on every view |
| `/runs/{id}` | 12 SQL, 74 ms warm, 313 ms cold, 106 KB |
| Intel projection after each run | 98–303 SQL. That is more than the pipeline itself (76–87). |
| Live lookups on every run | India Post PIN 1.6 s and IFSC 0.6–1.0 s, run concurrently |
| Startup on an empty database | 2–3.4 s, 194 SQL, 43 tables. It crashes (see above). |

## 2. Module map (agent B)
`onboarding/` is **12,052 lines of Python**, 2,633 lines of templates and 1,418 lines of SPA JavaScript. Tests are 2,853 lines and scripts 642. There are **43 tables**.

| Area | Files (lines) | Verdict |
|---|---|---|
| Core pipeline | `pipeline` 318, `runner` 40, `rules` 801 (≈160 of it bill rules), `decision` 169, `ai/read` 256, `authenticity/*` 438, `validators` 308, `matching` 117, `names` 191, `sources` 117, `pincode` 123, `countries` 89 | **Keep** |
| Web: vendor, console, run view | `web` 1587 (of which ≈240 Intel, ≈400 AP, prefill and pre-qualified), `portal` 813 (of which ≈450 AP, Google, contact, tour), `access` 62, `auth` 145, `security` 124, `db` 130, `config`, `main` 219, `mailer` 147, `seeding` 212, `demo_data` 523 | **Keep, trim and split** |
| Accounts payable (PS-1) | `ap/*` 854, `bills` 334, `api/payables` 172, bill templates 414, 4 JS files 229 | **Cut** |
| Vendor Intelligence | `intel/*` 1,328, `workspace` 104 (but see §5), `api/vendors` + `api/vendor_profile` 257, 3 JS files 217 | **Cut** |
| Reliability | `reliability` 250 | **Cut** |
| Follow-ups | `followups` 192 | **Cut** (the Outbox stays) |
| Extras | `captcha` 56, `google_auth` 81, `i18n` 230, tour, contact, `/check` | **Cut** |
| Unsolicited and pre-qualified | in `web`, `api/registrations`, `43-invites.js` | **Cut** |
| Prefill and address | `prefill` 155, `address` 149 | **Behind flags, off** (`address.compare` = R-ADDR-01 is kept on; see §5) |
| The SPA | `frontend/*` 1,418, `api/*` ≈955, `appshell`, `console.html`, `build_frontend.py` | **Replace with Jinja** (§4) |

## 3. The cut list (approval needed)

| # | Cut | Removes (approx. lines) | Why it helps the PS-2 demo |
|---|---|---|---|
| C1 | **Accounts payable**: `ap/*`, `bills.py`, the bill rules in `rules.py`, `BILL_HIGH_RISK`; routes `/bill`, `/bills*`, `/invoices`, `/purchase-orders*`, `/vendor/bills*`, `/change-requests*`, `/audit`; `seed_purchase_orders`, `load_payables_sample`; bill scenarios `bill_kesari` and `bill_brindavan`; 10 tables | ≈2,900 code + ≈450 tests | It is PS-1. It adds 10 tables, 6 menu items and most of the console's query cost. |
| C2 | **Vendor Intelligence**: `intel/*`, Vendor 360, `/runs/{id}/simulate` (no caller), `/relationships`, the startup backfill; 11 tables | ≈2,000 + 298 tests | No grader asks for it. It does 98–303 SQL per run, and an Intel line that ran after the decision could turn a finished run into `failed`. |
| C3 | **Reliability panel** and the approval gate that depends on it; 1 table | ≈330 | It shows graders "Not connected" and "couldn't reach it", and labels a name mismatch as "GST isn't active". |
| C4 | **Follow-ups** loop and its startup task; 1 table. The **Outbox stays** and lists every vendor message. | ≈260 | A background loop on a free instance; not asked for. |
| C5 | **captcha, Google login, i18n** (English only, `t` becomes identity then is removed), **/tour, /contact** (and `contact_messages`). **/check** stays only in demo mode, or goes. | ≈700 | Fewer moving parts and external calls during a live demo. |
| C6 | **Unsolicited registration and pre-qualified suppliers.** Onboarding becomes **invite-only**, stated in the UI and in `/assumptions`. R-INV-01's "no invite" branch stays as a safeguard. `unsolicited_nilgiri` leaves the scenario list. | ≈350 | Invite-only is the anti-fraud design. It also removes the way Nilgiri landed in "internal review" on production. |
| C7 | **Upload-first prefill** (`/apply/read`, R-PF-01) behind `FEATURE_PREFILL=false`. **Google address validation** (R-ADDR-02) is already off without a key; it moves under `FEATURE_ADDRESS_GOOGLE`. | flags | Less to break live. R-ADDR-01 (the address matches the GST certificate) stays on. |
| C8 | **The SPA** (`frontend/`, `api/*`, `appshell`, `console.html`, `app.js`, `build_frontend.py`, `test_api.py`). It is replaced by Jinja templates restored from git (§4). One small read-only JSON endpoint per run stays (`GET /api/runs/{id}`, step 9 NFR). | ≈2,500 | One UI and one navigation. The graded screens are already Jinja. |

**After the cuts:** about **5,900 lines of Python and 2,100 lines of templates**, no SPA, and about **1,500 lines of tests** before the new golden tests. **19 tables** remain.

To reach about 15 tables I propose merging:
- `email_deliveries` into `messages`;
- `staff_logins` into `employees`;
- `vendor_links` into `applications` (the owning vendor account id).

That leaves 16. Keeping `revoked_sessions` costs one table and keeps real log-out; I'd keep it. **Please confirm.**

Also cut: the cursor-following clouds and the spinnable "stars" on Home. They are distractions in a graded demo. The Home page becomes the dashboard table.

## 4. One UI: Jinja (recommended)

| Factor | All Jinja | All SPA |
|---|---|---|
| Graded screens (run view and SSE, apply, status) | Already Jinja and working | All rewritten |
| Run-page actions | Form routes exist | No API exists for them |
| Remaining SPA screens | 5 small ones: dashboard, invites, outbox, assumptions, system. They are restored from git (`dashboard.html` @ `1c980fe^`, `invites` @ `c5e0d32^`, `outbox` @ `442381c^`, `system` @ `dfeea33^`, `assumptions` @ `ab5cb7b^`); their data functions are still in `web.py`. | — |
| Effort | ≈1–1.5 days | ≈3–5 days, and it rewrites the graded flows just before a live demo |

**Decision:** Jinja plus a little plain JS in static files (SSE, small interactions). That means:
- navigation defined once in `base.html`, and one write path per action (form routes);
- inline scripts moved into `/static/js/*.js`, so the Jinja pages get a strict CSP;
- the Tailwind Play CDN replaced by a standalone Tailwind CLI build, with the minified CSS committed. Classes built at runtime in `run.html:91` must be safelisted;
- Sacramento switched to `display=swap`;
- the Leaflet/Nominatim map picker on the apply form goes with the prefill flag (default off).

The dashboard (`/console`) becomes one table of applications with:
- ref, vendor, requester, status, risk tier, fraud flag, runs, last run time and duration, who acts next;
- status and risk filters, counts per status, a CSV export.

## 5. Things that must move before they can be cut (agent B's "risky cuts")
1. `address.compare` (R-ADDR-01, used in every scenario) imports `prefill.split_address`. Move `split_address` into `address.py` first.
2. The bill section of `rules.py` holds `money`, `inr` and `_parse_any_date`, which `decision.py:9` imports together with `BILL_HIGH_RISK`. Move the helpers into a small `util/money.py` first.
3. `runner._run` and `run_action` run Intel and reliability imports **after** the commit. Remove them together, and make sure post-decision work can never flip a finished run (step 2.5).
4. The module-level imports at the bottom of `web.py` (`web.py:1349-1353`) and `models.py` (`models.py:328-330`) go in the same commit as the packages they import.
5. `_dashboard_ctx`, `_work_summary` and `_todo` query the AP, Intel and follow-up tables. Rewrite them as one "latest run per application" query plus a grouped count (step 6) in the same commit.
6. `workspace._apps` and `documents` feed the **kept** Applications view. Move them; don't delete them.
7. `unsolicited_nilgiri` comes out of `scripts/run_scenario.py` and `tests/test_pipeline.py` together.
8. **Production database:**
   - `seed(reset=True)` uses `drop_all`, which only knows the tables still in the code. The orphaned tables' foreign keys would make the drop of `applications` and `runs` fail on Postgres.
   - Fix: an idempotent `scripts/drop_orphans.py` that drops the cut tables with CASCADE, plus a reset that does the same.
   - **I won't run it on production without asking you.**

## 6. Target structure (after step 7)
```
onboarding/
  main.py            app, middleware, startup (cheap)
  config.py          settings + feature flags
  rules_config.py    thresholds + RULESET_VERSION        (step 9)
  domain/
    states.py        (status, action) -> status transition table
    policy.py        who may do what (from _allowed_actions / _decision_rights)
    rules/           one module per layer: invite, completeness, identifiers, consistency, sources, risk
    decision.py      decide(), grade A0-A4, messages
    names.py matching.py validators.py countries.py pincode.py
  services/
    pipeline.py runner.py actions.py (run_action state changes + vendor texts) queries.py (dashboard, counts)
  sources/           registries (simulated, realistic shapes) + live IFSC + PIN, behind an adapter
  ai/read.py  authenticity/
  web/
    vendor.py        apply, status, vendor auth/home
    console.py       dashboard, invites, runs, actions, outbox
    admin.py         system, demo reset, scenario launcher (demo mode)
    public.py        landing, login, assumptions
  security.py auth.py access.py db.py models.py mailer.py seeding.py demo_data.py
  templates/  static/ (css built by Tailwind CLI, js/*.js)
```

## 7. Order of work (each step is one commit; tests and golden scenarios green before the next)

| Phase | Work | Who |
|---|---|---|
| 2. Safety net | Pin a temporary SQLite database and `ADMIN_PASSCODE` in `conftest` for the whole session, and never pop to `.env` (**production guard**). Point the 4 test modules at `fixtures/read_cache`, so nothing skips for cache reasons. Add `tests/test_scenarios.py`: all section-3 scenarios through the HTTP invite path, asserting status, risk tier, reason codes and stage events. Add a table-driven `decide()` precedence and invariant test. Golden tests green on the **current** code. | 1 agent |
| 3. Fix | **E (reliability):** P0-1 to P0-4, cache-first reading with one deadline, `to_thread` for CPU work, post-decision isolation, the empty-database startup crash. **F (security):** S1–S9, CSP on Jinja, no default passcode, docs off, signed actor cookie, a rate limit on the reset passcode. | 2 agents, worktrees |
| 4. Cut | C1–C8 in the §5 order. Drop the orphaned tables (script only). Remove unused dependencies (`pymupdf` → dev). | 1 agent, alone |
| 5. Restructure | §6, including `domain/states.py` and splitting `rules.evaluate` by layer, with identical golden output. Ruff config. | 1 agent |
| 6. Build | **G:** Jinja UI and Tailwind build. **H:** queries and SSE notify; `/system` IFSC cache; indexes; cheap startup; `scripts/bench.py`, adapted from agent D's script. **I:** docs and CI. **J:** demo reset, seed, scenario launcher. | 4 agents |
| 7. Market patterns | Step 9 (second PR). | K, L, then M |
| 8. Review | Correctness, security, and a demo rehearsal at 375 px. | 3 read-only agents |

## 8. Questions for you
1. **Cut list C1–C8:** approve as written, or change any item? In particular:
   - C1 removes the invoice and bill flow entirely; the bank-change story returns as the PS-2 `bank_change_after_approval` scenario in step 9.
   - C5: should `/check` stay in demo mode, or go?
2. **Tables:** OK to merge down to 16 as proposed in §3?
3. **UI:** OK with Jinja (§4)? It throws away the recent SPA work, which was mostly for screens being cut.
4. **P0-1 recovery:**
   - On startup, re-queue interrupted runs. If the documents are still stored this is safe, and I'd do it.
   - Also add a reviewer "Re-run checks" action and let the vendor resubmit after a failed or interrupted run.
   - OK?
5. **S1:** drop the anonymous "guest" path entirely: `demo` is honoured only with `DEMO_TOOLS=true` **and** a known scenario key, and still needs a vendor login or an invite token. OK?
