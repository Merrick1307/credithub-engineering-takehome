"""Allow unmapped event journaling and enforce canonical event identity.

Revision ID: 006
Revises: 005
"""

from alembic import op


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unknown/ambiguous loan callbacks are still financial-event facts, so the
    # event journal must not require a successfully resolved loan foreign key.
    # Batch mode keeps SQLite-compatible local migrations while emitting normal
    # ALTER operations on PostgreSQL.
    with op.batch_alter_table("payment_events") as batch:
        batch.alter_column("loan_id", nullable=True)
        batch.create_unique_constraint(
            "uq_payment_events_canonical_identity",
            ["provider", "merchant_scope", "event_kind", "external_ref"],
        )


def downgrade() -> None:
    with op.batch_alter_table("payment_events") as batch:
        batch.drop_constraint("uq_payment_events_canonical_identity", type_="unique")
        batch.alter_column("loan_id", nullable=False)
