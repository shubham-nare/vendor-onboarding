"""Demo scenarios: fictional vendors, the documents they upload, and the seeded vendor master.

Everything here is FICTIONAL test data. GSTINs are built with the real check-digit
algorithm so the rules behave realistically, but the PANs/GSTINs were never looked up
in any registry and must never be. IFSCs are real public branch codes (so the live
IFSC lookup works); account numbers are made up. Emails use example.com (reserved).

One source of truth: the document generator and the "Load demo scenario" button both
read from here.
"""

from __future__ import annotations

from onboarding.validators import gstin_check_char


def gstin(state: str, pan: str, entity: str = "1") -> str:
    first = f"{state}{pan}{entity}Z"
    return first + gstin_check_char(first)


# --- Businesses -------------------------------------------------------------

NILGIRI = {
    "legal_name": "Nilgiri Packaging Solutions Private Limited",
    "pan": "AAHCN4821K",
    "gstin": gstin("29", "AAHCN4821K"),  # 29AAHCN4821K1Z4
    "cin": "U22220KA2016PTC094512",
    "incorporated": "14/03/2016",
    "address": "Plot 47, 2nd Phase, Peenya Industrial Area",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pin": "560058",
    "constitution": "Private Limited Company",
    "liability_date": "01/07/2017",
    "gst_issue_date": "21/07/2017",
    "bank": {
        "ifsc": "HDFC0000009",
        "bank": "HDFC Bank",
        "branch": "Bangalore - Kasturba Gandhi Marg",
        "account": "50200071234567",
        "holder": "NILGIRI PACKAGING SOLUTIONS PVT LTD",
        "type": "Current",
    },
    "contact": {"name": "Anitha Raghavan", "email": "accounts@nilgiripack.example.com", "phone": "+91 98450 11234"},
}

TEJAS = {
    "legal_name": "Tejas Industrial Supplies Private Limited",
    "pan": "AAJCT9052D",
    "gstin": gstin("36", "AAJCT9052D"),  # 36AAJCT9052D1Z7
    "cin": "U51909TG2014PTC093417",
    "incorporated": "02/09/2014",
    "address": "8-2-293/A, Road No. 12, Banjara Hills",
    "city": "Hyderabad",
    "state": "Telangana",
    "pin": "500034",
    "constitution": "Private Limited Company",
    "liability_date": "01/07/2017",
    "gst_issue_date": "18/07/2017",
    "udyam": {
        "number": "UDYAM-TS-02-0012345",
        "type": "Small",
        "activity": "Trading",
        "registered_on": "11/08/2021",
        "nic": "46593 - Wholesale of industrial machinery and equipment",
    },
    "bank": {
        "ifsc": "ICIC0000008",
        "bank": "ICICI Bank",
        "branch": "CIBD Hyderabad",
        "account": "012305004321",
        "holder": "TEJAS INDUSTRIAL SUPPLIES PVT LTD",
        "type": "Current",
    },
    "contact": {"name": "Vikram Reddy", "email": "vikram@tejasindustrial.example.com", "phone": "+91 99490 56781"},
}

# Partnership firm that uploads its sister company's GST certificate.
KAVERI_TRADERS = {
    "legal_name": "Kaveri Agro Traders",
    "pan": "AAKFK7316M",
    "address": "Shop 14, Market Yard, Gultekdi",
    "city": "Pune",
    "state": "Maharashtra",
    "pin": "411037",
    "formed": "05/06/2012",
    "bank": {
        "ifsc": "ICIC0000005",
        "bank": "ICICI Bank",
        "branch": "Pune Bund Garden",
        "account": "000405112233",
        "holder": "KAVERI AGRO TRADERS",
        "type": "Current",
    },
    "contact": {"name": "Sachin Patil", "email": "sachin@kaveriagro.example.com", "phone": "+91 98220 44310"},
}
KAVERI_FOODS = {  # the sister company whose GSTIN gets "borrowed"
    "legal_name": "Kaveri Agro Foods Private Limited",
    "pan": "AAHCK5590L",
    "gstin": gstin("27", "AAHCK5590L"),  # 27AAHCK5590L1ZX
    "address": "Gat No. 212, Chakan MIDC Phase II",
    "city": "Pune",
    "state": "Maharashtra",
    "pin": "410501",
    "constitution": "Private Limited Company",
    "liability_date": "01/07/2017",
    "gst_issue_date": "25/07/2017",
}

RANGOLI = {
    "legal_name": "Rangoli Print House Private Limited",
    "pan": "AAQCR6188B",
    "gstin": gstin("36", "AAQCR6188B"),  # 36AAQCR6188B1ZZ
    "cin": "U18101TG2018PTC127654",
    "incorporated": "19/01/2018",
    "address": "Unit 5, Plot 22, IDA Balanagar",
    "city": "Hyderabad",
    "state": "Telangana",
    "pin": "500037",
    "constitution": "Private Limited Company",
    "liability_date": "01/02/2018",
    "gst_issue_date": "09/02/2018",
    "bank": {
        "ifsc": "UTIB0000008",
        "bank": "Axis Bank",
        "branch": "Hyderabad",
        "account": "918020045615678",  # also on file for V-0042 Deccan Office Supplies
        "holder": "RANGOLI PRINT HOUSE PVT LTD",
        "type": "Current",
    },
    "contact": {"name": "Farhan Siddiqui", "email": "farhan@rangoliprint.example.com", "phone": "+91 90000 73452"},
}

SHINDE = {  # proprietorship: legal name = owner, trade name = business
    "trade_name": "Shinde Electricals",
    "proprietor": "Ramesh Vitthal Shinde",
    "proprietor_short": "Ramesh Shinde",
    "father": "Vitthal Dattatray Shinde",
    "dob": "17/04/1979",
    "pan": "BVKPS5274R",
    "gstin": gstin("27", "BVKPS5274R"),  # 27BVKPS5274R1ZE
    "address": "Shop 3, Laxmi Road, Sadashiv Peth",
    "city": "Pune",
    "state": "Maharashtra",
    "pin": "411030",
    "constitution": "Proprietorship",
    "liability_date": "01/07/2017",
    "gst_issue_date": "30/07/2017",
    "bank": {
        "ifsc": "MAHB0000001",
        "bank": "Bank of Maharashtra",
        "branch": "Pune - Bajirao Road",
        "account": "60234567891",
        "holder": "RAMESH VITTHAL SHINDE",  # personal savings account
        "type": "Savings",
    },
    "contact": {"name": "Ramesh Shinde", "email": "shinde.electricals@example.com", "phone": "+91 98230 66012"},
}


# The buying company (us). Bills must be addressed to it; its state decides CGST+SGST vs IGST.
BUYER = {
    "legal_name": "Vardhan Engineering Private Limited",
    "pan": "AAKCV3382N",
    "gstin": gstin("27", "AAKCV3382N"),
    "address": "Gat No. 418, Chakan Industrial Area Phase I, Pune, Maharashtra, 410501",
    "state": "Maharashtra",
}

# Bill-first vendors: they already did work for us and register to get paid.
KESARI = {  # Pune (same state as us): CGST + SGST is right
    "legal_name": "Kesari Facility Services Private Limited",
    "pan": "AAKCK4417F",
    "gstin": gstin("27", "AAKCK4417F"),
    "cin": "U74900MH2015PTC268431",
    "incorporated": "09/06/2015",
    "address": "Office 6, Shivneri Complex, Bhosari MIDC",
    "city": "Pune",
    "state": "Maharashtra",
    "pin": "411026",
    "constitution": "Private Limited Company",
    "liability_date": "01/07/2017",
    "gst_issue_date": "27/07/2017",
    "bank": {
        "ifsc": "HDFC0000007",
        "bank": "HDFC Bank",
        "branch": "Pune - Law College Road",
        "account": "50200088412375",
        "holder": "KESARI FACILITY SERVICES PVT LTD",
        "type": "Current",
    },
    "contact": {"name": "Sneha Kulkarni", "email": "billing@kesarifacility.example.com", "phone": "+91 98901 22745"},
}

BRINDAVAN = {  # Bengaluru (other state): should charge IGST, but its bill charges CGST + SGST
    "legal_name": "Brindavan Cooling Systems Private Limited",
    "pan": "AAFCB6623Q",
    "gstin": gstin("29", "AAFCB6623Q"),
    "cin": "U29199KA2017PTC104287",
    "incorporated": "23/02/2017",
    "address": "No. 61, 3rd Cross, Yeshwanthpur Industrial Suburb",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pin": "560022",
    "constitution": "Private Limited Company",
    "liability_date": "01/07/2017",
    "gst_issue_date": "19/07/2017",
    "bank": {
        "ifsc": "UTIB0000009",
        "bank": "Axis Bank",
        "branch": "Bangalore",
        "account": "921020033457781",
        "holder": "BRINDAVAN COOLING SYSTEMS PVT LTD",
        "type": "Current",
    },
    "contact": {"name": "Manjunath Gowda", "email": "accounts@brindavancooling.example.com", "phone": "+91 97411 30982"},
}


# --- Documents (what the generator renders) ---------------------------------

def gst_cert(b: dict, *, legal_name: str | None = None, trade_name: str = "", proprietor: str = "") -> dict:
    return {
        "kind": "gst_certificate",
        "gstin": b["gstin"],
        "legal_name": (legal_name or b["legal_name"]).upper(),
        "trade_name": trade_name.upper(),
        "constitution": b["constitution"],
        "address": f"{b['address']}, {b['city']}, {b['state']}, {b['pin']}",
        "state": b["state"],
        "liability_date": b["liability_date"],
        "issue_date": b["gst_issue_date"],
        "proprietor": proprietor.upper(),
    }


def pan_card(name: str, pan: str, *, date_label: str, date: str, father: str = "") -> dict:
    return {"kind": "pan_card", "name": name.upper(), "pan": pan, "date_label": date_label, "date": date, "father": father.upper()}


def cheque(b: dict, *, signatory: str) -> dict:
    return {"kind": "cancelled_cheque", **b["bank"], "signatory": signatory}


def udyam_cert(b: dict) -> dict:
    return {
        "kind": "udyam_certificate",
        **b["udyam"],
        "name": b["legal_name"].upper(),
        "address": f"{b['address']}, {b['city']}, {b['state']}, {b['pin']}",
        "incorporated": b["incorporated"],
    }


def tax_invoice(b: dict) -> dict:
    return {
        "kind": "tax_invoice",
        "seller": b["legal_name"].upper(),
        "seller_gstin": b["gstin"],
        "seller_address": f"{b['address']}, {b['city']}, {b['state']}, {b['pin']}",
        "invoice_no": "TIS/2026-27/0418",
        "date": "14/10/2026",
        "buyer": "SUNRISE AUTO COMPONENTS PVT LTD",
        "buyer_gstin": gstin("36", "AAKCS2207H"),
        "buyer_address": "Survey No. 88, Medchal Industrial Estate, Hyderabad, Telangana, 501401",
        "lines": [
            {"desc": "Pneumatic Cylinder 63mm Bore", "hsn": "84123100", "qty": 12, "rate": 4850.00},
            {"desc": "Solenoid Valve 5/2 Way 1/4 inch", "hsn": "84818090", "qty": 20, "rate": 1275.00},
            {"desc": "PU Tubing 8mm (100 m roll)", "hsn": "39173290", "qty": 6, "rate": 2390.00},
        ],
        "cgst": 9,
        "sgst": 9,
    }


def service_invoice(b: dict, *, invoice_no: str, date: str, lines: list[dict], igst: int = 0, cgst: int = 0, sgst: int = 0,
                    bank_line: str = "") -> dict:
    """A services tax invoice addressed to us (BUYER)."""
    return {
        "kind": "tax_invoice",
        "seller": b["legal_name"].upper(),
        "seller_gstin": b["gstin"],
        "seller_address": f"{b['address']}, {b['city']}, {b['state']}, {b['pin']}",
        "invoice_no": invoice_no,
        "date": date,
        "buyer": BUYER["legal_name"].upper(),
        "buyer_gstin": BUYER["gstin"],
        "buyer_address": BUYER["address"],
        "place_of_supply": "Maharashtra (27)",
        "desc_label": "Description of Services",
        "code_label": "SAC",
        "lines": lines,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "bank_line": bank_line or f"Bank: {b['bank']['bank']}, A/c {b['bank']['account']}, IFSC {b['bank']['ifsc']}",
    }


def invoice_total(lines: list[dict], rate_pct: int) -> float:
    taxable = sum(l["qty"] * l["rate"] for l in lines)
    return round(taxable * (1 + rate_pct / 100), 2)


KESARI_LINES = [
    {"desc": "Emergency deep cleaning of Plant 2 shop floor after waterlogging (3 days, 14 staff)", "hsn": "998533", "qty": 1, "rate": 84000.00},
    {"desc": "Cleaning chemicals, absorbents and disposal of sludge", "hsn": "998533", "qty": 1, "rate": 22500.00},
]
BRINDAVAN_LINES = [
    {"desc": "Breakdown repair of Plant 2 control-room AC: compressor replacement", "hsn": "998719", "qty": 1, "rate": 62000.00},
    {"desc": "Refrigerant top-up, labour and site visit charges", "hsn": "998719", "qty": 1, "rate": 18400.00},
]


# --- Form submissions -------------------------------------------------------

def form(b: dict, business_type: str, *, msme: bool = False, udyam_no: str = "", proprietor: str = "",
         legal_name: str | None = None, gstin_value: str | None = None, cin: str = "") -> dict:
    return {
        "country": "India",
        "gst_registered": True,
        "business_type": business_type,
        "legal_name": legal_name or b["legal_name"],
        "proprietor_name": proprietor,
        "gstin": gstin_value or b["gstin"],
        "pan": b["pan"],
        "cin": cin,
        "llpin": "",
        "address": b["address"],
        "city": b["city"],
        "state": b["state"],
        "pin": b["pin"],
        "contact_name": b["contact"]["name"],
        "contact_email": b["contact"]["email"],
        "contact_phone": b["contact"]["phone"],
        "bank_holder": b["bank"]["holder"],
        "bank_account": b["bank"]["account"],
        "ifsc": b["bank"]["ifsc"],
        "msme": msme,
        "udyam_no": udyam_no,
    }


SCENARIOS: dict[str, dict] = {
    "happy_nilgiri": {
        "title": "Happy path: a clean, consistent submission",
        "expected": "APPROVED",
        "form": form(NILGIRI, "PVT_LTD", cin=NILGIRI["cin"]),
        "documents": {
            "gst_certificate": gst_cert(NILGIRI),
            "pan_card": pan_card(NILGIRI["legal_name"], NILGIRI["pan"], date_label="Date of Incorporation/Formation", date=NILGIRI["incorporated"]),
            "bank_proof": cheque(NILGIRI, signatory=NILGIRI["bank"]["holder"]),
        },
    },
    "wrongdoc_tejas": {
        "title": "Wrong document in the GST slot + Udyam certificate missing",
        "expected": "PENDING_VENDOR",
        "form": form(TEJAS, "PVT_LTD", msme=True, udyam_no=TEJAS["udyam"]["number"], cin=TEJAS["cin"]),
        "documents": {
            "gst_certificate": tax_invoice(TEJAS),  # a tax invoice, not REG-06
            "pan_card": pan_card(TEJAS["legal_name"], TEJAS["pan"], date_label="Date of Incorporation/Formation", date=TEJAS["incorporated"]),
            "bank_proof": cheque(TEJAS, signatory=TEJAS["bank"]["holder"]),
            # udyam_certificate deliberately missing
        },
    },
    "wrongdoc_tejas_resubmit": {
        "title": "Tejas resubmits with the right documents",
        "expected": "APPROVED",
        "resubmission_of": "wrongdoc_tejas",
        "form": form(TEJAS, "PVT_LTD", msme=True, udyam_no=TEJAS["udyam"]["number"], cin=TEJAS["cin"]),
        "documents": {
            "gst_certificate": gst_cert(TEJAS),
            "pan_card": pan_card(TEJAS["legal_name"], TEJAS["pan"], date_label="Date of Incorporation/Formation", date=TEJAS["incorporated"]),
            "bank_proof": cheque(TEJAS, signatory=TEJAS["bank"]["holder"]),
            "udyam_certificate": udyam_cert(TEJAS),
        },
    },
    "borrowed_gstin_kaveri": {
        "title": "Borrowed GSTIN: a sister company's GST registration",
        "expected": "REJECTED",
        "form": form(KAVERI_TRADERS, "PARTNERSHIP", gstin_value=KAVERI_FOODS["gstin"]),
        "documents": {
            "gst_certificate": gst_cert(KAVERI_FOODS),
            "pan_card": pan_card(KAVERI_TRADERS["legal_name"], KAVERI_TRADERS["pan"], date_label="Date of Incorporation/Formation", date=KAVERI_TRADERS["formed"]),
            "bank_proof": cheque(KAVERI_TRADERS, signatory="KAVERI AGRO TRADERS"),
        },
    },
    "shared_bank_rangoli": {
        "title": "Bank account already on file for another vendor",
        "expected": "PENDING_REVIEW",
        "form": form(RANGOLI, "PVT_LTD", cin=RANGOLI["cin"]),
        "documents": {
            "gst_certificate": gst_cert(RANGOLI),
            "pan_card": pan_card(RANGOLI["legal_name"], RANGOLI["pan"], date_label="Date of Incorporation/Formation", date=RANGOLI["incorporated"]),
            "bank_proof": cheque(RANGOLI, signatory=RANGOLI["bank"]["holder"]) | {"as_image": True},
        },
    },
    "proprietor_shinde": {
        "title": "Proprietorship paid into the owner's personal account",
        "expected": "APPROVED",
        "form": form(SHINDE | {"legal_name": SHINDE["trade_name"]}, "PROPRIETORSHIP", proprietor=SHINDE["proprietor_short"]),
        "documents": {
            "gst_certificate": gst_cert(SHINDE, legal_name=SHINDE["proprietor"], trade_name=SHINDE["trade_name"], proprietor=SHINDE["proprietor"]),
            "pan_card": pan_card(SHINDE["proprietor"], SHINDE["pan"], date_label="Date of Birth", date=SHINDE["dob"], father=SHINDE["father"]) | {"as_image": True},
            "bank_proof": cheque(SHINDE, signatory=SHINDE["bank"]["holder"]),
        },
    },
    "bill_kesari": {
        "title": "No invite: did work for us, registers with its bill",
        "expected": "APPROVED",
        "bill": True,
        "form": form(KESARI, "PVT_LTD", cin=KESARI["cin"]) | {
            "bill_mode": True, "bill_invoice_number": "KFS/2026-27/0193", "bill_invoice_date": "2026-10-21",
            "bill_amount": f"{invoice_total(KESARI_LINES, 18):.2f}",
            "bill_description": "Emergency deep cleaning of the Plant 2 shop floor after the waterlogging on 17 Oct",
            "bill_engaged_by": "Priya Nair", "bill_po": ""},
        "documents": {
            "gst_certificate": gst_cert(KESARI),
            "pan_card": pan_card(KESARI["legal_name"], KESARI["pan"], date_label="Date of Incorporation/Formation", date=KESARI["incorporated"]),
            "bank_proof": cheque(KESARI, signatory=KESARI["bank"]["holder"]),
            "invoice": service_invoice(KESARI, invoice_no="KFS/2026-27/0193", date="21/10/2026", lines=KESARI_LINES, cgst=9, sgst=9),
        },
    },
    "bill_brindavan": {
        "title": "Bill with the wrong GST type and a mistyped amount",
        "expected": "PENDING_VENDOR",
        "bill": True,
        "form": form(BRINDAVAN, "PVT_LTD", cin=BRINDAVAN["cin"]) | {
            "bill_mode": True, "bill_invoice_number": "BCS/26-27/0877", "bill_invoice_date": "2026-10-24",
            "bill_amount": "98472.00",  # digits swapped: the invoice says 94,872.00
            "bill_description": "Breakdown repair of the Plant 2 control-room AC (compressor replaced)",
            "bill_engaged_by": "rahul.desai@vardhan.example.com", "bill_po": ""},
        "documents": {
            "gst_certificate": gst_cert(BRINDAVAN),
            "pan_card": pan_card(BRINDAVAN["legal_name"], BRINDAVAN["pan"], date_label="Date of Incorporation/Formation", date=BRINDAVAN["incorporated"]),
            "bank_proof": cheque(BRINDAVAN, signatory=BRINDAVAN["bank"]["holder"]),
            # Karnataka -> Maharashtra is an inter-state supply (IGST), but the bill charges CGST + SGST
            "invoice": service_invoice(BRINDAVAN, invoice_no="BCS/26-27/0877", date="24/10/2026", lines=BRINDAVAN_LINES, cgst=9, sgst=9),
        },
    },
}


# Bills an ACTIVE Kesari sends later through the supplier portal (rendered to fixtures/documents/extra/).
EXTRA_DOCUMENTS = {
    "kesari_bill_clean": service_invoice(
        KESARI, invoice_no="KFS/2026-27/0207", date="28/10/2026", cgst=9, sgst=9,
        lines=[{"desc": "Housekeeping of Plant 2 canteen and washrooms, October 2026", "hsn": "998533", "qty": 1, "rate": 34000.00}]),
    # Same vendor, but the bill asks to be paid into a NEW account: the classic bank-change fraud.
    "kesari_bill_newbank": service_invoice(
        KESARI, invoice_no="KFS/2026-27/0211", date="30/10/2026", cgst=9, sgst=9,
        lines=[{"desc": "Pest control treatment, Plant 2 stores", "hsn": "998531", "qty": 1, "rate": 20000.00}],
        bank_line="Bank details (NEW ACCOUNT, please update your records): Kotak Mahindra Bank, A/c 4613902788, IFSC KKBK0000721"),
}


# --- Seeded vendor master + blocklist ---------------------------------------

VENDOR_MASTER = [
    {"vendor_id": "V-0011", "legal_name": "Coromandel Logistics Private Limited", "pan": "AAFCC3381P", "gstin": gstin("33", "AAFCC3381P"),
     "account": "33120200004417", "ifsc": "ICIC0000001", "status": "Active"},
    {"vendor_id": "V-0027", "legal_name": "Sahyadri Tools and Hardware", "pan": "AAGFS7720N", "gstin": gstin("27", "AAGFS7720N"),
     "account": "50100055671230", "ifsc": "HDFC0000007", "status": "Active"},
    {"vendor_id": "V-0042", "legal_name": "Deccan Office Supplies", "pan": "AAKFD4519Q", "gstin": gstin("36", "AAKFD4519Q"),
     "account": "918020045615678", "ifsc": "UTIB0000008", "status": "Active"},  # same account as Rangoli
    {"vendor_id": "V-0058", "legal_name": "Malabar Spices Exports Private Limited", "pan": "AAICM6604R", "gstin": gstin("32", "AAICM6604R"),
     "account": "917020011223344", "ifsc": "UTIB0000009", "status": "Active"},
    {"vendor_id": "V-0063", "legal_name": "Ganga Electricals", "pan": "AAOFG2210K", "gstin": gstin("09", "AAOFG2210K"),
     "account": "30442189001", "ifsc": "SBIN0001234", "status": "Inactive"},
]

BLOCKLIST = [
    {"pan": "AAECV9931L", "gstin": gstin("07", "AAECV9931L"), "account": "", "reason": "Invoice fraud, 2025 (internal case AP-2025-117)"},
]
