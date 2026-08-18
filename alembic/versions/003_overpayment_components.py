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
    # Batch mode keeps the local SQLite deployment path compatible while
    # emitting ordinary ALTER statements on PostgreSQL.
    with op.batch_alter_table("repayments") as batch:
        batch.add_column(sa.Column("entry_type", sa.String(), nullable=False, server_default="repayment"))
        batch.add_column(sa.Column("loan_balance_delta", sa.NUMERIC(20, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("overpayment_balance_delta", sa.NUMERIC(20, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("overpayment_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("adjusts_repayment_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_repayments_overpayment_id", "overpayments", ["overpayment_id"], ["id"])
        batch.create_foreign_key("fk_repayments_adjusts_repayment_id", "repayments", ["adjusts_repayment_id"], ["id"])
        batch.create_index("ix_repayments_overpayment_id", ["overpayment_id"])


def downgrade() -> None:
    with op.batch_alter_table("repayments") as batch:
        batch.drop_index("ix_repayments_overpayment_id")
        batch.drop_constraint("fk_repayments_adjusts_repayment_id", type_="foreignkey")
        batch.drop_constraint("fk_repayments_overpayment_id", type_="foreignkey")
        for column in ("adjusts_repayment_id", "overpayment_id", "overpayment_balance_delta", "loan_balance_delta", "entry_type"):
            batch.drop_column(column)
    op.drop_table("overpayments")
