# How Vendor Assurance works

This explains the whole vendor onboarding process: who uses it, what happens to an application from invite to active vendor, every check it runs, how it decides, and what is real and what is simulated in this build.

Everything here matches the code in `onboarding/`. Rule IDs (like `R-XD-03`) are the same ones you see on the run page.

---

## 1. The idea in one paragraph

A company needs to add a new supplier (a "vendor") before it can pay them. Done badly, this is where payment fraud starts:
- a fake company;
- a borrowed GST number;
- a bank account belonging to someone else;
- a PAN hand-written on plain paper that "passed" because the number looked valid.

Vendor Assurance takes the vendor's form and documents and checks them as a careful finance team would. It reads every document with AI and checks whether the files themselves are genuine. It validates every ID mathematically, cross-checks each document against the others and against official sources, and looks for fraud patterns in the company's own vendor list.

It then gives one of four outcomes, with every reason visible:
- **Approved**
- **Pending: vendor to fix**
- **Pending: internal review**
- **Rejected**

It also writes the vendor a clear message saying exactly what is needed.

**Three principles run through everything:**

1. **Rules decide; the AI only reads.** Gemini transcribes documents and describes what it sees. Plain, testable code makes every decision. Every outcome traces back to a named rule with its evidence.
2. **"Couldn't read it clearly" is never treated as "read it and it's different."** Unclear documents lead to "please upload a clearer copy," never to a rejection.
3. **People make the final calls.** A person activates every vendor and confirms every rejection. The person who asked for the vendor can never approve it.

---

## 1b. Two front doors

The home page (`/`) asks **"Who are you?"**:

- **"I work at Vardhan Engineering"** → **Employee log in** (`/company/login`), then the internal console (`/console`): dashboard, runs, bills, vendors, invites. Every company page needs an employee login, because the console shows vendors' bank details, PAN and documents. In production this would be the company's single sign-on.
- **"I'm a vendor or supplier"** → the **supplier portal**:
  - **Accounts:** a vendor **creates an account** (company, name, work email, password) and **logs in** on later visits.
    - Passwords are stored only as salted **scrypt** hashes.
    - The session is a signed, http-only cookie, valid for 14 days.
    - Wrong-password errors don't reveal which emails have accounts.
    - There's no password reset in the demo (email is blocked on the free host).
  - **Home (`/vendor`):** the vendor's registration status in plain words, the messages we sent, the next step ("Update my registration" when we asked for something), their vendor ID once active, and their bills.
  - **Two ways in, one account:**
    - **invited:** the invite link asks them to create an account (company and email pre-filled from the invite), then opens the form;
    - **no invite, has a bill:** "Register and submit your bill" (section 4).
  - **Privacy:** a vendor only ever sees their own registration and bills.
    - An application tied to an account opens only for that account.
    - Another vendor gets "not found".
  - **Demo shortcuts:** the console's "Try a scenario" list still opens the forms without a login, so reviewers can try cases quickly.

## 2. Who is involved

| Role | In the demo | What they can do |
|---|---|---|
| **Requester** | Priya Nair (Operations), Rahul Desai (Plant Head) | The employee who needs the vendor. Sends the invite with a business reason and expected spend. **Can't approve, activate or reject** the vendor they asked for (segregation of duties). |
| **Procurement reviewer** | Arjun Mehta (Procurement) | Reviews applications. Can activate low and medium-risk vendors, ask the vendor for more, confirm a rejection, or overturn an automatic rejection into a review. (In audit language, the *maker*.) |
| **Finance controller** | Kavita Rao (Finance) | Everything the reviewer can do, plus the high-risk cases: vendors with spend of **₹50 lakh a year or more**, or any **fraud-class signal**. Only the Finance controller can reject after a review. (The *checker*.) |
| **Vendor** | The supplier's contact | Gets a private link, fills the form, uploads documents, sees their status page and the messages sent to them. Never sees internal reasoning. |

**Logins.** Employees log in with their work email; vendors log in to the supplier portal with the account they created. The two use separate cookies, each signed for its purpose, so a vendor's login can never open a company page. Passwords are stored only as salted scrypt hashes.

**Demo logins** (fictional, created by `seeding.py` and again at app start if missing; the login pages list them with a **Fill** button, and the shared demo password is `DEMO_PASSWORD` in `onboarding/seeding.py`):

| Who | Email | What they see |
|---|---|---|
| Company (Arjun Mehta, Procurement reviewer) | `arjun.mehta@vardhan.example.com` | The console. Priya, Rahul and Kavita log in the same way with their own `@vardhan.example.com` emails. |
| Vendor (Sneha Kulkarni, Kesari Facility Services) | `billing@kesarifacility.example.com` | An empty vendor account, ready to register with a bill (a demo link pre-fills Kesari's details and documents). |

After logging in, the **"Acting as"** menu (top right) lets the demo switch person without logging out. It lists each person with their role and what they're allowed to do, so you can watch the permissions change. In production each person logs in as themselves and the menu doesn't exist.

---

## 3. The journey, end to end

```
 Requester               Vendor                    Vendor Assurance (automatic)            People
 ───────                 ──────                    ────────────────────────────            ──────
 Sends invite  ──link──▶ Fills form,         ──▶  1 Invite check
 (reason, spend)         uploads documents         2 Intake (store + fingerprint files)
                                                   3 Scope & completeness
                                                   4 Read documents (Gemini, blind)
                                                   5 Document authenticity
                                                   6 Identifier checks (+ live IFSC)
                                                   7 Cross-document & name checks
                                                   8 Source verification
                                                   9 Risk checks (vendor master, blocklist)
                                                  10 Decision + messages
                                                          │
                     ┌────────────────────────────────────┼──────────────────────────────┐
                     ▼                                    ▼                              ▼
             PENDING: VENDOR TO FIX              PENDING: INTERNAL REVIEW          APPROVED / REJECTED
             message sent at once:               vendor gets a neutral             message HELD until a
             "We need 2 things: …"               "under review" note               person acts
                     │                                    │                              │
             Vendor fixes and resubmits          Reviewer/Finance: approve,           Activate → vendor ID V-10xx
             on the same link → new run,         ask vendor, or reject             or confirm/overturn rejection
             compared with the last one
```

A typical run takes **about 12–15 seconds**. Almost all of that is Gemini reading the documents; every rule after that is instant.

---

## 4. Step 0: the invite

Onboarding is **invite-only**. The employee who needs the vendor (the **requester**) fills in the Invites page with:
- the vendor company name and contact email;
- **why we need this vendor** (the business reason);
- the spend category and expected yearly spend band.

This creates a private link (`/apply/<token>`). In production it is emailed to the vendor; the free host blocks email, so in the demo the link is shown on screen and messages go to the **Outbox** page.

**Why invite-only?** It ties every new vendor to a real business need:
- **Fake vendors.** The textbook procurement fraud is a supplier nobody asked for, often set up by an insider, receiving payments. If every vendor must start with a named employee asking for it, giving a business reason and expected spend, a vendor nobody asked for can't slip in.
- **Accountability.** The audit trail always shows who wanted this vendor and why, and the declared spend sets the risk level.
- **Separation of duties.** Because we know who asked, that same person can be stopped from approving it.
- **A check on the right company.** The app compares the business that applied with the one that was invited (`R-INV-02`).

Spend of **₹50 lakh a year or more** marks the invite as high-spend, which makes the vendor **high risk**: only the Finance controller can activate it.

Someone can also apply at `/apply` without an invite. That application always goes to internal review (`R-INV-01`); it can never be approved automatically.

### Without an invite: registering with a bill (`/bill`)

Real companies also get vendors who **already did the work**: an emergency repair, a one-off service someone arranged, and now the supplier wants to be paid. Procurement calls this *after-the-fact* or *no-PO* spend. It is also the classic route for invoice fraud: a convincing bill from a "vendor" nobody engaged.

The design follows one principle: **a vendor can prove who they are, but only someone inside the company can confirm that we owe them.**

1. **The vendor registers at `/bill`.** It's the same form and documents as an invited vendor, plus a **Your bill** section:
   - the tax invoice file, invoice number, date and total (including GST);
   - what the work was;
   - **who at our company engaged them** (name or work email);
   - a PO number, if they have one.
2. **All the normal vendor checks run**, plus a **Bill checks** stage (shown only for these registrations):

   | Rule | Check | If it fails |
   |---|---|---|
   | `R-BILL-01` | The invoice number typed matches the bill | VENDOR |
   | `R-BILL-02` | The bill was issued by this vendor (seller GSTIN = the vendor's GSTIN) | REVIEW (someone else's invoice) |
   | `R-BILL-03` | The bill is addressed to us (buyer GSTIN = ours). Without that we can't pay it or claim the GST credit. | VENDOR, with our exact name, GSTIN and address |
   | `R-BILL-04` | The amount typed matches the bill's total (to within ₹1) | VENDOR |
   | `R-BILL-05` | The bill adds up: taxable value + GST = total | VENDOR |
   | `R-BILL-06` | **The right kind of GST:** CGST + SGST when the vendor is in our state, IGST when it isn't. Decided from the two GSTINs' state codes. | VENDOR ("send a corrected invoice"); no GST at all is a WARN |
   | `R-BILL-07` | Dated sensibly: not in the future (VENDOR); not more than a year old (REVIEW: the credit may be lost) | VENDOR / REVIEW |
   | `R-BILL-08` | The same invoice (same seller GSTIN and invoice number) wasn't already submitted on another application | REVIEW, fraud class (double billing) |
   | `R-BILL-09` | The person they named is a real employee | REVIEW (nobody to vouch for the work) |

   The bill also goes through the same authenticity checks as every other document (editing software, broken signatures, AI-generated images…).
3. **`R-INV-01` is a warning, not a block.** "No invite: the vendor registered with a bill." The run can still come out *Approved* (at medium risk), *Vendor to fix* or *Review* on its merits.
4. **The named employee must confirm.** On the run page they see **"Yes, I engaged this vendor"** and **"No, I didn't engage them"**. Only that employee can press either button.
   - **Yes:** they become the vendor's **requester**, so segregation of duties applies: they can't approve the vendor themselves.
   - **No:** the case becomes possible invoice fraud. It goes to internal review, and only the Finance controller can decide. The vendor's status page just says the work is "waiting for our team to confirm", so they learn nothing.
   - **Activation is blocked until the engagement is confirmed**, even when the automatic decision is *Approved*.
5. **Risk:** a single bill of **₹10 lakh or more** makes the vendor high risk, so the Finance controller must approve.
6. **Payment:** never automatic. After activation the bill is "passed to accounts payable" and paid only once a purchase order is raised for the work and the receipt is recorded (outside this demo). The vendor is told the same in plain words.

---

### Bills from active vendors (`/vendor/bills/new`)

Once a vendor is active, it sends later bills from the portal without registering again. Each bill:

1. **Is checked.** Gemini reads the invoice. Then the same bill rules (`R-BILL-01`…`09`) run against the vendor's **verified** record in the vendor master, plus document type and authenticity, plus:

   | Rule | Check | If it fails |
   |---|---|---|
   | `R-BILL-10` | **The bank account printed on the bill is the one we verified.** Asking to be paid into a new account through an invoice is the most common vendor-payment fraud. | REVIEW, fraud class. Pay only the verified account; confirm any change by calling the vendor on a number we already have. |

2. **Gets a status:**
   - **Vendor to fix** (with the exact items; the vendor corrects and resubmits the same bill);
   - **Internal review** (wrong seller, duplicate, bank change, unknown employee…);
   - **Awaiting confirmation**.
3. **Is confirmed** by the employee the vendor named ("Yes, I engaged this vendor for this work" or "No, I didn't"). Only that employee can answer. A "no" makes it fraud class.
4. **Is approved for payment by someone else:**
   - the employee who asked for the work can't approve it;
   - **₹10 lakh or more, or any fraud signal:** only the Finance controller can approve;
   - only the Finance controller can reject.
5. **Is never paid from here.** "Approved for payment" means it goes on to purchase-order and goods-receipt matching.

The company sees all of this on **Bills** (`/bills`) and each bill's page:
- the vendor's verified profile (vendor ID, GSTIN, masked PAN, the account we pay into, how well each fact was proven at onboarding, a link to the onboarding run);
- the reasons and every check;
- what the AI read;
- the actions, and the audit trail.

**Vendors** (`/vendors`) lists every portal account and where it stands. The vendor sees only plain-language status: "with our team", "approved", or the items to fix.

## 5. Step 1: the vendor's form and documents

The vendor fills four sections:

1. **Business:** type (proprietorship, partnership, LLP, private or public limited…), legal name, proprietor's name (for proprietorships), GSTIN, PAN, CIN or LLPIN where relevant, and "registered for GST in India."
2. **Address & contact:** address, city, state, PIN, contact person, email, phone.
3. **Bank account:** account holder name, account number, IFSC, and whether they are MSME-registered (with the Udyam number).
4. **Documents** (PDF, JPG or PNG, up to 10 MB each):
   - GST registration certificate (Form GST REG-06, as downloaded from the GST portal);
   - PAN card;
   - cancelled cheque or bank letter;
   - Udyam (MSME) certificate, only if they said they are MSME-registered.

Which fields and documents are required depends on the business type: a company needs a CIN, an LLP needs an LLPIN, and so on.

On submit, each file is stored once and identified by its **SHA-256 fingerprint**. That fingerprint later catches the same file being reused by a different applicant.

---

## 6. The ten stages of a run

Each stage appears live on the run page as it happens (section 14). Every stage produces rule results; each result is **PASS, FAIL, WARN, SKIPPED or ERROR**. Each rule also carries an **outcome if it fails**:

| Outcome if it fails | Meaning |
|---|---|
| **REJECT** | Can't be fixed in place: an identity conflict or the blocklist. A person must confirm before the vendor is told. |
| **REVIEW** | A person must judge: fraud signals, borderline names, possible duplicates, system errors. |
| **VENDOR** | The vendor can fix it. The rule carries the exact sentence to send them. |
| **WARN** | Shown to the reviewer only; doesn't change the status (it can raise the risk tier). |

### Stage 1: Invite check
- `R-INV-01`: the application came through an employee's invite, and the link wasn't expired, revoked or already used by another application. Otherwise → REVIEW.
- `R-INV-02`: the business that applied is the one that was invited (fuzzy name match). Otherwise → REVIEW.

### Stage 2: Intake
Files are stored and fingerprinted, and a run record is created. A resubmission is linked to the vendor's previous run.

### Stage 3: Scope & completeness
- `R-SCOPE-01` / `R-SCOPE-02`: the automated path covers **India-based, GST-registered** vendors only. Anything else goes to internal review for a manual path; it is never auto-rejected.
- `R-COMP-01`: all required details are filled in. Otherwise → VENDOR ("Please fill in: …").
- `R-COMP-02`: all required documents are uploaded. Otherwise → VENDOR. It also covers "you said you're MSME-registered but didn't attach the Udyam certificate."

### Stage 4: Read documents (AI)
See section 7 for how the reading works. The rules here:
- `R-DOC-00`: reading failed altogether → ERROR, which goes to REVIEW (a person looks at the file).
- `R-DOC-01`: **is it the right document?** A tax invoice uploaded in the GST certificate slot → VENDOR: *"The file you uploaded as your GST registration certificate (gst_certificate.pdf) appears to be a tax invoice. Please upload your GST registration certificate (Form GST REG-06, downloadable from the GST portal)."*

### Stage 5: Document authenticity
Is each file genuine? See section 8. Signals become rules named after their code (`R-AU-1`, `R-AU-3`, …).

### Stage 6: Identifier checks
Pure maths and format rules on what the vendor typed. See section 9.
- `R-ID-01` to `R-ID-09`: format and check-digit rules.
- `R-BANK-01`: live IFSC directory lookup.

### Stage 7: Cross-document & name checks
Does every document agree with the form and with the other documents? See section 10.
- `R-XD-01` to `R-XD-05`: IDs on the documents vs the form, including the identity-conflict check.
- `R-NAME-01` to `R-NAME-03`: business, PAN and account-holder names.
- `R-DOC-03`: the bank proof doesn't show a holder name.
- `R-MSME-01` / `R-MSME-02`: Udyam number and payment terms.

### Stage 8: Source verification
Ask the issuing authority instead of trusting a document: GST registry, PAN registry, penny-drop on the bank account, company registry. See section 11. **These are simulated in this build, and labelled as simulated everywhere.**

### Stage 9: Risk checks
Fraud patterns in the company's own data. See section 12.
- `R-RISK-01`: blocklist.
- `R-RISK-02`: bank account shared with another vendor.
- `R-RISK-03`: already registered.
- `R-RISK-04`: same document file submitted by a different applicant.

### Stage 9b: Bill checks (bill-first registrations only)
`R-BILL-01` to `R-BILL-09`: see "Without an invite: registering with a bill" in section 4.

### Stage 10: Decision
A fixed order of precedence turns all the rule results into one status, a risk tier, a proof level for every key fact, a vendor message and an internal note. See sections 13–15.

---

## 7. How the AI reads documents

Every document is sent to **Gemini 3.5 Flash Lite**, falling back to Gemini 3.1 Flash Lite if the first is busy. Each document gets its own call, and up to all of an application's documents are read in parallel.

**The AI never sees what the vendor typed.** The prompt contains no form values, so the model can't just agree with the form. It reports what is on the page, and code does the comparing.

For each document, Gemini returns a structured answer (validated against a strict schema):

- **Document type:** GST certificate, PAN card, cancelled cheque, bank letter, Udyam certificate, tax invoice, Aadhaar, or other, with a quote as evidence.
- **Document form (how it was made):**
  - `ORIGINAL_DIGITAL`: a file produced by a portal or software;
  - `SCAN_OR_PHOTOCOPY`;
  - `PHOTO_OF_PHYSICAL_ORIGINAL`: a camera photo of a real card or paper;
  - `PHOTO_OF_SCREEN`: a camera photo of a monitor or phone;
  - `SCREENSHOT`;
  - `HANDWRITTEN_OR_PLAIN_PAPER`: details written or typed on plain paper;
  - `DIGITALLY_COMPOSED`: assembled or edited in software;
  - `AI_GENERATED`;
  - `UNSURE`.
- **Integrity notes:** misspelled or garbled printed words (real bank and government printing has none), visible watermarks or logos (for example an AI generator's mark), and covered or redacted regions.
- **Fields,** each transcribed exactly as printed, with a short evidence quote and a **legibility grade** (clear, partial, unreadable, not present):
  - GSTIN, legal name, trade name, constitution, address, state, issue date;
  - PAN, name on card;
  - account number, IFSC, bank, branch, account holder name;
  - Udyam number, enterprise type;
  - and more.

The legibility grade matters. A field read as "partial" is never treated as a mismatch; it becomes "please upload a clearer copy."

**If the AI is unavailable**, a saved reading of the *same file* (matched by fingerprint) is used, and the run page says so ("saved reading (AI unavailable)"). If there is no saved reading, the document goes to a person (`R-DOC-00`). A run never silently guesses.

---

## 8. Is the document genuine? (authenticity)

This layer exists because of a real case from Shubham's background-verification work: someone hand-wrote their PAN on a blank sheet, photographed it, and it was "verified" because the number was valid. **A valid number proves nothing about the document.**

The authenticity check combines three kinds of evidence:

1. **Gemini's visual judgement:** the document form and integrity notes above.
2. **The file itself:** PDF producer and creator software, author, creation and modification dates, number of saves, image EXIF software, hidden text, and content-provenance markers.
3. **The digital signature:** GST certificates downloaded from the portal are digitally signed by GSTN. The system verifies the signature cryptographically, including GSTN's older SHA-1 format, which common libraries refuse to check.

### The signals

| Code | What it catches | Severity |
|---|---|---|
| **AU-1** | Hand-written or typed on plain paper | vendor: "upload the original document" |
| AU-1 | Photo of a screen | vendor: "upload the original file" |
| AU-1 | A certificate uploaded as a screenshot or image, not the portal PDF | vendor: "upload the original PDF from the portal" |
| AU-1 | A certificate as a photo of a printout | warn (the signature can't be checked) |
| **AU-2** | AI judges it assembled in software or AI-generated | review (a person looks; the AI's visual verdict alone varies between runs) |
| AU-2 | Garbled or misspelled printed text | **fraud** |
| AU-2 | An AI generator's watermark visible | **fraud** |
| AU-2 | Parts covered or redacted | warn |
| **AU-3** | Digital signature present but **broken**: the file changed after signing | **fraud** |
| **AU-4** | Digital signature verified: signer, chain, signing time | info (good news) |
| **AU-5** | Created or saved with editing software (Canva, Photoshop, PDF editors…) | warn |
| **AU-12** | Page says "Digitally signed" but the file has no signature | warn (an honest browser re-save does this too) |
| **AU-13** | File created more than a year after the document's own issue date | warn |
| **AU-12 (combined)** | Editing software **plus** a missing signature and/or a rebuild years later: "Likely edited" | **fraud** |
| **AU-14** | File metadata names a person (Author = …) | info, reviewers only |
| **AU-6** | File saved many times | info |
| **AU-8** | Hidden instruction-like text aimed at automated checks (prompt injection) | **fraud** |
| **AU-11** | AI or content-provenance markers in the file | review |

**Severity, from lowest to highest:**
- **info:** shown to the reviewer only.
- **warn:** shown, and caps the document's proof level at A1.
- **vendor:** the vendor must send a better document.
- **review:** a person must look.
- **fraud:** a person must look, and the case is **fraud class**. The vendor gets a neutral "under review" note, so a fraudster learns nothing about what was caught.

**Authenticity signals never reject on their own.** A heuristic can be wrong, so the strongest thing it can do is send the application to a person.

### Each document gets its own proof level
- **A3 Cryptographically proven:** a valid, intact digital signature and no concerns.
- **A2 Genuine:** no concerns, and it looks like a real original, scan or photo of a physical document.
- **A1 Evidenced:** anything weaker. The value is shown on a document, but the document isn't shown to be genuine.

### About the demo's own documents
The demo vendors are fictional, so their documents carry a **SPECIMEN** banner. A fictional PAN card can't legally carry the national emblem, so it would look "fake" to the AI. The system recognises these fixtures by their SHA-256 fingerprint and switches off the visual-fakeness signals for them only, with a visible note. Everything else still runs on them: reading, rules, signature checks.

---

## 9. Identifier checks (maths, not AI)

These run on what the vendor typed and need no documents:

| Rule | Check |
|---|---|
| `R-ID-01` | GSTIN has the standard 15-character format. |
| `R-ID-02` | GSTIN **check digit** is valid (the official checksum on the last character). A failure almost always means a typing error → VENDOR. |
| `R-ID-04` | **The PAN embedded in the GSTIN** (characters 3–12) equals the PAN the vendor gave. Every GSTIN contains its owner's PAN, so a mismatch means the GSTIN belongs to someone else. |
| `R-ID-05` | The GSTIN's **state code** (first two digits) matches the declared state. |
| `R-ID-03` | PAN has the standard 10-character format. |
| `R-ID-06` | The PAN's **4th character** matches the business type: C = company, P = individual (proprietorship), F = firm or LLP, and so on. |
| `R-ID-07` | CIN fits the business type. |
| `R-ID-08` / `R-ID-09` | IFSC format and account-number format. |
| `R-BANK-01` | **Live** lookup of the IFSC in Razorpay's public IFSC directory: which bank and branch it is. If the service is down, a bundled snapshot is used and labelled; if neither answers → ERROR, which goes to REVIEW. |

---

## 10. Cross-document and name checks

### Comparing IDs: misreads are corrected only where that's provably safe
AI reading sometimes confuses look-alike characters (0/O, 1/I, 5/S, 8/B). The matching code corrects them **only where the position's character type is fixed**:
- in a PAN, positions 1–5 and 10 must be letters and 6–9 digits;
- in a GSTIN, the format fixes most positions, and **the check digit then proves the corrected value**;
- an IFSC's 5th character is always zero.

**Account numbers are never corrected:** there is no way to prove a fix.

Each comparison ends as:
- **match**;
- **match after correcting a misread** (shown with the correction);
- **mismatch** (clearly read and different);
- **unreadable** (ask for a clearer copy, never a mismatch);
- **missing**.

| Rule | Check | If it fails |
|---|---|---|
| `R-XD-01` | GSTIN on the form vs the GST certificate | VENDOR |
| `R-XD-02` | PAN on the form vs the PAN card | VENDOR |
| **`R-XD-03`** | **Identity conflict:** the certificate's GSTIN (check digit valid, clearly read) contains a *different* PAN from the PAN card, while the PAN card agrees with the form. The GST registration belongs to **another legal entity**, for example a sister company's GSTIN. Two independent sources agree, so a misread is very unlikely. | **REJECT** (a person confirms) |
| `R-XD-04` / `04b` | Account number and IFSC on the form vs the cancelled cheque | VENDOR |
| `R-XD-05` | "Constitution" on the GST certificate vs the business type the vendor chose | VENDOR |

### Comparing names
Names are normalised before comparing: "Pvt Ltd" = "Private Limited," "M/s" and punctuation are dropped, and so on. They are then scored from 0 to 100:
- **90 and above: match.**
- **75–89: partial.**
- **Below 75: mismatch.**

For individuals, initials are understood ("R. Sharma" vs "Ravi Sharma").

| Rule | Check | If it fails |
|---|---|---|
| `R-NAME-01` | Business name vs the GST certificate (legal or trade name) | partial → WARN; mismatch → VENDOR |
| `R-NAME-02` | Name on the PAN card vs the legal name (or the proprietor's name for a proprietorship) | partial → WARN; mismatch → VENDOR |
| `R-NAME-03` | **Account holder** on the cheque vs the business | partial → REVIEW; unreadable or mismatch → VENDOR ("payments can only go to an account in your business's name") |

**The proprietorship case.** A proprietorship is not a separate legal person: the owner *is* the business. So an account in the owner's personal name is legitimate. `R-NAME-03` accepts the proprietor's name (or the GST legal name) as the account holder, but only if all three of these hold:
- the business type is proprietorship;
- the PAN is an individual's (4th character P);
- the PAN card's name matches the proprietor.

A naive exact-match rule would wrongly reject this. The run says "matched the proprietor's name (proprietorship: the owner and the business are one legal person)" and the vendor is rated **medium risk**, not rejected.

### MSME
- `R-MSME-01`: the Udyam number typed matches the certificate.
- `R-MSME-02` (WARN): for micro and small enterprises, a reminder of the legal payment terms. They must be paid within 15 days, or up to 45 days with a written agreement (MSMED Act s.15).

---

## 11. Source verification: asking the authority

The real fix for the plain-paper PAN case is to **ask the issuer**, not trust the paper. The system has a common adapter for each source, so a production provider (such as Cashfree, Perfios or Karza) slots in by configuration.

| Rule | Source | In this build |
|---|---|---|
| `R-SRC-GST` | GST registry: GSTIN active? Legal name? | **Simulated** registry |
| `R-SRC-PAN` | PAN registry: valid? Name? | **Simulated** |
| `R-SRC-PAN2` | PAN inoperative (not linked to Aadhaar) → TDS at the higher 20% rate | **Simulated** (WARN) |
| `R-SRC-BANK` | **Penny-drop:** ₹1 to the account; the bank returns the holder's name | **Simulated** |
| `R-SRC-CIN` | Company registry (MCA) | **Simulated** |
| `R-BANK-01` | IFSC branch directory | **Live** (Razorpay) |

Simulated answers are labelled in amber on every run and **can never raise a fact to A4**. Free sandboxes for these APIs need a registered business's KYC, which a candidate can't provide. The design shows exactly where they plug in.

Simulated or not, the logic is real. For example, when the bank (penny-drop) says the account belongs to "DECCAN OFFICE SUPPLIES" and not the applicant, `R-SRC-BANK` fails → REVIEW.

---

## 12. Risk checks: fraud patterns in our own data

These compare the application with the company's **vendor master** (existing vendors) and **blocklist**:

| Rule | Pattern | Outcome |
|---|---|---|
| `R-RISK-01` | PAN, GSTIN or bank account is on the blocklist | **REJECT**, fraud class |
| `R-RISK-02` | **The bank account already belongs to another vendor** (different PAN). This is the classic payment-diversion pattern: shared or third-party account, doctored cheque, collusion. | REVIEW, fraud class. The note tells the reviewer to verify with the bank. |
| `R-RISK-03` | The PAN or GSTIN is already registered (risk of a duplicate vendor and double payment) | REVIEW |
| `R-RISK-04` | **The exact same file** (same SHA-256) was submitted by a different applicant: template fraud | REVIEW, fraud class |

---

## 13. The decision: one status, by fixed precedence

All rule results are combined in a **fixed order**. The first matching line wins:

1. **Out of scope** (not India or not GST-registered) → **Pending: internal review** (manual path).
2. Any failed rule with outcome **REJECT** → **Rejected**.
3. Any failed **REVIEW** rule, or any **ERROR** → **Pending: internal review**.
4. Any failed **VENDOR** rule → **Pending: vendor to fix**.
5. Otherwise → **Approved**.

So a fraud signal can never be hidden behind a simple fix. If there is both a missing document and a shared bank account, the status is *internal review*, not *vendor to fix*.

**A safety check on approval.** Approval also requires every applicable **required rule** to have actually **passed**: SKIPPED doesn't count. The required rules are invite, completeness, all identifier checks, IFSC, the GSTIN, PAN and account comparisons, the business and holder names, the blocklist and the shared-account check. If an approval ever lacked one, the code stops with an error rather than approve.

### Risk tier
- **High:** any fraud-class signal, or the requester declared spend of ₹50 lakh a year or more. Needs the Finance controller.
- **Medium:** any warning, or a proprietorship paid into the owner's personal account.
- **Low:** everything clean.

### "Why" cards
The run page shows up to six reason cards: the rules that decided the status, each with its rule ID, title, detail and what happens next. For example: "A reviewer decides: approve, ask the vendor, or reject."

---

## 14. How well is each fact proven? (assurance levels A0–A4)

"Approved" means more when the buyer can see *how* each key fact was established. Every key fact gets a level, shown as a 5-bar **proof ladder**:

| Level | Name | Meaning | Example |
|---|---|---|---|
| **A0** | Declared | The vendor typed it. Nothing backs it up. | A PAN in the form with no readable PAN card |
| **A1** | Evidenced | A document shows the same value, but the document isn't shown to be genuine. | A hand-written note; a photo with warnings |
| **A2** | Genuine | A document shows it and looks genuine: no editing traces, a real photo or scan, nothing obscured. | A clear phone photo of a real PAN card |
| **A3** | Cryptographically proven | The document carries the issuer's valid digital signature. | GST certificate downloaded from the portal, signed by GSTN, unchanged |
| **A4** | Confirmed at source | The issuing authority confirmed it directly. | Bank branch via the live IFSC directory; in production also GSTN, PAN and penny-drop |

How each fact is graded:
- **GSTIN** and **legal name:** from the GST certificate, up to A3 if signed. An identity conflict (`R-XD-03`) drops the GSTIN to A0.
- **PAN:** from the PAN card, capped at A2 (a physical card has no digital signature).
- **Bank account:** needs both the account comparison and the holder-name check to pass. Capped at A2 in this build; a real penny-drop would make it A4.
- **Bank branch:** A4 when the live IFSC lookup answered.
- **MSME:** from the Udyam certificate, capped at A2.

If the rule linking a fact to its document failed, the fact is A0, however genuine the document.

---

## 15. Messages: what the vendor hears vs what reviewers see

Every run writes **two messages**:

**To the vendor**, in plain language and never revealing internal reasoning:

| Status | Message | Sent when |
|---|---|---|
| Vendor to fix | A numbered list of exactly what to do, using each failed rule's own wording, plus "Your PAN, GSTIN and bank details checked out, so you won't need to re-enter them." | **Immediately** |
| Internal review | A neutral "being reviewed, no action needed, within 2 business days." Fraud-class cases get **only** this, so a fraudster learns nothing. Out-of-scope cases are told about the manual path. | Immediately |
| Rejected | The specific reason (for example, "the GST registration you provided belongs to a different legal entity…") | **Held** until a person confirms |
| Approved | "Passed our checks; you'll get confirmation once activated." | **Held** until a person activates |

**To the reviewer (internal note):** the status, the risk tier, a fraud flag, and every FAIL, ERROR and WARN rule with its internal detail.

Messages appear on the vendor's status page (sent ones only) and in the **Outbox**. In production they are emailed.

---

## 16. People's decisions and segregation of duties

After the automatic decision, the run page offers only the actions that apply:

| Current status | Actions | Who may act |
|---|---|---|
| **Approved** | **Activate vendor:** adds it to the vendor master with an ID (`V-1001`, `V-1002`…), sends the held approval and a "your vendor ID is…" message. | Procurement reviewer or Finance controller. **Finance controller only** if high risk or fraud-flagged. |
| **Rejected** | **Confirm rejection:** sends the held rejection message. | Reviewer or Finance controller |
| | **Overturn:** "Don't reject: send to internal review" (reason required) | Reviewer or Finance controller |
| **Internal review** | **Approve and activate** (reason required) | Reviewer or Finance controller; **Finance controller only** if high risk or fraud |
| | **Ask the vendor for something** (the reviewer writes the message) | Reviewer or Finance controller |
| | **Reject** (reason required; the vendor gets a polite, non-specific rejection) | **Finance controller only** |
| Vendor to fix | Nothing: waiting for the vendor | — |

The rules behind this table:
- **The requester who asked for the vendor can't take any of these actions.** The button shows a lock and the reason: "Segregation of duties: the employee who requested this vendor can't approve, activate or reject it."
- Blocked actions stay visible but disabled, with the reason, so you can see the controls working.
- Actions need a written reason where it matters, and every action goes on the **audit trail** (who, role, when, what, why).
- Actions only apply to the **latest** submission.

### Who sees what (need to know)

Each person sees only what their job needs, not just different buttons. The rules live in one file, `onboarding/access.py`, and are enforced on the server: a hidden link doesn't help, because the page itself refuses.

| Information | Requester (Priya, Rahul) | Procurement reviewer (Arjun) | Finance controller (Kavita) |
|---|---|---|---|
| Applications and bills listed | Only their own (invites they sent; registrations and bills that name them) | All | All |
| Status and what the vendor was told | Their own | Yes | Yes |
| Documents and what the AI read | No | Yes | Yes |
| Every check, reasons, internal note | No | Yes | Yes |
| Fraud flags | No | Yes | Yes |
| PAN, GSTIN, bank account | No | Masked | Masked PAN; full bank account of active vendors |
| Vendor directory | Names, vendor IDs, status | With contacts | With contacts |
| Outbox, document check, system | No | Yes | Yes |

Why this way:
- **A requester may be the person a fraud check is about.** If Priya colluded with a vendor, seeing "the bank account on this bill isn't the verified one" would tell her exactly what was caught. So a requester sees a plain status ("Procurement or Finance is taking a closer look"), never the flags or the evidence.
- **Requesters don't need ID numbers or documents** to do their part, which is to confirm whether they asked for the work. Fewer people seeing PANs and bank details means fewer places they can leak from.
- **Only Finance sees the full bank account**, because Finance releases the payment. Everyone else sees the last four digits.
- **Another requester's request doesn't exist for you:** Rahul opening Kesari's page (Priya's vendor) gets "visible to Procurement and Finance only". The live-view feeds and the document files are guarded the same way.
- The "Acting as" menu switches person in the demo, so you can watch the same page change: Priya sees her requests in plain words, Rahul can't open them, Arjun sees all the evidence, and Kavita also sees the account number.

**Machine decision vs lifecycle.** The run keeps the machine's decision forever, for example "Approved." The application separately tracks where it is now: Active, Rejected, Pending vendor… The dashboard shows both, as in "Approved, now active."

---

## 17. Resubmission: fixing and trying again

When the status is *vendor to fix*, the vendor opens the **same link** and sees:
- the "What we need from you" message;
- the form pre-filled with their earlier answers;
- each document slot marked "keeps: previous-file.pdf." An empty slot keeps the earlier file; a new upload replaces it.

The resubmission creates a **new run** linked to the old one, and is checked from scratch. The run page then shows:
- a **Submission 1 → Submission 2** switcher;
- a comparison with the previous submission: **Resolved** (failed before, passes now), **Still open**, and **New** problems.

In the demo, Tejas Industrial Supplies first uploads a tax invoice as its GST certificate and forgets the Udyam certificate → *vendor to fix*. It resubmits with the right files → *Approved*. Both problems show as resolved.

---

## 18. The screens

| Screen | What it shows |
|---|---|
| **Dashboard** (`/`) | Counters (applications, active/approved, waiting on vendor, internal review, rejected, fraud-class flags), average run time, first-time approvals, the **past runs** table (decision, current status, risk, requested by, time), and **Try a scenario** to start any demo case. |
| **Run page** (`/runs/<id>`) | The **live run**: the ten stages filling in as they happen, with each document's reading shown as it completes. Then the decision stamp, why cards, people's actions and audit trail, the **proof ladder** for each fact, each **document** (what the AI read it as, how it was made, authenticity signals, signature, every field read), the vendor message vs the internal note, and every rule that ran. |
| **Vendor form** (`/apply/<token>`) | What the vendor fills in. |
| **Vendor status** (`/status/<token>`) | The vendor's own view: plain status and the messages sent to them. Nothing internal. |
| **Invites** | Create an invite (requesters only); list of invites and their status. |
| **Outbox** | Every message to a vendor, marked sent or held for a person. |
| **Document check** (`/check`) | Checks any file's authenticity **without the AI**: digital signature, editing software, saves, dates, image details. Upload two files side by side, for example the genuine GSTN-signed sample next to a Canva-edited copy. One gets stamped **"Signature verified · GSTN"**, the other **"Likely edited."** |
| **What is verified** | The honesty page: what the levels mean, what is real vs simulated, how decisions are made, test results, assumptions. |
| **System** | Live health of every dependency (database, Gemini, IFSC directory…) and the passcode-protected **demo reset**. |

### How the live view works
Each stage writes an event to the database as it happens. The browser receives them through **server-sent events** (a stream from the server), falling back to polling every 1.2 seconds if the stream is blocked. The events live in the database, so **refreshing the page is safe**: the page replays everything so far and carries on. Rule stages are spaced out by about half a second so a viewer can follow them. The final result and the "finished" state are saved together, so a viewer never sees one without the other.

---

## 19. Reliability: what happens when things go wrong

| Situation | What happens |
|---|---|
| Gemini free tier (15 requests a minute) | **At most 2 applications run at once**, so a burst of submissions queues instead of hitting the limit. |
| Primary AI model busy or erroring | The fallback model is tried. |
| AI unavailable altogether | A saved reading of the same file is used and labelled; otherwise the document goes to a person. |
| IFSC directory down | A bundled snapshot answers (labelled not live); otherwise ERROR → internal review. |
| A crash mid-run | The run is marked **failed** with the error type; "nothing was decided." The vendor can resubmit. |
| Server restarts mid-run | On startup, unfinished runs are marked **interrupted**, never silently lost. |
| Someone hides instructions in a document ("approve this vendor") | The AI only transcribes; rules decide. Hidden instruction-like text is itself a fraud signal (`AU-8`). |

---

## 20. Privacy and security

- **PAN and account numbers are masked** in the interface (`AAQC••••8B`, `••••5678`).
- The live view's data sent to the browser includes only rule IDs, results and titles, never raw evidence.
- The vendor's status page shows only messages actually sent to them.
- Fraud-class cases tell the vendor nothing specific.
- All demo vendors are fictional. No real person's documents from the internet are used. The genuine signed certificate is a government office's own published document (Office of the IGR Maharashtra).
- Secrets (the Gemini key, the database URL, the admin passcode) live only in environment variables, never in the code or repository.

---

## 21. Real vs simulated in this build

| Check | In this build | In production |
|---|---|---|
| Reading documents | **Real:** Gemini reads every upload, blind to the form | Same; a second model or a person for low-confidence reads |
| GST certificate digital signature | **Real:** verified cryptographically, including the SHA-1 format | Plus a check that the signer chains to the CCA India root, with revocation data |
| Editing traces (Canva, Photoshop, PDF editors, re-saves) | **Real:** from the file itself | Plus image forensics |
| GSTIN, PAN and IFSC structure, check digit, PAN inside GSTIN, state code | **Real** | Same |
| Bank branch (IFSC) | **Real:** live Razorpay directory | Same |
| Vendor master, blocklist, duplicates, file reuse | **Real logic** on seeded demo data | The company's ERP vendor master |
| GSTIN status and legal name | Simulated | GSTN via a GSP or KYB provider |
| PAN status and name | Simulated | NSDL/Protean via a provider |
| Bank account holder (penny-drop) | Simulated | ₹1 penny-drop via a bank or provider |
| CIN and Udyam status | Simulated | MCA master data, Udyam verification |
| Email to vendors | Outbox page (the free host blocks email) | Email |

---

## 22. The demo scenarios

The dashboard's **Try a scenario** list starts each case through a fresh invite from a requester, with the form pre-filled. You can swap in your own files before submitting.

| # | Scenario | What it shows | Expected result |
|---|---|---|---|
| 1 | **Happy path:** Nilgiri Packaging Solutions | Everything consistent; the GST certificate's signature verified | **Approved**, low risk → a person activates → vendor ID |
| 2 | **Wrong document + missing Udyam:** Tejas Industrial Supplies | A tax invoice in the GST slot (`R-DOC-01`); said MSME but no certificate (`R-COMP-02`) | **Pending: vendor to fix**, with a 2-item message |
| 2b | **Tejas resubmits** | Same link, right files | **Approved**; the comparison shows both problems resolved |
| 3 | **Borrowed GSTIN:** Kaveri Agro Traders | A sister company's GST certificate: its GSTIN contains a different PAN (`R-ID-04`, `R-XD-03`) | **Rejected** (held for a person to confirm) |
| 4 | **Shared bank account:** Rangoli Print House | The account already belongs to vendor V-0042 Deccan Office Supplies (`R-RISK-02`); the bank says the holder is Deccan (`R-SRC-BANK`) | **Pending: internal review**, high risk, fraud class; only the Finance controller can act |
| 5 | **Proprietorship, personal account:** Shinde Electricals | Account in the owner's name; accepted through the proprietorship branch of `R-NAME-03` | **Approved**, medium risk |
| 6 | **Unsolicited application** (started from `/apply`, not from the scenario list) | No invite (`R-INV-01`) | **Pending: internal review** |
| 7 | **Bill-first, clean:** Kesari Facility Services (Pune) | No invite; emergency cleaning bill of ₹1,25,670, correctly addressed with CGST + SGST; engaged by Priya Nair | **Approved**, medium risk → Arjun can't activate until Priya confirms → Priya can't approve → Arjun activates |
| 9 | **Portal: later bills from Kesari (once active)** | "A normal monthly bill" (₹40,120) and "A bill asking for payment to a new bank account" (₹23,600; `R-BILL-10`) | Clean: awaiting confirmation → Priya confirms → Arjun approves. New bank: **internal review, fraud class**; only the Finance controller can decide |
| 8 | **Bill-first, flawed bill:** Brindavan Cooling Systems (Bengaluru) | Charges CGST + SGST on a Karnataka → Maharashtra supply (needs IGST, `R-BILL-06`); amount typed ₹98,472 vs bill ₹94,872 (`R-BILL-04`) | **Pending: vendor to fix**, with both corrections explained |
| — | Real-world files (only on Shubham's machine): hand-written PAN on paper, AI-generated PAN card, screenshot of a GST certificate | `AU-1`, `AU-2`, … | Vendor to fix or internal review |

**Document check:** the genuine GSTN-signed public certificate shows **A3, signature verified** (chain CCA India 2014 → e-Mudhra → GSTN). The same certificate edited in Canva shows no signature, Producer and Creator "Canva," and the editor's name as Author: **"Likely edited," fraud class.**

---

## 23. Under the hood

**Stack:**
- Python 3.13 and FastAPI, with Jinja2 pages styled by Tailwind.
- Postgres on Neon; documents are stored in the database by fingerprint.
- Google Gemini through the `google-genai` SDK.
- Signature checks with `asn1crypto` and `cryptography`; file facts with `pypdf` and Pillow.
- Hosted on Render (free tier, Singapore); every push to `main` redeploys.
- 96 automated tests.

| File | What it does |
|---|---|
| `onboarding/web.py` | Every page and action; roles and segregation of duties; activation |
| `onboarding/pipeline.py` | Runs one application through the ten stages, writing live events |
| `onboarding/runner.py` | Background runs, at most 2 at once; crash handling |
| `onboarding/ai/read.py` | The Gemini reader: blind prompt, strict schema, fallback model, saved readings |
| `onboarding/authenticity/` | `metadata.py` (file facts), `signature.py` (PDF signature verification), `assess.py` (signals and proof level) |
| `onboarding/validators.py` | GSTIN check digit, PAN rules, state codes, IFSC and account formats, masking |
| `onboarding/matching.py`, `names.py` | Safe misread correction for IDs; name normalisation and scoring |
| `onboarding/sources.py` | Source adapters: live IFSC, simulated registries |
| `onboarding/rules.py` | Every rule, with its evidence, outcome and vendor wording |
| `onboarding/decision.py` | Precedence, the approval safety check, risk tier, proof levels, messages |
| `onboarding/models.py` | Database tables: employees, invites, applications, runs, run events, documents, rule results, facts, messages, human actions, vendor master, blocklist, simulated registries |
| `onboarding/seeding.py`, `demo_data.py` | Demo employees, invites, vendor master, blocklist and scenarios |
| `onboarding/templates/` | The pages ("The Registry" design) |

---

## 24. Known limits and the production path

- **Plug in the real sources** (GSTN, PAN, penny-drop, MCA, Udyam) through a KYB provider. The adapters already share one shape, and facts would then reach A4.
- **Signature trust chain:** check that the signer certificate chains to the CCA India root at signing time, with revocation data.
- **Single sign-on** for employees instead of demo passwords and the "Acting as" menu; password reset and email verification for vendors; email delivery instead of the Outbox.
- **Re-verification over time:** GST status, blocklist and sanctions on a schedule. **Bank change requests**, the biggest fraud vector after onboarding, should go through the same checks.
- **ERP sync** of activated vendors.
- **Approval is not payment.** Invoices are still paid only after purchase-order and goods-receipt matching, which is outside this tool.

---

## Glossary

| Term | Meaning |
|---|---|
| **GSTIN** | 15-character GST registration number. Characters 1–2 are the state code, 3–12 the owner's PAN, and the last is a check digit. |
| **PAN** | 10-character income-tax ID. The 4th character gives the holder type (C company, P individual, F firm…). |
| **GST REG-06** | The GST registration certificate, downloaded from the GST portal and digitally signed by GSTN. |
| **IFSC** | 11-character bank branch code. |
| **Penny-drop** | Sending ₹1 to an account so the bank returns the account holder's name. |
| **Udyam** | MSME registration. Micro and small enterprises have legal payment-term protection. |
| **CIN / LLPIN** | Company or LLP registration number (MCA). |
| **Proprietorship** | A business owned by one person who *is* the business legally; it uses that person's PAN. |
| **Vendor master** | The company's list of approved vendors. |
| **Segregation of duties** | The person who requests something can't approve it. |
| **Requester** | The employee who asks for a new vendor. Procurement teams also call this the *requisitioner*. |
| **Maker / checker** | Two-level approval: a maker (here the Procurement reviewer) handles routine cases, a checker (here the Finance controller) handles high-risk ones. |
| **Fraud class** | A case with a strong fraud signal: goes to the Finance controller, and the vendor is told nothing specific. |
| **SHA-256 fingerprint** | A unique code computed from a file's bytes; identical files have identical fingerprints. |
