"""Unit tests for Database Models, Constraints and Traceability.

Validates:
1. Table creation across dialect-agnostic models.
2. Canonical job insertions with nullable company/location/description.
3. Unique constraint enforcement on (source, external_id).
4. Traceable duplicate logging linked to canonical_job_id.
5. Pipeline run telemetry and LLM token audit logging.
6. Ground-truth evaluation relational mapping.
"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import (
    Job,
    DuplicateRecord,
    PipelineRun,
    LLMAuditLog,
    GroundTruthEval
)


# In-memory SQLite session for fast, isolated unit testing
@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_canonical_job_with_nullables(db_session):
    """Verify canonical job creation succeeds even when company or location is null."""
    job = Job(
        source="hasjob",
        external_id="hasjob_101",
        title="Python Intern",
        company=None,  # Nullable per source capability
        raw_location=None,
        description="Write clean Python code.",
        apply_url="https://hasjob.co/demo/101",
        canonical_url_hash="hash_url_101",
        content_hash="hash_content_101",
        is_fresher_friendly=True
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.id is not None
    assert job.title == "Python Intern"
    assert job.company is None
    assert job.is_fresher_friendly is True
    assert job.is_active is True


def test_unique_constraint_source_external_id(db_session):
    """Verify that duplicate (source, external_id) raises IntegrityError."""
    job1 = Job(
        source="adzuna",
        external_id="adz_42",
        title="Software Engineer - Fresher",
        company="Infosys",
        apply_url="https://adzuna.in/jobs/42",
        canonical_url_hash="hash_adz_42",
        content_hash="content_adz_42"
    )
    db_session.add(job1)
    db_session.commit()

    # Attempt inserting identical source + external_id
    job2 = Job(
        source="adzuna",
        external_id="adz_42",
        title="Different Title Duplicate ID",
        apply_url="https://adzuna.in/jobs/42_alt",
        canonical_url_hash="hash_adz_42_alt",
        content_hash="content_adz_42_alt"
    )
    db_session.add(job2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_traceable_duplicate_record(db_session):
    """Verify duplicate record is stored separately and references canonical job."""
    canonical = Job(
        source="hasjob",
        external_id="hj_200",
        title="Frontend Intern (React)",
        company="Startup A",
        raw_location="Bengaluru",
        apply_url="https://hasjob.co/post/200",
        canonical_url_hash="url_hash_200",
        content_hash="content_hash_200"
    )
    db_session.add(canonical)
    db_session.commit()

    # Log detected duplicate candidate
    dup = DuplicateRecord(
        source="adzuna",
        external_id="adz_999",
        title="Frontend Intern (React)",
        company="Startup A",
        raw_location="Bangalore",
        apply_url="https://adzuna.in/post/999?utm_source=feed",
        canonical_url_hash="url_hash_200",
        content_hash="content_hash_200",
        duplicate_reason="canonical_url_match",
        canonical_job_id=canonical.id
    )
    db_session.add(dup)
    db_session.commit()

    assert dup.id is not None
    assert dup.canonical_job_id == canonical.id
    assert len(canonical.duplicates) == 1
    assert canonical.duplicates[0].duplicate_reason == "canonical_url_match"


def test_pipeline_run_telemetry(db_session):
    """Verify pipeline_runs table records batch ingestion stats."""
    run = PipelineRun(
        run_id="run_20261117_01",
        source="adzuna",
        fetch_count=50,
        unique_count=42,
        duplicate_count=8,
        classification_success_count=42,
        classification_failure_count=0,
        execution_duration_seconds=4.35,
        run_status="success"
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.id is not None
    assert run.unique_count + run.duplicate_count == run.fetch_count
    assert run.run_status == "success"


def test_llm_audit_logging(db_session):
    """Verify LLM token consumption and latency are recorded accurately."""
    log = LLMAuditLog(
        batch_id="batch_gemini_001",
        jobs_count=15,
        status="success",
        prompt_tokens=1820,
        completion_tokens=450,
        total_tokens=2270,
        model_name="gemini-2.5-flash",
        latency_seconds=1.85
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    assert log.id is not None
    assert log.total_tokens == log.prompt_tokens + log.completion_tokens
    assert log.status == "success"


def test_ground_truth_eval_relationship(db_session):
    """Verify manually verified ground-truth links to canonical job."""
    job = Job(
        source="hasjob",
        external_id="hj_gt_1",
        title="Junior Data Analyst",
        company="Fintech Co",
        raw_location="Pune",
        apply_url="https://hasjob.co/gt/1",
        canonical_url_hash="hash_gt_1",
        content_hash="content_gt_1",
        role_category="Data & Analytics",
        standardized_city="Pune",
        is_fresher_friendly=True,
        model_confidence=0.95
    )
    db_session.add(job)
    db_session.commit()

    eval_record = GroundTruthEval(
        job_id=job.id,
        human_role_category="Data & Analytics",
        human_city="Pune",
        human_fresher_status="fresher_friendly",
        role_match=(job.role_category == "Data & Analytics"),
        city_match=(job.standardized_city == "Pune"),
        fresher_match=(job.is_fresher_friendly is True),
        notes="Verified directly from job description specifying 0-1 years exp."
    )
    db_session.add(eval_record)
    db_session.commit()

    assert eval_record.role_match is True
    assert eval_record.city_match is True
    assert eval_record.fresher_match is True
    assert job.ground_truth.human_role_category == "Data & Analytics"
