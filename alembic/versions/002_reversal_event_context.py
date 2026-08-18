"""Add canonical event context required for reversal reconciliation.

Revision ID: 002
Revises: 001
"""

from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_events", sa.Column("provider", sa.String(), nullable=False, server_default="paystack"))
    op.add_column("payment_events", sa.Column("merchant_scope", sa.String(), nullable=False, server_default=""))
    op.add_column("payment_events", sa.Column("event_kind", sa.String(), nullable=False, server_default="transaction.credit"))
    op.add_column("payment_events", sa.Column("original_payment_reference", sa.String(), nullable=True))
    op.add_column("payment_events", sa.Column("provider_status", sa.String(), nullable=False, server_default="succeeded"))
    op.add_column("payment_events", sa.Column("fingerprint", sa.String(), nullable=True))
    op.add_column("payment_events", sa.Column("applied_amount", sa.NUMERIC(20, 2), nullable=False, server_default="0"))
    op.add_column("payment_events", sa.Column("overpaid_amount", sa.NUMERIC(20, 2), nullable=False, server_default="0"))
    op.create_index(
        "ix_payment_events_canonical_identity",
        "payment_events",
        ["provider", "merchant_scope", "event_kind", "external_ref"],
    )
    op.create_index(
        "ix_payment_events_reversal_original",
        "payment_events",
        ["provider", "merchant_scope", "original_payment_reference"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_events_reversal_original", table_name="payment_events")
    op.drop_index("ix_payment_events_canonical_identity", table_name="payment_events")
    for column in (
        "overpaid_amount", "applied_amount", "fingerprint", "provider_status",
        "original_payment_reference", "event_kind", "merchant_scope", "provider",
    ):
        op.drop_column("payment_events", column)
