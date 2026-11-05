"""Language for the public pages (top bar, home, thank-you, contact, how it works). The choice is a cookie.

Only these pages' headings, buttons and short text are translated; forms, checks and messages stay in English.
A phrase without a translation shows in English. Usage in a template: {{ 'View demo' | t }}.
"""

from __future__ import annotations

from jinja2 import pass_context

LANGS = {"en": "English", "hi": "हिन्दी"}
COOKIE = "lang"

HI = {
    # top bar
    "How it works": "यह कैसे काम करता है",
    "For suppliers": "आपूर्तिकर्ताओं के लिए",
    "Register for future work": "भविष्य के काम के लिए पंजीकरण करें",
    "Submit a bill": "बिल जमा करें",
    "Track your registration": "अपना पंजीकरण देखें",
    "Log in": "लॉग इन करें",
    "Employee log in": "कर्मचारी लॉग इन",
    "View demo": "डेमो देखें",
    "Contact us": "संपर्क करें",
    "Language": "भाषा",
    "My account": "मेरा खाता",
    "Log out": "लॉग आउट",
    "Menu": "मेनू",
    # home
    "Who are": "आप कौन",
    "you?": "हैं?",
    "Suppliers register, prove who they are and send their bills. The company checks every document, every number and every bill before anyone is paid.":
        "आपूर्तिकर्ता पंजीकरण करते हैं, अपनी पहचान साबित करते हैं और अपने बिल भेजते हैं। किसी को भुगतान करने से पहले कंपनी हर दस्तावेज़, हर नंबर और हर बिल की जाँच करती है।",
    "I'm a vendor or supplier": "मैं एक विक्रेता या आपूर्तिकर्ता हूँ",
    "Create an account": "खाता बनाएँ",
    "Go to my account": "मेरे खाते पर जाएँ",
    "Open the console": "कंसोल खोलें",
    # thank-you
    "Thank you for registering.": "पंजीकरण के लिए धन्यवाद।",
    "Thank you for submitting your bill.": "अपना बिल जमा करने के लिए धन्यवाद।",
    "Thank you for updating your registration.": "अपना पंजीकरण अपडेट करने के लिए धन्यवाद।",
    "Thank you for registering for future work.": "भविष्य के काम के लिए पंजीकरण करने के लिए धन्यवाद।",
    "Thank you for getting in touch.": "संपर्क करने के लिए धन्यवाद।",
    "We are checking your details and will email you shortly.": "हम आपके विवरण की जाँच कर रहे हैं और जल्द ही आपको ईमेल करेंगे।",
    "We'll reply by email within two working days.": "हम दो कार्य दिवसों के भीतर ईमेल से जवाब देंगे।",
    "Your reference": "आपका संदर्भ",
    "Track it in your supplier account": "अपने आपूर्तिकर्ता खाते में स्थिति देखें",
    "Back to the home page": "होम पेज पर वापस जाएँ",
    "Thank you,": "धन्यवाद,",
    "The Supplier Team": "आपूर्तिकर्ता टीम",
    # contact
    "We usually reply within two working days.": "हम आमतौर पर दो कार्य दिवसों के भीतर जवाब देते हैं।",
    "Supplier help": "आपूर्तिकर्ता सहायता",
    "Payments and invoices": "भुगतान और चालान",
    "Our address": "हमारा पता",
    "Send us a message": "हमें संदेश भेजें",
    "Your name": "आपका नाम",
    "Company": "कंपनी",
    "Email": "ईमेल",
    "Topic": "विषय",
    "Message": "संदेश",
    "Send": "भेजें",
    # how it works
    "See how it works": "देखें यह कैसे काम करता है",
    "From the first document to the first payment, in four steps.": "पहले दस्तावेज़ से पहले भुगतान तक, चार चरणों में।",
    "Try it as a supplier": "आपूर्तिकर्ता के रूप में आज़माएँ",
    "Try it as our team": "हमारी टीम के रूप में आज़माएँ",
}


def lang_of(request) -> str:
    v = request.cookies.get(COOKIE, "en") if request is not None else "en"
    return v if v in LANGS else "en"


def translate(text: str, lang: str) -> str:
    return HI.get(text, text) if lang == "hi" else text


@pass_context
def t(ctx, text: str) -> str:
    return translate(text, lang_of(ctx.get("request")))
