"""Vendor portal accounts: password hashing and the signed session cookie.

Standard library only:
  - passwords: scrypt (salted, memory-hard), compared in constant time
  - session: "<account id>.<issued at>.<HMAC-SHA256>" in an http-only cookie; 14 days
Employees log in the same way (their work email), with a separate cookie. Each cookie's signature
includes its purpose, so a vendor's cookie can never be replayed as an employee's (or the reverse).
In production the company side would use the company's single sign-on instead.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from onboarding.config import get_settings

COOKIE = "vendor_session"
COMPANY_COOKIE = "company_session"
MAX_AGE = 14 * 24 * 3600
MIN_PASSWORD = 8
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2)
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, TypeError):
        return False


def _key() -> bytes:
    s = get_settings()
    base = s.session_secret or ("derived:" + s.database_url)
    return hashlib.sha256(base.encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()


def make_session(account_id: int, purpose: str = "vendor") -> str:
    payload = f"{account_id}.{int(time.time())}"
    return f"{payload}.{_sign(purpose + '|' + payload)}"


def read_session(value: str | None, purpose: str = "vendor") -> int | None:
    """The id in a valid, unexpired cookie made for this purpose, else None."""
    if not value or value.count(".") != 2:
        return None
    acct, issued, sig = value.split(".")
    if not hmac.compare_digest(sig, _sign(f"{purpose}|{acct}.{issued}")):
        return None
    try:
        if time.time() - int(issued) > MAX_AGE:
            return None
        return int(acct)
    except ValueError:
        return None


def password_problem(password: str) -> str:
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if password.lower() in {"password", "password1", "12345678", "qwertyui"}:
        return "That password is too easy to guess."
    return ""
