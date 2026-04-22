from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Transaction, Merchant, Event, PaymentStatus

router = APIRouter()


@router.get("/transactions")
def list_transactions(
    merchant_id: Optional[str] = Query(None),
    status: Optional[PaymentStatus] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)

    if merchant_id:
        query = query.filter(Transaction.merchant_id == merchant_id)
    if status:
        query = query.filter(Transaction.status == status)
    if from_date:
        query = query.filter(Transaction.created_at >= from_date)
    if to_date:
        # extend to end of day so same-day from/to range works correctly
        if to_date.hour == 0 and to_date.minute == 0 and to_date.second == 0:
            to_date = to_date + timedelta(days=1) - timedelta(seconds=1)
        query = query.filter(Transaction.created_at <= to_date)

    sort_column = getattr(Transaction, sort_by, Transaction.created_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    total = query.count()
    transactions = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
        "data": [
            {
                "transaction_id": str(t.transaction_id),
                "merchant_id": t.merchant_id,
                "amount": float(t.amount),
                "currency": t.currency,
                "status": t.status.value,
                "settlement_status": t.settlement_status.value,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in transactions
        ],
    }


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    txn = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="transaction not found")

    merchant = db.get(Merchant, txn.merchant_id)
    events = db.query(Event).filter(Event.transaction_id == transaction_id).order_by(Event.timestamp.asc()).all()

    return {
        "transaction_id": str(txn.transaction_id),
        "amount": float(txn.amount),
        "currency": txn.currency,
        "status": txn.status.value,
        "settlement_status": txn.settlement_status.value,
        "created_at": txn.created_at,
        "updated_at": txn.updated_at,
        "merchant": {
            "merchant_id": merchant.merchant_id,
            "merchant_name": merchant.merchant_name,
        },
        "event_history": [
            {
                "event_id": str(e.event_id),
                "event_type": e.event_type,
                "timestamp": e.timestamp,
            }
            for e in events
        ],
    }
