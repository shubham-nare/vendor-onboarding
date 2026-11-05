# Demo script: 5-minute recording plan

Goal: show the happy path running live, then edge cases, narrating what the process does and why. Based on the
video plan (kept outside the repo); this file is the in-repo, code-checked version.

**Cast** (all `@mamoni.in`, password = `DEMO_PASSWORD`): Priya Nair and Rahul Desai (requesters), Arjun Mehta
(Procurement, "maker"), Kavita Rao (Finance, "checker"). The vendor in beat 1 signs in with the seeded demo vendor
account (`billing@kesarifacility.example.com`, same `DEMO_PASSWORD`; in demo mode the vendor login page has a
one-click fill) or by registering a new account in the incognito window. Use the seeded one: it is faster.

**Windows:** A = staff (log in per person, or switch with "Acting as"). B = incognito, the vendor.

**Golden outcomes** (what you should see):

| Scenario | Outcome | Rules to point at |
|---|---|---|
| happy_nilgiri | APPROVED, low risk, activation gives V-1001 | all required rules pass |
| wrongdoc_tejas | PENDING_VENDOR (R-COMP-02, R-DOC-01) | then `wrongdoc_tejas_resubmit`: APPROVED, medium, with a diff |
| borrowed_gstin_kaveri | REJECTED (R-XD-03) | vendor message held until a person confirms |
| shared_bank_rangoli | PENDING_REVIEW, fraud, high (R-RISK-02) | Finance only |
| proprietor_shinde | APPROVED, medium | backup beat |

## Beats

### 0. Intro (window A, Priya, dashboard)  0:15
Say: invite-first onboarding; the vendor submits GST, PAN and bank proof; **rules decide, AI only reads**; people make the final call.

### 1. Nilgiri happy path, fully live  1:55
1. **Window A, Priya:** Invites -> new invite: company "Nilgiri Packaging Solutions Private Limited", a contact email, business reason (packaging for Plant 2), category Packaging, band 10-25 lakh -> create. Copy the link shown after creation. Point at: the invite ties the vendor to a real business need; the spend band feeds risk. (0:20)
2. **Window B, incognito:** paste the link (append `?demo=happy_nilgiri` to get the pre-filled form and the sample-file list). You are sent to vendor login: sign in as the demo vendor, and the form opens. Attach the three files from `fixtures/documents/happy_nilgiri/`: `gst_certificate.pdf`, `pan_card.pdf`, `bank_proof.pdf`. Submit. (0:25)
3. **Live run view** (this is what graders grade; never cut it). Stages tick at the pace setting: invite, intake, completeness, read (AI), authenticity, identifiers, consistency, sources, risk, decision. Narrate: the AI reads each document without seeing what was typed; authenticity = file fingerprints, editor traces, signature; GSTIN check digit, PAN inside the GSTIN, live IFSC lookup; cross-document names; registry checks are simulated and labelled; the decision comes from rules. (0:40)
4. **Decision card:** APPROVED, low risk. Point at the facts table with proof levels A0-A4 (declared, evidenced, genuine, cryptographically proven, confirmed at source) and that simulated registries never reach A4. **Window A as Priya:** Activate is blocked ("Segregation of duties"). Switch to **Arjun** -> Activate -> vendor ID V-1001. (0:30)

### 2. Tejas wrong document (launcher)  0:55
Window A (staff login required): open `/demo/wrongdoc_tejas` -> form pre-filled with sample files -> Submit. Run ends **Pending: vendor to fix** (R-COMP-02, R-DOC-01). Point at: one complete, neutral vendor message ("2 things to fix") instead of a vague rejection; the wrong document (tax invoice in place of the GST certificate) and the missing Udyam. Open the vendor status page, then resubmit on the **same link** with `?demo=wrongdoc_tejas_resubmit` appended -> APPROVED, medium. Point at the **diff** (resolved: R-COMP-02, R-DOC-01).

### 3. Kaveri borrowed GSTIN (launcher)  0:35
`/demo/borrowed_gstin_kaveri` -> Submit -> **REJECTED**, rule **R-XD-03** (the GST certificate belongs to another legal entity). Point at: the AI only read; a rule caught the mismatch; the vendor message shows as **held**, separate from the internal note. Switch to **Kavita** -> Confirm reject. Keep narration to about 15 s if running long.

### 4. Rangoli shared bank (launcher)  0:50
`/demo/shared_bank_rangoli` -> Submit -> **PENDING_REVIEW**, fraud flag, high risk, **R-RISK-02** (the account is already on file for another vendor). Point at: the vendor sees a neutral "under review" message, no tip-off; the internal note has the detail. **Arjun** tries to approve -> blocked (needs the Finance controller). **Kavita** can clear it after verifying with the bank.

### 5. Close  0:20
Dashboard: every run, status, risk. Say what is simulated (GST, PAN, penny-drop, Udyam registries) and what is live (Gemini, IFSC). Add: "couldn't read it" is never "different"; an unreadable document asks the vendor for a clearer copy.

**Backup, not timed:** `/demo/proprietor_shinde` -> APPROVED, medium (proprietor).

## Timing budget

An invite run has 10 stages (the 11th, "bill", exists only for bill-first registrations). At 0.4 s per stage:
10 x 0.4 = **4.0 s of animation per run**, plus the reading (saved copies, near instant). Five runs (Nilgiri,
Tejas, Tejas resubmit, Kaveri, Rangoli) = about 20 s of pure stage time; the rest is clicking and narration.

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
