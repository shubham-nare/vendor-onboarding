# Demo script: 5-minute recording plan

Goal: show the happy path running live, then edge cases, narrating what the process does and why. Based on the
video plan (kept outside the repo); this file is the in-repo, code-checked version.

**Cast** (all `@parakh.tech`, password = `DEMO_PASSWORD`): Priya Nair and Rahul Desai (requesters), Arjun Mehta
(Procurement, "maker"), Kavita Rao (Finance, "checker"). The vendor in beat 1 is Nilgiri's own contact person,
Anitha Raghavan: the seeded demo vendor login `anitha@nilgiripack.example.com` (password `DEMO_PASSWORD`; seeded only
in demo mode with `DEMO_PASSWORD` set). Don't use the Kesari demo vendor for beat 1: a Kesari login submitting
Nilgiri's registration looks wrong on camera. Fallback: register a new vendor account in the incognito window.

**Windows:** A = staff (log in per person, or switch with "Acting as"). B = incognito, the vendor.

**Golden outcomes** (what you should see):

| Scenario | Outcome | Rules to point at |
|---|---|---|
| happy_nilgiri | APPROVED, low risk, activation gives V-1001 | all required rules pass |
| wrongdoc_tejas | PENDING_VENDOR (R-COMP-02, R-DOC-01) | then `wrongdoc_tejas_resubmit`: APPROVED, medium, with a diff |
| borrowed_gstin_kaveri | REJECTED (R-XD-03) | vendor message held until a person confirms |
| shared_bank_rangoli | PENDING_REVIEW, fraud, high (R-RISK-02) | Finance only |
| proprietor_shinde | APPROVED, medium | backup beat |

## Revision (2026-11-06): real documents for the happy path

Beat 1 now uses **NIT Raipur's real, self-published documents** (GST REG-06, PAN, bank details; nitrr.ac.in). They are kept in the local demo kit (`Desktop/Parakh demo kit/8_real_institution_nit_raipur/`), **not in this repo**. Its README has the exact form values. NIT Raipur's public registry record is in the simulated registry (`demo_data.NITRR`), so the registry checks find it as the real GST lookup would.

**Order matters** (anti-fraud rules see re-used documents): reset → **NIT Raipur happy path first** → then the variants.

| Case (real documents, unedited) | Result (local run, live Gemini) | Key rule |
|---|---|---|
| NIT Raipur, all 3 documents | **APPROVED** → activate → **V-1001** | all pass; R-AU-5 warns that the bank letter was typed in LibreOffice |
| Country "United Kingdom" with an Indian GSTIN as the tax ID | PENDING_VENDOR | R-ID-11 "looks like a GSTIN from India", R-ID-12 SWIFT country |
| NIT Raipur's PAN with IIT BHU's GST certificate (borrowed GSTIN) | **REJECTED** | R-XD-03 (plus R-RISK-03/04: already registered, documents re-used) |
| IIT BHU giving NIT Raipur's bank account | PENDING_REVIEW, fraud, high | R-RISK-02 |
| Bank letter uploaded as the GST certificate | back to the vendor (before NIT Raipur is activated) | R-DOC-01 |
| Bank proof missing | PENDING_VENDOR | R-COMP-02 |
| A screenshot of the real GST PDF | PENDING_REVIEW | R-AU-1 "uploaded as an image, not the original PDF" |

Tejas (resubmission with a diff), Kaveri (held rejection) and Rangoli (Finance only) keep their designed synthetic documents: they isolate one behaviour each. Forgeries (AI-made cheque, Canva-edited certificate) are in the kit's folder 6.

## Beats

### 0. Intro (window A, Priya, dashboard)  0:15
Say: invite-first onboarding; the vendor submits GST, PAN and bank proof; **rules decide, AI only reads**; people make the final call.

### 1. Nilgiri happy path, fully live  1:55
1. **Window A, Priya:** Invites -> new invite: company "Nilgiri Packaging Solutions Private Limited", contact email `anitha@nilgiripack.example.com`, business reason (packaging for Plant 2), category Packaging, band 10-25 lakh -> create. Copy the link shown after creation. Point at: the invite ties the vendor to a real business need; the spend band feeds risk. (0:20)
2. **Window B, incognito:** paste the link (append `?demo=happy_nilgiri` to get the pre-filled form and the sample-file list). You are sent to vendor login: sign in as Anitha (`anitha@nilgiripack.example.com`), and the form opens. Attach the three files from `fixtures/documents/happy_nilgiri/`: `gst_certificate.pdf`, `pan_card.pdf`, `bank_proof.pdf`. Submit. The vendor lands on the thank-you page (a vendor never sees the internal view). (0:25)
3. **Live run view, window A** (this is what graders grade; never cut it). Switch to window A -> Applications -> Nilgiri -> open the run. With saved readings the run itself takes about 5-10 s (4.5-5.2 s on a warm local server, about 10 s on a cold process; expect more on Render), so it is usually finished by the time the page opens: for 2 minutes after a run finishes, the page **auto-plays a replay of the recorded checks**, labelled "Just finished: replaying the recorded checks (the run took X s)", and the decision card appears only when the replay reaches the decision. Opened mid-run, it catches up step by step and then follows live. Any later time: press **"▶ Replay the checks"**. Say: *"the checks ran in a few seconds; here they are step by step."* (The label shows the real duration.) Stages: invite, intake, completeness, read (AI), authenticity, identifiers, consistency, sources, risk, decision. Narrate: the AI reads each document without seeing what was typed; authenticity = file fingerprints, editor traces, signature; GSTIN check digit, PAN inside the GSTIN, live IFSC lookup; cross-document names; registry checks are simulated and labelled; the decision comes from rules. (0:40)
4. **Decision card:** APPROVED, low risk. Point at the facts table with proof levels A0-A4 (declared, evidenced, genuine, cryptographically proven, confirmed at source) and that simulated registries never reach A4. **Window A as Priya:** Activate is blocked ("Segregation of duties"). Switch to **Arjun** -> Activate -> vendor ID V-1001. (0:30)

### 2. Tejas wrong document (launcher)  0:55
Window A (staff login required): open `/demo/wrongdoc_tejas` -> form pre-filled with sample files -> Submit. Run ends **Pending: vendor to fix** (R-COMP-02, R-DOC-01). Point at: one complete, neutral vendor message ("2 things to fix") instead of a vague rejection; the wrong document (tax invoice in place of the GST certificate) and the missing Udyam. Open the vendor status page, then resubmit on the **same link** with `?demo=wrongdoc_tejas_resubmit` appended (a launcher link accepts its scenario's own resubmission without a vendor login) -> APPROVED, medium. Point at the **diff** (resolved: R-COMP-02, R-DOC-01).

### 3. Kaveri borrowed GSTIN (launcher)  0:35
`/demo/borrowed_gstin_kaveri` -> Submit -> **REJECTED**, rule **R-XD-03** (the GST certificate belongs to another legal entity). Point at: the AI only read; a rule caught the mismatch; the vendor message shows as **held**, separate from the internal note. Switch to **Kavita** -> Confirm reject. Keep narration to about 15 s if running long.

### 4. Rangoli shared bank (launcher)  0:50
`/demo/shared_bank_rangoli` -> Submit -> **PENDING_REVIEW**, fraud flag, high risk, **R-RISK-02** (the account is already on file for another vendor). Point at: the vendor sees a neutral "under review" message, no tip-off; the internal note has the detail. **Arjun** tries to approve -> blocked (needs the Finance controller). **Kavita** can clear it after verifying with the bank.

### 5. Close  0:20
Dashboard: every run, status, risk. Say what is simulated (GST, PAN, penny-drop, Udyam registries) and what is live (Gemini, IFSC). Add: "couldn't read it" is never "different"; an unreadable document asks the vendor for a clearer copy.

**Backup, not timed:** `/demo/proprietor_shinde` -> APPROVED, medium (proprietor).

## Timing budget

An invite run has 10 stages (the 11th, "bill", exists only for bill-first registrations). At 0.4 s per stage:
10 x 0.4 = **4.0 s of animation per run**, plus the reading (saved copies, near instant) and the checks themselves.

**Measured in the rehearsal (2026-11-06, local server, saved readings, STAGE_PACE_SECONDS=0.4):** Nilgiri 5.2 s,
Tejas 4.5 s, Tejas resubmission 4.6 s, Kaveri 4.8 s, Rangoli 4.5 s, Shinde 4.8 s per run. The whole scripted flow
(every request of the five beats, including the backup) ran in 38 s of machine time, so the 5-minute budget is
narration and clicking. On Render, add the cold start (see DEPLOY.md: wake it first) and network latency.

| Beat | Time | Running total |
|---|---|---|
| Intro | 0:15 | 0:15 |
| 1 Nilgiri (invite 0:20, submit 0:25, live run 0:40, decision + people 0:30) | 1:55 | 2:10 |
| 2 Tejas + resubmit | 0:55 | 3:05 |
| 3 Kaveri | 0:35 | 3:40 |
| 4 Rangoli | 0:50 | 4:30 |
| 5 Close | 0:20 | 4:50 |
| Slack | 0:10 | **5:00** |

If long: shrink Kaveri to 15 s, or drop it. Never shrink the Nilgiri live run.

## Pre-recording checklist
- [ ] Render env set per `docs/DEPLOY.md` ("Submission / interview settings"), including `STAGE_PACE_SECONDS=0.4`.
- [ ] Site awake: `/readyz` returns 200 (twice, 2 minutes before).
- [ ] System page: Gemini key/status looks healthy.
- [ ] In-app **Reset demo data** done (passcode), so each take starts clean.
- [ ] Window A logged in as Priya, with logins ready for Arjun and Kavita. Window B incognito, closed.
- [ ] Files ready: `fixtures/documents/happy_nilgiri/{gst_certificate,pan_card,bank_proof}.pdf` in a desktop folder.
- [ ] Both windows the same size, 110-125% zoom, notifications and bookmarks bar off.
- [ ] One full timed dry run, then reset again.
- [ ] Be honest on camera: demo documents use saved AI readings (repeatable); any new file is read live by Gemini.

## If something goes wrong live
- **Site slow or asleep:** wait for `/readyz`; skip the intro, start at beat 1.
- **Run stuck:** on the run page use "Re-run checks" (Procurement or Finance). Startup also re-queues runs interrupted less than an hour ago. Otherwise move on to the next launcher scenario.
- **Gemini slow or failing:** saved readings are used first for fixture files, and a 60 s per-run deadline falls back to the saved reading. Say so and continue.
- **Rate-limit or lockout message:** launcher submits are exempt from the submit limit; the last resort is `RATE_LIMITS=false` on Render (redeploy).
- **Vendor login problem:** register a new vendor account in the incognito window.
- **Wrong state in a take:** reset (passcode) and restart the take; do not repair live.
- **Nilgiri live beat fails entirely:** use `/demo/happy_nilgiri` through the launcher and say the invite step is the same.
- **Out of time:** drop Kaveri, then the Arjun-blocked click in Rangoli; keep the live run and one edge case.
