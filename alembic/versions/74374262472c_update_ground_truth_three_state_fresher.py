"""update_ground_truth_three_state_fresher

Revision ID: 74374262472c
Revises: fb052bc11f19
Create Date: 2026-11-18 08:30:02.696432

"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74374262472c'
down_revision: Union[str, Sequence[str], None] = 'fb052bc11f19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Replace binary human_is_fresher with 3-state human_fresher_status."""
    # Step 1: Add new column
    with op.batch_alter_table('ground_truth_evals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('human_fresher_status', sa.String(length=30), nullable=True))

    # Step 2: Data migration - Recover genuine 3-class ground-truth labels from benchmark JSON
    bind = op.get_bind()
    benchmark_path = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "ground_truth_benchmark.json"
    if benchmark_path.exists():
        with open(benchmark_path, "r", encoding="utf-8") as f:
            benchmark_data = json.load(f)
        for entry in benchmark_data:
            bind.execute(
                sa.text(
                    "UPDATE ground_truth_evals SET human_fresher_status = :status WHERE job_id = :job_id"
                ),
                {"status": entry["human_fresher_status"], "job_id": entry["job_id"]}
            )
    else:
        # Fallback if benchmark JSON is not on disk
        bind.execute(
            sa.text(
                "UPDATE ground_truth_evals SET human_fresher_status = CASE "
                "WHEN human_is_fresher = 1 THEN 'fresher_friendly' "
                "ELSE 'not_fresher_friendly' END"
            )
        )

    # Set default for any remaining nulls
    bind.execute(
        sa.text("UPDATE ground_truth_evals SET human_fresher_status = 'uncertain' WHERE human_fresher_status IS NULL")
    )

    # Step 3: Drop old column and make human_fresher_status non-nullable
    with op.batch_alter_table('ground_truth_evals', schema=None) as batch_op:
        batch_op.alter_column('human_fresher_status', nullable=False, server_default='uncertain')
        batch_op.drop_column('human_is_fresher')


def downgrade() -> None:
    """Downgrade schema: Restore binary human_is_fresher safely if no uncertain records exist."""
    bind = op.get_bind()

    # Step 1: Pre-check for uncertain records before any DDL or data alteration
    uncertain_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM ground_truth_evals WHERE human_fresher_status = 'uncertain'")
    ).scalar()

    if uncertain_count and uncertain_count > 0:
        raise RuntimeError(
            f"Unsafe downgrade prevented: Found {uncertain_count} ground_truth_evals records with "
            "human_fresher_status = 'uncertain'. The legacy Boolean schema (human_is_fresher) "
            "cannot represent three states and would cause irreversible data loss. "
            "Resolve or archive uncertain records before downgrading."
        )

    # Step 2: Safe downgrade when only decisive states ('fresher_friendly' or 'not_fresher_friendly') exist
    with op.batch_alter_table('ground_truth_evals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('human_is_fresher', sa.Boolean(), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE ground_truth_evals SET human_is_fresher = CASE "
            "WHEN human_fresher_status = 'fresher_friendly' THEN 1 "
            "WHEN human_fresher_status = 'not_fresher_friendly' THEN 0 "
            "ELSE 0 END"
        )
    )

    with op.batch_alter_table('ground_truth_evals', schema=None) as batch_op:
        batch_op.alter_column('human_is_fresher', nullable=False)
        batch_op.drop_column('human_fresher_status')
