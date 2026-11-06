"""Request-level protection shared by every route: who the visitor is (behind Render's proxy), rate limits for
abuse-prone actions, what an uploaded file really is, and the same-site check on state-changing requests."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request

# --- the visitor's address ------------------------------------------------------------------------------------
_XFF_LOGGED = False


def client_ip(request: Request) -> str:
    """The visitor's address. Each trusted proxy (TRUSTED_PROXY_HOPS, Render: 1) APPENDS the address it saw to
    X-Forwarded-For, so the right-most entries are the trustworthy ones; anything to their left was sent by the client
    and can be made up (it used to reset the rate limits). With no proxy hops, or no header, the socket address."""
    from onboarding.config import get_settings
    hops = get_settings().trusted_proxy_hops
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    global _XFF_LOGGED
    if fwd and not _XFF_LOGGED:   # once per process, so the hop count can be checked after a deploy (no addresses logged)
        _XFF_LOGGED = True
        import logging
        logging.getLogger("onboarding.security").warning(   # WARNING: the only level shown without a logging config
            "client address: X-Forwarded-For has %d entr%s; TRUSTED_PROXY_HOPS=%d, so the rate limits use entry %d from the right",
            len(fwd), "y" if len(fwd) == 1 else "ies", hops, min(hops, len(fwd)))
    if hops > 0 and fwd:
        return fwd[-min(hops, len(fwd))][:64]
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

    def allow_more(self, key: str) -> bool:
        """True while this key is under the limit, without counting an event."""
        now = time.monotonic()
        return len([t for t in self._hits.get(key, []) if now - t < self.window]) < self.limit

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
# wrong reset passcodes: always on (not switched off with RATE_LIMITS), so the passcode can't be guessed
RESET_WRONG = RateLimit(5, 3600, "Too many wrong passcodes. Reset is locked for an hour.")
ALL_LIMITS = [LOGIN_PER_ACCOUNT, LOGIN_PER_IP, SIGNUP_PER_IP, SUBMIT_PER_IP, READ_PER_IP, CONTACT_PER_IP, RESET_WRONG]


def check_login(request: Request, email: str) -> None:
    ip = client_ip(request)
    LOGIN_PER_IP.check(ip)
    LOGIN_PER_ACCOUNT.check(f"{ip}|{email.strip().lower()}")


# --- uploads ----------------------------------------------------------------------------------------------------
ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png"}
UPLOAD_HELP = "Please upload a PDF, JPG or PNG file."
MAX_FILE_BYTES = 10 * 1024 * 1024
_CHUNK = 256 * 1024


async def read_upload(up, what: str = "The file", limit: int = MAX_FILE_BYTES) -> bytes:
    """An uploaded file's bytes, read in chunks and abandoned with 413 as soon as it passes `limit`, so a huge file
    is never held in memory whole."""
    buf = bytearray()
    while chunk := await up.read(_CHUNK):
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(413, f"{what} is larger than {limit // (1024 * 1024)} MB. Please upload a smaller file.")
    return bytes(buf)


class BodyLimit:
    """ASGI middleware: refuse a request body over the limit with 413, before the app parses it. Checks the declared
    Content-Length first, then counts the bytes actually received (a chunked upload has no length)."""

    def __init__(self, app, limit: int | None = None):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from onboarding.config import get_settings
        limit = self.limit or get_settings().max_request_bytes
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            return await _too_large(send, limit)
        seen, started = 0, False

        async def counted_receive():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise BodyTooLarge()
            return msg

        async def tracking_send(msg):
            nonlocal started
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        try:
            await self.app(scope, counted_receive, tracking_send)
        except BaseException as e:   # may arrive wrapped in an exception group by the middlewares in between
            if not _contains(e, BodyTooLarge):
                raise
            if not started:
                await _too_large(send, limit)


class BodyTooLarge(Exception):
    pass


def _contains(e: BaseException, kind: type) -> bool:
    if isinstance(e, kind):
        return True
    return isinstance(e, BaseExceptionGroup) and any(_contains(x, kind) for x in e.exceptions)


async def _too_large(send, limit: int) -> None:
    import json
    body = json.dumps({"error": f"The upload is too large (over {limit // (1024 * 1024)} MB in total)."}).encode()
    await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


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
