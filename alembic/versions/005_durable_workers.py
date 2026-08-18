"""Make outbox and lookup retries durable, leaseable work queues.

Revision ID: 005
Revises: 004
"""

from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Outbox rows may be generic notifications or refund commands. The single
    # publisher leases both and routes each event type to its configured consumer.
    op.add_column("outbox_events", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.add_column("outbox_events", sa.Column("status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("outbox_events", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox_events", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox_events", sa.Column("leased_by", sa.String(), nullable=True))
    op.add_column("outbox_events", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("outbox_events", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE outbox_events SET available_at = created_at, updated_at = created_at WHERE available_at IS NULL")
    # SQLite needs table recreation for ALTER CONSTRAINT; PostgreSQL performs
    # the same operations in place.
    with op.batch_alter_table("outbox_events") as batch:
        batch.alter_column("available_at", nullable=False)
        batch.alter_column("updated_at", nullable=False)
        batch.create_unique_constraint("uq_outbox_events_idempotency_key", ["idempotency_key"])
    op.create_index("ix_outbox_events_claim", "outbox_events", ["event_type", "status", "available_at"])

    op.add_column("provider_lookup_retries", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("provider_lookup_retries", sa.Column("leased_by", sa.String(), nullable=True))
    op.create_index("ix_provider_lookup_retries_claim", "provider_lookup_retries", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_provider_lookup_retries_claim", table_name="provider_lookup_retries")
    op.drop_column("provider_lookup_retries", "leased_by")
    op.drop_column("provider_lookup_retries", "lease_expires_at")
    op.drop_index("ix_outbox_events_claim", table_name="outbox_events")
    op.drop_constraint("uq_outbox_events_idempotency_key", "outbox_events", type_="unique")
    for column in ("updated_at", "last_error", "leased_by", "lease_expires_at", "available_at", "status", "idempotency_key"):
        op.drop_column("outbox_events", column)
