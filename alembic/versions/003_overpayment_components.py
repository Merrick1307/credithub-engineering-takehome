"""Add overpayment projections and component-aware repayment ledger rows.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "overpayments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("loan_id", sa.Uuid(), sa.ForeignKey("loans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_event_id", sa.Uuid(), sa.ForeignKey("payment_events.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("amount", sa.NUMERIC(20, 2), nullable=False),
        sa.Column("refunded_amount", sa.NUMERIC(20, 2), nullable=False, server_default="0"),
        sa.Column("reversed_amount", sa.NUMERIC(20, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("repayments", sa.Column("entry_type", sa.String(), nullable=False, server_default="repayment"))
    op.add_column("repayments", sa.Column("loan_balance_delta", sa.NUMERIC(20, 2), nullable=False, server_default="0"))
    op.add_column("repayments", sa.Column("overpayment_balance_delta", sa.NUMERIC(20, 2), nullable=False, server_default="0"))
    op.add_column("repayments", sa.Column("overpayment_id", sa.Uuid(), sa.ForeignKey("overpayments.id"), nullable=True))
    op.add_column("repayments", sa.Column("adjusts_repayment_id", sa.Uuid(), sa.ForeignKey("repayments.id"), nullable=True))
    op.create_index("ix_repayments_overpayment_id", "repayments", ["overpayment_id"])


def downgrade() -> None:
    op.drop_index("ix_repayments_overpayment_id", table_name="repayments")
    for column in ("adjusts_repayment_id", "overpayment_id", "overpayment_balance_delta", "loan_balance_delta", "entry_type"):
        op.drop_column("repayments", column)
    op.drop_table("overpayments")
