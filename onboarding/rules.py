"""The rule engine: every check is deterministic code; every result carries its evidence.

Outcome codes if a rule fails (docs/PRODUCT.md §10):
  REJECT  - cannot be fixed in place (identity conflict, blocklist); a human confirms
  REVIEW  - a person must judge (fraud signals, borderline names, possible duplicates, errors)
  VENDOR  - the vendor can fix it; tell them exactly what to send
  WARN    - shown to the reviewer; no effect on status
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from onboarding import matching as M
from onboarding import validators as V
from onboarding.ai.read import DocRead, FieldReading
from onboarding.authenticity.assess import Authenticity
from onboarding.sources import SourceResult

PASS, FAIL, WARN, SKIPPED, ERROR = "PASS", "FAIL", "WARN", "SKIPPED", "ERROR"
SLOT_TYPES = {
    "gst_certificate": {"GST_CERTIFICATE"},
    "pan_card": {"PAN_CARD"},
    "bank_proof": {"CANCELLED_CHEQUE", "BANK_LETTER"},
    "udyam_certificate": {"UDYAM_CERTIFICATE"},
    "invoice": {"TAX_INVOICE"},
}
SLOT_LABEL = {"gst_certificate": "GST registration certificate", "pan_card": "PAN card",
              "bank_proof": "cancelled cheque or bank letter", "udyam_certificate": "Udyam (MSME) certificate",
              "invoice": "bill (tax invoice)"}
SLOT_TITLE = {"gst_certificate": "GST certificate", "pan_card": "PAN card", "bank_proof": "Bank proof", "udyam_certificate": "Udyam certificate",
              "invoice": "Bill"}
DOC_LABEL = {"GST_CERTIFICATE": "GST certificate", "PAN_CARD": "PAN card", "CANCELLED_CHEQUE": "cancelled cheque",
             "BANK_LETTER": "bank letter", "UDYAM_CERTIFICATE": "Udyam certificate", "TAX_INVOICE": "tax invoice",
             "AADHAAR": "Aadhaar card", "OTHER": "different document"}
FIELD_LABEL = {"legal_name": "Legal name", "gstin": "GSTIN", "pan": "PAN", "address": "Address", "city": "City",
               "state": "State", "pin": "PIN code", "contact_name": "Contact name", "contact_email": "Contact email",
               "alt_contact_name": "Alternate contact name", "alt_contact_email": "Alternate contact email", "alt_contact_phone": "Alternate contact phone",
               "bank_holder": "Account holder name", "bank_account": "Bank account number", "ifsc": "IFSC",
               "business_type": "Business type", "cin": "CIN", "llpin": "LLPIN", "proprietor_name": "Proprietor's name",
               "udyam_no": "Udyam number", "bill_invoice_number": "Invoice number", "bill_amount": "Bill amount",
               "bill_description": "What the work was", "bill_engaged_by": "Who at our company engaged you"}


@dataclass
class R:
    rule_id: str
    layer: str
    result: str
    title: str
    outcome: str = ""            # if FAIL
    evidence: dict = field(default_factory=dict)
    vendor_text: str = ""        # what to tell the vendor (VENDOR outcome)
    internal: str = ""           # what the reviewer should know
    fraud: bool = False          # fraud class -> neutral vendor message

    def __post_init__(self):
        # R(id, layer, PASS, title, {evidence}) is a natural way to write a passing rule.
        if isinstance(self.outcome, dict):
            self.evidence, self.outcome = {**self.outcome, **self.evidence}, ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocInfo:
    slot: str
    filename: str
    sha256: str
    mime: str
    read: DocRead | None
    read_origin: str              # live | cache | cache-fallback | failed
    auth: Authenticity | None


@dataclass
class Context:
    form: dict
    docs: dict[str, DocInfo]
    invite: dict | None = None            # {status, company_name, expires_at, application_id, sponsor}
    application_id: int | None = None
    sources: dict[str, SourceResult] = field(default_factory=dict)
    master: list[dict] = field(default_factory=list)       # vendor-master rows sharing PAN/GSTIN/account
    blocklist: list[dict] = field(default_factory=list)    # matching blocklist rows
    reused_files: list[dict] = field(default_factory=list)  # same file in another vendor's application
    bill: dict | None = None              # bill-first registration: {engaged_employee, engaged_department, duplicates}
    as_of: datetime | None = None         # when the rules are evaluated (frozen, so a saved decision replays exactly)


# --- helpers ----------------------------------------------------------------------------
def _now(ctx: "Context") -> datetime:
    """When the rules are evaluated: frozen in ctx.as_of (stored times without a zone are UTC), else now."""
    t = ctx.as_of or datetime.now(timezone.utc)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def fld(d: DocInfo | None, name: str) -> FieldReading | None:
    if not d or not d.read:
        return None
    return next((f for f in d.read.fields if f.name == name and (f.value or f.legibility != "not_present")), None)


def val(d: DocInfo | None, name: str) -> tuple[str | None, str]:
    f = fld(d, name)
    return (f.value, f.legibility) if f else (None, "not_present")


def usable(d: DocInfo | None, slot: str) -> bool:
    return bool(d and d.read and d.read.doc_type in SLOT_TYPES[slot])


def constitution_type(text: str) -> str | None:
    t = (text or "").lower()
    if "private limited" in t:
        return "PVT_LTD"
    if "public limited" in t:
        return "PUBLIC_LTD"
    if "limited liability partnership" in t or t.strip() == "llp":
        return "LLP"
    if "partnership" in t:
        return "PARTNERSHIP"
    if "proprietor" in t:
        return "PROPRIETORSHIP"
    return None


def required_fields(form: dict) -> list[str]:
    req = ["legal_name", "gstin", "pan", "address", "city", "state", "pin", "contact_name", "contact_email",
           "bank_holder", "bank_account", "ifsc", "business_type"]
    bt = form.get("business_type")
    if bt in ("PVT_LTD", "PUBLIC_LTD"):
        req.append("cin")
    if bt == "LLP":
        req.append("llpin")
    if bt == "PROPRIETORSHIP":
        req.append("proprietor_name")
    if form.get("msme"):
        req.append("udyam_no")
    if form.get("bill_mode"):
        req += ["bill_engaged_by"]   # everything else about the bill is read from the bill itself
    return req


def required_docs(form: dict) -> list[str]:
    return (["gst_certificate", "pan_card", "bank_proof"] + (["udyam_certificate"] if form.get("msme") else [])
            + (["invoice"] if form.get("bill_mode") else []))


def reupload(slot: str, what: str) -> str:
    return f"We couldn't clearly read the {what} on your {SLOT_LABEL[slot]}. Please upload a clearer, complete copy (whole page, nothing cropped or covered)."


# --- the rules ------------------------------------------------------------------------------
def evaluate(ctx: Context) -> list[R]:
    f, docs, out = ctx.form, ctx.docs, []
    add = out.append
    bt = f.get("business_type", "")
    pan, gstin = V.normalise_id(f.get("pan", "")), V.normalise_id(f.get("gstin", ""))
    individual = V.pan_code(pan) == "P"

    # Layer 0: invite ------------------------------------------------------------------
    inv = ctx.invite
    if not inv and ctx.bill is not None:
        who = ctx.bill.get("engaged_employee")
        add(R("R-INV-01", "invite", WARN, "No invite: the vendor registered with a bill for work already done"
              + (f". {who} must confirm the engagement before the vendor is activated" if who else ""), "WARN",
              {"engaged_by": f.get("bill_engaged_by", "")},
              internal="Bill-first registration. Nobody vouched for this vendor in advance; the employee the vendor named must confirm."))
    elif not inv:
        add(R("R-INV-01", "invite", FAIL, "Application did not come through an employee's invite", "REVIEW",
              internal="Unsolicited application: no valid invite token. Never auto-approved.", fraud=True))
    else:
        expired = inv.get("expires_at") and inv["expires_at"] < _now(ctx)
        other_app = inv.get("application_id") and ctx.application_id and inv["application_id"] != ctx.application_id
        if inv.get("status") in ("revoked",) or expired or other_app:
            why = "expired" if expired else ("already used by another application" if other_app else inv.get("status"))
            add(R("R-INV-01", "invite", FAIL, f"Invite link is {why}", "REVIEW", {"invite_status": why},
                  internal="The invite can't vouch for this application.", fraud=bool(other_app)))
        else:
            add(R("R-INV-01", "invite", PASS, f"Requested by {inv.get('sponsor', 'an employee')}: {inv.get('reason', '')}"))
        nm = M.compare_name(inv.get("company_name", ""), f.get("legal_name", ""), individual=False)
        if nm.status == M.MATCH or (bt == "PROPRIETORSHIP" and M.compare_name(inv.get("company_name", ""), f.get("proprietor_name", ""), individual=True).status == M.MATCH):
            add(R("R-INV-02", "invite", PASS, "The business that applied is the one that was invited", {"invited": inv.get("company_name"), "applied": f.get("legal_name"), "score": nm.score}))
        else:
            add(R("R-INV-02", "invite", FAIL, "The business that applied is not the one that was invited", "REVIEW",
                  {"invited": inv.get("company_name"), "applied": f.get("legal_name"), "score": nm.score},
                  internal="Invite link may have been forwarded or reached the wrong company.", fraud=True))

    # Layer 1: scope gate ------------------------------------------------------------------
    if (f.get("country") or "India").strip().lower() != "india":
        country = f.get("country", "")
        add(R("R-SCOPE-01", "scope", FAIL, f"Vendor registered outside India ({country})", "REVIEW",
              vendor_text="Vendors registered outside India are onboarded by our team directly; we'll contact you within 3 business days. No action is needed now."))
        return out
    if not f.get("gst_registered", True):
        add(R("R-SCOPE-02", "scope", FAIL, "Vendor is not GST-registered", "REVIEW",
              vendor_text="Vendors without a GST registration are onboarded by our team directly; we'll contact you within 3 business days."))
        return out
    add(R("R-SCOPE-01", "scope", PASS, "India-based, GST-registered vendor (automated path)"))

    # Layer 2: completeness ---------------------------------------------------------------
    missing = [k for k in required_fields(f) if not str(f.get(k) or "").strip()]
    add(R("R-COMP-01", "completeness", FAIL if missing else PASS,
          "Required details missing" if missing else "All required details provided", "VENDOR",
          {"missing": missing}, vendor_text=f"Please fill in: {', '.join(FIELD_LABEL.get(m, m) for m in missing)}." if missing else ""))
    missing_docs = [s for s in required_docs(f) if s not in docs]
    udyam_note = (f" You told us you're MSME-registered ({f.get('udyam_no')}); please attach the Udyam certificate, or change your answer if you're not MSME-registered."
                  if "udyam_certificate" in missing_docs else "")
    add(R("R-COMP-02", "completeness", FAIL if missing_docs else PASS,
          "Required documents missing" if missing_docs else "All required documents uploaded", "VENDOR",
          {"missing": missing_docs},
          vendor_text=(f"Please upload: {', '.join(SLOT_LABEL[s] for s in missing_docs)}.{udyam_note}") if missing_docs else ""))

    # Layer 3: document reading + authenticity -----------------------------------------------
    for slot, d in docs.items():
        if not d.read:
            add(R("R-DOC-00", "documents", ERROR, f"Automatic reading failed for the {SLOT_LABEL.get(slot, slot)}", "REVIEW",
                  {"file": d.filename}, internal="AI reading unavailable; review the document manually."))
            continue
        if d.read.doc_type not in SLOT_TYPES.get(slot, set()):
            got = DOC_LABEL.get(d.read.doc_type, d.read.doc_type)
            add(R("R-DOC-01", "documents", FAIL, f"Wrong document in the {SLOT_LABEL[slot]} slot: it's a {got}", "VENDOR",
                  {"file": d.filename, "detected": d.read.doc_type, "evidence": d.read.doc_type_evidence},
                  vendor_text=f"The file you uploaded as your {SLOT_LABEL[slot]} ({d.filename}) appears to be a {got}. Please upload your {SLOT_LABEL[slot]}"
                              + (" (Form GST REG-06, downloadable from the GST portal)." if slot == "gst_certificate" else ".")))
        else:
            add(R("R-DOC-01", "documents", PASS, f"{SLOT_TITLE[slot]} recognised", {"file": d.filename, "read_from": d.read_origin}))
        if d.auth:
            for s in d.auth.signals:
                if s.severity in ("info",):
                    continue
                outcome = {"vendor": "VENDOR", "review": "REVIEW", "fraud": "REVIEW", "warn": "WARN"}[s.severity]
                add(R(f"R-{s.code}", "authenticity", WARN if outcome == "WARN" else FAIL, f"{SLOT_TITLE.get(slot, slot)}: {s.title}",
                      outcome, {"file": d.filename, "detail": s.detail}, vendor_text=s.vendor_text, internal=s.detail, fraud=s.severity == "fraud"))

    gst_doc = docs.get("gst_certificate") if usable(docs.get("gst_certificate"), "gst_certificate") else None
    pan_doc = docs.get("pan_card") if usable(docs.get("pan_card"), "pan_card") else None
    bank_doc = docs.get("bank_proof") if usable(docs.get("bank_proof"), "bank_proof") else None
    udyam_doc = docs.get("udyam_certificate") if usable(docs.get("udyam_certificate"), "udyam_certificate") else None

    # Layer 4: identifiers typed in the form ------------------------------------------------
    if gstin:
        ok_fmt, ok_chk = V.gstin_format_ok(gstin), V.gstin_checksum_ok(gstin)
        add(R("R-ID-01", "identifiers", PASS if ok_fmt else FAIL, "GSTIN format" + ("" if ok_fmt else " is not standard"), "VENDOR", {"gstin": gstin},
              vendor_text="" if ok_fmt else f"The GSTIN '{gstin}' isn't in the standard 15-character format (e.g. 29ABCDE1234F1Z5). Please re-enter it exactly as shown on your GST certificate."))
        if ok_fmt:
            add(R("R-ID-02", "identifiers", PASS if ok_chk else FAIL, "GSTIN check digit " + ("valid" if ok_chk else "fails: likely a typing error"), "VENDOR", {"gstin": gstin},
                  vendor_text="" if ok_chk else f"The GSTIN '{gstin}' fails the official check-digit test, which usually means a typing error. Please copy it exactly from your GST certificate."))
        emb = V.gstin_embedded_pan(gstin)
        add(R("R-ID-04", "identifiers", PASS if emb == pan else FAIL,
              "PAN inside the GSTIN matches the PAN entered" if emb == pan else f"PAN inside the GSTIN ({emb}) differs from the PAN entered ({pan})", "VENDOR",
              {"gstin_pan": emb, "pan": pan},
              vendor_text="" if emb == pan else f"Your GSTIN contains the PAN {emb}, but the PAN you entered is {pan}. A GSTIN is always issued on the holder's own PAN, so please check both numbers."))
        code, sname = V.gstin_state(gstin)
        declared = V.state_code_for_name(f.get("state", ""))
        okst = declared == code
        add(R("R-ID-05", "identifiers", PASS if okst else FAIL, f"GSTIN state ({sname}) " + ("matches" if okst else "differs from") + f" the declared state ({f.get('state')})", "VENDOR",
              {"gstin_state": sname, "declared": f.get("state")},
              vendor_text="" if okst else f"Your GSTIN is registered in {sname} (code {code}), but you gave a principal place of business in {f.get('state')}. Please provide the GSTIN for the state you'll invoice us from, with that state's address."))
    pin = str(f.get("pin") or "").strip()
    if pin:
        from onboarding.pincode import pin_problem
        why = pin_problem(pin, f.get("state", ""))
        add(R("R-ID-10", "identifiers", FAIL if why else PASS, "PIN code fits the declared state" if not why else f"PIN code doesn't fit the address: {why}",
              "VENDOR", {"pin": pin, "state": f.get("state")},
              vendor_text=f"{why} Please check the PIN code and state of your registered address." if why else ""))
    if pan:
        okp = V.validate_pan(pan)
        add(R("R-ID-03", "identifiers", PASS if okp else FAIL, "PAN format" + ("" if okp else " is not standard"), "VENDOR", {"pan": pan},
              vendor_text="" if okp else f"The PAN '{pan}' isn't in the standard format (5 letters, 4 digits, 1 letter). Please check it."))
        exp = V.EXPECTED_PAN_CODE.get(bt)
        got = V.pan_code(pan)
        if exp:
            okt = got == exp
            add(R("R-ID-06", "identifiers", PASS if okt else FAIL,
                  f"PAN holder type ({V.PAN_HOLDER_TYPES.get(got, got)}) " + ("fits" if okt else "doesn't fit") + f" the business type ({V.BUSINESS_TYPES.get(bt, bt)})",
                  "VENDOR", {"pan_type": got, "expected": exp},
                  vendor_text="" if okt else f"You selected '{V.BUSINESS_TYPES.get(bt, bt)}', but PAN {pan} is issued to a {V.PAN_HOLDER_TYPES.get(got, 'different holder type')}. Please correct the business type, or give the PAN of the business."))
    if bt in ("PVT_LTD", "PUBLIC_LTD") and f.get("cin"):
        okc = V.cin_ok(f["cin"], bt)
        add(R("R-ID-07", "identifiers", PASS if okc else FAIL, "CIN format fits the business type" if okc else "CIN doesn't look right for this business type", "VENDOR",
              {"cin": f["cin"]}, vendor_text="" if okc else f"Your CIN '{f['cin']}' doesn't look right for a {V.BUSINESS_TYPES[bt]}. Please copy it from your certificate of incorporation."))
    if f.get("ifsc"):
        oki = V.validate_ifsc(f["ifsc"])
        add(R("R-ID-08", "identifiers", PASS if oki else FAIL, "IFSC format" + ("" if oki else " is invalid"), "VENDOR", {"ifsc": f["ifsc"]},
              vendor_text="" if oki else f"The IFSC '{f['ifsc']}' isn't valid (11 characters, 5th character is zero). It's printed on your cheque book."))
    if f.get("bank_account"):
        oka = V.account_number_ok(f["bank_account"])
        add(R("R-ID-09", "identifiers", PASS if oka else FAIL, "Account number format" + ("" if oka else " is invalid"), "VENDOR",
              vendor_text="" if oka else "Please check your bank account number; it should contain 9 to 18 digits."))

    # Layer 5a: bank branch (live) ------------------------------------------------------------
    ifsc_src = ctx.sources.get("ifsc")
    if ifsc_src:
        if ifsc_src.status == "FOUND":
            add(R("R-BANK-01", "bank", PASS, f"IFSC belongs to {ifsc_src.data.get('BANK')}, {ifsc_src.data.get('BRANCH')}", evidence={"source": ifsc_src.source, **ifsc_src.data}))
        elif ifsc_src.status == "NOT_FOUND":
            add(R("R-BANK-01", "bank", FAIL, "IFSC doesn't match any bank branch", "VENDOR", {"source": ifsc_src.source},
                  vendor_text=f"IFSC {f.get('ifsc')} doesn't match any bank branch we can find (banks that merged issue new IFSCs). Please check the IFSC printed on your cheque."))
        else:
            add(R("R-BANK-01", "bank", ERROR, "Bank branch lookup unavailable", "REVIEW", {"note": ifsc_src.note}, internal="Re-run the check later."))

    # Layer 5b: cross-document consistency ----------------------------------------------------
    if gst_doc:
        v, leg = val(gst_doc, "gstin")
        m = M.compare_id("gstin", gstin, v, leg)
        _xd(add, "R-XD-01", "GSTIN on the form vs the GST certificate", m, "gst_certificate", "GSTIN",
            f"The GSTIN on your form ({gstin}) is different from the one on your GST certificate ({m.doc_value}). Please correct whichever is wrong.")
    else:
        add(R("R-XD-01", "consistency", SKIPPED, "No GST certificate to compare against"))
    if pan_doc:
        v, leg = val(pan_doc, "pan")
        m = M.compare_id("pan", pan, v, leg)
        _xd(add, "R-XD-02", "PAN on the form vs the PAN card", m, "pan_card", "PAN",
            f"The PAN on your form ({pan}) is different from the one on the PAN card you uploaded ({m.doc_value}). Please correct whichever is wrong.")
    else:
        add(R("R-XD-02", "consistency", SKIPPED, "No PAN card to compare against"))

    # Identity conflict: the certificate's (check-digit-valid) GSTIN embeds a PAN that differs from
    # the PAN card, while the PAN card agrees with the form -> two different legal entities.
    if gst_doc and pan_doc:
        cv, cleg = val(gst_doc, "gstin")
        pv, pleg = val(pan_doc, "pan")
        cert_gstin = V.normalise_id(cv or "")
        if cleg == "clear" and V.gstin_checksum_ok(cert_gstin) and pleg == "clear":
            card_pan = M.correct(pv or "", M.PAN_CLASSES)[0]
            cert_pan = V.gstin_embedded_pan(cert_gstin)
            if card_pan == pan and cert_pan != pan:
                gst_name = val(gst_doc, "legal_name")[0] or "another entity"
                add(R("R-XD-03", "consistency", FAIL, f"GST registration belongs to a different legal entity ({gst_name})", "REJECT",
                      {"certificate_gstin": cert_gstin, "pan_in_gstin": cert_pan, "pan_card": card_pan, "gst_legal_name": gst_name},
                      vendor_text=(f"The GST registration you provided ({cert_gstin}) belongs to {gst_name.title()}, a different legal entity from the applicant "
                                   f"({f.get('legal_name')}, PAN {pan}). We can only onboard a business using its own GST registration. If {f.get('legal_name')} has its own GSTIN, "
                                   f"please start a new application with it."),
                      internal="Check-digit-valid GSTIN on the certificate; PAN card and form agree on a different PAN. Two independent sources: a misread is very unlikely."))
            else:
                add(R("R-XD-03", "consistency", PASS, "GST certificate and PAN card describe the same legal entity"))
    if bank_doc:
        v, leg = val(bank_doc, "account_number")
        m = M.compare_account(f.get("bank_account", ""), v, leg)
        _xd(add, "R-XD-04", "Account number on the form vs the bank proof", m, "bank_proof", "account number",
            "The account number on your form doesn't match your cancelled cheque. Please correct it, or upload the bank proof for the account you want paid into.")
        v, leg = val(bank_doc, "ifsc")
        if v:
            m = M.compare_id("ifsc", f.get("ifsc", ""), v, leg)
            _xd(add, "R-XD-04b", "IFSC on the form vs the bank proof", m, "bank_proof", "IFSC",
                f"The IFSC on your form ({f.get('ifsc')}) doesn't match your cancelled cheque ({m.doc_value}). Please correct it.")
    if gst_doc and (ct := constitution_type(val(gst_doc, "constitution")[0] or "")):
        okk = ct == bt
        add(R("R-XD-05", "consistency", PASS if okk else FAIL, "Constitution on the GST certificate " + ("matches" if okk else "differs from") + " the business type",
              "VENDOR", {"certificate": val(gst_doc, "constitution")[0], "declared": bt},
              vendor_text="" if okk else f"Your GST certificate lists your business as '{val(gst_doc, 'constitution')[0]}', but you selected '{V.BUSINESS_TYPES.get(bt, bt)}'. Please correct the business type or upload the right certificate."))

    # Layer 5c: names ----------------------------------------------------------------------------
    legal = f.get("legal_name", "")
    prop = f.get("proprietor_name", "")
    if gst_doc:
        gl, gleg = val(gst_doc, "legal_name")
        tn, _ = val(gst_doc, "trade_name")
        best = max((M.compare_name(legal, c, individual=False, legibility=gleg) for c in (gl, tn) if c), key=lambda r: r.score, default=None)
        _name(add, "R-NAME-01", "Business name vs the GST certificate", best, "VENDOR", "gst_certificate",
              f"The business name you entered ('{legal}') doesn't match the name on your GST certificate ('{gl}'). Please enter your name exactly as registered for GST.")
    name02_ok = False
    if pan_doc:
        pn, pleg = val(pan_doc, "name_on_card")
        expected = prop if bt == "PROPRIETORSHIP" else legal
        r2 = M.compare_name(expected, pn, individual=individual, legibility=pleg) if pn or pleg != "not_present" else None
        name02_ok = bool(r2 and r2.status == M.MATCH)
        _name(add, "R-NAME-02", f"Name on the PAN card vs the {'proprietor' if bt == 'PROPRIETORSHIP' else 'legal'} name", r2, "VENDOR", "pan_card",
              f"The name on the PAN card ('{pn}') doesn't match {'the proprietor' if bt == 'PROPRIETORSHIP' else 'the business'} ('{expected}'). Please check that you uploaded the right PAN card.")
    if bank_doc:
        holder, hleg = val(bank_doc, "account_holder_name")
        if not holder and hleg == "not_present":
            add(R("R-DOC-03", "documents", FAIL, "Bank proof doesn't show the account holder's name", "VENDOR",
                  vendor_text="Your cancelled cheque doesn't show the account holder's name. Please upload a cheque with the name printed, or a letter from your bank confirming the holder name, account number and IFSC."))
            holder, hleg = f.get("bank_holder", ""), "clear"
        cands = [("legal name", legal)]
        branch = bt == "PROPRIETORSHIP" and individual and name02_ok
        if branch:
            cands += [("proprietor's name", prop), ("GST legal name", val(gst_doc, "legal_name")[0] if gst_doc else "")]
        scored = [(lbl, M.compare_name(c, holder, individual=individual and lbl != "legal name", legibility=hleg)) for lbl, c in cands if c]
        lbl, best = max(scored, key=lambda x: x[1].score)
        note = f"matched the {lbl}" + (" (proprietorship: the owner and the business are one legal person)" if branch and lbl != "legal name" else "")
        if best.status == M.MATCH:
            add(R("R-NAME-03", "names", PASS, f"Account holder '{holder}' {note}", evidence={"holder": holder, "score": best.score, "candidate": lbl}))
        elif best.status == M.PARTIAL:
            add(R("R-NAME-03", "names", FAIL, f"Account holder '{holder}' only partly matches ({best.score})", "REVIEW",
                  {"holder": holder, "score": best.score}, internal="Borderline holder name: verify the account belongs to the vendor."))
        elif best.status == M.UNREADABLE:
            add(R("R-NAME-03", "names", FAIL, "Account holder name couldn't be read", "VENDOR", vendor_text=reupload("bank_proof", "account holder name")))
        else:
            add(R("R-NAME-03", "names", FAIL, f"Account holder '{holder}' doesn't match the business ({best.score})", "VENDOR",
                  {"holder": holder, "score": best.score},
                  vendor_text=f"Payments can only go to an account held in your business's name. The account holder on your bank proof is '{holder}', which doesn't match '{legal}'. Please give an account in the business's name, with a cancelled cheque or bank letter showing it."))

    # Layer 6: sources (simulated in this build; labelled) --------------------------------------------
    names_ok = [legal] + ([prop] if bt == "PROPRIETORSHIP" else [])
    g = ctx.sources.get("gst")
    if g:
        if g.status != "FOUND":
            add(R("R-SRC-GST", "sources", FAIL, "GSTIN not found in the GST registry", "REVIEW", {"source": g.source}, internal="Possible fake or mistyped GSTIN."))
        elif g.data.get("status") != "Active":
            add(R("R-SRC-GST", "sources", FAIL, f"GSTIN status is {g.data.get('status')}", "REVIEW", {"source": g.source, **g.data}))
        else:
            reg_names = [g.data.get("legal_name"), g.data.get("trade_name")]
            ok = any(M.compare_name(n, rn, individual=individual).status == M.MATCH for n in names_ok for rn in reg_names if rn and n)
            add(R("R-SRC-GST", "sources", PASS if ok else FAIL, "GST registry: active, name " + ("matches" if ok else f"is '{g.data.get('legal_name')}'"),
                  "REVIEW", {"source": g.source, **g.data}, internal="" if ok else "Registry name differs from the applicant."))
    p = ctx.sources.get("pan")
    if p:
        if p.status != "FOUND":
            add(R("R-SRC-PAN", "sources", FAIL, "PAN not found in the PAN registry", "REVIEW", {"source": p.source}))
        else:
            ok = any(M.compare_name(n, p.data.get("name", ""), individual=individual).status == M.MATCH for n in names_ok if n)
            add(R("R-SRC-PAN", "sources", PASS if ok else FAIL, "PAN registry: valid, name " + ("matches" if ok else f"is '{p.data.get('name')}'"), "REVIEW", {"source": p.source, **p.data}))
            if p.data.get("aadhaar_linked") is False:
                add(R("R-SRC-PAN2", "sources", WARN, "PAN is inoperative (not linked to Aadhaar): TDS applies at the higher rate (20%)", "WARN", {"source": p.source}))
    b = ctx.sources.get("bank")
    if b:
        if b.status != "FOUND":
            add(R("R-SRC-BANK", "sources", WARN, "Account could not be confirmed at source (penny-drop)", "WARN", {"source": b.source}))
        else:
            holder = b.data.get("holder_name", "")
            cands = names_ok + ([val(gst_doc, "legal_name")[0]] if (gst_doc and bt == "PROPRIETORSHIP") else [])
            ok = any(M.compare_name(n, holder, individual=individual).status == M.MATCH for n in cands if n)
            add(R("R-SRC-BANK", "sources", PASS if ok else FAIL, f"Bank confirms the account holder is '{holder}'" + ("" if ok else ", not the applicant"),
                  "REVIEW", {"source": b.source, "holder": holder}, internal="" if ok else "The bank says this account belongs to someone else.", fraud=not ok))
    c = ctx.sources.get("cin")
    if c:
        add(R("R-SRC-CIN", "sources", PASS if c.status == "FOUND" else WARN,
              "Company registry: " + (f"{c.data.get('status')}, {c.data.get('name')}" if c.status == "FOUND" else "CIN not found"), "WARN", {"source": c.source, **c.data}))

    # Layer 7: risk (vendor master, blocklist, reused files) ------------------------------------------
    if ctx.blocklist:
        add(R("R-RISK-01", "risk", FAIL, "PAN, GSTIN or bank account is on the blocklist", "REJECT", {"hits": ctx.blocklist},
              vendor_text="After review, we're unable to proceed with your registration. If you believe this is a mistake, please contact procurement@nareenterprises.example.com.",
              internal=f"Blocklist reason: {ctx.blocklist[0].get('reason')}", fraud=True))
    else:
        add(R("R-RISK-01", "risk", PASS, "Not on the blocklist"))
    acct = f.get("bank_account", "")
    shared = [m for m in ctx.master if m["account"] == acct and m["ifsc"].upper() == f.get("ifsc", "").upper() and m["pan"] != pan]
    if shared:
        o = shared[0]
        add(R("R-RISK-02", "risk", FAIL, f"Bank account already on file for another vendor: {o['vendor_id']} {o['legal_name']}", "REVIEW",
              {"other_vendor": o["vendor_id"], "other_name": o["legal_name"], "other_pan": V.mask_pan(o["pan"]), "status": o["status"]},
              internal=(f"Account {V.mask_account(acct)} is already linked to {o['vendor_id']} {o['legal_name']} ({o['status']}). Possible causes: shared or third-party "
                        "account, doctored cheque, collusion, or a data error. Verify with the bank before deciding."), fraud=True))
    else:
        add(R("R-RISK-02", "risk", PASS, "Bank account not used by any other vendor"))
    dup = [m for m in ctx.master if m["pan"] == pan or m["gstin"] == gstin]
    if dup:
        add(R("R-RISK-03", "risk", FAIL, f"Already registered: {dup[0]['vendor_id']} {dup[0]['legal_name']}", "REVIEW", {"vendor": dup[0]["vendor_id"]},
              vendor_text="", internal="Possible duplicate vendor record (risk of double payment)."))
    if ctx.reused_files:
        add(R("R-RISK-04", "risk", FAIL, "A document was already submitted by a different applicant", "REVIEW", {"reused": ctx.reused_files},
              internal="Same file (SHA-256) in another vendor's application: possible template fraud.", fraud=True))

    # Layer 8: MSME ------------------------------------------------------------------------------------
    if f.get("msme") and udyam_doc:
        un, leg = val(udyam_doc, "udyam_number")
        okn = V.normalise_id(un or "") == V.normalise_id(f.get("udyam_no", ""))
        etype = (val(udyam_doc, "enterprise_type")[0] or "").upper()
        add(R("R-MSME-01", "msme", PASS if okn else FAIL, "Udyam number matches the certificate" if okn else "Udyam number differs from the certificate", "VENDOR",
              {"form": f.get("udyam_no"), "certificate": un, "type": etype},
              vendor_text="" if okn else f"The Udyam certificate you uploaded shows {un}, which doesn't match the number you entered ({f.get('udyam_no')}). Please check it."))
        if any(t in etype for t in ("MICRO", "SMALL")):
            add(R("R-MSME-02", "msme", WARN, f"{etype.title()} enterprise: pay within 15 days, or up to 45 days with a written agreement (MSMED Act s.15)", "WARN"))

    # Layer 9: the bill (bill-first registrations) --------------------------------------------------------
    if f.get("bill_mode"):
        _bill_rules(add, ctx, docs.get("invoice") if usable(docs.get("invoice"), "invoice") else None)
    return out


# --- bills ----------------------------------------------------------------------------------------------
BILL_HIGH_RISK = 10_00_000   # a single bill of Rs 10 lakh or more needs the Finance controller
BILL_MAX_AGE_DAYS = 365      # older bills risk losing the GST input credit: a person decides


def money(text) -> float | None:
    """'1,25,670.00', 'Rs. 1,25,670', 'INR 125670' -> 125670.0 (None if not a number)."""
    if text is None:
        return None
    t = str(text).replace(",", "").replace("\u20b9", "").replace("INR", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def inr(x: float | None) -> str:
    """Indian digit grouping: 125670 -> 'Rs 1,25,670.00'."""
    if x is None:
        return "-"
    whole, frac = f"{x:.2f}".split(".")
    neg = whole.startswith("-")
    whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{'-' if neg else ''}\u20b9{whole}.{frac}"


def _parse_any_date(text: str | None) -> datetime | None:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime((text or "").strip(), fmt)
        except ValueError:
            continue
    return None


def bill_fields_from_read(read) -> dict:
    """What the bill itself says, read by the AI, in the form's field names: the vendor doesn't retype it.
    Only clearly read values count (a partly read number would mislead the duplicate check)."""
    out = {"bill_invoice_number": "", "bill_invoice_date": "", "bill_amount": "", "bill_description": "", "bill_po": ""}
    if read is None:
        return out
    clear = {x.name: (x.value or "").strip() for x in read.fields if x.value and x.legibility == "clear"}
    some = {x.name: (x.value or "").strip() for x in read.fields if x.value and x.legibility in ("clear", "partial")}
    out["bill_invoice_number"] = clear.get("invoice_number", "").upper()
    d = _parse_any_date(clear.get("invoice_date"))
    out["bill_invoice_date"] = d.strftime("%Y-%m-%d") if d else clear.get("invoice_date", "")
    amt = money(clear.get("total_amount"))
    out["bill_amount"] = f"{amt:.2f}" if amt is not None else ""
    out["bill_description"] = some.get("work_description", "")
    out["bill_po"] = clear.get("po_number", "").upper()
    return out


def _bill_rules(add, ctx: Context, inv_doc: DocInfo | None) -> None:
    from onboarding.demo_data import BUYER  # the buying company (us)

    f = ctx.form
    bill = ctx.bill or {}
    gstin = V.normalise_id(f.get("gstin", ""))
    typed_amount = money(f.get("bill_amount"))
    from_doc = bool(f.get("bill_read_from_document"))   # the figures were read from the bill, not typed by the vendor

    # Who engaged the vendor: must be a real employee (they confirm it after the run).
    who = bill.get("engaged_employee")
    if who:
        add(R("R-BILL-09", "bill", PASS, f"Engaged by {who} ({bill.get('engaged_department', '')}): they will be asked to confirm",
              {"typed": f.get("bill_engaged_by"), "employee": who}))
    else:
        add(R("R-BILL-09", "bill", FAIL, f"Nobody called '{f.get('bill_engaged_by', '')}' works here", "REVIEW",
              {"typed": f.get("bill_engaged_by")},
              internal="The vendor named someone who isn't in the employee directory. Find out who engaged them before anything else."))

    # Same invoice already submitted (double billing).
    if bill.get("duplicates"):
        d = bill["duplicates"][0]
        add(R("R-BILL-08", "bill", FAIL, f"Invoice {f.get('bill_invoice_number')} was already submitted ({d['ref']})", "REVIEW",
              {"other_application": d["ref"]}, internal="Same seller GSTIN and invoice number on another application: possible double billing.", fraud=True))

    if not inv_doc:
        return  # wrong or missing invoice file: R-DOC-01 / R-COMP-02 already ask for it

    # Invoice number on the form vs the bill
    num, nleg = val(inv_doc, "invoice_number")
    if num and nleg == "clear":
        same = from_doc or V.normalise_id(num).replace("/", "").replace("-", "") == V.normalise_id(f.get("bill_invoice_number", "")).replace("/", "").replace("-", "")
        add(R("R-BILL-01", "bill", PASS if same else FAIL, f"Invoice number read from the bill: {num}" if from_doc else
              ("Invoice number matches the bill" if same else f"Invoice number differs from the bill ({num})"), "VENDOR",
              {"form": f.get("bill_invoice_number"), "invoice": num},
              vendor_text="" if same else f"The invoice number you entered ({f.get('bill_invoice_number')}) doesn't match the bill you uploaded ({num}). Please correct it."))
    elif nleg in ("partial", "unreadable"):
        add(R("R-BILL-01", "bill", FAIL, "Invoice number couldn't be read on the bill", "VENDOR", vendor_text=reupload("invoice", "invoice number")))

    # The bill is from this vendor
    sg, sleg = val(inv_doc, "seller_gstin")
    m = M.compare_id("gstin", gstin, sg, sleg)
    if m.status in (M.MATCH, M.MATCH_CORRECTED):
        add(R("R-BILL-02", "bill", PASS, "The bill is issued by this vendor (seller GSTIN matches)", {"seller_gstin": m.doc_value}))
    elif m.status == M.MISMATCH:
        add(R("R-BILL-02", "bill", FAIL, f"The bill was issued by a different GSTIN ({m.doc_value})", "REVIEW",
              {"seller_gstin": m.doc_value, "vendor_gstin": gstin},
              internal="The invoice belongs to another registration: a related company's bill, or someone else's invoice reused."))
    else:
        add(R("R-BILL-02", "bill", FAIL, "Seller GSTIN couldn't be read on the bill", "VENDOR", vendor_text=reupload("invoice", "seller GSTIN")))

    # The bill is addressed to us
    bg, bleg = val(inv_doc, "buyer_gstin")
    bm = M.compare_id("gstin", BUYER["gstin"], bg, bleg)
    to_us = (f"Please issue the bill to {BUYER['legal_name']}, GSTIN {BUYER['gstin']}, {BUYER['address']}. "
             "We can only pay, and claim GST credit on, a bill addressed to us.")
    if bm.status in (M.MATCH, M.MATCH_CORRECTED):
        add(R("R-BILL-03", "bill", PASS, f"The bill is addressed to us ({BUYER['legal_name']})"))
    elif bm.status == M.MISMATCH:
        add(R("R-BILL-03", "bill", FAIL, f"The bill is addressed to another GSTIN ({bm.doc_value})", "VENDOR", {"buyer_gstin": bm.doc_value},
              vendor_text=f"Your bill is addressed to GSTIN {bm.doc_value}, which isn't ours. " + to_us))
    elif bleg == "not_present":
        add(R("R-BILL-03", "bill", FAIL, "The bill doesn't show our GSTIN", "VENDOR", vendor_text="Your bill doesn't show our GSTIN. " + to_us))
    else:
        add(R("R-BILL-03", "bill", FAIL, "Buyer GSTIN couldn't be read on the bill", "VENDOR", vendor_text=reupload("invoice", "buyer GSTIN")))

    # Amount typed vs the bill's total
    total_txt, tleg = val(inv_doc, "total_amount")
    total = money(total_txt)
    if total is None:
        add(R("R-BILL-04", "bill", FAIL, "The bill's total couldn't be read", "VENDOR", vendor_text=reupload("invoice", "total amount")))
    elif typed_amount is not None and abs(total - typed_amount) <= 1:
        add(R("R-BILL-04", "bill", PASS, f"Total read from the bill: {inr(total)}" if from_doc else f"Amount entered matches the bill: {inr(total)}",
              {"form": typed_amount, "invoice": total}))
    else:
        add(R("R-BILL-04", "bill", FAIL, f"Amount entered ({inr(typed_amount)}) differs from the bill's total ({inr(total)})", "VENDOR",
              {"form": typed_amount, "invoice": total},
              vendor_text=f"The amount you entered ({inr(typed_amount)}) doesn't match your bill's total ({inr(total)}). Please correct the amount."))

    # The bill adds up, and charges the right kind of GST
    taxable = money(val(inv_doc, "taxable_value")[0])
    cg, sg_, ig = (money(val(inv_doc, k)[0]) or 0.0 for k in ("cgst_amount", "sgst_amount", "igst_amount"))
    if taxable is not None and total is not None:
        ok = abs(taxable + cg + sg_ + ig - total) <= 1
        add(R("R-BILL-05", "bill", PASS if ok else FAIL, "The bill adds up (taxable value + GST = total)" if ok else "The bill doesn't add up", "VENDOR",
              {"taxable": taxable, "cgst": cg, "sgst": sg_, "igst": ig, "total": total},
              vendor_text="" if ok else f"Your bill's figures don't add up: taxable value {inr(taxable)} plus GST {inr(cg + sg_ + ig)} isn't the total {inr(total)}. Please send a corrected invoice."))
    seller_state, buyer_state = gstin[:2], BUYER["gstin"][:2]
    s_name, b_name = V.GST_STATE_CODES.get(seller_state, seller_state), V.GST_STATE_CODES.get(buyer_state, buyer_state)
    if cg + sg_ + ig == 0:
        add(R("R-BILL-06", "bill", WARN, "No GST charged on the bill", "WARN", internal="Check whether the supply is exempt or the vendor is a composition dealer."))
    elif seller_state == buyer_state:
        ok = cg > 0 and sg_ > 0 and ig == 0
        add(R("R-BILL-06", "bill", PASS if ok else FAIL, f"Right GST for a supply within {b_name}: CGST + SGST" if ok else "Wrong type of GST for a supply within the same state", "VENDOR",
              {"seller_state": s_name, "buyer_state": b_name, "cgst": cg, "sgst": sg_, "igst": ig},
              vendor_text="" if ok else f"You and we are both in {b_name}, so the bill must charge CGST + SGST, not IGST. Please send a corrected invoice."))
    else:
        ok = ig > 0 and cg == 0 and sg_ == 0
        add(R("R-BILL-06", "bill", PASS if ok else FAIL, f"Right GST for a supply from {s_name} to {b_name}: IGST" if ok else f"Wrong type of GST: a supply from {s_name} to {b_name} needs IGST", "VENDOR",
              {"seller_state": s_name, "buyer_state": b_name, "cgst": cg, "sgst": sg_, "igst": ig},
              vendor_text="" if ok else (f"Your bill charges CGST + SGST, but you're in {s_name} and we're in {b_name}, so this is an inter-state supply and must "
                                         f"charge IGST instead. We can't claim the GST credit otherwise. Please send a corrected invoice.")))

    # Payment details printed on the bill must point to the account we verified (bank-change fraud)
    acct, aleg = val(inv_doc, "account_number")
    on_file = f.get("bank_account", "")
    if acct and aleg == "clear" and on_file:
        am = M.compare_account(on_file, acct, aleg)
        if am.status == M.MISMATCH:
            add(R("R-BILL-10", "bill", FAIL, "The bill asks for payment to a different bank account than the one we verified", "REVIEW",
                  {"on_bill": V.mask_account(acct), "verified": V.mask_account(on_file)},
                  internal=(f"Bill shows account {V.mask_account(acct)}; the verified account is {V.mask_account(on_file)}. Changing bank details through an "
                            "invoice is the most common vendor-payment fraud. Pay only the verified account; confirm any change by calling the vendor "
                            "on a number we already have."), fraud=True))
        else:
            add(R("R-BILL-10", "bill", PASS, "Bank account on the bill is the verified one", {"on_bill": V.mask_account(acct)}))

    # Date
    dtxt, _ = val(inv_doc, "invoice_date")
    d = _parse_any_date(dtxt) or _parse_any_date(f.get("bill_invoice_date"))
    if d:
        age = (_now(ctx).astimezone().replace(tzinfo=None) - d).days
        if age < 0:
            add(R("R-BILL-07", "bill", FAIL, f"The bill is dated in the future ({d:%d %b %Y})", "VENDOR",
                  vendor_text=f"Your bill is dated {d:%d %b %Y}, which is in the future. Please check the invoice date."))
        elif age > BILL_MAX_AGE_DAYS:
            add(R("R-BILL-07", "bill", FAIL, f"The bill is {age} days old", "REVIEW", {"date": f"{d:%Y-%m-%d}"},
                  internal="Old bill: the GST input credit may no longer be claimable, and old work is hard to verify."))
        else:
            add(R("R-BILL-07", "bill", PASS, f"Bill dated {d:%d %b %Y} ({age} days ago)"))


def _xd(add, rule_id: str, title: str, m: M.IdMatch, slot: str, what: str, mismatch_text: str) -> None:
    if m.status == M.MATCH:
        add(R(rule_id, "consistency", PASS, f"{title}: match", evidence={"form": m.form_value, "document": m.doc_value}))
    elif m.status == M.MATCH_CORRECTED:
        add(R(rule_id, "consistency", PASS, f"{title}: match after correcting a misread", evidence={"form": m.form_value, "document": m.doc_value, "correction": m.detail}))
    elif m.status in (M.UNREADABLE, M.MISSING):
        add(R(rule_id, "consistency", FAIL, f"{title}: couldn't be read on the document", "VENDOR", {"detail": m.detail}, vendor_text=reupload(slot, what)))
    else:
        add(R(rule_id, "consistency", FAIL, f"{title}: different", "VENDOR", {"form": m.form_value, "document": m.doc_value}, vendor_text=mismatch_text))


def _name(add, rule_id: str, title: str, r: M.NameResult | None, mismatch_outcome: str, slot: str, mismatch_text: str) -> None:
    if not r:
        add(R(rule_id, "names", SKIPPED, f"{title}: no name on the document"))
    elif r.status == M.MATCH:
        add(R(rule_id, "names", PASS, f"{title}: match ({r.score}{'; ' + r.note if r.note else ''})", evidence={"form": r.form_value, "document": r.doc_value, "score": r.score}))
    elif r.status == M.PARTIAL:
        add(R(rule_id, "names", WARN, f"{title}: partial match ({r.score})", "WARN", {"form": r.form_value, "document": r.doc_value, "score": r.score}))
    elif r.status in (M.UNREADABLE, M.MISSING):
        add(R(rule_id, "names", FAIL, f"{title}: couldn't be read", "VENDOR", vendor_text=reupload(slot, "name")))
    else:
        add(R(rule_id, "names", FAIL, f"{title}: different ({r.score})", mismatch_outcome, {"form": r.form_value, "document": r.doc_value, "score": r.score}, vendor_text=mismatch_text))
