"""Vendor Intelligence: one canonical vendor, its evidence history, its relationships and what to do next.

Built on top of the onboarding pipeline without changing its decisions (docs/PRODUCT_EVOLUTION.md):
  models.py    new tables only (additive)
  crypto.py    keyed HMAC matching keys + AES-GCM for values that must be retrievable
  snapshot.py  the exact input of each decision (encrypted), replay and the fidelity check
  project.py   identity, evidence, fact history, graph and risk flags, built from finished runs (idempotent)
  vendor360.py the read side: one vendor's profile, connections and next best actions
"""
