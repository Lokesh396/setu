import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Event, Merchant, Transaction, PaymentStatus, SettlementStatus

router = APIRouter()

VALID_TRANSITIONS = {
    PaymentStatus.payment_initiated: [PaymentStatus.payment_processed, PaymentStatus.payment_failed],
    PaymentStatus.payment_processed: [],
    PaymentStatus.payment_failed: [],
}


@router.post("/seed", status_code=200)
def seed(db: Session = Depends(get_db)):
    with open("sample_events.json") as f:
        events = json.load(f)

    ingested = 0
    skipped = 0

    for payload in events:
        event_id = UUID(payload["event_id"])
        transaction_id = UUID(payload["transaction_id"])

        if db.get(Event, event_id):
            skipped += 1
            continue

        merchant = db.get(Merchant, payload["merchant_id"])
        if not merchant:
            merchant = Merchant(
                merchant_id=payload["merchant_id"],
                merchant_name=payload["merchant_name"],
            )
            db.add(merchant)

        event_type = payload["event_type"]
        timestamp = payload["timestamp"]

        if event_type == "payment_initiated":
            txn = db.get(Transaction, transaction_id)
            if not txn:
                txn = Transaction(
                    transaction_id=transaction_id,
                    merchant_id=payload["merchant_id"],
                    amount=payload["amount"],
                    currency=payload["currency"],
                    status=PaymentStatus.payment_initiated,
                    settlement_status=SettlementStatus.pending,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                db.add(txn)

        elif event_type == "settled":
            txn = db.get(Transaction, transaction_id)
            if txn:
                txn.settlement_status = SettlementStatus.settled
                txn.updated_at = timestamp

        else:
            txn = db.get(Transaction, transaction_id)
            if not txn:
                skipped += 1
                continue
            new_status = PaymentStatus(event_type)
            if new_status in VALID_TRANSITIONS.get(txn.status, []):
                txn.status = new_status
                txn.updated_at = timestamp

        event = Event(
            event_id=event_id,
            transaction_id=transaction_id,
            event_type=event_type,
            timestamp=timestamp,
        )
        db.add(event)
        ingested += 1

        if ingested % 500 == 0:
            db.commit()

    db.commit()
    return {"ingested": ingested, "skipped": skipped}
