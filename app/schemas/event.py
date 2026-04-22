import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EventIn(BaseModel):
    event_id:       uuid.UUID
    event_type:     Literal["payment_initiated", "payment_processed", "payment_failed", "settled"]
    transaction_id: uuid.UUID
    merchant_id:    str
    merchant_name:  str
    amount:         float
    currency:       str = "INR"
    timestamp:      datetime
