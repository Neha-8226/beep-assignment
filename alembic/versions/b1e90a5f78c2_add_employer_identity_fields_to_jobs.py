"""add_employer_identity_fields_to_jobs

Revision ID: b1e90a5f78c2
Revises: ad807d9ec04a
Create Date: 2026-11-19 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1e90a5f78c2'
down_revision: Union[str, Sequence[str], None] = 'ad807d9ec04a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add posting_organization and hiring_organization to jobs table."""
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('posting_organization', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('hiring_organization', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema: Remove posting_organization and hiring_organization from jobs table."""
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('hiring_organization')
        batch_op.drop_column('posting_organization')
