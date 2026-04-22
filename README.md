# Payment Event Ingestion & Reconciliation Service

A backend service for ingesting payment lifecycle events, tracking transaction state, and identifying reconciliation discrepancies.

---

## Architecture Overview

```
app/
├── main.py                  — FastAPI app, table creation on startup
├── api/
│   ├── events.py            — POST /events
│   ├── transactions.py      — GET /transactions, GET /transactions/{id}
│   ├── reconciliation.py    — GET /reconciliation/summary, /discrepancies
│   └── seed.py              — POST /seed
├── models/
│   └── models.py            — SQLAlchemy ORM models + indexes
├── db/
│   └── database.py          — DB engine, session, Base
└── config/
    └── settings.py          — loads DATABASE_URL from .env

schemas/
└── event.py                 — Pydantic request validation
```

**Stack:** FastAPI, PostgreSQL, SQLAlchemy ORM, Pydantic

Business logic lives in route handlers directly. A service layer would add indirection without benefit at this scale — in production, event ingestion logic would move to a service class to support independent testing and reuse.

---

## Local Setup

### Prerequisites
- Python 3.10+
- PostgreSQL running locally

### Steps

```bash
# clone the repo
git clone https://github.com/Lokesh396/setu.git
cd setu

# create virtual environment
python -m venv venv
source venv/bin/activate

# install dependencies
pip install -r requirements.txt

# create the database
psql -U postgres -c "CREATE DATABASE setu;"

# configure environment
cp .env.example .env
# edit .env and set your DATABASE_URL

# start the server
uvicorn app.main:app --reload
```

Tables are created automatically on startup via `Base.metadata.create_all`.

### Seed Data

Hit `POST /seed` to load all 10,355 sample events:
This endpoint is exposed for reviewer convenience.

```bash
curl -X POST http://localhost:8000/seed
```

Safe to call multiple times — duplicate events are skipped idempotently.

---

## API Documentation

Full interactive docs available at `http://localhost:8000/docs`.

### POST /events

Ingest a payment lifecycle event.

**Request body:**
```json
{
  "event_id": "b768e3a7-9eb3-4603-b21c-a54cc95661bc",
  "event_type": "payment_initiated",
  "transaction_id": "2f86e94c-239c-4302-9874-75f28e3474ee",
  "merchant_id": "merchant_2",
  "merchant_name": "FreshBasket",
  "amount": 15248.29,
  "currency": "INR",
  "timestamp": "2026-01-08T12:11:58.085567+00:00"
}
```

**Event types:** `payment_initiated`, `payment_processed`, `payment_failed`, `settled`

**Response:**
```json
{"message": "event ingested"}
```

---

### GET /transactions

List transactions with optional filters, pagination, and sorting.

**Query params:**

| Param | Type | Description |
|---|---|---|
| `merchant_id` | string | Filter by merchant |
| `status` | string | Filter by payment status |
| `from_date` | datetime | Filter by created_at >= |
| `to_date` | datetime | Filter by created_at <= |
| `page` | int | Page number (default: 1) |
| `page_size` | int | Results per page (default: 20, max: 100) |
| `sort_by` | string | Column to sort by (default: created_at) |
| `order` | string | `asc` or `desc` (default: desc) |

**Response:**
```json
{
  "total": 3800,
  "page": 1,
  "page_size": 20,
  "data": [...]
}
```

---

### GET /transactions/{transaction_id}

Fetch a single transaction with merchant info and full event history.

**Response:**
```json
{
  "transaction_id": "...",
  "amount": 15248.29,
  "currency": "INR",
  "status": "payment_processed",
  "settlement_status": "settled",
  "created_at": "...",
  "updated_at": "...",
  "merchant": {
    "merchant_id": "merchant_2",
    "merchant_name": "FreshBasket"
  },
  "event_history": [
    {"event_id": "...", "event_type": "payment_initiated", "timestamp": "..."},
    {"event_id": "...", "event_type": "payment_processed", "timestamp": "..."},
    {"event_id": "...", "event_type": "settled", "timestamp": "..."}
  ]
}
```

---

### GET /reconciliation/summary

Aggregated transaction summary grouped by one or more dimensions.

**Query params:**

| Param | Default | Options |
|---|---|---|
| `group_by` | `merchant` | `merchant`, `date`, `status` — comma separated |

**Examples:**
```
GET /reconciliation/summary?group_by=merchant
GET /reconciliation/summary?group_by=date
GET /reconciliation/summary?group_by=merchant,date
GET /reconciliation/summary?group_by=merchant,date,status
```

**Response:**
```json
{
  "group_by": ["merchant", "date"],
  "data": [
    {
      "merchant_id": "merchant_1",
      "merchant_name": "...",
      "date": "2026-01-08",
      "total_transactions": 120,
      "total_amount": 182934.50,
      "initiated": 10,
      "processed": 80,
      "failed": 30,
      "settled": 75
    }
  ]
}
```

---

### GET /reconciliation/discrepancies

Returns transactions where payment state and settlement state are inconsistent.

**Discrepancy cases:**
- `payment_processed` but `settlement_status = pending` — processed but never settled
- `payment_failed` but `settlement_status = settled` — settled after a failure
- Duplicate events (same event_id) are dropped before reaching the state machine, so they never cause conflicting transitions. The 190 duplicates in the sample data are all silently skipped at ingestion.

**Query params:** `page`, `page_size`

**Response:**
```json
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "transaction_id": "...",
      "merchant_id": "merchant_3",
      "status": "payment_failed",
      "settlement_status": "settled",
      "discrepancy_reason": "settled after failure",
      ...
    }
  ]
}
```

---

## Schema Design

```
merchants         — merchant_id (PK), merchant_name
transactions      — transaction_id (PK), merchant_id (FK), amount, currency,
                    status (enum), settlement_status (enum), created_at, updated_at
events            — event_id (PK), transaction_id (FK), event_type, timestamp
```

**Indexes:**
- `transactions(merchant_id)` — filter by merchant
- `transactions(status)` — filter by status
- `transactions(created_at)` — date range filter
- `transactions(updated_at)` — sort discrepancies
- `events(transaction_id)` — event history lookup

**Two status columns** (`status` and `settlement_status`) track payment and settlement as independent lifecycles. This allows discrepancy detection via a simple SQL WHERE clause without scanning event history.

---

## Idempotency

Duplicate events (same `event_id`) are silently skipped. The `event_id` primary key constraint prevents duplicate storage. The sample data contains 190 duplicate event IDs — all handled correctly.

---

## State Machine

Valid payment transitions:
```
payment_initiated → payment_processed
payment_initiated → payment_failed
payment_processed → (no further payment transitions)
```

Settlement is tracked separately via `settlement_status`. Invalid transitions are stored in event history but do not update transaction state.

---

## Assumptions & Tradeoffs

**Events arrive in order.** Verified against the sample data — all 3,800 transactions follow the correct lifecycle sequence. Out-of-order delivery (e.g. `payment_processed` before `payment_initiated`) returns a 400. A production system would use a message queue with ordering guarantees.

**Duplicate events are truly identical**. The system assumes a duplicate `event_id` always carries the same `event_type` and `transaction_id` as the original. A duplicate with the same `event_id` but a different `event_type` would be silently skipped rather than flagged — this case is not handled. The sample data confirms all 190 duplicates are exact copies.

**One event per type per transaction**. The system assumes each event type appears at most once per transaction. If two distinct `payment_initiated` events arrive for the same transaction (different `event_id`, same `event_type`), the second is stored in event history but does not update transaction state — it will not be flagged as a discrepancy. The sample data confirms this does not occur.

**Offset-based pagination.** Used for simplicity. Deep pagination degrades on large datasets because PostgreSQL scans skipped rows. Keyset (cursor-based) pagination would be the production choice.

**No service layer.** Business logic lives in route handlers. At this scale the indirection adds no value. A production system would extract event ingestion into a service class for independent testing and reuse.

**Reconciliation is query-time.** Discrepancies are computed on read via SQL rather than precomputed and stored. Clean for this scale; a production system with millions of records would maintain a materialized view or a background reconciliation job.

---

## Deployment

https://setu-tti9.onrender.com/docs

---

## AI Disclosure

Claude (Anthropic) was used as a sounding board during development. The schema design, state machine logic, idempotency approach, and reconciliation query design were my own decisions — I used Claude to pressure-test those decisions, spot bugs, and discuss tradeoffs (e.g. whether to use one or two status columns, whether to keep a separate reconciliation table, offset vs keyset pagination). Boilerplate was accelerated with AI assistance. All code was written with full understanding of every line.
