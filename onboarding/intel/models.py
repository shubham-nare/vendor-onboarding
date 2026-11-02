"""Vendor Intelligence tables. Additive only: no existing table is changed (there is no migration tool yet).

Every table carries tenant_id so cross-buyer isolation never needs a rewrite. Evidence items, fact observations
and decision snapshots are written once and never updated (enforced in code; a database trigger comes with Alembic).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from onboarding.models import Base, now

TENANT = "default"


class Vendor(Base):
    """One legal entity we deal with. vendor_id (VND-0001) is generated here and never changes; PAN is the main
    matching attribute for Indian vendors, not the identity itself (a vendor without a PAN still gets a vendor_id)."""
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT, index=True)
    vendor_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    country: Mapped[str] = mapped_column(String(2), default="IN")
    status: Mapped[str] = mapped_column(String(20), default="onboarding")  # onboarding | active | rejected | on_record
    origin: Mapped[str] = mapped_column(String(20), default="application")  # application | vendor_master
    erp_vendor_id: Mapped[str] = mapped_column(String(20), default="", index=True)  # vendor_master.vendor_id, once there
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VendorApplication(Base):
    """Which vendor an application belongs to, and how that was decided."""
    __tablename__ = "vendor_applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_pk: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    method: Mapped[str] = mapped_column(String(30))   # pan_match | new_vendor | no_pan
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VendorIdentifier(Base):
    """An identifier a vendor has used. lookup_key = keyed HMAC; value_enc = AES-GCM of the original."""
    __tablename__ = "vendor_identifiers"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    vendor_pk: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))     # PAN | GSTIN | CIN | LLPIN | UDYAM | BANK_ACCOUNT | IFSC | EMAIL | PHONE | ADDRESS
    lookup_key: Mapped[str] = mapped_column(String(40), index=True)
    value_enc: Mapped[str] = mapped_column(Text, default="")
    display: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(10), default="current")  # current | previous
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    first_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("vendor_pk", "kind", "lookup_key"),)


class EvidenceItem(Base):
    """An immutable piece of evidence: a submitted form, a document (by SHA-256), a source answer, a rule result,
    a vendor-master record or a person's decision. `basis` says how trustworthy it is: live | simulated | snapshot |
    document | signature | math | declared | vendor_master | rule | human."""
    __tablename__ = "evidence_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    vendor_pk: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30))      # form_submission | document | source_response | rule_result | vendor_master_record | human_decision
    ref: Mapped[str] = mapped_column(String(120))      # stable key, e.g. run:7:doc:pan_card
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    basis: Mapped[str] = mapped_column(String(20))
    source_label: Mapped[str] = mapped_column(String(200), default="")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)   # masked
    __table_args__ = (UniqueConstraint("vendor_pk", "kind", "ref"),)


class FactObservation(Base):
    """What we believed about one fact at one time, at which assurance level, from which evidence. Never updated:
    a later observation supersedes an earlier one (supersedes_id), so the history stays."""
    __tablename__ = "fact_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    vendor_pk: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    fact: Mapped[str] = mapped_column(String(30))      # GSTIN | LEGAL_NAME | PAN | BANK_ACCOUNT | BANK_BRANCH | MSME
    value_display: Mapped[str] = mapped_column(String(255))
    value_key: Mapped[str] = mapped_column(String(40), default="")
    level: Mapped[str] = mapped_column(String(4))      # A0..A4 (same meaning as the onboarding grading)
    basis: Mapped[str] = mapped_column(String(20))
    source_label: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(String(255), default="")
    evidence_item_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_items.id"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    supersedes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("vendor_pk", "fact", "run_id"),)


class GraphNode(Base):
    """A thing vendors can share: a PAN, GSTIN, bank account, IFSC, address, email, phone, document, or a vendor."""
    __tablename__ = "graph_nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    kind: Mapped[str] = mapped_column(String(20))
    lookup_key: Mapped[str] = mapped_column(String(64))
    display: Mapped[str] = mapped_column(String(255), default="")
    vendor_pk: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "lookup_key"),)


class GraphEdge(Base):
    """A typed relationship with provenance (evidence item, rule), status and time.
    status: verified (evidence-backed) | declared (only stated) | inferred (derived) | unresolved (a conflict for a person).
    valid_to is set when the relationship stops being current (e.g. the vendor declared a different bank account)."""
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    src_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    dst_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(12))
    basis: Mapped[str] = mapped_column(String(20))
    rule_id: Mapped[str] = mapped_column(String(20), default="")
    evidence_item_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_items.id"), nullable=True)
    first_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = (UniqueConstraint("src_id", "dst_id", "type"),)


class RiskEvent(Base):
    """Something a reviewer must look at, raised only where an existing onboarding rule already justifies it
    (shared bank account, reused document, identity conflict, blocklist, duplicate registration). Never a decision."""
    __tablename__ = "risk_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    vendor_pk: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    application_id: Mapped[int] = mapped_column(Integer, index=True)
    run_id: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))   # review | fraud
    title: Mapped[str] = mapped_column(Text)
    reviewer_action: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="open")   # open | resolved
    resolution: Mapped[str] = mapped_column(Text, default="")
    evidence_item_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_items.id"), nullable=True)
    edge_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_vendor_pk: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("run_id", "rule_id"),)


class DecisionSnapshot(Base):
    """The complete input of one decision (encrypted: it holds the raw form) and its outcome, so it can be replayed.
    reconstructed=True: rebuilt after the fact from stored data; replay_ok says whether that rebuild reproduces the
    original decision exactly (simulation is refused if not)."""
    __tablename__ = "decision_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True)
    policy_version: Mapped[str] = mapped_column(String(20), default="v1")
    context_enc: Mapped[str] = mapped_column(Text)
    context_sha256: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[dict] = mapped_column(JSON)          # {status, risk_tier, rules: [[id, result, outcome]]}
    reconstructed: Mapped[bool] = mapped_column(Boolean, default=False)
    replay_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    replay_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SimulationRun(Base):
    """A counterfactual: the only thing a simulation ever writes."""
    __tablename__ = "simulation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scenario: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DomainEvent(Base):
    """Business events (run.completed, decision.recorded, ...), recorded with when they were processed.
    Separate from run_events, which only drive the live view."""
    __tablename__ = "domain_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    type: Mapped[str] = mapped_column(String(40), index=True)
    aggregate: Mapped[str] = mapped_column(String(20))
    aggregate_id: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
