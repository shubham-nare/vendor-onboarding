"""Language for the public pages (top bar, home, thank-you, contact, how it works). The choice is a cookie.

Only these pages' headings, buttons and short text are translated; forms, checks and messages stay in English.
A phrase without a translation shows in English. Usage in a template: {{ 'View demo' | t }}.
"""

from __future__ import annotations

from jinja2 import pass_context

LANGS = {"en": "English", "hi": "हिन्दी", "mr": "मराठी", "te": "తెలుగు", "zh": "中文"}
COOKIE = "lang"

HI = {
    # top bar
    "How it works": "यह कैसे काम करता है",
    "For suppliers": "आपूर्तिकर्ताओं के लिए",
    "Register for future work": "भविष्य के काम के लिए पंजीकरण करें",
    "Submit a bill": "बिल जमा करें",
    "Track your registration": "अपना पंजीकरण देखें",
    "Log in": "लॉग इन करें",
    "Vendor log in": "विक्रेता लॉग इन",
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


MR = {
    "How it works": "हे कसे काम करते",
    "For suppliers": "पुरवठादारांसाठी",
    "Register for future work": "भविष्यातील कामासाठी नोंदणी करा",
    "Submit a bill": "बिल सादर करा",
    "Track your registration": "तुमची नोंदणी पहा",
    "Log in": "लॉग इन करा",
    "Vendor log in": "विक्रेता लॉग इन",
    "Employee log in": "कर्मचारी लॉग इन",
    "View demo": "डेमो पहा",
    "Contact us": "आमच्याशी संपर्क साधा",
    "Language": "भाषा",
    "My account": "माझे खाते",
    "Log out": "लॉग आउट",
    "Menu": "मेनू",
    "I'm a vendor or supplier": "मी विक्रेता किंवा पुरवठादार आहे",
    "Create an account": "खाते तयार करा",
    "Go to my account": "माझ्या खात्यावर जा",
    "Open the console": "कन्सोल उघडा",
    "Thank you for registering.": "नोंदणी केल्याबद्दल धन्यवाद.",
    "Thank you for submitting your bill.": "तुमचे बिल सादर केल्याबद्दल धन्यवाद.",
    "Thank you for updating your registration.": "तुमची नोंदणी अद्ययावत केल्याबद्दल धन्यवाद.",
    "Thank you for registering for future work.": "भविष्यातील कामासाठी नोंदणी केल्याबद्दल धन्यवाद.",
    "Thank you for getting in touch.": "संपर्क साधल्याबद्दल धन्यवाद.",
    "We are checking your details and will email you shortly.": "आम्ही तुमच्या तपशिलांची तपासणी करत आहोत आणि लवकरच तुम्हाला ईमेल करू.",
    "We'll reply by email within two working days.": "आम्ही दोन कामकाजाच्या दिवसांत ईमेलद्वारे उत्तर देऊ.",
    "Your reference": "तुमचा संदर्भ क्रमांक",
    "Track it in your supplier account": "तुमच्या पुरवठादार खात्यात स्थिती पहा",
    "Back to the home page": "मुख्य पानावर परत जा",
    "Thank you,": "धन्यवाद,",
    "The Supplier Team": "पुरवठादार टीम",
    "We usually reply within two working days.": "आम्ही सहसा दोन कामकाजाच्या दिवसांत उत्तर देतो.",
    "Supplier help": "पुरवठादार मदत",
    "Payments and invoices": "देयके आणि बिले",
    "Our address": "आमचा पत्ता",
    "Send us a message": "आम्हाला संदेश पाठवा",
    "Your name": "तुमचे नाव",
    "Company": "कंपनी",
    "Email": "ईमेल",
    "Topic": "विषय",
    "Message": "संदेश",
    "Send": "पाठवा",
    "See how it works": "हे कसे काम करते ते पहा",
    "From the first document to the first payment, in four steps.": "पहिल्या कागदपत्रापासून पहिल्या देयकापर्यंत, चार टप्प्यांत.",
    "Try it as a supplier": "पुरवठादार म्हणून वापरून पहा",
    "Try it as our team": "आमची टीम म्हणून वापरून पहा",
}

TE = {
    "How it works": "ఇది ఎలా పనిచేస్తుంది",
    "For suppliers": "సరఫరాదారుల కోసం",
    "Register for future work": "భవిష్యత్ పనుల కోసం నమోదు చేసుకోండి",
    "Submit a bill": "బిల్లు సమర్పించండి",
    "Track your registration": "మీ నమోదు స్థితిని చూడండి",
    "Log in": "లాగిన్ అవ్వండి",
    "Vendor log in": "విక్రేత లాగిన్",
    "Employee log in": "ఉద్యోగి లాగిన్",
    "View demo": "డెమో చూడండి",
    "Contact us": "మమ్మల్ని సంప్రదించండి",
    "Language": "భాష",
    "My account": "నా ఖాతా",
    "Log out": "లాగ్ అవుట్",
    "Menu": "మెనూ",
    "I'm a vendor or supplier": "నేను విక్రేత లేదా సరఫరాదారుని",
    "Create an account": "ఖాతా సృష్టించండి",
    "Go to my account": "నా ఖాతాకు వెళ్లండి",
    "Open the console": "కన్సోల్ తెరవండి",
    "Thank you for registering.": "నమోదు చేసుకున్నందుకు ధన్యవాదాలు.",
    "Thank you for submitting your bill.": "మీ బిల్లు సమర్పించినందుకు ధన్యవాదాలు.",
    "Thank you for updating your registration.": "మీ నమోదును నవీకరించినందుకు ధన్యవాదాలు.",
    "Thank you for registering for future work.": "భవిష్యత్ పనుల కోసం నమోదు చేసుకున్నందుకు ధన్యవాదాలు.",
    "Thank you for getting in touch.": "మమ్మల్ని సంప్రదించినందుకు ధన్యవాదాలు.",
    "We are checking your details and will email you shortly.": "మేము మీ వివరాలను తనిఖీ చేస్తున్నాము, త్వరలో మీకు ఈమెయిల్ చేస్తాము.",
    "We'll reply by email within two working days.": "రెండు పని దినాలలో ఈమెయిల్ ద్వారా సమాధానం ఇస్తాము.",
    "Your reference": "మీ సూచన సంఖ్య",
    "Track it in your supplier account": "మీ సరఫరాదారు ఖాతాలో స్థితిని చూడండి",
    "Back to the home page": "హోమ్ పేజీకి తిరిగి వెళ్లండి",
    "Thank you,": "ధన్యవాదాలు,",
    "The Supplier Team": "సరఫరాదారుల బృందం",
    "We usually reply within two working days.": "మేము సాధారణంగా రెండు పని దినాలలో సమాధానం ఇస్తాము.",
    "Supplier help": "సరఫరాదారుల సహాయం",
    "Payments and invoices": "చెల్లింపులు మరియు ఇన్‌వాయిస్‌లు",
    "Our address": "మా చిరునామా",
    "Send us a message": "మాకు సందేశం పంపండి",
    "Your name": "మీ పేరు",
    "Company": "కంపెనీ",
    "Email": "ఈమెయిల్",
    "Topic": "విషయం",
    "Message": "సందేశం",
    "Send": "పంపండి",
    "See how it works": "ఇది ఎలా పనిచేస్తుందో చూడండి",
    "From the first document to the first payment, in four steps.": "మొదటి పత్రం నుండి మొదటి చెల్లింపు వరకు, నాలుగు దశల్లో.",
    "Try it as a supplier": "సరఫరాదారుగా ప్రయత్నించండి",
    "Try it as our team": "మా బృందంగా ప్రయత్నించండి",
}

ZH = {   # Simplified Chinese
    "How it works": "运作方式",
    "For suppliers": "供应商专区",
    "Register for future work": "登记以承接未来业务",
    "Submit a bill": "提交账单",
    "Track your registration": "查看注册进度",
    "Log in": "登录",
    "Vendor log in": "供应商登录",
    "Employee log in": "员工登录",
    "View demo": "查看演示",
    "Contact us": "联系我们",
    "Language": "语言",
    "My account": "我的账户",
    "Log out": "退出登录",
    "Menu": "菜单",
    "I'm a vendor or supplier": "我是供应商",
    "Create an account": "创建账户",
    "Go to my account": "前往我的账户",
    "Open the console": "打开控制台",
    "Thank you for registering.": "感谢您的注册。",
    "Thank you for submitting your bill.": "感谢您提交账单。",
    "Thank you for updating your registration.": "感谢您更新注册信息。",
    "Thank you for registering for future work.": "感谢您登记承接未来业务。",
    "Thank you for getting in touch.": "感谢您与我们联系。",
    "We are checking your details and will email you shortly.": "我们正在核实您的信息，稍后将通过电子邮件通知您。",
    "We'll reply by email within two working days.": "我们将在两个工作日内通过电子邮件回复。",
    "Your reference": "您的参考编号",
    "Track it in your supplier account": "在供应商账户中查看进度",
    "Back to the home page": "返回首页",
    "Thank you,": "谢谢，",
    "The Supplier Team": "供应商团队",
    "We usually reply within two working days.": "我们通常在两个工作日内回复。",
    "Supplier help": "供应商帮助",
    "Payments and invoices": "付款与发票",
    "Our address": "我们的地址",
    "Send us a message": "给我们留言",
    "Your name": "您的姓名",
    "Company": "公司",
    "Email": "电子邮件",
    "Topic": "主题",
    "Message": "留言",
    "Send": "发送",
    "See how it works": "了解运作方式",
    "From the first document to the first payment, in four steps.": "从第一份文件到第一笔付款，只需四步。",
    "Try it as a supplier": "以供应商身份试用",
    "Try it as our team": "以我方团队身份试用",
}

TABLES = {"hi": HI, "mr": MR, "te": TE, "zh": ZH}


def lang_of(request) -> str:
    v = request.cookies.get(COOKIE, "en") if request is not None else "en"
    return v if v in LANGS else "en"


def translate(text: str, lang: str) -> str:
    return TABLES.get(lang, {}).get(text, text)


@pass_context
def t(ctx, text: str) -> str:
    return translate(text, lang_of(ctx.get("request")))
