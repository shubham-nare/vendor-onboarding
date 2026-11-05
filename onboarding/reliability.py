"""How reliable does this vendor look? Our own history first, then three outside sources.

1. Our history (always on): fraud signals in this check, earlier applications with the same GSTIN, PAN or bank account
   that were rejected or flagged, invoices from this vendor that were blocked or rejected, a GST registration only
   a few months old.
2. News (free, GDELT DOC 2.0 API, no key): recent articles naming the business next to fraud words. Names collide,
   so a hit is "for a person to check", never proof.
3. Sanctions and debarment lists (OpenSanctions; needs OPENSANCTIONS_API_KEY).
4. Google rating (Places API; needs GOOGLE_MAPS_API_KEY). Only the rating and the number of reviews are used; the
   review text isn't fetched or kept.

A source without a key is "not connected"; one that fails is "unavailable". Neither counts against the vendor.
The score (0-100, higher = more concern) is advisory: at HIGH the reviewer sees a warning they must acknowledge
before approving. It never rejects anyone, and the vendor never sees it.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from onboarding import names as N
from onboarding.config import get_settings

log = logging.getLogger(__name__)
HIGH, MEDIUM = 60, 25
SOURCE_NAMES = {"history": "Our records", "news": "News", "sanctions": "Sanctions and debarment lists", "reviews": "Google rating"}
CAP = {"history": 100, "news": 25, "sanctions": 70, "reviews": 20}
FRAUD_WORDS = '(fraud OR scam OR raid OR arrested OR cheating OR "tax evasion" OR "fake invoice" OR blacklisted)'
_SUFFIX = re.compile(r"\b(private|pvt|limited|ltd|llp|inc|co|company|the)\b\.?", re.I)


def level_of(score: int) -> str:
    return "high" if score >= HIGH else ("medium" if score >= MEDIUM else "low")


def search_name(legal_name: str) -> str:
    """'NILGIRI PACKAGING PRIVATE LIMITED' -> 'NILGIRI PACKAGING' (news rarely prints the suffix)."""
    return " ".join(_SUFFIX.sub(" ", legal_name or "").replace("(", " ").replace(")", " ").split())


def _sig(source, weight, title, detail="", link="") -> dict:
    return dict(source=source, weight=weight, title=title, detail=detail, link=link)


# --- 1. our own history ------------------------------------------------------------------------------------
async def history(s, run, app) -> list[dict]:
    from onboarding.models import Application, Document, Run, RuleResult, VendorBill, VendorMaster
    from onboarding.rules import _parse_any_date
    out = []
    f = run.form or {}
    for r in (await s.execute(select(RuleResult).where(RuleResult.run_id == run.id, RuleResult.result == "FAIL"))).scalars():
        ev = r.evidence or {}
        if r.rule_id == "R-RISK-01":
            out.append(_sig("history", 60, "On our blocklist", r.title))
        elif ev.get("fraud"):
            out.append(_sig("history", 40, "Fraud signal in this check", r.title))
        elif r.rule_id == "R-SRC-GST":
            out.append(_sig("history", 30, "GST registration isn't active", r.title))
    keys = {k: str(f.get(k) or "").upper() for k in ("gstin", "pan", "bank_account")}
    keys = {k: v for k, v in keys.items() if v}
    if keys:   # earlier applications from the same business (or using the same bank account)
        latest = {}
        for rr, a in (await s.execute(select(Run, Application).join(Application, Application.id == Run.application_id)
                                      .where(Run.application_id != app.id).order_by(Run.id.desc()).limit(1000))).all():
            latest.setdefault(a.id, (rr, a))
        for rr, a in latest.values():
            same = [k for k, v in keys.items() if str((rr.form or {}).get(k) or "").upper() == v]
            if not same:
                continue
            what = " and ".join({"gstin": "GSTIN", "pan": "PAN", "bank_account": "bank account"}[k] for k in same)
            if a.current_status == "REJECTED":
                out.append(_sig("history", 35, f"Rejected before: {a.ref}", f"Same {what}; that application was rejected.", f"/runs/{rr.id}"))
            elif (rr.summary or {}).get("fraud"):
                out.append(_sig("history", 30, f"Fraud signals on an earlier application: {a.ref}", f"Same {what}.", f"/runs/{rr.id}"))
    vids = [v for (v,) in (await s.execute(select(VendorMaster.vendor_id).where(
        (VendorMaster.gstin == keys.get("gstin", "-")) | (VendorMaster.pan == keys.get("pan", "-"))))).all()]
    if vids:
        bills = (await s.execute(select(VendorBill).where(VendorBill.vendor_id.in_(vids)))).scalars().all()
        flagged = [b for b in bills if b.fraud or b.status == "blocked"]
        rejected = [b for b in bills if b.status == "rejected" and b not in flagged]
        if flagged:
            out.append(_sig("history", min(50, 25 * len(flagged)), f"{len(flagged)} invoice{'s' if len(flagged) > 1 else ''} blocked or flagged for fraud",
                            ", ".join(b.invoice_number or b.ref for b in flagged[:4]), f"/bills/{flagged[0].id}"))
        if rejected:
            out.append(_sig("history", 10, f"{len(rejected)} invoice{'s' if len(rejected) > 1 else ''} rejected",
                            ", ".join(b.invoice_number or b.ref for b in rejected[:4])))
    doc = (await s.execute(select(Document).where(Document.run_id == run.id, Document.slot == "gst_certificate"))).scalars().first()
    if doc and doc.read:
        fields = (doc.read.get("read") or doc.read).get("fields", []) if isinstance(doc.read, dict) else []
        issued = next((x.get("value") for x in fields if x.get("name") == "issue_date" and x.get("value")), None)
        when = _parse_any_date(issued)
        if when:
            when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
            months = (datetime.now(timezone.utc) - when).days // 30
            if 0 <= months < 6:
                out.append(_sig("history", 15, f"GST registration is only {months} month{'s' if months != 1 else ''} old", f"Registered {issued}."))
    return out


# --- 2. news (GDELT) ------------------------------------------------------------------------------------------
_news_lock = asyncio.Lock()
_news_last = 0.0
NEWS_GAP = 5.5     # GDELT asks for at most one request every 5 seconds


async def news(legal_name: str) -> tuple[str, list[dict]]:
    global _news_last
    q = search_name(legal_name)
    if len(q) < 5:                     # too short to mean one business
        return "checked", [_sig("news", 0, "Name too short to search the news reliably", q)]
    params = {"query": f'"{q}" {FRAUD_WORDS}', "mode": "artlist", "maxrecords": "10", "format": "json", "timespan": "12m", "sort": "datedesc"}
    for attempt in range(2):
        async with _news_lock:
            wait = _news_last + NEWS_GAP - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            _news_last = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=20) as c:
                    r = await c.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params)
            except Exception as e:
                log.info("news search failed: %s", type(e).__name__)
                return "unavailable", []
        if r.status_code == 429 and attempt == 0:
            continue
        try:
            arts = (r.json() or {}).get("articles", []) if r.status_code == 200 and r.text.strip().startswith("{") else None
        except ValueError:
            arts = None
        if arts is None:
            return "unavailable", []
        if not arts:
            return "checked", []
        top = arts[:3]
        return "checked", [_sig("news", 25 if len(arts) >= 3 else 15,
                                f"{len(arts)} news article{'s' if len(arts) > 1 else ''} in the last year name \"{q}\" next to fraud words",
                                "For a person to check: other businesses can share this name. " + " · ".join(a.get("title", "")[:90] for a in top),
                                top[0].get("url", ""))]
    return "unavailable", []


# --- 3. sanctions and debarment (OpenSanctions) ----------------------------------------------------------------
async def sanctions(legal_name: str) -> tuple[str, list[dict]]:
    key = get_settings().opensanctions_api_key
    if not key:
        return "not connected", []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.opensanctions.org/search/default", params={"q": legal_name, "schema": "LegalEntity", "limit": 5},
                            headers={"Authorization": f"ApiKey {key}"})
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:
        log.info("sanctions search failed: %s", type(e).__name__)
        return "unavailable", []
    out = []
    for e in results:
        cap = e.get("caption") or ""
        if N.compare(cap, legal_name).score >= N.MATCH_AT:
            topics = (e.get("properties") or {}).get("topics") or e.get("topics") or []
            out.append(_sig("sanctions", 70, f"Named on a watch list: {cap}", ", ".join(topics or e.get("datasets", [])[:3]),
                            f"https://www.opensanctions.org/entities/{e.get('id', '')}/"))
            break
    return "checked", out


# --- 4. Google rating (Places API, text search) ------------------------------------------------------------------
async def reviews(legal_name: str, city: str) -> tuple[str, list[dict]]:
    key = get_settings().google_maps_api_key
    if not key:
        return "not connected", []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://places.googleapis.com/v1/places:searchText", json={"textQuery": f"{legal_name} {city}".strip()},
                             headers={"X-Goog-Api-Key": key,
                                      "X-Goog-FieldMask": "places.displayName,places.rating,places.userRatingCount,places.googleMapsUri"})
        r.raise_for_status()
        places = r.json().get("places", [])
    except Exception as e:
        log.info("rating lookup failed: %s", type(e).__name__)
        return "unavailable", []
    p = next((p for p in places if N.compare((p.get("displayName") or {}).get("text", ""), legal_name).score >= N.PARTIAL_AT), None)
    if not p or not p.get("userRatingCount"):
        return "checked", [_sig("reviews", 0, "No Google listing with reviews found", "Common for businesses that only sell to companies.")]
    rating, n, link = p.get("rating", 0), p.get("userRatingCount", 0), p.get("googleMapsUri", "")
    if n >= 10 and rating < 2.5:
        return "checked", [_sig("reviews", 20, f"Poor Google rating: {rating} from {n} reviews", "", link)]
    if n >= 10 and rating < 3.5:
        return "checked", [_sig("reviews", 8, f"Below-average Google rating: {rating} from {n} reviews", "", link)]
    return "checked", [_sig("reviews", 0, f"Google rating {rating} from {n} reviews", "", link)]


# --- putting it together ------------------------------------------------------------------------------------
def score(signals: list[dict]) -> int:
    by: dict[str, int] = {}
    for x in signals:
        by[x["source"]] = by.get(x["source"], 0) + int(x["weight"])
    return min(100, sum(min(CAP.get(k, 100), v) for k, v in by.items()))


async def check_run(run_id: int):
    """Check the vendor behind this run and store the result. Never raises."""
    from onboarding.models import Application, ReliabilityCheck, Run
    from onboarding.pipeline import sessions
    try:
        async with sessions()() as s:
            run = await s.get(Run, run_id)
            if not run or run.state != "done":
                return None
            app = await s.get(Application, run.application_id)
            f = run.form or {}
            name = f.get("legal_name") or app.legal_name
            signals = await history(s, run, app)
            st = {"history": "checked"}
            if get_settings().news_search:   # news uses the trade name ("BYJU'S"), not the legal one, when the certificate prints it
                st["news"], extra = await news(await trade_name(s, run.id) or name)
                signals += extra
            else:
                st["news"] = "off"
            (st["sanctions"], a), (st["reviews"], b) = await asyncio.gather(sanctions(name), reviews(name, f.get("city", "")))
            signals += a + b
            sc = score(signals)
            row = ReliabilityCheck(application_id=app.id, run_id=run.id, score=sc, level=level_of(sc),
                                   signals=sorted(signals, key=lambda x: -x["weight"]), sources=st)
            s.add(row)
            await s.commit()
            return row
    except Exception:
        log.exception("reliability check for run %s failed", run_id)
        return None


async def trade_name(s, run_id: int) -> str:
    from onboarding.models import Document
    doc = (await s.execute(select(Document).where(Document.run_id == run_id, Document.slot == "gst_certificate"))).scalars().first()
    fields = (doc.read or {}).get("fields", []) if doc and isinstance(doc.read, dict) else []
    return next((x.get("value") or "" for x in fields if x.get("name") == "trade_name" and x.get("value")), "")


async def latest(s, application_id: int):
    from onboarding.models import ReliabilityCheck
    return (await s.execute(select(ReliabilityCheck).where(ReliabilityCheck.application_id == application_id)
                            .order_by(ReliabilityCheck.id.desc()))).scalars().first()
