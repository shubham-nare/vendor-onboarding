# Deploying to Render (free plan) with Neon Postgres

Settings are read by `onboarding/config.py` (`Settings`) from environment variables or a local `.env`
(never commit `.env`). Names are case-insensitive: `gemini_api_key` is `GEMINI_API_KEY`.

## 1. Every setting the app reads

"Prod" = a real deployment; "Demo" = the submission/interview site (`DEMO_TOOLS=true`, fictional data on a remote DB);
"Local" = a laptop with SQLite. render.yaml column: what the Blueprint declares today.

| Variable | Required? | Default | Purpose | render.yaml |
|---|---|---|---|---|
| `DATABASE_URL` | Prod and Demo: yes. Local: no | `sqlite+aiosqlite:///./local.db` | Neon connection string (pooled or direct) | `sync: false` (you paste it) |
| `DB_DIRECT` | optional | `true` | Use Neon's direct endpoint even if the `-pooler` URL is pasted (fewer round trips) | not set |
| `SESSION_SECRET` | **Prod and Demo on a remote DB: yes** (16+ chars). Local demo: optional | blank | Signs login and person-switcher cookies. Without it the app refuses to start on a remote DB or with `DEMO_TOOLS` off | `generateValue: true` (Blueprint sync only) |
| `ADMIN_PASSCODE` | Needed to use the in-app reset | blank (reset off) | Passcode for "Reset demo data"; must be 12+ chars, not `change-me`. 5 wrong tries lock it for an hour | `generateValue: true` (Blueprint sync only) |
| `DEMO_TOOLS` | Demo: `true`. Prod: leave false | `false` | Person switcher, scenario launcher (`/demo/{key}`), demo logins, sample files, `/check`, stage pacing | not set (set in the dashboard) |
| `DEMO_PASSWORD` | Demo: yes | blank (no demo logins) | Password of the seeded demo logins (4 employees and the demo vendor). Only works with `DEMO_TOOLS=true` | `sync: false` |
| `GEMINI_API_KEY` | Needed for live reading of new files | blank | Reads documents. Saved readings of the fixture files work without it | `sync: false` |
| `GEMINI_MODEL` | optional | `gemini-3.5-flash-lite` | Primary reading model | value set |
| `GEMINI_FALLBACK_MODEL` | optional | `gemini-3.1-flash-lite` | Used if the primary fails | value set |
| `READ_CACHE_FIRST` | optional | `true` | Use the saved reading of the same file (SHA-256) before asking the AI: same file, same decision | not set |
| `READ_DEADLINE_SECONDS` | optional | `60` | One reading budget per run; after it, the saved reading or a "please re-upload" | not set |
| `REQUEUE_WINDOW_MINUTES` | optional | `60` | At startup, runs cut off by a restart less than this long ago are re-run once | not set |
| `STAGE_PACE_SECONDS` | Demo: set `0.4` | `0.4` | Seconds between stage updates so the live run view visibly animates | not set |
| `FEATURE_PAYABLES`, `FEATURE_INTEL`, `FEATURE_RELIABILITY`, `FEATURE_FOLLOWUPS`, `FEATURE_UNSOLICITED` | optional | all `false` | Out-of-scope features, hidden unless turned on (routes, navigation, background work) | not set |
| `INTEL_SECRET` | optional | blank = `SESSION_SECRET` | Keys for Vendor Intelligence identifier HMACs. Changes when `SESSION_SECRET` first exists (see reset below) | not set |
| `TRUSTED_PROXY_HOPS` | optional | `1` | Proxies that append to `X-Forwarded-For` (Render: 1); decides the visitor address used by rate limits | not set |
| `RATE_LIMITS` | optional | `true` | Per-IP and per-account limits. `false` is a last-resort fallback | not set |
| `MAX_REQUEST_BYTES` | optional | 25 MB | Whole request body cap (each file is also capped at 10 MB) | not set |
| `CAPTCHA`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | optional | `true`, blank, blank | Bot check on public forms; demo mode uses Cloudflare's test keys | not set |
| `NEWS_SEARCH` | optional | `true` | Free news search for vendor reliability (only matters with `FEATURE_RELIABILITY`) | not set |
| `OPENSANCTIONS_API_KEY`, `GOOGLE_MAPS_API_KEY` | optional | blank | Keyed reliability sources; "not connected" while blank | not set |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | optional | blank | "Continue with Google" for vendors; hidden while blank | not set |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `MAIL_REDIRECT_TO` | optional | blank, `587`, blank, blank, blank, blank | Email to vendors; off until `SMTP_HOST` and `MAIL_FROM` are set (messages stay in the Outbox). `MAIL_REDIRECT_TO` sends all mail to one inbox | not set |
| `PYTHON_VERSION` | Render only | n/a | Python runtime | `3.13.9` |

Notes:
- `DEMO_TOOLS=true` against a remote DB logs one startup warning ("fine for the fictional-data demo").
- The plan once named `DATA_KEY` / `INDEX_KEY`; the code has no such settings (encryption at rest is parked on branch `parked/s9-encryption`). The only key setting is `INTEL_SECRET`.
- `/healthz` never touches the database. `/readyz` touches it once and returns 200 or 503.
- `/docs`, `/redoc`, `/openapi.json` are off in every mode.

## 2. Submission / interview settings

> **Set `SESSION_SECRET`, `DEMO_TOOLS`, `DEMO_PASSWORD` and `ADMIN_PASSCODE` on Render BEFORE merging to main.**
> `generateValue` in render.yaml applies only on a Blueprint sync, so a normal auto-deploy will not create them.
> Without `SESSION_SECRET` the app refuses to start on a remote database (`Refusing to start: set SESSION_SECRET ...`).

Render dashboard -> the service -> Environment:

| Variable | Value |
|---|---|
| `DEMO_TOOLS` | `true` |
| `DEMO_PASSWORD` | `<a password you will type on camera>` |
| `SESSION_SECRET` | `<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">` |
| `ADMIN_PASSCODE` | `<12+ characters, e.g. generate the same way>` |
| `GEMINI_API_KEY` | `<your Gemini key>` |
| `DATABASE_URL` | `<Neon connection string>` |
| `STAGE_PACE_SECONDS` | `0.4` |
| `FEATURE_PAYABLES`, `FEATURE_INTEL`, `FEATURE_RELIABILITY`, `FEATURE_FOLLOWUPS`, `FEATURE_UNSOLICITED` | leave unset (off) |

Everything else keeps its default. `TRUSTED_PROXY_HOPS` stays `1`.

## 3. Reset to clean demo data

System page -> "Reset demo data" -> enter `ADMIN_PASSCODE`. It needs a signed-in Procurement or Finance person
(requesters are refused), refuses while a run is in progress, and is off while the passcode is blank, short or `change-me`.

What it does (`seeding.seed(reset=True)`): drops **every table** and recreates it, so all runs, applications,
documents, messages, invites, vendor accounts and activated vendor IDs are gone. It then reloads: the four employees,
the demo logins (from `DEMO_PASSWORD`), the demo vendor account, one seeded invite per scenario (a fresh `/demo/{key}`
invite is cloned from these), the vendor master, blocklist, simulated registries and sample purchase orders.
What it keeps: anything outside the database: saved readings (`fixtures/read_cache`), fixture documents, the Neon
database itself. The in-app reset has no host confirmation: the passcode is the confirmation.

Do it **right after the first deploy** (the intel keys change once `SESSION_SECRET` exists; R-RISK-02 reads the vendor
master directly and is unaffected), and again before every recording take.

## 4. Cold start

Render free sleeps after 15 minutes idle, and Neon suspends too. Document-only options:
- Switch the service to **Starter** for the review window; or
- point an external pinger (for example UptimeRobot) at `/readyz` every 10 minutes. `/readyz` touches the DB once, so it wakes Neon as well (`/healthz` would not).

## 5. Warm-up before recording
1. Open the site early (and `/readyz`) until it answers 200.
2. Log in once per persona (Priya, Arjun, Kavita; the demo vendor in a private window): the first scrypt check is slow.
3. Run one cached scenario through the launcher, then reset.
4. Open `/system` and check the Gemini key/status.

## 6. Rate limits on recording day
- After the first request on a fresh deploy, find the one-time WARNING in the Render logs: `client address: X-Forwarded-For has N entries; TRUSTED_PROXY_HOPS=1 ...`. `N=1` with hops 1 confirms the setting. Higher N means more proxies sit in front: raise `TRUSTED_PROXY_HOPS` to match, or all visitors may share one address.
- Launcher submits (`/demo/{key}` invites) are exempt from the submit limit.
- `RATE_LIMITS=false` is a last-resort fallback (redeploy needed). Wrong reset passcodes stay limited either way.

## 7. Script safety
`python -m onboarding.seeding --reset` from the command line refuses a remote database unless you pass `--production`
and then type the host back exactly. Tests abort if the database URL is not local. Never point either at the demo
Neon database by accident.

## 5. Custom domain (vendors.parakh.tech)

The app builds every link from the request's host, so a custom domain needs no code change.
1. Get the domain `parakh.tech`, for example from get.tech (free for a year with the GitHub Student Developer Pack) or any registrar.
2. Render → the service → **Settings → Custom Domains → Add** `vendors.parakh.tech`.
3. At the domain's DNS: a **CNAME** record, name `vendors`, value `vendor-onboarding-c0dm.onrender.com`. Render verifies it and issues the HTTPS certificate itself, usually within minutes (DNS can take up to an hour).
4. If "Continue with Google" is configured: add `https://vendors.parakh.tech/vendor/google/callback` to the OAuth client's authorised redirect URIs.
5. The `onrender.com` address keeps working. The keep-alive pinger can stay on it, because it is the same service.
