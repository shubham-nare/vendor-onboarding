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


class StaffLogin(Base):
    """An employee's password for the company console (salted scrypt hash). The email is the employee's."""
    __tablename__ = "staff_logins"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class EmailDelivery(Base):
    """One email of one vendor message (added table). status: sent | failed | not_configured | no_address."""
    __tablename__ = "email_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True, unique=True)
    to_addr: Mapped[str] = mapped_column(String(400), default="")
    delivered_to: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    error: Mapped[str] = mapped_column(String(300), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    audience: Mapped[str] = mapped_column(String(10))   # vendor | internal
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(10), default="draft")  # draft | sent | held
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReliabilityCheck(Base):
    """How reliable a vendor looks, from our own history and outside sources (onboarding/reliability.py).
    One row per check; the newest for an application is the one shown. Advisory only: a person decides."""
    __tablename__ = "reliability_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    score: Mapped[int] = mapped_column(Integer, default=0)            # 0-100, higher = more concern
    level: Mapped[str] = mapped_column(String(10), default="low")    # low | medium | high
    signals: Mapped[list] = mapped_column(JSON, default=list)        # [{source, weight, title, detail, link}]
    sources: Mapped[dict] = mapped_column(JSON, default=dict)        # source -> checked | not connected | unavailable | off


class FollowUp(Base):
    """One step of chasing a vendor who hasn't answered: a reminder to the vendor, or an escalation to the
    employee who asked for them. Keyed by the check (run) that is waiting, so a resubmission that is again
    incomplete starts its own clock, and the daily job never sends the same step twice."""
    __tablename__ = "follow_ups"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))       # reminder | escalation
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)   # the vendor reminder
    note_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)      # the note to the requester
    to_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    waiting_days: Mapped[int] = mapped_column(Integer, default=0)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("run_id", "kind"),)


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


class VendorAccount(Base):
    """A vendor's login to the supplier portal. Passwords are stored only as salted scrypt hashes."""
    __tablename__ = "vendor_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)   # lower-case
    password_hash: Mapped[str] = mapped_column(String(300))
    company_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VendorLink(Base):
    """Ties an account to an invite it opened (before submitting) and to the application it created."""
    __tablename__ = "vendor_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("vendor_accounts.id"), index=True)
    invite_id: Mapped[int | None] = mapped_column(ForeignKey("invites.id"), nullable=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VendorBill(Base):
    """A bill from an ACTIVE vendor (after onboarding). Checked like the registration bill, confirmed by
    the employee who engaged the vendor, then approved for payment by someone else."""
    __tablename__ = "vendor_bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)          # BILL-0001
    account_id: Mapped[int] = mapped_column(ForeignKey("vendor_accounts.id"), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(String(20), index=True)                 # V-1001
    invoice_number: Mapped[str] = mapped_column(String(60))
    invoice_date: Mapped[str] = mapped_column(String(20), default="")
    amount: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    engaged_by_text: Mapped[str] = mapped_column(String(200), default="")
    engaged_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    po_number: Mapped[str] = mapped_column(String(60), default="")
    filename: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(ForeignKey("stored_files.sha256"))
    read: Mapped[dict] = mapped_column(JSON, default=dict)
    authenticity: Mapped[dict] = mapped_column(JSON, default=dict)
    rules: Mapped[list] = mapped_column(JSON, default=list)
    vendor_items: Mapped[list] = mapped_column(JSON, default=list)   # what the vendor must fix
    fraud: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_tier: Mapped[str] = mapped_column(String(10), default="")
    # checking | vendor_fix | for_review | awaiting_confirmation | ready_for_approval | approved | rejected | failed
    status: Mapped[str] = mapped_column(String(30), default="checking")
    confirmation: Mapped[str] = mapped_column(String(20), default="awaiting")      # awaiting | confirmed | denied
    trail: Mapped[list] = mapped_column(JSON, default=list)          # [{at, who, role, action, comment}]
    submissions: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Vendor Intelligence tables live in their own module; importing it registers them with Base.metadata (create_all).
from onboarding.intel import models as _intel_models  # noqa: E402,F401

from onboarding.ap import models as _ap_models  # noqa: E402,F401  (purchase orders, invoices, payments, audit)
