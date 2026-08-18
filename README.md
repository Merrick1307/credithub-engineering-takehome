# CreditHub — Engineering Take-Home: Payment Webhook

Welcome, and thanks for taking the time. This is a small, self-contained slice
of a lending platform — a **FastAPI + SQLAlchemy** backend and a **React + Vite**
frontend.

In the real world, loan repayments aren't typed in by hand — they **arrive from
rails** (payment gateways, NIBSS GSI, core-banking postings) as webhook events,
and the platform **reconciles** each one against a loan as it lands. Your task is
that webhook: **a payment arrives, and you reconcile it — record it, match it to
its loan, apply it, and close the loan when it's fully repaid — on receipt.**

**Timebox:** ~1–2 days. Ship what you'd be comfortable putting in front of a
bank, and be explicit about anything you'd do differently with more time.

**Use AI freely.** We build AI-first — Claude, Copilot, Cursor, whatever you use.
We're not testing whether you can code without help; we're testing your judgment
about the code that comes out. (See `NOTES.md`.)

---

## Run it locally

Needs **Python 3.11+** and **Node 20.19+**.

```bash
./run-local.sh          # seeds the DB, API on :8137, frontend on :5137 → open http://localhost:5137
```
Or two terminals — see the commands at the bottom. Tests: `pytest`.

*(Non-standard ports on purpose — 8000/5173 often clash with other projects. The
frontend proxies to :8137, so keep the API on that port.)*

## The flow

1. A payment lands → the gateway POSTs it to **`/webhooks/payments`**. The
   frontend's **"Simulate incoming payment"** button fires a synthetic one.
2. **You reconcile it on receipt:** record it, match it to its loan, apply the
   money (or reject it), and close the loan when fully repaid.
3. The feed and the loan balances update live in the UI — no extra step.

## What's here

**Backend** (`app/`)
- `models.py` — `Loan`, `PaymentEvent`, `Repayment`, `AuditLog`.
- `loans.py` — read endpoints (provided).
- `payments.py` — **provided:** `GET /payment-events` (the feed). **Your task:**
  the `POST /webhooks/payments` stub.
- `audit.py` — audit helper (writes into the caller's transaction).
- `auth.py` — `require_webhook_token` (the `X-Webhook-Token` header).
- `tests/` — `test_loans.py` + the feed test pass; the webhook spec in
  `test_payments.py` **fails** against the stub.

**Frontend** (`frontend/`)
- React + Vite. The base screen — feed + live balances — is **provided**
  (`Simulate` sends a payment; `Resend ↻` re-fires one, a rail redelivery). The
  core task is the backend; building an **admin reconciliation & issues panel** is
  a frontend extension (see *Your task*).

---

## Your task — `POST /webhooks/payments`

A payment just arrived from a rail. Body: `{external_ref, loan_id, amount, channel?}`.
Reconcile it **on receipt**. Contract:

- **`401`** without a valid `X-Webhook-Token` (see `auth.py`).
- **Record** every incoming payment as a `PaymentEvent`, then either:
  - **Apply** it: record a `Repayment`, reduce the loan's outstanding, **close the
    loan** (`paid_off`) when fully repaid, mark the event **`applied`**, and write
    an **audit** record — all in **one transaction**. Return `200 {event, loan}`.
  - **Reject** it (event **`rejected`** with a `reason`, still `200`) when it can't
    be applied: the loan is unknown or not `active`, the amount **overpays**, or the
    payment is a **duplicate** — a rail redelivers, so the same `external_ref`
    applied twice must only count once.
- Decide and document how you treat **overpayment**.

### Extensions (expected in a strong submission)
- **Admin reconciliation & issues panel (frontend).** The provided feed shows raw
  events; build an admin-facing view that gives an operator the *operational
  picture*: what reconciled successfully, and — front and centre — the **issues
  that need attention** (rejected payments and *why*: duplicates, closed loans,
  overpayments), plus summary health (applied vs rejected, total reconciled,
  failure rate). Think about how you'd surface exceptions so an admin can act.
  Build on `GET /payment-events`; you may add a `GET /audit-log` endpoint for a
  richer activity trail. We're looking at your product judgment as much as the code.
- **Concurrency (backend).** Make reconciliation correct under two webhooks racing
  on the same `external_ref` / loan.

### Optional
A real provider **signature** check instead of the shared token.

---

## What to hand back

1. Your code (a branch/PR-style diff is ideal).
2. **`NOTES.md`** — short: key decisions + edge cases; **anything you'd flag
   before this ships to a real lender**; and **how you used AI** (where it helped,
   where you overrode it).

We'll follow up with a ~30-minute call where you walk us through your own code.

---

<details><summary>Two-terminal run</summary>

```bash
# terminal 1 — backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.scripts.seed
uvicorn app.main:app --reload --port 8137     # http://localhost:8137/docs

# terminal 2 — frontend
cd frontend && npm install && npm run dev      # http://localhost:5137
```
</details>
