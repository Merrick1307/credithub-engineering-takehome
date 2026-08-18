# PostgreSQL Setup & Alembic Migrations

## Overview

This project now includes:
- **PostgreSQL schema** with proper `NUMERIC(20,2)` types for all money fields
- **Alembic migrations** for schema versioning and reproducibility
- **Connection pooling** via SQLAlchemy's `QueuePool` (PostgreSQL) and `NullPool` (SQLite)
- **Dependency injection** via `app/dependencies.py` (injected by lifespan context manager)

## Running Tests (SQLite)

Tests use SQLite in-memory to avoid PostgreSQL setup overhead. Run normally:

```bash
pytest tests/ -v
```

The test fixture in `tests/conftest.py`:
1. Drops and recreates SQLite tables
2. Seeds initial data (2 loans)
3. Initializes the session factory for DI
4. Runs the test

All 12 tests pass with SQLite.

## Running Against PostgreSQL

### Prerequisites

1. **PostgreSQL server** running locally (version 12+)
2. **Create database and user**:

```bash
sudo -u postgres psql
CREATE USER credithub WITH PASSWORD 'credithub';
CREATE DATABASE credithub OWNER credithub;
GRANT ALL PRIVILEGES ON DATABASE credithub TO credithub;
\q
```

### Run Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Check migration status
alembic current
alembic history

# Downgrade one version (if needed)
alembic downgrade -1
```

### Environment Variables

Set `DATABASE_URL` to use PostgreSQL:

```bash
# Development
export DATABASE_URL="postgresql+psycopg://credithub:credithub@localhost/credithub"

# Production would use environment-specific credentials
```

If `DATABASE_URL` is not set, the app falls back to SQLite (`sqlite:///./takehome.db`).

### Start the Server

```bash
# With PostgreSQL
export DATABASE_URL="postgresql+psycopg://credithub:credithub@localhost/credithub"
uvicorn app.main:app --reload

# With SQLite (default)
uvicorn app.main:app --reload
```

The lifespan context manager will:
1. Initialize the connection pool on startup
2. Log "✓ Database connection pool initialized"
3. Dispose the pool on shutdown
4. Log "✓ Database connection pool closed"

## Connection Pool Configuration

### PostgreSQL (`QueuePool`)

In `app/db.py`:
- **`pool_size=10`**: Keep 10 persistent connections
- **`max_overflow=20`**: Allow up to 20 additional connections when pool exhausted
- **`pool_recycle=3600`**: Recycle connections after 1 hour (prevents "connection timeout" errors)
- **`pool_pre_ping=True`**: Test connections before using (handles stale connections)

Tune these based on workload:
- High traffic: Increase `pool_size` to 20–50
- Low traffic: Decrease `pool_size` to 5

### SQLite (`NullPool`)

SQLite does not support connection pooling (not thread-safe at that level).
Each request gets its own connection; the pool is a no-op.

## Schema Design

### Money Fields

All monetary amounts use `NUMERIC(20, 2)`:
- 20 digits total
- 2 decimal places
- Supports amounts up to **999,999,999,999,999,999.99**
- **Never** uses `Float` (no precision loss)
- Serialized as strings in JSON to preserve decimals exactly

```sql
-- Example: NUMERIC(20,2) column
amount NUMERIC(20, 2) NOT NULL
```

### Tables

1. **`loans`** — Loan principal and repayment status
   - PK: `id`
   - Indexed: `status`, `disbursed_at`

2. **`payment_events`** — Incoming payments from providers
   - PK: `id`
   - FK: `loan_id` → `loans.id`
   - Indexed: `external_ref` (for dedup), `loan_id`, `status`, `received_at`

3. **`repayments`** — Append-only component ledger of applications, reversals,
   overpayments, and refunds
   - PK: `id`
   - FK: `loan_id`, `payment_event_id`
   - Indexed: `loan_id`, `payment_event_id`, `created_at`

4. **`overpayments`** — Current projection of overpayment balances
5. **`webhook_deliveries`** — Sanitized callback-delivery facts
6. **`reconciliation_issues`** — Staff-operable exception queue
7. **`provider_lookup_retries`** — Persisted manual lookup-retry candidates
8. **`outbox_events`** — Committed downstream notifications awaiting publication
9. **`audit_log`** — Immutable user/system action trail
   - Indexed: `entity`, `created_at`

### Enum Types

PostgreSQL uses native `ENUM` types:
- `loanstatus`: `active`, `paid_off`, `cancelled`, `written_off`
- `paymentstatus`: `pending`, `applied`, `rejected`

SQLite stores these as `VARCHAR` (no native enum type).

## Creating a New Migration

1. **Make a schema change** in `app/models.py` (if ORM-driven)

2. **Create a revision file**:
```bash
alembic revision --autogenerate -m "description of change"
```

3. **Review the generated file** in `alembic/versions/` — autogenerate is not perfect; adjust if needed

4. **Test locally**:
```bash
alembic upgrade +1
# Test app
alembic downgrade -1
```

5. **Commit** the migration file along with code changes

### Manual Migration Example

For complex changes (e.g., data migrations), write a manual migration:

```python
# alembic/versions/002_add_customer_id.py
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'

def upgrade():
    op.add_column('loans', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.create_index('ix_loans_customer_id', 'loans', ['customer_id'])

def downgrade():
    op.drop_index('ix_loans_customer_id', table_name='loans')
    op.drop_column('loans', 'customer_id')
```

## Dependency Injection

The `app/dependencies.py` module provides a single `get_db()` dependency:

```python
@app.get("/loans")
def list_loans(db = Depends(get_db)):
    # db is a SQLAlchemy Session from the pool
    return db.query(Loan).all()
```

The session factory is injected by the lifespan context manager in `main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    set_session_factory(SessionLocal)  # Startup
    yield
    engine.dispose()  # Shutdown
```

This pattern:
- Decouples database configuration from dependencies
- Allows easy testing (just call `set_session_factory(test_factory)`)
- Enables pool lifecycle management

## Monitoring

### Check Active Connections

```sql
-- PostgreSQL: See active connections
SELECT usename, count(*) FROM pg_stat_activity GROUP BY usename;

-- Check pool capacity
SELECT datname, count(*) as connections FROM pg_stat_activity GROUP BY datname;
```

### Connection Pool Stats

SQLAlchemy provides pool statistics (enabled when `echo=True` in `app/db.py`):

```python
# In a debugger or Jupyter:
print(engine.pool.checkedout())  # Checked-out connections
print(engine.pool.size())        # Pool size
print(engine.pool.overflow())    # Current overflow
```

## Troubleshooting

### "RuntimeError: Database session factory not initialized"

This happens when dependencies are called before the lifespan startup runs.

**Solution**: Ensure the lifespan context manager is attached to the FastAPI app:

```python
app = FastAPI(lifespan=lifespan)
```

In tests, call `set_session_factory(SessionLocal)` explicitly in the fixture (see `tests/conftest.py`).

### "NUMERIC value out of range"

`NUMERIC(20, 2)` supports amounts up to ~999 trillion NGN. If exceeded:
- Increase precision: `NUMERIC(22, 2)` (up to 99 trillion)
- Or increase scale if sub-kobo precision needed: `NUMERIC(20, 4)` (4 decimal places)

Create a migration to alter the columns.

### "Connection pool exhausted"

Too many concurrent requests. Tune:
- Increase `pool_size` in `app/db.py`
- Reduce request duration (optimize queries, use async where possible)
- Add load balancing

### "Stale connection" or "Connection lost"

PostgreSQL may close idle connections after a timeout. SQLAlchemy handles this:
- `pool_pre_ping=True` tests connections before use
- `pool_recycle=3600` recycles after 1 hour

If still occurring:
- Check PostgreSQL `idle_in_transaction_session_timeout`
- Reduce `pool_recycle` to 300–900 seconds

## Admin lookup retries

This demo persists provider-lookup candidates and exposes an authenticated
`POST /admin/reconciliation/provider-lookups/{retry_id}/retry` action. The
action performs one synchronous attempt and writes its audit result. It is an
operator recovery tool, not a background worker.

In production, a worker should claim due pending rows with `FOR UPDATE SKIP
LOCKED`, apply bounded exponential backoff, persist attempt/error state, and
publish alerting after the retry budget is exhausted. The admin endpoint should
then enqueue or lease a retry rather than run provider network I/O in the HTTP
request.

## Next Steps

- **Outbox worker**: publish persisted `outbox_events` asynchronously
- **Metrics**: Add `last_heartbeat` to pool monitoring
