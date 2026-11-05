"""Vendor portal accounts: password hashing and the signed session cookie.

Standard library only:
  - passwords: scrypt (salted, memory-hard), compared in constant time
  - session: "<account id>.<issued at>.<HMAC-SHA256>" in an http-only cookie; 14 days
Employees log in the same way (their work email), with a separate cookie. Each cookie's signature
includes its purpose, so a vendor's cookie can never be replayed as an employee's (or the reverse).
In production the company side would use the company's single sign-on instead.
"""

from __future__ import annotations

import asyncio
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


async def hash_password_async(password: str) -> str:
    """scrypt takes ~0.2 s of CPU and 16 MB: run it on a worker thread so the server keeps answering other requests."""
    return await asyncio.to_thread(hash_password, password)


_DUMMY = None


async def verify_password_async(password: str, stored: str | None) -> bool:
    """Like verify_password, off the event loop. With no stored hash (unknown email) it still does the same work,
    so response time doesn't reveal which emails have accounts."""
    global _DUMMY
    if not stored:
        if _DUMMY is None:
            _DUMMY = await hash_password_async(secrets.token_hex(8))
        await asyncio.to_thread(verify_password, password, _DUMMY)
        return False
    return await asyncio.to_thread(verify_password, password, stored)


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2)
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, TypeError):
        return False


_LOCAL_KEY = secrets.token_bytes(32)   # only on a developer's machine without SESSION_SECRET: logins end on restart


def _key() -> bytes:
    """SESSION_SECRET; never derived from the database URL. main.py refuses to start without it unless the app runs in
    demo mode on a local database, where a random per-process key is used instead."""
    from onboarding.config import dev_keys_allowed
    s = get_settings()
    if s.session_secret:
        return hashlib.sha256(s.session_secret.encode()).digest()
    if dev_keys_allowed(s):
        return _LOCAL_KEY
    raise RuntimeError("SESSION_SECRET is not set; it is required unless the app runs in demo mode on a local database.")


def _sign(payload: str) -> str:
    return hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()


def make_session(account_id: int, purpose: str = "vendor") -> str:
    payload = f"{account_id}.{int(time.time())}"
    return f"{payload}.{_sign(purpose + '|' + payload)}"


# Signatures of ended log-ins (loaded from revoked_sessions at start-up, added to on every log-out).
_REVOKED: set[str] = set()


def read_session(value: str | None, purpose: str = "vendor") -> int | None:
    """The id in a valid, unexpired, not logged-out cookie made for this purpose, else None."""
    if not value or value.count(".") != 2:
        return None
    acct, issued, sig = value.split(".")
    if not hmac.compare_digest(sig, _sign(f"{purpose}|{acct}.{issued}")) or sig in _REVOKED:
        return None
    try:
        if time.time() - int(issued) > MAX_AGE:
            return None
        return int(acct)
    except ValueError:
        return None


ACTOR_COOKIE = "actor"   # the demo person switcher: who a logged-in employee is acting as


def make_actor(employee_id: int, staff_id: int | None) -> str:
    """A signed actor cookie, bound to the employee who is logged in: it can't be forged, edited, or reused by
    another login. Purpose "actor" keeps it from ever passing as a session cookie."""
    return make_session(employee_id, purpose=f"actor:{staff_id or 0}")


def read_actor(value: str | None, staff_id: int | None) -> int | None:
    """The employee id in a valid actor cookie made for this login, else None."""
    return read_session(value, purpose=f"actor:{staff_id or 0}") if staff_id else None


def actor_ids(request) -> tuple[int | None, int | None]:
    """(staff_id, actor_id) for the audit trail: who is logged in, and who they act as (the same person unless the demo
    person switcher is in use). No valid actor cookie means the logged-in employee, never anyone else."""
    staff_id = read_session(request.cookies.get(COMPANY_COOKIE), purpose="company")
    if not staff_id:
        return None, None
    acting = read_actor(request.cookies.get(ACTOR_COOKIE), staff_id) if get_settings().demo_tools else None
    return staff_id, acting or staff_id


def audit_comment(request, comment: str) -> str:
    """A human action's comment, plus who was really logged in when the demo person switcher was in use, so the
    audit trail keeps both people (HumanAction.employee_id holds the acted-as employee). Unchanged otherwise."""
    staff_id, actor_id = actor_ids(request)
    if staff_id and actor_id != staff_id:
        return f"{comment} [taken via the person switcher by logged-in employee #{staff_id}]".strip()
    return comment


PASSWORD_RULE =f"At least {MIN_PASSWORD} characters, with an uppercase letter, a lowercase letter, a number and a symbol such as @"


def password_problem(password: str) -> str:
    """'' if the password is strong enough, otherwise what is missing."""
    missing = []
    if len(password) < MIN_PASSWORD:
        missing.append(f"at least {MIN_PASSWORD} characters")
    if not any(c.isupper() for c in password):
        missing.append("an uppercase letter")
    if not any(c.islower() for c in password):
        missing.append("a lowercase letter")
    if not any(c.isdigit() for c in password):
        missing.append("a number")
    if not any(not c.isalnum() for c in password):
        missing.append("a symbol such as @")
    if missing:
        return "Your password needs " + ", ".join(missing[:-1]) + (" and " if len(missing) > 1 else "") + missing[-1] + "."
    if password.lower() in {"password@1", "password1!", "p@ssw0rd", "p@ssword1", "welcome@123", "admin@123"}:
        return "That password is too easy to guess."
    return ""


async def revoke(value: str | None, purpose: str) -> None:
    """End a log-in for good: its cookie stops working on this server at once and after a restart."""
    from datetime import datetime, timezone
    from onboarding.models import RevokedSession
    from onboarding.pipeline import sessions
    if read_session(value, purpose) is None:
        return
    _, issued, sig = value.split(".")
    _REVOKED.add(sig)
    async with sessions()() as s:
        if not await s.get(RevokedSession, sig):
            s.add(RevokedSession(sig=sig, expires_at=datetime.fromtimestamp(int(issued) + MAX_AGE, timezone.utc)))
            await s.commit()


async def load_revoked(s) -> int:
    """At start-up: remember the ended log-ins that haven't expired, and forget the rest."""
    from datetime import datetime, timezone
    from sqlalchemy import delete, select
    from onboarding.models import RevokedSession
    now = datetime.now(timezone.utc)
    await s.execute(delete(RevokedSession).where(RevokedSession.expires_at < now))
    _REVOKED.update((await s.execute(select(RevokedSession.sig))).scalars())
    return len(_REVOKED)
