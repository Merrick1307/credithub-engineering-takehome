"""Add operational reconciliation facts and admin lookup retry state.

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("correlation_id", sa.String(), nullable=True))
    op.create_table("webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("provider", sa.String(), nullable=False),
        sa.Column("delivery_status", sa.String(), nullable=False), sa.Column("payload_digest", sa.String(), nullable=False),
        sa.Column("payment_event_id", sa.Uuid(), sa.ForeignKey("payment_events.id")),
        sa.Column("correlation_id", sa.String(), nullable=False), sa.Column("detail", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table("reconciliation_issues",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"), sa.Column("reason", sa.String(), nullable=False),
        sa.Column("payment_event_id", sa.Uuid(), sa.ForeignKey("payment_events.id")), sa.Column("loan_id", sa.Uuid(), sa.ForeignKey("loans.id")),
        sa.Column("overpayment_id", sa.Uuid(), sa.ForeignKey("overpayments.id")), sa.Column("assigned_to", sa.String()), sa.Column("resolution_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_table("provider_lookup_retries",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("provider", sa.String(), nullable=False), sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()), sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("payment_event_id", sa.Uuid(), sa.ForeignKey("payment_events.id")), sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("reconciliation_issues.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table("outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("event_type", sa.String(), nullable=False), sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reconciliation_issues_status_created", "reconciliation_issues", ["status", "created_at"])
    op.create_index("ix_provider_lookup_retries_status", "provider_lookup_retries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_provider_lookup_retries_status", table_name="provider_lookup_retries")
    op.drop_index("ix_reconciliation_issues_status_created", table_name="reconciliation_issues")
    op.drop_table("outbox_events")
    op.drop_table("provider_lookup_retries")
    op.drop_table("reconciliation_issues")
    op.drop_table("webhook_deliveries")
    op.drop_column("audit_log", "correlation_id")
