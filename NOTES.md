# Notes

This repository currently contains the design work for the reconciliation layer.
The ADR and implementation plan have been completed; the application code has
now been implemented.

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
  hardening would be explicit follow-up work rather than superficial stubs.

## The implementation

### My part

I implemented the planned package boundaries and reconciliation slice. The
FastAPI transport is now separated into API controllers, the application use
case, domain DTOs/enums, repository and provider ports, SQLAlchemy adapters,
and provider-specific adapters. The implementation includes provider-routed
webhooks, authenticated mock/core-banking paths, canonical normalization,
payment/reversal/refund reconciliation, append-only repayment components,
overpayment projections, durable idempotency, audit records, reconciliation
issues, provider-lookup retry records, paginated staff admin endpoints, Alembic
migrations, and a Docker/PostgreSQL deployment configuration.

### Assistance gotten from AI

AI helped translate the ADR and implementation plan into concrete package
boundaries, repository interfaces, migrations, provider adapter templates,
reconciliation tests, and the Docker/Alembic setup. It also helped highlight
while i reason through the transactional outbox and lookup-retry records as 
durable seams for background processing.

### How I steered it

I kept the financial reconciliation decision synchronous in the webhook request
and restricted asynchronous processing to non-financial follow-up work. I used
the existing SQLAlchemy models as persistence projections while keeping domain
money and canonical-event concepts separate. I added mock and core-banking
adapters as demonstrable provider paths, without having to do real third-party
production integrations (real integration/implementation is just a matter of
swapping backends in provider registry), and kept the initial staff retry action
manual and audited.

### Key decisions and lender-production flags

- The webhook controller authenticates and normalizes provider input before it
  invokes `ReconcilePaymentUseCase`; persistence remains behind the unit-of-work
  and repository ports.
- The `outbox_events` table and `provider_lookup_retries` table are durable
  integration points, but neither has an automatic worker yet. The first worker
  should publish committed outbox rows; a later, separately controlled worker
  may claim and run due provider-lookup retries.
- Financial reconciliation must remain request-time and transactionally
  authoritative. A worker must never independently re-apply, reverse, or refund
  a payment without using the same idempotent use case and database locks.
- `requirements.txt` is intentionally retained for this small, timeboxed
  FastAPI service. Poetry is optional tooling, not a correctness improvement;
  adopting it should include a committed lock file and aligned Docker/local
  commands rather than keeping two competing dependency sources of truth.
- The root `app/` modules are transitional framework/persistence composition
  code: `main.py` remains the composition root; `db.py` and `models.py` belong
  under the SQLAlchemy persistence adapter; `audit.py` belongs with persistence;
  `auth.py` belongs with inbound authentication; `dependencies.py` belongs to
  the API layer; and `seed.py` belongs in an operational/scripts package.
- Before lender production, I'd implement and operate fully, the outbox publisher, 
  retry scheduling/leases, real provider contract verification, secret management,
  PostgreSQL concurrency coverage, monitoring, and recovery runbooks.

## Background processing amendment

### My part

The transactional outbox is the single durable dispatcher for both generic
post-commit notifications and core-banking refund commands. The publisher routes
each event type to its configured HTTP consumer; the refund orchestrator is a
webhook consumer and never polls or claims the outbox itself.

### Assistance gotten from AI

AI helped highlight that using the generic outbox as both notification transport
and refund-command queue would blur two operational responsibilities. It helped
define separate lease-safe worker responsibilities while preserving one shared
financial reconciliation path.

### How I steered it

I retained the outbox publisher as the only process that claims and retries
outbox rows. For the timeboxed demonstration, it routes
`overpayment.refund.requested` to a dedicated refund webhook, whose orchestrator
sends a signed core-banking callback to the local provider route. I kept its
resulting financial effect inside the normal authenticated webhook and use-case
flow.

### Key decisions and lender-production flags

- `outbox_publisher` publishes every durable event, routing refund commands to
  the refund orchestrator and generic notifications to their downstream consumer.
- `overpayment_refund_runner` is an internal HTTP consumer. It validates
  `overpayment.refund.requested` and ignores all other event types; publisher
  leases, retries, and the idempotent callback reference remain the boundary.
- The demo sends signed `overpayment.refunded` callbacks to
  `/webhooks/payments/core_banking`; the provider adapter maps this to canonical
  `transaction.refund`. This reduces only the overpayment balance and never the
  loan balance.
- The demo runner is limited to overpayments whose original credit came through
  `core_banking`, because refund correlation currently requires the same provider
  and merchant scope.
- `lookup_retry_runner` is a separate scheduled driver. It claims due lookup
  tasks and invokes `ReconcilePaymentUseCase`; no worker mutates financial
  records directly.
- Production must replace the local core-banking loopback with the provider's
  documented outbound refund API and operate the outbox, publisher retry, and
  dead-letter monitoring/runbooks.


## The frontend

### My part

I evolved the existing two-page React/Vite frontend (public servicing page and
admin console with secret-based data loading) into a comprehensive operational
dashboard. I stated an enhanced frontend requirements which provides paginated 
views for reconciliation events, loans, overpayments, and provider-lookup retries, 
with filtering by provider, status, kind, loan ID, and reference. It retains the 
synthetic payment simulator for testing webhook delivery manual redelivery of events, 
and in addition now includes detailed event drill-downs showing ledger components, 
overpayment state, webhook deliveries, reconciliation issues, and audit history.

### Assistance gotten from AI

AI helped enhance the existing React/Vite structure, implement pagination logic,
create the infinite scroll table components, and expand the dashboard layout.
It also helped with the event detail modal.

### How I steered it

I kept the frontend as a pure client-side application that calls the existing
FastAPI admin endpoints. I retained the admin token authentication pattern but
required it as a 'login credential' to the new multi-page/tabs app. Once logged in,
the admin then has access to all views and is able to perform all operations.
for backward compatibility, i let the synthetic payment simulator keep using 
the legacy `/webhooks/payments` endpoint.

### Key decisions and lender-production flags

- The frontend remains a client-side application; all financial mutations stay
  server-side through authenticated API endpoints.
- Synthetic payments and manual redelivery are staff-only actions protected by
  the admin token and recorded in the audit log.
- Event kind mappings (`transaction.credit`, `transaction.reversal`,
  `transaction.refund`) and provider name mappings are client-side display
  helpers; the canonical values remain authoritative in the backend.
- Before lender production, I'd add proper authentication (OAuth/JWT), role-based
  access control, input validation, rate limiting, CSRF protection, and
  comprehensive error handling.
