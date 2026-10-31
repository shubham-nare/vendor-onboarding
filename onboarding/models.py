"""Database tables (docs/PLAN.md §3). Works on Neon Postgres and on local SQLite."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # sponsor | maker | checker
    email: Mapped[str] = mapped_column(String(200), default="")


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sponsor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    company_name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str] = mapped_column(String(200))
    business_reason: Mapped[str] = mapped_column(Text)
    spend_category: Mapped[str] = mapped_column(String(100))
    spend_band: Mapped[str] = mapped_column(String(40))       # e.g. "10-25 lakh"
    high_spend: Mapped[bool] = mapped_column(Boolean, default=False)
    scenario_key: Mapped[str] = mapped_column(String(60), default="", index=True)  # demo only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | used | expired | revoked
    sponsor: Mapped[Employee] = relationship()


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # e.g. VOB-0007
    invite_id: Mapped[int | None] = mapped_column(ForeignKey("invites.id"), nullable=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    current_status: Mapped[str] = mapped_column(String(30), default="IN_PROGRESS")
    invite: Mapped[Invite | None] = relationship()
    runs: Mapped[list["Run"]] = relationship(back_populates="application", order_by="Run.id")


class Bill(Base):
    """A bill submitted with a vendor's self-registration (no invite): the vendor already did work for us.
    The vendor's private link (token) works like an invite link for status and resubmission. The bill's
    figures live in each run's form; this row holds who must confirm the engagement, and their answer."""
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    engaged_by_text: Mapped[str] = mapped_column(String(200), default="")      # what the vendor typed
    engaged_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    confirmation: Mapped[str] = mapped_column(String(20), default="awaiting")  # awaiting | confirmed | denied
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    engaged_employee: Mapped[Employee | None] = relationship()


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    form: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed | interrupted
    status: Mapped[str] = mapped_column(String(30), default="")       # APPROVED | PENDING_VENDOR | PENDING_REVIEW | REJECTED
    risk_tier: Mapped[str] = mapped_column(String(10), default="")
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)          # reason cards, assurance panel, diff
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application: Mapped[Application] = relationship(back_populates="runs")
    events: Mapped[list["RunEvent"]] = relationship(order_by="RunEvent.seq")
    documents: Mapped[list["Document"]] = relationship()
    rules: Mapped[list["RuleResult"]] = relationship()
    facts: Mapped[list["Fact"]] = relationship()
    messages: Mapped[list["Message"]] = relationship()
    actions: Mapped[list["HumanAction"]] = relationship(order_by="HumanAction.id")


class RunEvent(Base):
    """One row per stage update: the live run view replays these."""
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20))   # running | done | failed | skipped
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("run_id", "seq"),)


class StoredFile(Base):
    """File bytes, de-duplicated by SHA-256 (also powers the 'same file reused' check)."""
    __tablename__ = "stored_files"
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    mime: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    slot: Mapped[str] = mapped_column(String(40))           # gst_certificate | pan_card | bank_proof | udyam_certificate
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(ForeignKey("stored_files.sha256"), index=True)
    read: Mapped[dict] = mapped_column(JSON, default=dict)          # Gemini result
    authenticity: Mapped[dict] = mapped_column(JSON, default=dict)  # signals, level


class RuleResult(Base):
    __tablename__ = "rule_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(20))
    layer: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(10))       # PASS | FAIL | WARN | SKIPPED | ERROR
    outcome_if_fail: Mapped[str] = mapped_column(String(10), default="")  # REJECT | REVIEW | VENDOR | WARN
    title: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class Fact(Base):
    """A key fact about the vendor and how well it's proven (A0-A4)."""
    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(4))
    source: Mapped[str] = mapped_column(String(200))
    live: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    audience: Mapped[str] = mapped_column(String(10))   # vendor | internal
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(10), default="draft")  # draft | sent | held
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HumanAction(Base):
    __tablename__ = "human_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    employee: Mapped[Employee] = relationship()


class VendorMaster(Base):
    __tablename__ = "vendor_master"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(20), unique=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    pan: Mapped[str] = mapped_column(String(10), index=True)
    gstin: Mapped[str] = mapped_column(String(15), index=True)
    account: Mapped[str] = mapped_column(String(20), index=True)
    ifsc: Mapped[str] = mapped_column(String(11))
    status: Mapped[str] = mapped_column(String(20))
    source_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set when activated from a run


class Blocklist(Base):
    __tablename__ = "blocklist"
    id: Mapped[int] = mapped_column(primary_key=True)
    pan: Mapped[str] = mapped_column(String(10), default="", index=True)
    gstin: Mapped[str] = mapped_column(String(15), default="", index=True)
    account: Mapped[str] = mapped_column(String(20), default="")
    reason: Mapped[str] = mapped_column(Text)


class SimRegistry(Base):
    """What the SIMULATED source adapters answer from (GST, PAN, penny-drop, CIN, Udyam)."""
    __tablename__ = "sim_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))     # gst | pan | bank | cin | udyam
    key: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("kind", "key"),)
