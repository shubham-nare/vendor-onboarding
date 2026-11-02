"""Accounts payable: purchase orders, receipts, invoice cases, payments, change requests and the audit log.

Additive tables only (no migration tool yet). An invoice is still a vendor_bills row (the vendor's upload and its
checks); invoice_cases adds what the brief needs around it: the purchase order and receipt it was matched to, the
match result, and the payment lifecycle. Approval to onboard a vendor is never approval to pay: payment needs an
approved invoice, then a separate release by a different person.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from onboarding.models import Base, now

TENANT = "default"


class PurchaseOrder(Base):
    """A company-side purchase order (entered or imported). vendor_gstin ties it to the supplier even before the
    vendor is onboarded; vendor_pk is set once the vendor exists in Vendor Intelligence."""
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    po_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    vendor_gstin: Mapped[str] = mapped_column(String(15), index=True)
    vendor_name: Mapped[str] = mapped_column(String(200), default="")
    vendor_pk: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(12), default="open")     # open | closed | cancelled
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    cost_centre: Mapped[str] = mapped_column(String(40), default="")
    requester_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)   # who needs the work
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)    # who approved the PO
    service_from: Mapped[str] = mapped_column(String(10), default="")
    service_to: Mapped[str] = mapped_column(String(10), default="")
    payee_account_key: Mapped[str] = mapped_column(String(40), default="")    # HMAC of the approved payee account
    payee_account_display: Mapped[str] = mapped_column(String(40), default="")
    payee_ifsc: Mapped[str] = mapped_column(String(11), default="")
    source: Mapped[str] = mapped_column(String(10), default="manual")         # manual | import | seed
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="")
    unit_price: Mapped[float] = mapped_column(Float)
    tax_rate: Mapped[float] = mapped_column(Float, default=18.0)   # GST %, all heads together


class GoodsReceipt(Base):
    """A goods-receipt note or a service confirmation: the company's record that the work was delivered."""
    __tablename__ = "goods_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="service")   # goods | service
    received_on: Mapped[str] = mapped_column(String(10), default="")
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("po_lines.id"))
    quantity: Mapped[float] = mapped_column(Float)


class InvoiceCase(Base):
    """Everything around one invoice (a vendor_bills row) beyond the vendor's upload: the PO and receipts it was
    matched to, the three-way match, and payment. payment_status: none | unpaid | on_hold | in_progress | paid."""
    __tablename__ = "invoice_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    bill_id: Mapped[int] = mapped_column(ForeignKey("vendor_bills.id"), unique=True)
    vendor_pk: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    po_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_ids: Mapped[list] = mapped_column(JSON, default=list)
    match: Mapped[dict] = mapped_column(JSON, default=dict)      # {lines: [...], expected_total, invoiced_total, tolerance}
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(12), default="none")
    hold_reason: Mapped[str] = mapped_column(Text, default="")
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    released_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_reference: Mapped[str] = mapped_column(String(60), default="")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_recorded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChangeRequest(Base):
    """A vendor's request to change company details or the bank account. A new account starts unverified and needs
    its own review; it never inherits the old account's status."""
    __tablename__ = "change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    vendor_pk: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("vendor_accounts.id"), index=True)
    erp_vendor_id: Mapped[str] = mapped_column(String(20), default="")
    kind: Mapped[str] = mapped_column(String(20))            # bank_account | contact | address
    requested: Mapped[dict] = mapped_column(JSON, default=dict)   # masked display values
    requested_enc: Mapped[str] = mapped_column(Text, default="")  # AES-GCM of the full new values (bank account)
    document_sha256: Mapped[str] = mapped_column(String(64), default="")
    document_name: Mapped[str] = mapped_column(String(255), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="submitted")   # submitted | approved | rejected
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    """Immutable record of a material action: decisions, overrides, invoice dispositions, holds, payments, PO and
    receipt entries, bank-change reviews. Written once, never updated."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), default=TENANT)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_label: Mapped[str] = mapped_column(String(120), default="")
    entity: Mapped[str] = mapped_column(String(20))           # invoice | application | purchase_order | receipt | change_request | vendor
    entity_id: Mapped[str] = mapped_column(String(40))
    entity_label: Mapped[str] = mapped_column(String(120), default="")
    vendor_pk: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    override: Mapped[bool] = mapped_column(Boolean, default=False)
