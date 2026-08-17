# Notes

This repository currently contains the design work for the reconciliation layer.
The ADR and implementation plan have been completed; the application code has
not yet been changed to implement them.

## The ADR

### My part

I supplied the business context and the decisions the architecture must support:

- provider-routed, signature-verified webhooks for payment gateways, NIBSS GSI,
  and lender/core-banking systems;
- provider lookup as an additional verification step where the provider supports
  it;
- provider-specific JSON or XML parsing followed by one strict canonical event;
- `decimal.Decimal` in Python and exact decimal types in PostgreSQL for all money;
- durable idempotency, database uniqueness, transactions, and same-loan race
  protection;
- an append-only repayment ledger, overpayment handling, closed-loan behavior,
  encrypted provider credentials, and an issues-first operations dashboard;
- synchronous reconciliation, while keeping `ReconcilePaymentUseCase`
  independent of FastAPI so another driver can invoke it later; and
- provider-originated credits, reversals, and refunds as webhook deliveries.

I also defined the final event and ledger semantics. Provider labels are retained
as `provider_event_type` but mapped by adapters to canonical
`transaction.credit`, `transaction.reversal`, or `transaction.refund`. A
reversal must reference a pre-existing successful credit with a committed
repayment and/or overpayment ledger component. Overpayments are recorded both in
the append-only repayment ledger and in an operational `overpayments` projection.

### Assistance gotten from AI

AI helped turn the requirements into a structured ADR, identify architecture
boundaries, draft the Mermaid component/data diagrams, and formalize transaction,
idempotency, locking, audit, security, and observability invariants. It also
helped enumerate alternatives and explain why Redis cannot be the source of
financial correctness.

### How I steered it

I rejected a full double-entry ledger as unnecessary for this bounded context
and kept a smaller append-only repayment ledger. I clarified that Redis caches
only completed idempotency results, reconciliation remains synchronous, and
mutable provider status is not part of economic identity. I also corrected the
initial AI proposal that refunds should bypass the repayment ledger: overpayment
creation, refund, and reversal are now ledger facts so both loan and overpayment
balances can be replayed.

### Key decisions and lender-production flags

- PostgreSQL is authoritative; Redis loss must affect latency only.
- Every callback attempt is a `webhook_deliveries` fact, while only authenticated
  and final-success financial actions can create ledger rows.
- Ledger/event/audit history is append-only. Reversals and corrections append
  compensating rows instead of editing history.
- The `overpayments` table is a projection with `active` and `refunded` statuses;
  partial refunds remain `active` until the replayed balance reaches zero.
- Before production, each provider's signature scheme, event mapping, reference
  uniqueness, lookup behavior, acknowledgement contract, retry policy, and
  reversal/refund correlation rules must be verified against its real contract.
- Retention/redaction, key rotation, permissions, reconciliation checks, backup
  recovery, load tests, and regulatory review are required before lender use.

## The implementation plan

### My part

I set the expected delivery order and scope: freeze contracts first, establish
exact money and PostgreSQL persistence, implement ports/adapters and secure
JSON/XML normalization, add atomic reconciliation, publish through an outbox,
then build the admin panel and operational controls. I required the plan to cover
race conditions, lookup retry storage and manual retriggering, reversal/refund
webhooks, and tests for every money-changing path.

### Assistance gotten from AI

AI translated the ADR into milestones, package boundaries, request sequences,
decision flowcharts, pseudocode, schema tasks, test matrices, rollout steps, and
a definition of done. It also proposed concrete PostgreSQL concurrency tests and
dashboard/observability acceptance criteria.

### How I steered it

I kept reconciliation in the HTTP request rather than moving it to a worker;
only outbox publication is asynchronous. I narrowed overpayment status to
`active | refunded`, required overpayments to have matching repayment-ledger
components, and required refund/reversal callbacks to append compensating ledger
components. I also required raw provider event names to be preserved while the
domain receives one canonical namespaced event kind.

### Key decisions and edge cases

- A credit may create a `repayment` component, an `overpayment` component, or
  both; their sum must equal the successful credit amount.
- A refund reduces only the overpayment ledger balance and projection. It never
  changes the loan balance.
- A full reversal compensates every eligible component of the original
  successful credit. Unsupported partial, missing-original, already-reversed,
  ambiguous, or post-refund reversals are quarantined.
- Same-reference duplicates, changed-fingerprint conflicts, concurrent payments,
  concurrent refunds, and refund-versus-reversal races require PostgreSQL tests
  with real parallel transactions.
- The one-to-two-day slice should demonstrate one complete provider path and the
  core correctness guarantees. Remaining provider integrations and production
  hardening should be explicit follow-up work rather than superficial stubs.
