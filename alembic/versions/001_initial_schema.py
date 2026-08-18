"""Initial PostgreSQL schema with NUMERIC types.

Revision ID: 001
Revises:
Create Date: 2026-08-17 10:58:59.883+01:00

This migration establishes the foundation for the payment reconciliation system.
Uses PostgreSQL NUMERIC(20,2) for all money fields to maintain decimal precision
(never float) and includes proper indexes and constraints.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    loan_status_enum = postgresql.ENUM(
        'active', 'paid_off', 'cancelled', 'written_off',
        name='loanstatus',
        # The type is created explicitly below. Prevent create_table() from
        # issuing a second CREATE TYPE for this same enum.
        create_type=False
    )
    payment_status_enum = postgresql.ENUM(
        'pending', 'applied', 'rejected',
        name='paymentstatus',
        create_type=False
    )
    loan_status_enum.create(op.get_bind(), checkfirst=True)
    payment_status_enum.create(op.get_bind(), checkfirst=True)

    # Create loans table
    op.create_table(
        'loans',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('borrower_name', sa.String(), nullable=False),
        # Use NUMERIC(20,2) for precise decimal storage (20 digits, 2 decimal places)
        # Supports amounts up to 999,999,999,999,999,999.99
        sa.Column('principal', sa.NUMERIC(precision=20, scale=2), nullable=False),
        sa.Column('total_repayable', sa.NUMERIC(precision=20, scale=2), nullable=False),
        sa.Column('total_paid', sa.NUMERIC(precision=20, scale=2), nullable=False, server_default='0'),
        sa.Column('status', loan_status_enum, nullable=False, server_default='active'),
        sa.Column('disbursed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_loans_status', 'loans', ['status'])
    op.create_index('ix_loans_disbursed_at', 'loans', ['disbursed_at'])

    # Create payment_events table
    op.create_table(
        'payment_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('external_ref', sa.String(), nullable=False),
        sa.Column('loan_id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.NUMERIC(precision=20, scale=2), nullable=False),
        sa.Column('channel', sa.String(), nullable=False, server_default='paystack'),
        sa.Column('status', payment_status_enum, nullable=False, server_default='pending'),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['loan_id'], ['loans.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_payment_events_external_ref', 'payment_events', ['external_ref'])
    op.create_index('ix_payment_events_loan_id', 'payment_events', ['loan_id'])
    op.create_index('ix_payment_events_status', 'payment_events', ['status'])
    op.create_index('ix_payment_events_received_at', 'payment_events', ['received_at'])

    # Create repayments ledger table (append-only)
    op.create_table(
        'repayments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('loan_id', sa.Uuid(), nullable=False),
        sa.Column('payment_event_id', sa.Uuid(), nullable=True),
        sa.Column('amount', sa.NUMERIC(precision=20, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['loan_id'], ['loans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['payment_event_id'], ['payment_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_repayments_loan_id', 'repayments', ['loan_id'])
    op.create_index('ix_repayments_payment_event_id', 'repayments', ['payment_event_id'])
    op.create_index('ix_repayments_created_at', 'repayments', ['created_at'])

    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('detail', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_entity_created_at', 'audit_log', ['entity', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_log_entity_created_at', table_name='audit_log')
    op.drop_table('audit_log')

    op.drop_index('ix_repayments_created_at', table_name='repayments')
    op.drop_index('ix_repayments_payment_event_id', table_name='repayments')
    op.drop_index('ix_repayments_loan_id', table_name='repayments')
    op.drop_table('repayments')

    op.drop_index('ix_payment_events_received_at', table_name='payment_events')
    op.drop_index('ix_payment_events_status', table_name='payment_events')
    op.drop_index('ix_payment_events_loan_id', table_name='payment_events')
    op.drop_index('ix_payment_events_external_ref', table_name='payment_events')
    op.drop_table('payment_events')

    op.drop_index('ix_loans_disbursed_at', table_name='loans')
    op.drop_index('ix_loans_status', table_name='loans')
    op.drop_table('loans')

    # Drop enum types
    sa.Enum(name='paymentstatus').drop(op.get_bind())
    sa.Enum(name='loanstatus').drop(op.get_bind())
