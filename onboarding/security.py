"""Request-level protection shared by every route: who the visitor is (behind Render's proxy), rate limits for
abuse-prone actions, what an uploaded file really is, and the same-site check on state-changing requests."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request

# --- the visitor's address ------------------------------------------------------------------------------------
def client_ip(request: Request) -> str:
    """Render (and most hosts) put the visitor's address first in X-Forwarded-For; without it, the socket address.
    Using only the socket address would put every visitor behind the proxy into one bucket."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "?"


# --- rate limits ------------------------------------------------------------------------------------------------
class RateLimit:
    """At most `limit` events per `window` seconds for one key, in this process. Simple and enough for one server;
    with several servers this would move to Redis. Old keys are dropped as they expire, so memory stays small."""

    def __init__(self, limit: int, window: float, message: str):
        self.limit, self.window, self.message = limit, window, message
        self._hits: dict[str, list[float]] = {}
        self._swept = time.monotonic()

    def _sweep(self, now: float) -> None:
        if now - self._swept < self.window:
            return
        self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
        self._swept = now

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        self._sweep(now)
        recent = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            return False
        self._hits[key] = recent + [now]
        return True

    def check(self, key: str) -> None:
        """Raise 429 with a plain message when the limit is reached."""
        from onboarding.config import get_settings
        if get_settings().rate_limits and not self.allow(key):
            raise HTTPException(429, self.message)

    def reset(self) -> None:
        self._hits.clear()


# log-in and sign-up: per address and per email, so guessing one account's password is slow and spraying many is too
LOGIN_PER_ACCOUNT = RateLimit(8, 600, "Too many log-in attempts for this account. Please wait 10 minutes and try again.")
LOGIN_PER_IP = RateLimit(30, 600, "Too many log-in attempts from your network. Please wait 10 minutes and try again.")
SIGNUP_PER_IP = RateLimit(10, 3600, "Too many accounts created from your network. Please try again in an hour.")
# every submission sends up to five documents to Gemini: keep the cost bounded
SUBMIT_PER_IP = RateLimit(12, 3600, "Too many submissions from your network in the last hour. Please try again later.")
READ_PER_IP = RateLimit(20, 600, "Too many files read in a short time. Please type the details below.")
CONTACT_PER_IP = RateLimit(5, 3600, "Too many messages from your network. Please try again in an hour.")
ALL_LIMITS = [LOGIN_PER_ACCOUNT, LOGIN_PER_IP, SIGNUP_PER_IP, SUBMIT_PER_IP, READ_PER_IP, CONTACT_PER_IP]


def check_login(request: Request, email: str) -> None:
    ip = client_ip(request)
    LOGIN_PER_IP.check(ip)
    LOGIN_PER_ACCOUNT.check(f"{ip}|{email.strip().lower()}")


# --- uploads ----------------------------------------------------------------------------------------------------
ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png"}
UPLOAD_HELP = "Please upload a PDF, JPG or PNG file."


def sniff(raw: bytes) -> str | None:
    """What the file really is, from its first bytes (the name and the browser's label can say anything)."""
    if raw.startswith(b"%PDF-") or raw[:1024].lstrip().startswith(b"%PDF-"):
        return "application/pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def require_document(raw: bytes, what: str = "The file") -> str:
    """The real type of an uploaded document, or 415 if it isn't a PDF, JPG or PNG."""
    mime = sniff(raw)
    if mime is None:
        raise HTTPException(415, f"{what} isn't a PDF, JPG or PNG. {UPLOAD_HELP}")
    return mime


# --- same-site requests (CSRF) ----------------------------------------------------------------------------------
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def cross_site(request: Request) -> bool:
    """True when a browser sent a state-changing request from another site. Browsers always send Origin (or at
    least Referer) on such requests; a request with neither comes from a script or a tool, not a victim's browser,
    and cookies alone (SameSite=Lax) already keep those from riding on a logged-in session."""
    if request.method not in UNSAFE:
        return False
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source or source == "null":
        return source == "null"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlparse(source).netloc.lower() != host.lower()


def file_response(data: bytes, stored_mime: str):
    """Serve an uploaded document. It is shown inline only if its bytes really are a PDF, JPG or PNG; anything else is
    a download. A sandbox policy stops any script inside from running on this site, whatever the file is."""
    from fastapi.responses import Response
    mime = sniff(data)
    inline = mime is not None
    return Response(data, media_type=mime or "application/octet-stream", headers={
        "Content-Disposition": "inline" if inline else "attachment",
        "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; object-src 'self'",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})
