"""Layer 5: ask an authority instead of trusting a document (docs/PRODUCT.md §7).

Every adapter returns the same shape, so a production provider (Cashfree, Perfios/Karza...)
replaces a simulated one by configuration.

  live=True    a real external call answered (only the IFSC directory today)
  live=False   SIMULATED registry or a bundled snapshot answered: shown in amber in the UI and
               never allowed to raise a fact to A4 ("confirmed at source")
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.models import SimRegistry

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "fixtures" / "ifsc_snapshot.json"
REGISTRY = "registry connector"   # answered by a registry connector (GST, PAN, penny-drop, MCA, Udyam)


@dataclass
class SourceResult:
    source: str            # human label, e.g. "Razorpay IFSC directory (live)"
    status: str            # FOUND | NOT_FOUND | ERROR
    live: bool
    data: dict = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


async def ifsc_lookup(ifsc: str, *, timeout: float = 3.0) -> SourceResult:
    """Live RBI branch directory via Razorpay's free API; bundled snapshot if the call fails."""
    code = (ifsc or "").strip().upper()
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"https://ifsc.razorpay.com/{code}")
        if r.status_code == 200:
            d = r.json()
            return SourceResult("Razorpay IFSC directory (live)", "FOUND", True,
                                {k: d.get(k) for k in ("BANK", "BRANCH", "CITY", "STATE", "ADDRESS")})
        if r.status_code == 404:
            return SourceResult("Razorpay IFSC directory (live)", "NOT_FOUND", True)
        raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
    except Exception as e:
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {"records": {}}
        if code in snap["records"]:
            return SourceResult(f"IFSC snapshot from {snap.get('captured_at', '?')} (live lookup failed)", "FOUND", False,
                                snap["records"][code], note=f"{type(e).__name__}")
        return SourceResult("Razorpay IFSC directory", "ERROR", False, note=f"{type(e).__name__}: {e}"[:160])


PIN_SOURCE = "India Post PIN directory (live)"


async def pin_lookup(pin: str, *, timeout: float = 3.0) -> SourceResult:
    """Live India Post PIN directory (api.postalpincode.in, free, no key): the post offices, district and state
    of a PIN code. On failure the rules fall back to the postal-region check in onboarding/pincode.py."""
    code = (pin or "").strip()
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"https://api.postalpincode.in/pincode/{code}")
        r.raise_for_status()
        d = (r.json() or [{}])[0]
        offices = d.get("PostOffice") or []
        if d.get("Status") != "Success" or not offices:
            return SourceResult(PIN_SOURCE, "NOT_FOUND", True)
        return SourceResult(PIN_SOURCE, "FOUND", True, {
            "districts": sorted({o.get("District") or "" for o in offices} - {""}),
            "states": sorted({o.get("State") or "" for o in offices} - {""}),
            "offices": [o.get("Name") for o in offices][:12],
            "blocks": sorted({o.get("Block") or "" for o in offices} - {"", "NA"}),
        })
    except Exception as e:
        return SourceResult("India Post PIN directory", "ERROR", False, note=f"{type(e).__name__}: {e}"[:160])


async def _sim(session: AsyncSession, kind: str, key: str, label: str) -> SourceResult:
    row = (await session.execute(select(SimRegistry).where(SimRegistry.kind == kind, SimRegistry.key == key))).scalar_one_or_none()
    return (SourceResult(label, "FOUND", False, dict(row.data), note=REGISTRY) if row
            else SourceResult(label, "NOT_FOUND", False, note=REGISTRY))


async def gst_status(session: AsyncSession, gstin: str) -> SourceResult:
    """Production: GSTN via a GSP or KYC provider (Cashfree / Perfios / Setu)."""
    return await _sim(session, "gst", (gstin or "").upper(), "GST registry")


async def pan_status(session: AsyncSession, pan: str) -> SourceResult:
    """Production: PAN verification via Protean-eligible providers (name, status, Aadhaar link)."""
    return await _sim(session, "pan", (pan or "").upper(), "PAN registry")


async def penny_drop(session: AsyncSession, account: str, ifsc: str) -> SourceResult:
    """Production: penny-drop / reverse penny-drop via a payments partner (returns the holder name)."""
    return await _sim(session, "bank", f"{account}@{(ifsc or '').upper()}", "bank account check (penny-drop)")


async def cin_status(session: AsyncSession, cin: str) -> SourceResult:
    return await _sim(session, "cin", (cin or "").upper(), "MCA company registry")


async def udyam_status(session: AsyncSession, udyam: str) -> SourceResult:
    return await _sim(session, "udyam", (udyam or "").upper(), "Udyam registry")
