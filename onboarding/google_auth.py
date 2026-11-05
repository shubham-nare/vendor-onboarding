"""'Continue with Google' for suppliers: the OAuth 2.0 authorization-code flow, no extra libraries.

  /vendor/google           -> Google's consent page (state kept in a signed, 10-minute cookie)
  /vendor/google/callback  -> code exchanged for tokens, then Google's userinfo (over TLS, from Google: trusted)
  a known email logs in; a new one is asked for its company name once (/vendor/google/finish)

Employees don't get this button: in a real company they would use the company's own sign-in (SSO),
and the demo staff emails are not Google accounts. Off until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set.
"""

import base64
import binascii
import hmac
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import Request

from onboarding import auth
from onboarding.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_COOKIE, NEW_COOKIE = "g_state", "g_new"
TTL = 600
NO_PASSWORD = "google"   # stored instead of a password hash: no password can ever match it


def configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def redirect_uri(request: Request) -> str:
    """Where Google sends the person back. Register exactly this URL on the OAuth client."""
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{scheme}://{request.url.netloc}/vendor/google/callback"


def seal(*parts: str) -> str:
    """Signed, time-stamped value for a short-lived cookie."""
    body = "|".join([*(p.replace("|", " ") for p in parts), str(int(time.time()))])
    return base64.urlsafe_b64encode(f"{body}|{auth._sign('google|' + body)}".encode()).decode()


def unseal(value: str | None, n: int) -> list[str] | None:
    """The n parts of a value made by seal(), if the signature is good and it is under 10 minutes old."""
    try:
        value = base64.urlsafe_b64decode((value or "").encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    body, _, sig = value.rpartition("|")
    if not body or not hmac.compare_digest(sig, auth._sign("google|" + body)):
        return None
    parts = body.split("|")
    if len(parts) != n + 1 or not parts[-1].isdigit() or time.time() - int(parts[-1]) > TTL:
        return None
    return parts[:-1]


def start(request: Request, nxt: str) -> tuple[str, str]:
    """(Google's consent URL, cookie value)."""
    state = secrets.token_urlsafe(24)
    q = urlencode({"client_id": get_settings().google_client_id, "redirect_uri": redirect_uri(request), "response_type": "code",
                   "scope": "openid email profile", "state": state, "prompt": "select_account"})
    return f"{AUTH_URL}?{q}", seal(state, nxt)


async def exchange(request: Request, code: str) -> dict:
    """The signed-in Google user's {'email', 'name', 'email_verified'}; raises on any failure."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=10) as c:
        tok = await c.post(TOKEN_URL, data={"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                            "redirect_uri": redirect_uri(request), "grant_type": "authorization_code"})
        tok.raise_for_status()
        info = await c.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        info.raise_for_status()
        return info.json()
