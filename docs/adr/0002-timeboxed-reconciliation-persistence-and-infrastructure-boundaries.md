# ADR-002: Timeboxed reconciliation persistence and infrastructure boundaries

- **Status:** Accepted
- **Date:** 2026-08-19
- **Amends:** [ADR-001](./0001-provider-aware-payment-reconciliation.md)
- **Scope:** Idempotency persistence, concurrency guarantees, Redis, provider
  credentials, rejected-event journaling, repayment history, and exercise
  compatibility

## Context

ADR-001 defines the production-shaped architecture for provider-aware loan
payment reconciliation.

Its core decisions remain valid:

- provider-specific authentication and payload handling stop at the adapter
  boundary;
- providers normalize into one canonical financial event model;
- money-changing reconciliation stays synchronous;
- the financial decision commits in one database transaction;
- financial history is append-only, with reversals and refunds represented by
  compensating entries;
- provider redelivery is treated as at-least-once;
- PostgreSQL is the authoritative persistence and concurrency boundary;
- post-commit integration work uses a transactional outbox; and
- provider lookup retries re-enter the same reconciliation use case instead of
  maintaining a second implementation of the financial rules.

During implementation of the one-to-two-day take-home slice, several
production-oriented components from ADR-001 were intentionally narrowed.

The final implementation does not introduce infrastructure simply to match the
shape of the initial design. It keeps the financial invariants and leaves
replaceable seams for components that are useful at production scale but not
required to demonstrate correctness in the exercise.

This ADR records those decisions.

## Decision

### 1. Canonical payment events are the durable idempotency boundary

The submitted implementation does not require a separate
`idempotency_records` workflow table.

A trusted economic action is identified by:

```text
provider + merchant_scope + event_kind + event_reference
````

The physical persistence model retains `external_ref` as the event-reference
column for compatibility with the original exercise, but provider-native flows
treat it as the canonical provider event reference.

PostgreSQL enforces uniqueness over the canonical identity.

Each canonical event also stores an immutable fingerprint. The timeboxed
implementation fingerprints the economic fields needed to distinguish an exact
redelivery from conflicting content:

```text
gross_amount | currency | original_payment_reference
```

Provider timestamps are excluded from this fingerprint. The legacy exercise
payload does not contain a provider transaction timestamp, and transport
redeliveries may legitimately arrive at different local times.

Mutable provider status and optional metadata are also excluded. A provider may,
for example, emit a pending callback and later a successful callback for the
same economic reference.

The resulting rules are:

```text
same identity + same fingerprint
    -> idempotent replay of committed result

same identity + different fingerprint
    -> identity conflict; do not apply a second financial event

new identity
    -> continue through normal reconciliation
```

The database uniqueness constraint remains the final defense against concurrent
requests that both observe no existing event before attempting to insert.

### 2. PostgreSQL owns financial correctness

Financial correctness is database-owned.

The reconciliation path combines:

* canonical event uniqueness;
* immutable fingerprint comparison;
* one database transaction for the financial decision; and
* row locking on the affected loan before changing its balance.

Two concurrent deliveries of the same economic event therefore cannot apply
money twice.

Two different payments racing against the same loan cannot both calculate from
the same stale outstanding balance. After acquiring the loan lock, each request
recalculates against committed state.

A request that arrives second may consequently become:

* a smaller payment against the remaining balance;
* a partial application with an overpayment remainder; or
* a receipt against an already closed loan,

depending on the state committed by the first request.

The correctness guarantee is:

```text
effectively-once financial application
on top of at-least-once webhook delivery
```

It is not a claim of network-level exactly-once delivery.

### 3. Redis is an optional replay fast path

Redis is not required by the submitted reconciliation path.

A production deployment may add Redis as a completed-idempotency-result cache:

```text
identity key -> fingerprint + stored response
```

The cache would be populated only after the PostgreSQL transaction commits.

An exact cache hit can avoid repeating the full database lookup path for a
common provider redelivery.

Redis does not:

* own durable event identity;
* lock loans;
* contain an authoritative loan balance;
* decide whether an event can be applied; or
* replace PostgreSQL uniqueness.

A cache miss, expiry, eviction, outage, concurrent miss, or fingerprint mismatch
must return processing to PostgreSQL.

Redis therefore changes duplicate-request latency and database load, not the
financial correctness model.

### 4. Normalized rejected events remain part of the financial journal

A callback that has passed authentication and normalization may represent a
stable financial event even when the system cannot safely apply it.

Where a stable economic event exists, the implementation journals the event with
a rejected reconciliation result.

Examples include:

* unknown loans;
* closed or otherwise non-active loans;
* invalid financial amounts detected at reconciliation;
* terminal provider lookup failures;
* provider verification mismatches where a stable canonical event can be
  retained;
* reversal-integrity failures; and
* refund-integrity failures.

The loan association is nullable so an event can be retained even when no loan
can safely be resolved.

This is distinct from transport failure.

Unauthenticated or structurally malformed requests are not trusted financial
events. They may be retained as safe delivery/security facts but do not become
canonical payment events.

A verified provider callback whose status is not final success is also kept
outside monetary reconciliation. It must not claim the canonical financial
event identity in a way that prevents a later successful callback for the same
provider reference.

### 5. Provider-native replay and legacy duplicate behaviour are intentionally different

Provider-native webhook routes follow normal at-least-once delivery semantics.

An exact redelivery of an already committed event returns the stored financial
result with:

```text
idempotent_replay = true
```

No second repayment, overpayment, reversal, refund, or loan mutation occurs.

The original exercise endpoint:

```text
POST /webhooks/payments
```

is retained as a compatibility route for the supplied contract and synthetic
frontend flow.

The supplied exercise expects a repeated `external_ref` to be reported as a
duplicate rejection. The compatibility route therefore adapts the HTTP-facing
result to:

```text
status = rejected
reason = duplicate_payment
applied_amount = 0
```

while preserving the already committed event and loan state.

This is a transport/compatibility decision only. The underlying financial event
is still applied exactly once.

### 6. Demo provider credentials remain intentionally simple

The timeboxed implementation uses deterministic development/test credentials in
the in-memory provider registry.

This allows signature and provider-authentication paths to be exercised locally
without introducing a credential-management subsystem into the take-home.

These values are demonstration configuration only.

They must not be used as lender production credentials.

Provider-native webhook secrets remain server-side. They must not be:

* logged;
* placed in audit metadata;
* returned by admin APIs;
* stored in a future Redis idempotency cache; or
* shipped in production browser JavaScript.

The supplied synthetic/legacy simulator retains the exercise development token
for compatibility with the original frontend contract. That control is
development-only.

If payment simulation exists in a production operations interface, it should use
staff authentication and a separately authorized admin simulation endpoint. It
should not expose a provider webhook credential to the browser.

### 7. Production credential storage remains a separate adapter concern

Lender deployment should replace the deterministic demo registry credentials
with managed secret storage.

One suitable design is:

```text
provider credential
    -> versioned encrypted ciphertext
    -> scoped credential service
    -> short-lived decrypted in-memory value
    -> provider authenticator/lookup adapter
```

Provider verification secrets and lookup API credentials can be encrypted with
AES-256-GCM using provider-specific additional authenticated data and an explicit
key version.

The key-encryption key should come from managed infrastructure rather than source
control.

A production deployment should prefer Vault, a cloud secret manager, or a
KMS/HSM-backed envelope-encryption scheme with:

* least-privilege workload identity;
* explicit secret versions;
* credential rotation;
* auditable access;
* revocation procedures; and
* no long-lived plaintext credential persistence.

This is production hardening. The submitted demo does not claim to implement
this credential-storage system.

### 8. The existing repayment table serves as the append-only financial journal

ADR-001 describes the desired financial history as a `repayment_ledger`.

The submitted slice retains the existing physical `repayments` table instead of
renaming it solely to match that terminology.

Its semantic role has expanded beyond a simple payment-history table.

Rows represent append-only financial components such as:

```text
repayment
overpayment
repayment_reversal
overpayment_reversal
overpayment_refund
```

A reversal or refund appends a compensating component.

Previously committed financial rows are not rewritten to make history look as
though the original event never occurred.

The loan and overpayment records remain mutable current-state projections; the
repayment components provide the history used to explain those projections.

A future schema migration may rename or further normalize this structure as
`repayment_ledger`. The table name itself is not a financial invariant.

### 9. Overpayment projections and ledger facts serve different purposes

An overpayment has both:

* an operational projection describing its current refundable state; and
* append-only financial components recording how that balance was created,
  refunded, or reversed.

For an active loan:

```text
gross payment = applied amount + overpayment remainder
```

For example:

```text
outstanding = NGN 56,000
payment     = NGN 60,000

repayment component  = NGN 56,000
overpayment component = NGN 4,000
```

The loan closes and the NGN 4,000 remains available for refund.

An overpayment refund consumes only the overpayment balance. It does not reduce
the amount already applied to the loan.

A provider reversal is a different economic action. It can compensate the
original repayment component and may reopen a previously paid-off loan.

Refund and reversal therefore remain explicit canonical event kinds and are not
interchangeable status updates.

### 10. Core-banking refund automation remains a demo integration boundary

The transactional outbox is the durable dispatcher for committed post-transaction
work.

For the timeboxed core-banking demonstration, creation of a refundable
overpayment may append:

```text
overpayment.refund.requested
```

to the outbox.

The outbox publisher delivers that command to the refund orchestrator.

The orchestrator simulates the outbound provider action and returns a signed
provider-native:

```text
overpayment.refunded
```

callback through:

```text
POST /webhooks/payments/core_banking
```

The callback re-enters the same reconciliation use case and becomes canonical:

```text
transaction.refund
```

Only that authenticated callback consumes the overpayment balance.

The loopback is a test double.

A lender deployment should replace it with the provider's documented outbound
refund API while retaining the same durable command, retry, idempotency, and
confirmation boundaries.

### 11. SQLite remains convenient; PostgreSQL proves concurrency

SQLite remains the default for the ordinary take-home test suite because it is
fast and requires no external service.

It is not considered evidence of PostgreSQL row-lock behaviour.

Financial concurrency guarantees are covered separately by opt-in PostgreSQL
tests using:

```text
TEST_POSTGRES_DATABASE_URL
```

Those tests exercise cases such as:

* two concurrent deliveries of the same event identity; and
* two distinct payments racing against one remaining loan balance.

The expected invariants are:

```text
one economic event -> at most one financial application

loan applied total -> never exceeds outstanding

excess receipt -> represented through the documented overpayment policy
```

Before lender deployment, the financial race suite should run against the exact
PostgreSQL version, driver, and transaction/isolation configuration used in
production.

### 12. Infrastructure optimization must not create a second financial rules engine

Background processes may:

* publish committed outbox events;
* retry provider verification;
* orchestrate provider refund requests; and
* invoke the canonical reconciliation use case after confirmation.

They must not implement their own version of:

* loan allocation;
* overpayment calculation;
* reversal calculation;
* refund balance calculation; or
* idempotency policy.

Every financial effect must converge on the same
`ReconcilePaymentUseCase` and database invariants.

This keeps synchronous webhook processing, lookup retries, provider callbacks,
and future queue-based drivers consistent.

## Consequences

### Positive

* Financial correctness does not depend on Redis availability.
* The take-home has fewer infrastructure dependencies without weakening the
  double-application or same-loan race guarantees.
* Canonical payment events provide both financial history and durable economic
  identity for this slice.
* A Redis replay cache can be introduced later without changing reconciliation
  rules.
* Production secret management can replace the demo registry without changing
  the domain use case.
* The existing repayment table can demonstrate append-only financial history
  without a migration performed only for naming.
* Rejected financial events remain visible to reconciliation operations.
* Provider-native webhook semantics can remain idempotent even though the legacy
  exercise endpoint preserves its original duplicate contract.
* PostgreSQL-specific concurrency guarantees can be tested independently of the
  fast SQLite suite.

### Costs and trade-offs

* The canonical event row carries both event history and the timeboxed durable
  idempotency role, so a larger system may later split workflow-specific state
  into a dedicated table.
* Redis is not currently available to absorb large volumes of obvious
  redeliveries.
* Demo credentials are intentionally unsuitable for production and require a
  managed credential adapter before lender deployment.
* The physical `repayments` name does not communicate its expanded ledger-like
  role as clearly as a dedicated `repayment_ledger` name would.
* SQLite cannot exercise the most important locking behaviour, so PostgreSQL
  remains necessary for authoritative race testing.
* Maintaining a legacy webhook compatibility route creates one HTTP behaviour
  that differs intentionally from provider-native replay semantics.

## Alternatives considered

### Implement Redis as part of the take-home correctness path

Not selected.

PostgreSQL already provides the durable uniqueness and locking required for
correctness. Adding Redis would introduce configuration, TTL policy, failure
handling, serialization, lifecycle, and additional tests without strengthening
the authoritative financial boundary.

Redis remains useful as a later duplicate fast path.

### Use Redis locks as the primary concurrency mechanism

Rejected.

Expiry, eviction, failover, process pauses, network partitions, or incorrect lock
renewal can make a cache-based lock unsafe as the only protection against a
double financial application.

Database uniqueness and row locking remain authoritative.

### Add a separate `idempotency_records` table for the exercise

Not selected for the submitted slice.

The canonical event already has a stable provider-scoped identity, immutable
fingerprint, committed reconciliation result, and database uniqueness.

A separate workflow table may become useful if the system later needs states
such as long-lived `processing`, request ownership, distributed execution, or
stored response lifecycle independent of the financial event.

Those needs are not required for the demonstrated synchronous transaction.

### Implement encrypted credential persistence in the take-home

Not selected.

The exercise needs to demonstrate provider authentication and safe application
boundaries, not a full secrets-management platform.

The provider registry is deliberately replaceable so production credential
storage can be introduced without changing the reconciliation domain.

### Rename `repayments` immediately to `repayment_ledger`

Not selected.

The important decision is append-only financial history and compensating entries.

Renaming an existing table adds migration work but does not improve the financial
invariant demonstrated by the exercise.

### Move reconciliation to a durable worker

Not selected.

The incoming authenticated event can be reconciled synchronously within one
database transaction.

Workers are retained for post-commit integration and retry work.

If a future queue becomes the primary driver, it should invoke the same
transport-independent reconciliation use case.

## Relationship to ADR-001

ADR-001 remains the primary architectural decision for provider-aware payment
reconciliation.

This ADR records implementation decisions made while reducing that
production-shaped design to the bounded take-home slice.

All ADR-001 decisions remain in force unless this document explicitly amends
them.

Where the documents differ, ADR-002 takes precedence for the submitted
implementation in these areas:

1. durable idempotency is represented by canonical payment-event identity,
   fingerprinting, and PostgreSQL uniqueness instead of a required separate
   `idempotency_records` workflow table;
2. Redis is optional production optimization, not a submitted runtime dependency;
3. provider credentials use deterministic demo configuration in the timeboxed
   implementation, with managed encrypted secrets deferred to production;
4. the existing `repayments` table serves as the physical append-only financial
   history instead of requiring an immediate `repayment_ledger` rename;
5. SQLite remains the ordinary test-suite default, while PostgreSQL is used for
   authoritative concurrency tests; and
6. the legacy `/webhooks/payments` route preserves the supplied duplicate-response
   contract without changing provider-native idempotency semantics.

The following ADR-001 decisions are unchanged:

* provider-specific authentication and normalization through adapters;
* a provider-agnostic canonical financial event model;
* `Decimal` money and exact database monetary values;
* synchronous reconciliation;
* database-authoritative concurrency;
* partial application of active-loan overpayments;
* explicit reversal and refund event types;
* compensating append-only financial history;
* transactional outbox delivery;
* durable provider lookup retries;
* the core-banking refund test-double boundary; and
* operations-oriented reconciliation visibility.

## Production follow-up

Before real lender deployment, I will do the following additive infrastructure work:

* real provider contracts and signature/canonicalization rules;
* managed provider credential storage and rotation;
* optional Redis completed-result caching if webhook volume justifies it;
* production PostgreSQL concurrency validation;
* staff authentication and RBAC for admin operations;
* replacement of the core-banking refund loopback with the real outbound API;
* dead-letter and retry monitoring;
* structured logs, metrics, tracing, and correlation IDs;
* reconciliation/invariant monitoring;
* secret and key-management runbooks;
* backup/restore and disaster-recovery testing;
* load and failure testing;
* retention/redaction policy; and
* applicable security, compliance, and regulatory review.
