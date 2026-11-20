"""Migration Downgrade Safety Unit Tests.

Validates that revision 74374262472c:
1. Prevents unsafe downgrades and raises RuntimeError when 'uncertain' records exist in ground_truth_evals.
2. Leaves database schema and data completely untouched when downgrade is blocked.
3. Allows downgrade when only decisive records exist, accurately mapping them to boolean values.
"""
import os
import sqlite3
import datetime
from pathlib import Path
from alembic.config import Config
from alembic import command


def test_downgrade_safety_prevents_loss_of_uncertain_records(tmp_path):
    """Verify downgrade fails safely when uncertain records exist, leaving schema intact."""
    test_db = tmp_path / "migration_safety_test.db"
    orig_env = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db.as_posix()}"

    try:
        cfg = Config("alembic.ini")
        # Upgrade to head (includes revision 74374262472c)
        command.upgrade(cfg, "head")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        con = sqlite3.connect(test_db)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO jobs (source, external_id, title, apply_url, canonical_url_hash, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test_src", "job_001", "Backend Dev", "http://apply", "h1", "c1", now)
        )
        job_id = cur.lastrowid
        cur.execute(
            "INSERT INTO ground_truth_evals (job_id, human_role_category, human_fresher_status, evaluated_at) "
            "VALUES (?, ?, ?, ?)",
            (job_id, "Backend", "uncertain", now)
        )
        con.commit()
        con.close()

        # SCENARIO A: Downgrade should raise RuntimeError
        downgrade_blocked = False
        try:
            command.downgrade(cfg, "fb052bc11f19")
        except RuntimeError as e:
            downgrade_blocked = True
            assert "Unsafe downgrade prevented" in str(e)
            assert "cannot represent three states" in str(e)

        assert downgrade_blocked is True, "Expected downgrade to be blocked when uncertain records exist!"

        # Schema & data must remain unaltered
        con = sqlite3.connect(test_db)
        cur = con.cursor()
        columns = [d[1] for d in cur.execute("PRAGMA table_info(ground_truth_evals)").fetchall()]
        status_val = cur.execute("SELECT human_fresher_status FROM ground_truth_evals WHERE id = 1").fetchone()[0]
        con.close()

        assert "human_fresher_status" in columns
        assert "human_is_fresher" not in columns
        assert status_val == "uncertain"

    finally:
        if orig_env is not None:
            os.environ["DATABASE_URL"] = orig_env
        else:
            os.environ.pop("DATABASE_URL", None)


def test_downgrade_permits_when_no_uncertain_records(tmp_path):
    """Verify downgrade succeeds when only decisive (fresher_friendly / not_fresher_friendly) records exist."""
    test_db = tmp_path / "migration_clean_downgrade.db"
    orig_env = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db.as_posix()}"

    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        con = sqlite3.connect(test_db)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO jobs (source, external_id, title, apply_url, canonical_url_hash, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test_src", "job_002", "Senior Dev", "http://apply2", "h2", "c2", now)
        )
        job_id_1 = cur.lastrowid
        cur.execute(
            "INSERT INTO jobs (source, external_id, title, apply_url, canonical_url_hash, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test_src", "job_003", "Junior Dev", "http://apply3", "h3", "c3", now)
        )
        job_id_2 = cur.lastrowid

        # Insert only decisive records
        cur.execute(
            "INSERT INTO ground_truth_evals (job_id, human_role_category, human_fresher_status, evaluated_at) "
            "VALUES (?, ?, ?, ?)",
            (job_id_1, "Frontend", "not_fresher_friendly", now)
        )
        cur.execute(
            "INSERT INTO ground_truth_evals (job_id, human_role_category, human_fresher_status, evaluated_at) "
            "VALUES (?, ?, ?, ?)",
            (job_id_2, "Backend", "fresher_friendly", now)
        )
        con.commit()
        con.close()

        # SCENARIO B: Downgrade should succeed
        command.downgrade(cfg, "fb052bc11f19")

        # Verify schema reverted to human_is_fresher and values mapped accurately
        con = sqlite3.connect(test_db)
        cur = con.cursor()
        columns = [d[1] for d in cur.execute("PRAGMA table_info(ground_truth_evals)").fetchall()]
        val_not_fresher = cur.execute("SELECT human_is_fresher FROM ground_truth_evals WHERE job_id = ?", (job_id_1,)).fetchone()[0]
        val_fresher = cur.execute("SELECT human_is_fresher FROM ground_truth_evals WHERE job_id = ?", (job_id_2,)).fetchone()[0]
        con.close()

        assert "human_is_fresher" in columns
        assert "human_fresher_status" not in columns
        assert val_not_fresher == 0
        assert val_fresher == 1

    finally:
        if orig_env is not None:
            os.environ["DATABASE_URL"] = orig_env
        else:
            os.environ.pop("DATABASE_URL", None)
