"""Does a PIN code belong to the state given?

India Post allocates PIN codes by postal region: the first digit is the zone, the first two digits the
circle (usually one state), and a few three-digit prefixes belong to a smaller state or union territory
inside another circle (Goa inside Maharashtra's 40-44, Sikkim inside West Bengal's 70-74, and so on).

This checks the PIN against the state's postal region. It catches the common mistakes (a Bengaluru PIN
with "Maharashtra", a typo in the first digits) without a 150,000-row directory. It does not prove that
the exact six-digit PIN is in use: that needs India Post's PIN directory, a later integration.
"""

from __future__ import annotations

import re

# three-digit prefixes that differ from their two-digit circle (checked first)
SPECIFIC: dict[str, list[str]] = {
    "160": ["Chandigarh", "Punjab"],
    "194": ["Ladakh"],
    "246": ["Uttarakhand"], "247": ["Uttarakhand", "Uttar Pradesh"], "248": ["Uttarakhand"], "249": ["Uttarakhand"],
    "262": ["Uttarakhand", "Uttar Pradesh"], "263": ["Uttarakhand"],
    "362": ["Gujarat", "Dadra and Nagar Haveli and Daman and Diu"],
    "396": ["Gujarat", "Dadra and Nagar Haveli and Daman and Diu"],
    "403": ["Goa"],
    "533": ["Andhra Pradesh", "Puducherry"],
    "605": ["Tamil Nadu", "Puducherry"], "607": ["Tamil Nadu", "Puducherry"], "609": ["Tamil Nadu", "Puducherry"],
    "673": ["Kerala", "Puducherry"],
    "682": ["Kerala", "Lakshadweep"],
    "737": ["Sikkim"],
    "744": ["Andaman and Nicobar Islands"],
    "790": ["Arunachal Pradesh"], "791": ["Arunachal Pradesh"], "792": ["Arunachal Pradesh"],
    "793": ["Meghalaya"], "794": ["Meghalaya"],
    "795": ["Manipur"],
    "796": ["Mizoram"],
    "797": ["Nagaland"], "798": ["Nagaland"],
    "799": ["Tripura"],
}

# two-digit postal circles
TWO: dict[str, list[str]] = {
    "11": ["Delhi"],
    "12": ["Haryana"], "13": ["Haryana", "Punjab"],
    "14": ["Punjab"], "15": ["Punjab"], "16": ["Punjab"],
    "17": ["Himachal Pradesh"],
    "18": ["Jammu and Kashmir"], "19": ["Jammu and Kashmir"],
    **{str(n): ["Uttar Pradesh"] for n in range(20, 29)},
    **{str(n): ["Rajasthan"] for n in range(30, 35)},
    **{str(n): ["Gujarat"] for n in range(36, 40)},
    **{str(n): ["Maharashtra"] for n in range(40, 45)},
    **{str(n): ["Madhya Pradesh"] for n in range(45, 49)},
    "49": ["Chhattisgarh"],
    "50": ["Telangana"],
    "51": ["Andhra Pradesh"], "52": ["Andhra Pradesh"], "53": ["Andhra Pradesh"],
    **{str(n): ["Karnataka"] for n in range(56, 60)},
    **{str(n): ["Tamil Nadu"] for n in range(60, 65)},
    "67": ["Kerala"], "68": ["Kerala"], "69": ["Kerala"],
    **{str(n): ["West Bengal"] for n in range(70, 75)},
    "75": ["Odisha"], "76": ["Odisha"], "77": ["Odisha"],
    "78": ["Assam"],
    **{str(n): ["Bihar", "Jharkhand"] for n in range(80, 86)},
}

_PIN = re.compile(r"[1-8][0-9]{5}")


def states_for_pin(pin: str) -> list[str] | None:
    """The states a PIN's postal region covers; None if it isn't a six-digit Indian PIN, [] if no region uses it."""
    pin = (pin or "").strip()
    if not _PIN.fullmatch(pin):
        return None
    return SPECIFIC.get(pin[:3]) or TWO.get(pin[:2]) or []


def pin_problem(pin: str, state: str) -> str:
    """'' if the PIN fits the state, otherwise a plain sentence saying what's wrong."""
    pin = (pin or "").strip()
    states = states_for_pin(pin)
    if states is None:
        return f"'{pin}' isn't a valid PIN code: it has 6 digits and starts with 1 to 8."
    if not states:
        return f"PIN code {pin} isn't used by any Indian state's postal region."
    if state and state not in states:
        return f"PIN code {pin} is in {' / '.join(states)}, not {state}."
    return ""
