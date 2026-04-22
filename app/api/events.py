from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Event, Merchant, Transaction, PaymentStatus, SettlementStatus
from app.schemas.event import EventIn

router = APIRouter()

VALID_TRANSITIONS = {
    PaymentStatus.payment_initiated: [PaymentStatus.payment_processed, PaymentStatus.payment_failed],
    PaymentStatus.payment_processed: [],
    PaymentStatus.payment_failed:    [],
}


@router.post("/events", status_code=201)
def ingest_event(payload: EventIn, db: Session = Depends(get_db)):

    # idempotency check — same event_id, skip silently
    existing_event = db.get(Event, payload.event_id)
    if existing_event:
        return {"message": "duplicate event, skipped"}

    # upsert merchant
    merchant = db.get(Merchant, payload.merchant_id)
    if not merchant:
        merchant = Merchant(merchant_id=payload.merchant_id, merchant_name=payload.merchant_name)
        db.add(merchant)

    if payload.event_type == "payment_initiated":
        txn = db.get(Transaction, payload.transaction_id)
        if not txn:
            txn = Transaction(
                transaction_id=payload.transaction_id,
                merchant_id=payload.merchant_id,
                amount=payload.amount,
                currency=payload.currency,
                status=PaymentStatus.payment_initiated,
                settlement_status=SettlementStatus.pending,
                created_at=payload.timestamp,
                updated_at=payload.timestamp,
            )
            db.add(txn)

    elif payload.event_type == "settled":
        txn = db.get(Transaction, payload.transaction_id)
        if txn:
            txn.settlement_status = SettlementStatus.settled
            txn.updated_at = payload.timestamp

    else:
        # payment_processed or payment_failed — validate state machine
        txn = db.get(Transaction, payload.transaction_id)
        if txn:
            new_status = PaymentStatus(payload.event_type)
            if new_status in VALID_TRANSITIONS.get(txn.status, []):
                txn.status = new_status
                txn.updated_at = payload.timestamp
            # invalid transition — event stored but status not updated (discrepancy)

    # store event after transaction exists — FK constraint satisfied
    event = Event(
        event_id=payload.event_id,
        transaction_id=payload.transaction_id,
        event_type=payload.event_type,
        timestamp=payload.timestamp,
    )
    db.add(event)
    db.commit()
    return {"message": "event ingested"}
