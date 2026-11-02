"""Matching keys and encryption for sensitive identifiers (PAN, bank account, email, phone, address).

  lookup_key(kind, value)  keyed HMAC-SHA256 of the normalised value: two vendors with the same bank account
                           get the same key, but the graph tables never hold the number itself
  encrypt / decrypt        AES-256-GCM for values that must be shown again (e.g. Finance sees an active vendor's
                           full account number)

Keys come from INTEL_SECRET (production: a dedicated secret from a key manager), else they are derived from the
session secret or the database URL, with separate labels for matching and for encryption.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from onboarding import validators as V
from onboarding.config import get_settings

SENSITIVE = {"PAN", "BANK_ACCOUNT", "EMAIL", "PHONE", "ADDRESS"}


def _base() -> bytes:
    s = get_settings()
    return (s.intel_secret or s.session_secret or ("derived:" + s.database_url)).encode()


def _key(label: str) -> bytes:
    return hmac.new(_base(), f"vendor-intelligence|{label}".encode(), hashlib.sha256).digest()


def normalise(kind: str, value: str | None) -> str:
    v = (value or "").strip()
    if kind in ("PAN", "GSTIN", "CIN", "UDYAM", "IFSC", "LLPIN"):
        return V.normalise_id(v)
    if kind == "BANK_ACCOUNT":
        return re.sub(r"\D", "", v)
    if kind == "EMAIL":
        return v.lower()
    if kind == "PHONE":
        digits = re.sub(r"\D", "", v)
        return digits[-10:]
    if kind == "ADDRESS":
        return re.sub(r"[^a-z0-9]+", " ", v.lower()).strip()
    return v


def lookup_key(kind: str, value: str | None) -> str:
    n = normalise(kind, value)
    if not n:
        return ""
    return hmac.new(_key("lookup"), f"{kind}:{n}".encode(), hashlib.sha256).hexdigest()[:40]


def mask(kind: str, value: str | None) -> str:
    v = (value or "").strip()
    if kind == "PAN":
        return V.mask_pan(v)
    if kind == "BANK_ACCOUNT":
        return V.mask_account(v)
    if kind == "EMAIL" and "@" in v:
        user, _, dom = v.partition("@")
        return f"{user[:1]}•••@{dom}"
    if kind == "PHONE":
        d = re.sub(r"\D", "", v)
        return "••••" + d[-4:] if len(d) >= 4 else d
    return v


def encrypt(value: str | None) -> str:
    if not value:
        return ""
    nonce = os.urandom(12)
    ct = AESGCM(_key("encrypt")).encrypt(nonce, value.encode(), b"vi1")
    return "vi1:" + base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt(token: str | None) -> str:
    if not token or not token.startswith("vi1:"):
        return ""
    raw = base64.urlsafe_b64decode(token[4:].encode())
    return AESGCM(_key("encrypt")).decrypt(raw[:12], raw[12:], b"vi1").decode()
