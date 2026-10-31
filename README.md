# Vendor Assurance: vendor onboarding that checks the documents, not just the numbers

A live vendor-onboarding process for an Indian company, built for Zamp's AI Solutions Analyst case study (problem 2: vendor onboarding).

A sponsor invites a vendor. The vendor submits their details and documents: a GST certificate, a PAN card, a cancelled cheque and, if they're an MSME, a Udyam certificate. The process then runs each submission through these stages, shown live:

1. **Invite check**: did a sponsor invite this vendor, and is it the same business?
2. **Completeness**: are all the details and documents required for this type of business present?
3. **Reading documents**: Gemini reads every file without seeing what the vendor typed. It reports the document type, how the file was produced (original, scan, phone photo, screenshot, hand-written, digitally composed, AI-generated) and each field, verbatim.
4. **Authenticity**: code checks GSTN digital signatures cryptographically, traces of editors such as Canva or Photoshop, re-saves, signs of hand-writing or AI generation, and files reused across applicants.
5. **Identifiers**: GSTIN check digit, the PAN inside the GSTIN, state code, PAN type, and a **live** IFSC lookup.
6. **Consistency**: the form and each document must agree, using fuzzy name matching (including a proprietor paid into a personal account). Misreads are corrected only where provable, and account numbers are never corrected.
7. **Sources**: GST, PAN, penny-drop, CIN and Udyam registries. These are **simulated** in this build and clearly labelled.
8. **Risk**: blocklist, a bank account already on file for another vendor, duplicates.
9. **Decision**: Approved, Pending (vendor to fix), Pending (internal review) or Rejected, with every reason. A message to the vendor is written for each outcome.

**Rules decide; AI only reads.** People activate vendors and confirm rejections. The sponsor who asked for a vendor can't approve it.

Every key fact gets an **assurance level**:

| Level | Meaning |
|---|---|
| A0 | Declared |
| A1 | Evidenced |
| A2 | Genuine document |
| A3 | Cryptographically proven |
| A4 | Confirmed at source |

So a buyer can see what was proven, not just claimed: a valid PAN written on blank paper never passes as proven.

## Run locally

```bash
uv sync
cp .env.example .env          # add a Gemini API key; DATABASE_URL defaults to local SQLite
uv run python scripts/seed.py --reset
uv run uvicorn onboarding.main:app --reload
uv run pytest                 # tests that need saved AI readings are skipped without .read_cache/
```

## Stack

- FastAPI, Jinja2 and Tailwind
- Server-sent events for the live run view (it tails the database, so a refresh is safe)
- Neon Postgres
- Gemini 3.5 Flash Lite (free tier), with a fallback model and labelled saved readings
- Render (free)

## Test data

All demo vendors are fictional. Their documents carry a SPECIMEN banner and are recognised by fingerprint. The one real document is a GST certificate signed by GSTN, published by the Office of the IGR Maharashtra; it is used only to demonstrate the signature check. Personal test files (hand-written and edited fakes, the author's own PAN) are kept out of this repository.

Design notes: `docs/` in the parent project (product spec, plan, research).
