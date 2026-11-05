"""Bot check for the public forms (sign-up, log-in, contact): Cloudflare Turnstile plus a hidden honeypot field.

Keys come from TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY (free from the Cloudflare dashboard). Without them only the
honeypot runs: Cloudflare's public test keys would put a red "For testing only" notice on every form.
CAPTCHA=false turns it all off (tests).
"""

from __future__ import annotations

import logging

import httpx

from onboarding.config import get_settings

log = logging.getLogger(__name__)
TEST_SITE_KEY = "1x00000000000000000000AA"            # Cloudflare's documented always-pass test keys
TEST_SECRET = "1x0000000000000000000000000000000AA"
HONEYPOT = "website"                                   # people never see it; bots fill it in


def keys() -> tuple[str, str]:
    st = get_settings()
    if not st.captcha:
        return "", ""
    if st.turnstile_site_key and st.turnstile_secret_key:
        return st.turnstile_site_key, st.turnstile_secret_key
    return "", ""


def site_key() -> str:
    return keys()[0]


async def check(request) -> str:
    """'' when the visitor passes, otherwise the message to show."""
    if not get_settings().captcha:
        return ""
    form = await request.form()
    if str(form.get(HONEYPOT) or "").strip():
        return "Something went wrong. Please try again."
    site, secret = keys()
    if not site:
        return ""
    token = str(form.get("cf-turnstile-response") or "")
    if not token:
        return "Please complete the check that you're not a robot."
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post("https://challenges.cloudflare.com/turnstile/v0/siteverify",
                             data={"secret": secret, "response": token, "remoteip": request.client.host if request.client else ""})
        ok = bool(r.json().get("success"))
    except Exception as e:
        log.warning("captcha check unreachable: %s", type(e).__name__)
        ok = secret == TEST_SECRET          # test keys: don't block a demo on a network blip; real keys: fail closed
    return "" if ok else "The check that you're not a robot didn't pass. Please try again."
