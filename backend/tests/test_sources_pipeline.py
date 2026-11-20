"""Deterministic Unit Tests for Source Adapters and Ingestion Pipeline.

Uses mocked responses to validate:
1. Meaningful query parameters preserved during URL normalization.
2. Comprehensive India geographic eligibility edge cases.
3. Hasjob Atom feed parsing with company name splitting and fallback.
4. Remotive JSON parsing with null/missing field tolerance.
5. Per-source fault isolation (one source failure does not stop others).
6. Pipeline idempotency (second run detects duplicates).
7. Strict preservation of pending classification (is_fresher_friendly is None).
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, DuplicateRecord, PipelineRun
from app.ingestion.normalizer import normalize_url, is_india_eligible
from app.ingestion.sources.base import BaseSourceAdapter
from app.ingestion.sources.hasjob import HasjobAdapter
from app.ingestion.sources.remotive import RemotiveAdapter
from app.ingestion.pipeline import run_ingestion_pipeline


@pytest.fixture(scope="function")
def db_session():
    """Isolated in-memory SQLite session."""
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
# Safeguard 1: Meaningful Query Parameters Preserved in URL Normalization
# ---------------------------------------------------------------------------

def test_meaningful_query_parameters_preserved():
    """Verify job-identifying parameters are kept while tracking tokens are stripped."""
    raw_url = (
        "https://careers.company.com/openings/view"
        "?job_id=98765&token=xyz789&position=intern&utm_source=linkedin&ref=job_board"
    )
    clean = normalize_url(raw_url)

    # Job identifying parameters MUST be preserved
    assert "job_id=98765" in clean
    assert "token=xyz789" in clean
    assert "position=intern" in clean

    # Marketing tracking parameters MUST be removed
    assert "utm_source" not in clean
    assert "ref=" not in clean


# ---------------------------------------------------------------------------
# Safeguard 2: India Eligibility Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_loc,title,is_indian_source,expected_eligible,desc",
    [
        ("Remote", "Software Engineer", False, False, "Remote — location unspecified on global source"),
        ("Remote", "Software Engineer", True, True, "Remote — on Indian native source defaults to India"),
        ("Worldwide", "Backend Dev", False, True, "Worldwide — explicitly available globally"),
        ("Anywhere in the world", "Python Dev", False, True, "Anywhere in the world — global"),
        ("US Only", "Frontend Intern", False, False, "US only restriction"),
        ("Europe only", "Data Analyst", False, False, "Europe only restriction"),
        ("India - Remote", "QA Engineer", False, True, "India — Remote"),
        ("Bengaluru, India", "AI Intern", False, True, "Bengaluru, India"),
        ("Bangalore, Karnataka", "DevOps Intern", False, True, "City alias: Bangalore spelling"),
        ("Mumbai, Maharashtra", "Software Engineer", False, True, "Indian city: Mumbai"),
        ("Hyderabad", "Backend Intern", False, True, "Indian city: Hyderabad"),
        ("Chennai, Tamil Nadu", "Data Analyst", False, True, "Indian city: Chennai"),
        ("Kolkata, West Bengal", "Frontend Developer", False, True, "Indian city: Kolkata"),
        ("New Delhi", "Full Stack Intern", False, True, "Indian city: New Delhi"),
        ("Pune", "Full Stack Intern", False, True, "Pune Indian tech hub"),
        ("Remote", "DevOps Engineer (Remote - US applicants only)", False, False, "Remote but restricted to US applicants"),
        ("Remote, US", "Cloud Engineer", False, False, "Remote, US pattern"),
        (None, "Software Engineer", False, False, "Missing location (None) on global source"),
        (None, "Software Engineer", True, True, "Missing location (None) on Indian source"),
        ("", "Frontend Intern", False, False, "Empty location on global source"),
        ("Austin, TX", "Software Engineer", False, False, "Ambiguous foreign US city"),
        ("Berlin, Germany", "Backend Developer", False, False, "Ambiguous foreign European city"),
    ]
)
def test_india_eligibility_edge_cases(raw_loc, title, is_indian_source, expected_eligible, desc):
    eligible, reason = is_india_eligible(raw_loc, title, is_indian_source=is_indian_source)
    assert eligible == expected_eligible, f"Failed for case: {desc}. Reason: {reason}"


# ---------------------------------------------------------------------------
# Source Adapter Unit Tests (Mocked Network)
# ---------------------------------------------------------------------------

MOCK_ATOM_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Hasjob Feed</title>
  <entry>
    <title>Security Intern - CyberTech Solutions</title>
    <link href="https://hasjob.co/cybertech/101" />
    <id>tag:hasjob.co,2026:101</id>
    <updated>2026-11-17T12:00:00Z</updated>
    <summary>Exciting cybersecurity internship for college graduates in Bengaluru.</summary>
  </entry>
  <entry>
    <title>Junior Frontend Developer</title>
    <link href="https://hasjob.co/alpha/102" />
    <id>tag:hasjob.co,2026:102</id>
    <updated>2026-11-17T13:00:00Z</updated>
    <summary>React developer opening.</summary>
  </entry>
</feed>
"""

MOCK_REMOTIVE_JSON = {
    "jobs": [
        {
            "id": 501,
            "title": "Junior Python Developer",
            "company_name": "Global Tech",
            "candidate_required_location": "Worldwide",
            "url": "https://remotive.com/job/501",
            "description": "Full remote role open worldwide.",
            "publication_date": "2026-11-17T10:00:00Z"
        },
        {
            "id": 502,
            "title": "React Engineer",
            "company_name": "US Startup",
            "candidate_required_location": "USA Only",
            "url": "https://remotive.com/job/502",
            "description": "Must be located in USA.",
            "publication_date": "2026-11-17T11:00:00Z"
        }
    ]
}


def test_hasjob_adapter_parsing():
    """Verify Hasjob adapter correctly parses entries and splits company name."""
    adapter = HasjobAdapter()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = MOCK_ATOM_XML
        mock_urlopen.return_value.__enter__.return_value = mock_response

        records, req_count, err = adapter.fetch_records()

        assert err is None
        assert req_count == 1
        assert len(records) == 2

        # Entry 1: 'Security Intern - CyberTech Solutions'
        assert records[0]["title"] == "Security Intern"
        assert records[0]["company"] == "CyberTech Solutions"
        assert records[0]["source"] == "hasjob"
        assert records[0]["apply_url"] == "https://hasjob.co/cybertech/101"

        # Entry 2: No ' - ', company should be None
        assert records[1]["title"] == "Junior Frontend Developer"
        assert records[1]["company"] is None


def test_remotive_adapter_parsing():
    """Verify Remotive adapter parses JSON and extracts location restrictions."""
    adapter = RemotiveAdapter()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        import json
        mock_response.read.return_value = json.dumps(MOCK_REMOTIVE_JSON).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        records, req_count, err = adapter.fetch_records()

        assert err is None
        assert req_count == 1
        assert len(records) == 2
        assert records[0]["raw_location"] == "Worldwide"
        assert records[1]["raw_location"] == "USA Only"


# ---------------------------------------------------------------------------
# Pipeline Integration & Safeguards
# ---------------------------------------------------------------------------

class MockSuccessfulAdapter(BaseSourceAdapter):
    source_name = "mock_source_a"
    is_indian_source = True

    def fetch_records(self):
        return [
            {
                "source": "mock_source_a",
                "external_id": "a_1",
                "title": "Backend Intern",
                "company": "Startup A",
                "raw_location": "Bengaluru",
                "apply_url": "https://startupa.com/intern?ref=feed",
                "description": "Python, FastAPI",
                "posted_at": datetime.now(timezone.utc)
            }
        ], 1, None


class MockFailingAdapter(BaseSourceAdapter):
    source_name = "mock_source_b"
    is_indian_source = False

    def fetch_records(self):
        return [], 1, "Simulated 503 Gateway Timeout"


def test_pipeline_fault_isolation(db_session):
    """Verify failure in one adapter does not prevent successful ingestion from another."""
    adapters = [MockFailingAdapter(), MockSuccessfulAdapter()]

    summary = run_ingestion_pipeline(db=db_session, adapters=adapters, batch_run_id="test_run_iso")

    # Source B should record failure
    assert summary["sources"]["mock_source_b"]["status"] == "failed"
    assert "Simulated 503" in summary["sources"]["mock_source_b"]["error"]

    # Source A should succeed and insert job
    assert summary["sources"]["mock_source_a"]["status"] == "success"
    assert summary["sources"]["mock_source_a"]["unique_inserted"] == 1

    # Database checks
    job = db_session.query(Job).filter(Job.source == "mock_source_a").first()
    assert job is not None
    assert job.title == "Backend Intern"
    assert job.is_fresher_friendly is None  # Pending classification!

    # Check pipeline runs table contains both
    runs = db_session.query(PipelineRun).all()
    assert len(runs) == 2


def test_pipeline_idempotency_and_duplicate_tracking(db_session):
    """Verify running pipeline twice on identical data creates canonical first, duplicate second."""
    adapter = MockSuccessfulAdapter()

    # Run 1: Should insert 1 unique canonical job
    summary1 = run_ingestion_pipeline(db=db_session, adapters=[adapter], batch_run_id="run_1")
    assert summary1["totals"]["unique_inserted"] == 1
    assert summary1["totals"]["confirmed_duplicates"] == 0

    # Run 2: Exact same record should be detected as duplicate
    summary2 = run_ingestion_pipeline(db=db_session, adapters=[adapter], batch_run_id="run_2")
    assert summary2["totals"]["unique_inserted"] == 0
    assert summary2["totals"]["confirmed_duplicates"] == 1

    # Verify duplicate record is logged with audit link
    dup_row = db_session.query(DuplicateRecord).first()
    assert dup_row is not None
    assert dup_row.canonical_job_id is not None
    assert dup_row.duplicate_reason == "source_id_match"
