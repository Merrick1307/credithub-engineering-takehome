# Notes

## Approach

I kept the provided `POST /webhooks/payments` contract for the original tests and
synthetic frontend flow, then moved the reconciliation logic behind a provider-
agnostic application boundary so provider-native callbacks can use the same
financial path:

```text
provider callback
  -> authenticate
  -> decode provider payload
  -> normalize to CanonicalFinancialEvent
  -> ReconcilePaymentUseCase
  -> one database transaction
```

The repository demonstrates the legacy take-home route plus mock and
`core_banking` provider routes. Provider-specific authentication, payload shape,
amount representation, and event labels stop at the adapter boundary; the domain
works with canonical credit, reversal, and refund events.

## Key decisions and edge cases

### Reconciliation stays synchronous

The money-changing decision happens on webhook receipt. Loan updates, payment
event state, repayment-ledger rows, overpayment state, audit entries, issues, and
outbox records are committed transactionally. Background workers do not contain a
second implementation of the financial rules; when they need a financial effect,
they come back through the same idempotent reconciliation path.

### Exact money and append-only financial history

Financial calculations use `Decimal`/database `NUMERIC`, not binary floats.
Repayment history is append-only. Reversals and refunds append compensating ledger
components rather than editing historical rows.

### Overpayment policy

I chose partial application rather than rejecting the entire payment. If a loan
has NGN 56,000 outstanding and receives NGN 60,000, NGN 56,000 pays off the loan
and NGN 4,000 becomes an overpayment. The credit is returned as
`partially_applied`.

Overpayments have a mutable operational projection, but the creation/refund/
reversal movements are also represented in the append-only ledger. A refund
reduces only the overpayment balance; it does not reduce the amount already paid
toward the loan.

### Duplicate delivery and idempotency

Webhook delivery is treated as at-least-once. Canonical event identity is scoped
by provider, merchant scope, event kind, and provider reference, and the database
enforces that identity. A provider-native exact redelivery can replay the stored
result without applying money again; a conflicting payload for an existing
identity is treated as an integrity problem.

The legacy exercise endpoint preserves the supplied duplicate behaviour while
still guaranteeing that the balance changes only once. Callback attempts are
also recorded separately as webhook-delivery facts so transport redelivery is not
confused with a second economic event.

### Rejected events

Normalized financial events that cannot safely be applied are still journaled
where there is a stable economic event to record. Examples include unknown or
closed loans, invalid amounts, mapping failures, provider lookup failures, and
reversal-integrity failures. This makes them visible to reconciliation operations
rather than silently dropping them.

Malformed or unauthenticated requests are transport failures, not trusted
financial events. Provider statuses that are not final-success are treated as
non-actionable delivery state rather than being allowed to mutate a loan.

### Reversals and refunds

A negative credit is not interpreted as a reversal. Reversals/refunds are explicit
provider event types and must correlate to an original credit.

The implemented reversal slice supports safe full compensation of the original
credit components. Missing originals, unsupported partial reversals, already-
reversed payments, and incompatible post-refund reversals are quarantined rather
than guessed.

Refunds consume available overpayment value only and leave the loan balance
unchanged.

## Concurrency

Financial correctness is database-owned. The reconciliation path uses database
uniqueness and loan-row locking rather than relying on Redis or in-process locks.

The suite includes opt-in PostgreSQL race tests (enabled with
`TEST_POSTGRES_DATABASE_URL`) for:

- two simultaneous deliveries of the same event identity, proving one economic
  application; and
- two distinct payments racing against the same remaining loan balance, proving
  the loan cannot be overdrawn and excess value is handled by the overpayment
  policy.

There is separate PostgreSQL coverage for lease/`SKIP LOCKED` worker claiming.
SQLite remains the convenient default for the ordinary take-home test suite, but
I would run the financial race suite against the exact production PostgreSQL
version/isolation configuration before lender deployment.

## Durable follow-up work

Post-commit integration work uses a transactional outbox. The outbox publisher is
the only component that claims/publishes those rows and can route event types to
specific consumers.

For the demo, a core-banking overpayment can create an
`overpayment.refund.requested` command. The refund orchestrator simulates the
provider action and sends a signed `overpayment.refunded` callback back through
`/webhooks/payments/core_banking`. That callback is what consumes the overpayment
through the normal reconciliation use case. A production integration would call
the lender/provider's documented outbound refund API instead of this loopback.

Provider lookup retries are also persisted and leaseable; the retry driver invokes
the same reconciliation use case rather than editing financial records directly.

## Admin frontend

I evolved the provided React/Vite screen into an operations-oriented
reconciliation console while retaining the synthetic payment simulator.

It includes summary health, issues requiring attention, paginated/infinite-scroll
views for events, loans, overpayments and provider lookup retries, event and loan
detail overlays, manual redelivery, and event drill-downs showing ledger
components, webhook deliveries, overpayment state, issues, audit records, and a
reconciliation timeline derived from persisted event/ledger facts.

I kept the literal audit log separate from the derived timeline: the timeline is a
human-readable explanation of what happened, while the audit table remains the
actual persisted administrative record.

## What I would change before lender production

The included provider contracts and secrets are demonstration configuration. A
real lender rollout would require, at minimum:

- validating each provider's real signature/canonicalization, reference semantics,
  event mappings, acknowledgement rules, retries, lookup APIs, and reversal/refund
  correlation contract;
- moving secrets to managed secret storage with rotation and least-privilege
  service identities;
- replacing the development admin token with proper staff authentication, RBAC,
  auditable identity, and permission boundaries for financial actions;
- running the full money-changing concurrency suite on the production PostgreSQL
  configuration;
- operating outbox/retry dead-letter monitoring, reconciliation alerts, structured
  logs, metrics, tracing/correlation IDs, and recovery runbooks;
- backup/restore and disaster-recovery testing, load testing, retention/redaction,
  key management, security testing, and regulatory/compliance review.

## AI usage

I used AI extensively, as allowed by the exercise, for architecture exploration,
failure-mode enumeration, initial test matrices, implementation scaffolding,
provider adapter patterns, transactional-outbox reasoning, frontend iteration,
and code review.

I did not treat generated suggestions as authoritative. Examples where I changed
or rejected AI proposals include keeping reconciliation synchronous instead of
moving money-changing work to a worker, rejecting a full double-entry ledger as
unnecessary for this bounded slice, keeping PostgreSQL rather than Redis as the
source of financial correctness, making refunds ledger facts, separating outbox
claiming from refund orchestration, treating negative credits as invalid rather
than implicit reversals, and keeping the supplied webhook contract while adding a
provider-adapter boundary around it.

The main benefit of AI here was breadth and speed. The final scope, invariants,
and trade-offs are choices I can explain and defend in the walkthrough.
