from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import get_db

router = APIRouter()

ALLOWED_DIMENSIONS = {"merchant", "date", "status"}

DIMENSION_SELECT = {
    "merchant": "t.merchant_id, m.merchant_name,",
    "date":     "DATE(t.created_at) AS date,",
    "status":   "t.status, t.settlement_status,",
}

DIMENSION_GROUP = {
    "merchant": "t.merchant_id, m.merchant_name",
    "date":     "DATE(t.created_at)",
    "status":   "t.status, t.settlement_status",
}


@router.get("/reconciliation/summary")
def reconciliation_summary(
    group_by: str     = Query("merchant", description="Comma separated: merchant, date, status"),
    db:       Session = Depends(get_db),
):
    dimensions = [d.strip() for d in group_by.split(",")]
    invalid = set(dimensions) - ALLOWED_DIMENSIONS
    if invalid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"invalid dimensions: {invalid}. allowed: {ALLOWED_DIMENSIONS}")

    select_parts = " ".join(DIMENSION_SELECT[d] for d in dimensions)
    group_parts  = ", ".join(DIMENSION_GROUP[d] for d in dimensions)

    needs_merchant_join = "merchant" in dimensions

    query = f"""
        SELECT
            {select_parts}
            COUNT(*)                                                 AS total_transactions,
            SUM(t.amount)                                            AS total_amount,
            COUNT(*) FILTER (WHERE t.status = 'payment_initiated')  AS initiated,
            COUNT(*) FILTER (WHERE t.status = 'payment_processed')  AS processed,
            COUNT(*) FILTER (WHERE t.status = 'payment_failed')     AS failed,
            COUNT(*) FILTER (WHERE t.settlement_status = 'settled') AS settled
        FROM transactions t
        {"JOIN merchants m ON t.merchant_id = m.merchant_id" if needs_merchant_join else ""}
        GROUP BY {group_parts}
        ORDER BY {group_parts}
    """

    rows = db.execute(text(query)).fetchall()
    return {"group_by": dimensions, "data": [dict(row._mapping) for row in rows]}


@router.get("/reconciliation/discrepancies")
def reconciliation_discrepancies(
    page:      int     = Query(1, ge=1),
    page_size: int     = Query(20, ge=1, le=100),
    db:        Session = Depends(get_db),
):
    total = db.execute(text("""
        SELECT COUNT(*)
        FROM transactions t
        WHERE
            (t.status = 'payment_failed'    AND t.settlement_status = 'settled')
            OR
            (t.status = 'payment_processed' AND t.settlement_status = 'pending')
    """)).scalar()

    rows = db.execute(text("""
        SELECT
            t.transaction_id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.status,
            t.settlement_status,
            t.created_at,
            t.updated_at,
            CASE
                WHEN t.status = 'payment_failed'    AND t.settlement_status = 'settled' THEN 'settled after failure'
                WHEN t.status = 'payment_processed' AND t.settlement_status = 'pending' THEN 'processed but not settled'
            END AS discrepancy_reason
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.merchant_id
        WHERE
            (t.status = 'payment_failed'    AND t.settlement_status = 'settled')
            OR
            (t.status = 'payment_processed' AND t.settlement_status = 'pending')
        ORDER BY t.updated_at DESC
        LIMIT :limit OFFSET :offset
    """), {"limit": page_size, "offset": (page - 1) * page_size}).fetchall()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "data":      [dict(row._mapping) for row in rows],
    }
