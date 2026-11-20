"""Unit tests for Classification CLI Safety Controller.

Tests:
1. Rejection of unbounded runs (no --limit or --dry-run).
2. Enforcement of pilot cap (limit > 15 rejected without --override-pilot-limit).
3. Authorization of limit > 15 with --override-pilot-limit.
4. Dry-run mode produces 0 API calls and 0 database writes.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, LLMAuditLog
import scripts.run_classification as cli_script


@pytest.fixture
def mock_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed 20 dummy jobs
    for i in range(1, 21):
        job = Job(
            id=i,
            source="greenhouse",
            external_id=f"gh_{i}",
            title=f"Engineer {i}",
            company="Tech Corp",
            raw_location="Bengaluru",
            description=f"Job description for engineer {i} with Requirements: 0-1 years exp.",
            apply_url=f"https://example.com/apply/{i}",
            canonical_url_hash=f"hash_{i}",
            content_hash=f"content_{i}",
            role_category=None  # unclassified
        )
        session.add(job)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_cli_unbounded_run_rejected(capsys):
    """Verify CLI halts when neither --limit nor --dry-run is supplied."""
    with patch.object(sys, "argv", ["run_classification.py"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "An explicit job selection is required" in captured.out


def test_cli_pilot_limit_exceeded_rejected(capsys):
    """Verify limit > 15 without --override-pilot-limit halts execution."""
    with patch.object(sys, "argv", ["run_classification.py", "--limit", "25"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "exceeds pilot cap of 15 jobs" in captured.out


def test_cli_dry_run_zero_api_and_zero_db_writes(mock_db, capsys):
    """Verify dry-run mode previews jobs, makes 0 API calls and 0 database writes."""
    initial_unclassified = mock_db.query(Job).filter(Job.role_category.is_(None)).count()
    initial_audit_logs = mock_db.query(LLMAuditLog).count()

    with patch.object(sys, "argv", ["run_classification.py", "--dry-run", "--limit", "10"]), \
         patch("scripts.run_classification.SessionLocal", return_value=mock_db), \
         patch("scripts.run_classification.settings.GEMINI_API_KEY", "dummy_key"):
        
        # dry-run should not raise SystemExit
        cli_script.main()

    captured = capsys.readouterr()
    assert "EXECUTING DRY-RUN MODE (ZERO API CALLS, ZERO DB WRITES)" in captured.out
    assert "Dry-run sample selected for preview:   10" in captured.out
    assert "[DRY RUN COMPLETE] Verified: 0 Gemini API calls made. 0 database records modified." in captured.out

    # Verify zero database modifications
    post_unclassified = mock_db.query(Job).filter(Job.role_category.is_(None)).count()
    post_audit_logs = mock_db.query(LLMAuditLog).count()

    assert post_unclassified == initial_unclassified == 20
    assert post_audit_logs == initial_audit_logs == 0


def test_cli_override_pilot_limit_authorized(mock_db, capsys):
    """Verify limit > 15 is allowed when --override-pilot-limit is passed in dry-run mode."""
    with patch.object(sys, "argv", ["run_classification.py", "--limit", "20", "--override-pilot-limit", "--dry-run"]), \
         patch("scripts.run_classification.SessionLocal", return_value=mock_db):
        
        cli_script.main()

    captured = capsys.readouterr()
    assert "Dry-run sample selected for preview:   20" in captured.out
    assert "[DRY RUN COMPLETE]" in captured.out


# ---------------------------------------------------------------------------
# Tests for Explicit --job-ids Selection
# ---------------------------------------------------------------------------

def test_cli_job_ids_valid_selection(mock_db, capsys):
    """Verify explicit --job-ids selects precisely the requested jobs in exact order."""
    with patch.object(sys, "argv", ["run_classification.py", "--job-ids", "5,2,8", "--dry-run"]), \
         patch("scripts.run_classification.SessionLocal", return_value=mock_db):
        
        cli_script.main()

    captured = capsys.readouterr()
    assert "Dry-run sample selected for preview:   3" in captured.out
    assert "Engineer 5" in captured.out
    assert "Engineer 2" in captured.out
    assert "Engineer 8" in captured.out
    assert "BATCH JOB IDs TO CLASSIFY: [5, 2, 8]" in captured.out


def test_cli_job_ids_duplicate_rejected(capsys):
    """Verify duplicate IDs in --job-ids argument are rejected."""
    with patch.object(sys, "argv", ["run_classification.py", "--job-ids", "1,2,1", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "Duplicate job IDs detected" in captured.out


def test_cli_job_ids_invalid_format_rejected(capsys):
    """Verify non-integer IDs in --job-ids are rejected."""
    with patch.object(sys, "argv", ["run_classification.py", "--job-ids", "1,abc,3", "--dry-run"]):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "Invalid job ID format" in captured.out


def test_cli_job_ids_missing_rejected(mock_db, capsys):
    """Verify non-existent IDs in --job-ids are rejected."""
    with patch.object(sys, "argv", ["run_classification.py", "--job-ids", "1,9999", "--dry-run"]), \
         patch("scripts.run_classification.SessionLocal", return_value=mock_db):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "Specified job IDs not found in database" in captured.out
    assert "9999" in captured.out


def test_cli_job_ids_already_classified_rejected(mock_db, capsys):
    """Verify already-classified jobs in --job-ids are rejected."""
    # Mark job 1 as classified
    job1 = mock_db.query(Job).filter(Job.id == 1).first()
    job1.role_category = "Backend"
    mock_db.commit()

    with patch.object(sys, "argv", ["run_classification.py", "--job-ids", "1,2", "--dry-run"]), \
         patch("scripts.run_classification.SessionLocal", return_value=mock_db):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "Specified job IDs have already been classified: [1]" in captured.out


def test_cli_job_ids_pilot_cap_exceeded_rejected(mock_db, capsys):
    """Verify --job-ids with > 15 IDs halts unless --override-pilot-limit is passed."""
    # 16 IDs
    sixteen_ids = ",".join(str(i) for i in range(1, 17))
    with patch.object(sys, "argv", ["run_classification.py", "--job-ids", sixteen_ids, "--dry-run"]), \
         patch("scripts.run_classification.SessionLocal", return_value=mock_db):
        with pytest.raises(SystemExit) as exc_info:
            cli_script.main()
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "[SAFETY ERROR]" in captured.out
    assert "exceeds pilot cap of 15 jobs" in captured.out
