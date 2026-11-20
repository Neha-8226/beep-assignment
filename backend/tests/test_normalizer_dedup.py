"""Unit tests for Normalization and Deduplication Engine.

Tests:
1. URL canonicalization and tracking parameter removal.
2. Deterministic fallback ID generation for sources without native IDs.
3. Content hash consistency across whitespace and casing variations.
4. India geographic accessibility filtering.
5. Incomplete/invalid record validation.
6. Tier 1 exact source ID duplicate detection.
7. Tier 2 cross-source canonical URL duplicate detection.
8. Tier 3 potential duplicate handling with preserved evidence.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, DuplicateRecord
from app.ingestion.normalizer import (
    normalize_url,
    hash_url,
    normalize_text,
    generate_fallback_external_id,
    compute_content_hash,
    is_india_eligible,
    validate_raw_record
)
from app.ingestion.dedup import evaluate_candidate, record_duplicate


@pytest.fixture(scope="function")
def db_session():
    """Isolated in-memory SQLite session for testing deduplication queries."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Normalization Tests
# ---------------------------------------------------------------------------

def test_normalize_url_strips_tracking_parameters():
    url_with_tracking = "https://EXAMPLE.com/jobs/dev-101/?utm_source=newsletter&utm_medium=email&ref=job_board&real_param=active#apply"
    clean = normalize_url(url_with_tracking)

    assert "utm_source" not in clean
    assert "utm_medium" not in clean
    assert "ref=" not in clean
    assert "#apply" not in clean
    assert "real_param=active" in clean
    assert clean.startswith("https://example.com/jobs/dev-101")


def test_normalize_url_handles_trailing_slash_and_casing():
    url1 = "https://Acme.in/Careers/Software-Engineer/"
    url2 = "https://acme.in/careers/software-engineer"
    assert normalize_url(url1) == "https://acme.in/careers/software-engineer"
    assert hash_url(normalize_url(url1)) == hash_url(normalize_url(url2))


def test_generate_fallback_external_id_deterministic():
    id1 = generate_fallback_external_id("hasjob", "Junior Engineer", "Zeta", "https://hasjob.co/post/1")
    id2 = generate_fallback_external_id("hasjob", "Junior Engineer", "Zeta", "https://hasjob.co/post/1")
    assert id1 == id2
    assert id1.startswith("gen_")


def test_compute_content_hash_invariance():
    # Whitespace, casing, and punctuation variations should produce the exact same content hash
    h1 = compute_content_hash("Backend Developer - Fresher", "Startup Inc.", "Bengaluru, India")
    h2 = compute_content_hash("backend developer - fresher ", "startup inc", "bengaluru, india")
    assert h1 == h2


def test_is_india_eligible():
    # True cases
    ok_in, _ = is_india_eligible("Bengaluru, Karnataka")
    assert ok_in is True

    ok_city, _ = is_india_eligible("Pune, Maharashtra")
    assert ok_city is True

    ok_ncr, _ = is_india_eligible("Gurugram / Noida")
    assert ok_ncr is True

    ok_remote_world, _ = is_india_eligible("Remote (Worldwide)")
    assert ok_remote_world is True

    ok_title, _ = is_india_eligible("Remote", "Python Intern (India)")
    assert ok_title is True

    # False cases (Foreign-restricted)
    fail_us, reason_us = is_india_eligible("Remote (US Only)")
    assert fail_us is False
    assert "Foreign-only" in reason_us

    fail_eu, _ = is_india_eligible("Europe Only")
    assert fail_eu is False

    fail_london, _ = is_india_eligible("London, United Kingdom")
    assert fail_london is False


def test_validate_raw_record():
    valid, err = validate_raw_record({"title": "React Intern", "apply_url": "https://careers.company.com/job/1"})
    assert valid is True
    assert err is None

    no_title, err = validate_raw_record({"title": "", "apply_url": "https://careers.company.com/job/1"})
    assert no_title is False
    assert "title" in err

    no_url, err = validate_raw_record({"title": "Dev", "apply_url": ""})
    assert no_url is False
    assert "URL" in err


# ---------------------------------------------------------------------------
# Deduplication Engine Tests
# ---------------------------------------------------------------------------

def test_dedup_tier1_source_id_match(db_session):
    """Verify strong duplicate match on (source, external_id)."""
    # Seed canonical job
    canonical = Job(
        source="hasjob",
        external_id="hj_001",
        title="ML Intern",
        company="AI Lab",
        raw_location="Bengaluru",
        apply_url="https://hasjob.co/post/001",
        canonical_url_hash=hash_url("https://hasjob.co/post/001"),
        content_hash=compute_content_hash("ML Intern", "AI Lab", "Bengaluru")
    )
    db_session.add(canonical)
    db_session.commit()

    # Ingest candidate with same source and external_id
    res = evaluate_candidate(
        db=db_session,
        source="hasjob",
        external_id="hj_001",
        title="Machine Learning Intern",
        apply_url="https://hasjob.co/different-url"
    )

    assert res.is_unique is False
    assert res.duplicate_type == "confirmed"
    assert res.duplicate_reason == "source_id_match"
    assert res.canonical_job.id == canonical.id


def test_dedup_tier2_canonical_url_match(db_session):
    """Verify cross-source strong duplicate match via canonical URL."""
    clean_url = "https://company.com/careers/software-engineer-fresher"
    canonical = Job(
        source="adzuna",
        external_id="adz_555",
        title="Software Engineer - Fresher",
        company="Company Tech",
        raw_location="Hyderabad",
        apply_url=clean_url,
        canonical_url_hash=hash_url(clean_url),
        content_hash=compute_content_hash("Software Engineer", "Company Tech", "Hyderabad")
    )
    db_session.add(canonical)
    db_session.commit()

    # Ingest candidate from a different source pointing to the exact same URL with tracking params
    res = evaluate_candidate(
        db=db_session,
        source="hasjob",
        external_id="hj_888",
        title="Junior Developer",
        apply_url=clean_url + "?utm_source=jobboard&ref=aggregator"
    )

    assert res.is_unique is False
    assert res.duplicate_type == "confirmed"
    assert res.duplicate_reason == "canonical_url_match"
    assert res.canonical_job.id == canonical.id


def test_dedup_tier3_potential_duplicate(db_session):
    """Verify potential duplicate flag for identical title+company+location with distinct URLs."""
    canonical = Job(
        source="hasjob",
        external_id="hj_301",
        title="Full Stack Intern",
        company="Fintech Corp",
        raw_location="Pune",
        apply_url="https://hasjob.co/post/301",
        canonical_url_hash=hash_url("https://hasjob.co/post/301"),
        content_hash=compute_content_hash("Full Stack Intern", "Fintech Corp", "Pune")
    )
    db_session.add(canonical)
    db_session.commit()

    # Ingest candidate with same title/company/location but distinct application URL
    res = evaluate_candidate(
        db=db_session,
        source="adzuna",
        external_id="adz_902",
        title="Full Stack Intern",
        company="Fintech Corp",
        raw_location="Pune",
        apply_url="https://fintechcorp.com/careers/apply-now"
    )

    assert res.is_unique is False
    assert res.duplicate_type == "potential"
    assert res.duplicate_reason == "content_similarity_flag"
    assert "Content similarity flag" in res.evidence
    assert res.canonical_job.id == canonical.id

    # Record the duplicate and verify traceability
    dup_row = record_duplicate(
        db=db_session,
        source="adzuna",
        external_id="adz_902",
        title="Full Stack Intern",
        company="Fintech Corp",
        raw_location="Pune",
        apply_url="https://fintechcorp.com/careers/apply-now",
        result=res
    )
    db_session.commit()

    assert dup_row.id is not None
    assert dup_row.duplicate_type == "potential"
    assert dup_row.canonical_job_id == canonical.id


def test_dedup_unique_candidate(db_session):
    """Verify that a completely new, unique job passes deduplication."""
    res = evaluate_candidate(
        db=db_session,
        source="hasjob",
        external_id="hj_unique_1",
        title="DevOps Intern",
        company="Cloud Scale",
        raw_location="Mumbai",
        apply_url="https://hasjob.co/cloudscale/1"
    )

    assert res.is_unique is True
    assert res.duplicate_type is None
    assert res.canonical_job is None
