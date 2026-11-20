"""add_rejected_records_table

Revision ID: ad807d9ec04a
Revises: 74374262472c
Create Date: 2026-11-19 05:59:15.793358

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad807d9ec04a'
down_revision: Union[str, Sequence[str], None] = '74374262472c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create rejected_records table for fine-grained ingestion rejection auditability."""
    op.create_table(
        'rejected_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('company', sa.String(length=255), nullable=True),
        sa.Column('raw_location', sa.String(length=255), nullable=True),
        sa.Column('apply_url', sa.Text(), nullable=True),
        sa.Column('rejection_category', sa.String(length=50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('rule_version', sa.String(length=20), nullable=False, server_default='v1.0'),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('pipeline_run_id', sa.String(length=64), nullable=True),
        sa.Column('rejected_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rejected_records_id'), 'rejected_records', ['id'], unique=False)
    op.create_index(op.f('ix_rejected_records_source'), 'rejected_records', ['source'], unique=False)
    op.create_index(op.f('ix_rejected_records_rejection_category'), 'rejected_records', ['rejection_category'], unique=False)
    op.create_index(op.f('ix_rejected_records_pipeline_run_id'), 'rejected_records', ['pipeline_run_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema: Drop rejected_records table."""
    op.drop_index(op.f('ix_rejected_records_pipeline_run_id'), table_name='rejected_records')
    op.drop_index(op.f('ix_rejected_records_rejection_category'), table_name='rejected_records')
    op.drop_index(op.f('ix_rejected_records_source'), table_name='rejected_records')
    op.drop_index(op.f('ix_rejected_records_id'), table_name='rejected_records')
    op.drop_table('rejected_records')
