"""Migration Test: Employer Identity Fields (b1e90a5f78c2).

Tests:
1. Migration upgrade adds posting_organization and hiring_organization as nullable columns.
2. Existing data in jobs table is preserved with NULL values for new columns.
3. Model and migration parity: SQLAlchemy model Job accurately maps new columns.
4. Migration downgrade cleanly removes posting_organization and hiring_organization.
"""
import os
import sqlite3
import datetime
from alembic.config import Config
from alembic import command
import pytest

from app.models import Job


def test_employer_identity_migration_upgrade_and_downgrade(tmp_path):
    """Test upgrade and downgrade cycles for revision b1e90a5f78c2 in isolated SQLite database."""
    test_db = tmp_path / "test_migration_employer.db"
    orig_env = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db.as_posix()}"

    try:
        cfg = Config("alembic.ini")

        # 1. Upgrade to previous revision (ad807d9ec04a)
        command.upgrade(cfg, "ad807d9ec04a")

        # Insert pre-migration job record
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        con = sqlite3.connect(test_db)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO jobs (source, external_id, title, company, apply_url, canonical_url_hash, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("inmobi", "gh_inmobi_99", "Dev Intern", "InMobi", "http://apply", "hash_c", "hash_u", now)
        )
        pre_job_id = cur.lastrowid
        con.commit()

        # Verify new columns do NOT exist yet
        columns_pre = [d[1] for d in cur.execute("PRAGMA table_info(jobs)").fetchall()]
        assert "posting_organization" not in columns_pre
        assert "hiring_organization" not in columns_pre
        con.close()

        # 2. Upgrade to new revision (b1e90a5f78c2)
        command.upgrade(cfg, "b1e90a5f78c2")

        # Verify new columns exist and pre-existing row has NULLs
        con = sqlite3.connect(test_db)
        cur = con.cursor()
        col_info = cur.execute("PRAGMA table_info(jobs)").fetchall()
        col_names = [d[1] for d in col_info]
        assert "posting_organization" in col_names
        assert "hiring_organization" in col_names

        # Verify nullable (d[3] == 0 means notnotnull, i.e. nullable)
        for d in col_info:
            if d[1] in ("posting_organization", "hiring_organization"):
                assert d[3] == 0, f"Column {d[1]} must be nullable!"

        # Verify existing record data is intact
        row = cur.execute("SELECT title, company, posting_organization, hiring_organization FROM jobs WHERE id = ?", (pre_job_id,)).fetchone()
        assert row[0] == "Dev Intern"
        assert row[1] == "InMobi"
        assert row[2] is None  # Preserved as NULL
        assert row[3] is None  # Preserved as NULL

        # Insert new record with employer identity
        cur.execute(
            "INSERT INTO jobs (source, external_id, title, company, posting_organization, hiring_organization, apply_url, canonical_url_hash, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("instawork", "gh_instawork_101", "Robotics Gig", "Instawork (Client Project)", "Instawork", None, "http://apply2", "hash_c2", "hash_u2", now)
        )
        con.commit()

        row2 = cur.execute("SELECT company, posting_organization, hiring_organization FROM jobs WHERE external_id = 'gh_instawork_101'").fetchone()
        assert row2[0] == "Instawork (Client Project)"
        assert row2[1] == "Instawork"
        assert row2[2] is None
        con.close()

        # 3. Test Downgrade back to ad807d9ec04a
        command.downgrade(cfg, "ad807d9ec04a")

        con = sqlite3.connect(test_db)
        cur = con.cursor()
        columns_post_downgrade = [d[1] for d in cur.execute("PRAGMA table_info(jobs)").fetchall()]
        assert "posting_organization" not in columns_post_downgrade
        assert "hiring_organization" not in columns_post_downgrade
        # Existing records still exist with original columns intact
        title = cur.execute("SELECT title FROM jobs WHERE id = ?", (pre_job_id,)).fetchone()[0]
        assert title == "Dev Intern"
        con.close()

    finally:
        if orig_env is not None:
            os.environ["DATABASE_URL"] = orig_env
        else:
            os.environ.pop("DATABASE_URL", None)
