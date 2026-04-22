import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, relationship

from app.db.database import Base


class PaymentStatus(enum.Enum):
    payment_initiated = "payment_initiated"
    payment_processed = "payment_processed"
    payment_failed = "payment_failed"


class SettlementStatus(enum.Enum):
    pending = "pending"
    settled = "settled"


class Merchant(Base):
    __tablename__ = "merchants"

    merchant_id = mapped_column(String, primary_key=True)
    merchant_name = mapped_column(String, nullable=False)

    transactions = relationship("Transaction")


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = mapped_column(String, ForeignKey("merchants.merchant_id"), nullable=False)
    amount = mapped_column(Numeric(10, 2), nullable=False)
    currency = mapped_column(String(3), nullable=False, default="INR")
    status = mapped_column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.payment_initiated)
    settlement_status = mapped_column(Enum(SettlementStatus), nullable=False, default=SettlementStatus.pending)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    merchant = relationship('Merchant')
    events = relationship('Event')

    __table_args__ = (
        Index("ix_transactions_merchant_id", "merchant_id"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_created_at", "created_at"),
        Index("ix_transactions_updated_at", "updated_at"),
    )


class Event(Base):
    __tablename__ = "events"

    event_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    transaction_id = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=False)
    event_type = mapped_column(String(32), nullable=False)
    timestamp = mapped_column(DateTime(timezone=True), nullable=False)

    transaction = relationship('Transaction')

    __table_args__ = (
        Index("ix_events_transaction_id", "transaction_id"),
    )
