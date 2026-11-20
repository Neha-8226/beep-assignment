"""Comprehensive Unit & Integration Tests for Extraction & Relevance Engine.

Covers Milestone 6A remediation:
1. Hasjob Atom content extraction (prioritizing content over summary).
2. HTML sanitization preserving text readability and structure.
3. Hasjob native location extraction (e.g. city, state) without inventing missing facts.
4. Structured company extraction hierarchy (anchor, clean title, domain fallback).
5. Promotional text avoidance (e.g. '$100/hr' never treated as company).
6. Missing and malformed field resilience.
7. Context-aware seniority detection ('Lead Generation Intern' accepted; 'Technical Lead' rejected).
8. Explicit experience requirements (> 1 yr rejected, 0-1 yr accepted).
9. Ambiguous experience retention (retained as uncertain_review; never falsely claimed fresher-friendly).
10. Talent pool and non-individual vacancy detection.
11. Remotive worldwide eligibility screening.
12. Separation of concerns (India eligibility, vacancy type, fresher suitability).
13. Auditability: Traceable rejected_records persistence with categories and reasons.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Job, DuplicateRecord, PipelineRun, RejectedRecord
from app.ingestion.sources.hasjob import HasjobAdapter, sanitize_html, extract_company_and_title
from app.ingestion.sources.remotive import RemotiveAdapter
from app.ingestion.relevance import (
    evaluate_job_relevance,
    evaluate_vacancy_type,
    evaluate_seniority_and_fresher_suitability,
    RelevanceDecision
)
from app.ingestion.pipeline import run_ingestion_pipeline


# ---------------------------------------------------------------------------
# In-Memory Database Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    """Create isolated in-memory SQLite database with schema for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# 1. Hasjob Extraction & Sanitization Tests
# ---------------------------------------------------------------------------

def test_sanitize_html_preserves_structure_and_cleans_tags():
    """Verify HTML sanitization preserves readable layout and strips tags/scripts."""
    raw_html = (
        "<div><p>We are seeking a <strong>Junior Python Engineer</strong>.</p>"
        "<ul><li>FastAPI development</li><li>SQL database design</li></ul>"
        "<p>Compensation: ₹6 LPA - ₹8 LPA<br/>Apply now!</p></div>"
    )
    cleaned = sanitize_html(raw_html)
    assert cleaned is not None
    assert "Junior Python Engineer" in cleaned
    assert "FastAPI development" in cleaned
    assert "<div>" not in cleaned
    assert "<strong>" not in cleaned
    assert "<ul>" not in cleaned


def test_sanitize_html_handles_empty_and_entities():
    """Verify HTML unescaping and empty handling."""
    assert sanitize_html(None) is None
    assert sanitize_html("") is None
    assert sanitize_html("   ") is None
    unescaped = sanitize_html("AT&amp;T &lt;specialists&gt;")
    assert unescaped == "AT&T <specialists>"


def test_hasjob_extracts_native_content_and_location():
    """Verify Hasjob adapter extracts atom:content and atom:location."""
    atom_xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Hasjob Feed</title>
      <entry>
        <title>Cybersecurity Intern</title>
        <link href="https://hasjob.co/nestack.com/85q9v" />
        <id>https://hasjob.co/nestack.com/85q9v</id>
        <updated>2026-11-06T14:16:30Z</updated>
        <location>Hyderabad, Telangana, India (on-site, no WFH)</location>
        <content type="html">&lt;p&gt;&lt;strong&gt;&lt;a href="https://nestack.com"&gt;Nestack Technologies Pvt Ltd&lt;/a&gt;&lt;/strong&gt;&lt;/p&gt;&lt;p&gt;6-month cybersecurity internship.&lt;/p&gt;</content>
      </entry>
    </feed>
    """
    adapter = HasjobAdapter()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = atom_xml
        mock_urlopen.return_value.__enter__.return_value = mock_response

        records, req_count, err = adapter.fetch_records()
        assert err is None
        assert len(records) == 1
        rec = records[0]

        assert rec["title"] == "Cybersecurity Intern"
        assert rec["company"] == "Nestack Technologies Pvt Ltd"
        assert rec["raw_location"] == "Hyderabad, Telangana, India (on-site, no WFH)"
        assert "6-month cybersecurity internship" in rec["description"]
        assert rec["apply_url"] == "https://hasjob.co/nestack.com/85q9v"


def test_company_extraction_hierarchy_and_promo_rejection():
    """Verify company extraction prioritizes anchor, avoids promos, and falls back to clean domain."""
    # 1. Anchor in content takes precedence
    content = '<p><strong><a href="https://example.com">True Company</a></strong></p>'
    comp, title = extract_company_and_title("Dev Engineer - True Company", content, "https://hasjob.co/trueco.in/123")
    assert comp == "True Company"

    # 2. Rejection of promotional string in title suffix
    promo_title = "Generalist AI Trainer - remote, worldwide, $100/hr"
    comp_promo, clean_t = extract_company_and_title(promo_title, None, "https://hasjob.co/aitrainingjobs.xyz/xql2m")
    assert clean_t == "Generalist AI Trainer - remote, worldwide, $100/hr"
    # Company must NOT be '$100/hr'; falls back to clean domain
    assert comp_promo == "Aitrainingjobs"

    # 3. Clean title suffix when legitimate
    clean_suffix_title = "Forward Deployed Engineer - MyActionBoard"
    comp_suffix, clean_t2 = extract_company_and_title(clean_suffix_title, None, "https://hasjob.co/myactionboard.com/ccvh3")
    assert comp_suffix == "MyActionBoard"
    assert clean_t2 == "Forward Deployed Engineer"


# ---------------------------------------------------------------------------
# 2. Relevance, Seniority & Fresher Suitability Tests
# ---------------------------------------------------------------------------

def test_context_aware_seniority_internship_wins_over_lead():
    """Verify 'Lead Generation Intern' is classified as confirmed fresher, not rejected for 'Lead'."""
    decision = evaluate_job_relevance(
        title="Lead Generation Intern",
        raw_location="Bengaluru, Karnataka",
        description="Support our sales team with B2B lead prospecting.",
        is_indian_source=True
    )
    assert decision.is_accepted is True
    assert decision.outcome == "confirmed_fresher"
    assert decision.category == "fresher_friendly"
    assert "Internship" in decision.reason


def test_senior_titles_strictly_rejected():
    """Verify unambiguous leadership and senior titles are excluded with explicit category."""
    senior_titles = [
        "Head of Engineering",
        "Director of Product Engineering",
        "Principal Systems Architect",
        "Staff Software Engineer",
        "Java Technical Lead",
        "Engineering Manager - Data Platforms",
        "Tier III Service Desk Engineer",
        "Senior Cloud Infrastructure Developer"
    ]
    for st in senior_titles:
        decision = evaluate_job_relevance(
            title=st,
            raw_location="Bengaluru",
            description="Leading senior technical initiatives.",
            is_indian_source=True
        )
        assert decision.is_accepted is False, f"Expected rejection for {st}"
        assert decision.outcome == "not_fresher_suitable"
        assert decision.category == "seniority_exclusion"
        assert "title" in decision.reason.lower()


def test_explicit_experience_exceeded_rejected():
    """Verify roles explicitly mandating > 1 year of experience are rejected."""
    decision = evaluate_job_relevance(
        title="Full-Stack Developer",
        raw_location="Worldwide",
        description="Must have at least 3+ years of professional experience building React apps.",
        is_indian_source=False
    )
    assert decision.is_accepted is False
    assert decision.outcome == "not_fresher_suitable"
    assert decision.category == "seniority_exclusion"
    assert "3+ years" in decision.reason


def test_explicit_fresher_accepted():
    """Verify 0-1 YOE or explicit 'freshers welcome' are confirmed as fresher friendly."""
    decision = evaluate_job_relevance(
        title="Junior Frontend Developer",
        raw_location="Pune, India",
        description="Freshers welcome to apply. Requires basic HTML/CSS/JavaScript and 0-1 years of experience.",
        is_indian_source=True
    )
    assert decision.is_accepted is True
    assert decision.outcome == "confirmed_fresher"
    assert decision.category == "fresher_friendly"


def test_ambiguous_experience_retained_as_uncertain_review():
    """Verify ambiguous individual vacancies are preserved for review, NOT falsely claimed as confirmed fresher."""
    decision = evaluate_job_relevance(
        title="Professional Medical Content Writer",
        raw_location="Ghaziabad, India",
        description="Write clinical research summaries and health care articles for our portal.",
        is_indian_source=True
    )
    assert decision.is_accepted is True
    # Must be uncertain_review, NEVER confirmed_fresher
    assert decision.outcome == "uncertain_review"
    assert decision.category == "needs_review"
    assert "unstated" in decision.reason.lower()


def test_talent_pool_and_matching_network_rejected():
    """Verify talent pools, matching networks, and open submissions are rejected as non-individual vacancies."""
    decision = evaluate_job_relevance(
        title="Remote Professionals & Specialists – AI Matching Network",
        raw_location="Remote",
        description="Join our global talent network for all skill levels and industries to match with future gigs.",
        is_indian_source=True
    )
    assert decision.is_accepted is False
    assert decision.outcome == "not_individual_vacancy"
    assert decision.category == "talent_pool_exclusion"
    assert "talent/matching network" in decision.reason.lower()


# ---------------------------------------------------------------------------
# 3. Separation of Concerns Tests
# ---------------------------------------------------------------------------

def test_separation_of_india_eligibility_vs_fresher_suitability():
    """Verify India ineligibility is kept completely separate from fresher suitability."""
    # US-restricted internship: Fresher friendly BUT India-ineligible
    d1 = evaluate_job_relevance(
        title="Software Engineering Intern",
        raw_location="Remote (US applicants only)",
        description="Summer internship for college students in the United States.",
        is_indian_source=False
    )
    assert d1.is_accepted is False
    assert d1.outcome == "india_ineligible"
    assert d1.category == "geo_ineligible"

    # Indian senior role: India eligible BUT Not fresher suitable
    d2 = evaluate_job_relevance(
        title="Head of Arena Operations",
        raw_location="Mumbai, Maharashtra, India",
        description="Manage our arena operations team.",
        is_indian_source=True
    )
    assert d2.is_accepted is False
    assert d2.outcome == "not_fresher_suitable"
    assert d2.category == "seniority_exclusion"


# ---------------------------------------------------------------------------
# 4. Pipeline Integration & Traceable Rejection Telemetry
# ---------------------------------------------------------------------------

def test_pipeline_records_rejected_record_telemetry(db_session):
    """Verify rejected candidates are saved into rejected_records table with full audit trail."""
    mock_records = [
        # 1. Accepted confirmed fresher
        {
            "source": "hasjob",
            "external_id": "test-fresher-1",
            "title": "Data Analyst Intern",
            "company": "Analytics Corp",
            "raw_location": "Bengaluru, India",
            "description": "Internship for freshers.",
            "apply_url": "https://hasjob.co/analytics/1",
            "posted_at": datetime.now(timezone.utc)
        },
        # 2. Rejected senior title
        {
            "source": "hasjob",
            "external_id": "test-senior-1",
            "title": "Head of Engineering",
            "company": "Big Tech India",
            "raw_location": "Bengaluru, India",
            "description": "Executive leadership role.",
            "apply_url": "https://hasjob.co/bigtech/2",
            "posted_at": datetime.now(timezone.utc)
        },
        # 3. Rejected talent pool
        {
            "source": "hasjob",
            "external_id": "test-pool-1",
            "title": "Global Talent Matching Network",
            "company": "Talent Network Inc",
            "raw_location": "India",
            "description": "Join our talent pool for future roles.",
            "apply_url": "https://hasjob.co/pool/3",
            "posted_at": datetime.now(timezone.utc)
        },
        # 4. Rejected geographic ineligibility
        {
            "source": "remotive",
            "external_id": "test-geo-1",
            "title": "Junior Python Dev",
            "company": "US Firm",
            "raw_location": "USA Only",
            "description": "Entry level Python dev.",
            "apply_url": "https://remotive.com/job/4",
            "posted_at": datetime.now(timezone.utc)
        }
    ]

    class MockAdapter:
        source_name = "test_source"
        is_indian_source = False
        def fetch_records(self):
            return mock_records, 1, None

    summary = run_ingestion_pipeline(db=db_session, adapters=[MockAdapter()])

    # Verify summary numbers
    assert summary["totals"]["records_fetched"] == 4
    assert summary["totals"]["unique_inserted"] == 1
    assert summary["totals"]["records_rejected"] == 3

    # Verify Job table only contains the 1 accepted fresher job
    canonical_jobs = db_session.query(Job).all()
    assert len(canonical_jobs) == 1
    assert canonical_jobs[0].title == "Data Analyst Intern"
    assert canonical_jobs[0].is_fresher_friendly is None  # Remains pending classification

    # Verify RejectedRecord table contains exactly 3 audit records
    rejections = db_session.query(RejectedRecord).order_by(RejectedRecord.id).all()
    assert len(rejections) == 3

    # Check rejection 1: Seniority exclusion
    r1 = rejections[0]
    assert r1.external_id == "test-senior-1"
    assert r1.rejection_category == "seniority_exclusion"
    assert "Head-level" in r1.reason
    assert r1.rule_version == "v1.0"
    assert r1.pipeline_run_id is not None

    # Check rejection 2: Talent pool exclusion
    r2 = rejections[1]
    assert r2.external_id == "test-pool-1"
    assert r2.rejection_category == "talent_pool_exclusion"
    assert "talent/matching network" in r2.reason.lower()

    # Check rejection 3: Geographic exclusion
    r3 = rejections[2]
    assert r3.external_id == "test-geo-1"
    assert r3.rejection_category == "geo_ineligible"
    assert "Foreign-only restriction" in r3.reason


# ---------------------------------------------------------------------------
# 5. Milestone 6A Regression Tests (Tightened Eligibility & Geographic Rules)
# ---------------------------------------------------------------------------

def test_tightened_confirmed_fresher_rules():
    """Verify absence of experience or vague mentions do NOT automatically grant confirmed fresher."""
    # 1. Vague entry-level tasks: NOT confirmed fresher -> uncertain_review
    d1 = evaluate_job_relevance(
        title="Office Assistant",
        raw_location="Bengaluru, India",
        description="Assist with entry-level bookkeeping and clerical duties. Experience preferred but not required.",
        is_indian_source=True
    )
    assert d1.is_accepted is True
    assert d1.outcome == "uncertain_review"
    assert d1.category == "needs_review"

    # 2. Company onboarding 'trainees': NOT confirmed fresher -> uncertain_review
    d2 = evaluate_job_relevance(
        title="Inside Sales Representative",
        raw_location="Bengaluru, India",
        description="Our trainees receive a weekly stipend during onboarding. We seek motivated sales professionals.",
        is_indian_source=True
    )
    assert d2.is_accepted is True
    assert d2.outcome == "uncertain_review"
    assert d2.category == "needs_review"

    # 3. Explicit fresher targeting: CONFIRMED fresher
    d3 = evaluate_job_relevance(
        title="Software Engineer",
        raw_location="Bengaluru, India",
        description="We are hiring freshers! Freshers welcome to apply. Requires 0-1 years of experience.",
        is_indian_source=True
    )
    assert d3.is_accepted is True
    assert d3.outcome == "confirmed_fresher"
    assert d3.category == "fresher_friendly"


def test_ghaziabad_and_madurai_location_coverage():
    """Verify Ghaziabad and Madurai are recognized Indian cities."""
    from app.ingestion.normalizer import is_india_eligible, check_geographic_eligibility

    # Direct normalizer check
    ok_gz, r_gz = is_india_eligible("Ghaziabad", "Content Writer", is_indian_source=True)
    assert ok_gz is True
    assert "Ghaziabad" in r_gz

    ok_md, r_md = is_india_eligible("Madurai", "Marketing Executive", is_indian_source=True)
    assert ok_md is True
    assert "Madurai" in r_md

    # Pipeline relevance check: Legitimate Ghaziabad job is accepted (uncertain review), not rejected
    d_gz = evaluate_job_relevance(
        title="Professional Medical Content Writer",
        raw_location="Ghaziabad",
        description="PharmaBridge International is an India-based distributor.",
        is_indian_source=True
    )
    assert d_gz.is_accepted is True
    assert d_gz.outcome == "uncertain_review"

    d_md = evaluate_job_relevance(
        title="Digital Marketing Agency Specialist",
        raw_location="Madurai",
        description="Growth-focused digital partner based in Madurai, Tamil Nadu.",
        is_indian_source=True
    )
    assert d_md.is_accepted is True
    assert d_md.outcome == "uncertain_review"


def test_indian_state_and_alias_coverage():
    """Verify Indian states and city aliases are recognized as eligible."""
    from app.ingestion.normalizer import check_geographic_eligibility

    # State matching
    status_tn, _ = check_geographic_eligibility("Tamil Nadu", is_indian_source=True)
    assert status_tn == "eligible"

    status_up, _ = check_geographic_eligibility("Uttar Pradesh", is_indian_source=True)
    assert status_up == "eligible"

    # City aliases
    status_by, _ = check_geographic_eligibility("Bombay", is_indian_source=True)
    assert status_by == "eligible"

    status_md, _ = check_geographic_eligibility("Madras", is_indian_source=True)
    assert status_md == "eligible"

    status_cal, _ = check_geographic_eligibility("Calcutta", is_indian_source=True)
    assert status_cal == "eligible"


def test_ambiguous_location_retained_as_uncertain_review():
    """Verify ambiguous or unrecognized locations are retained as uncertain review, not auto-accepted or auto-rejected."""
    # An unrecognized Indian town name without explicit foreign restriction
    d = evaluate_job_relevance(
        title="Software Intern",
        raw_location="Pilani",
        description="Internship opportunity at startup campus.",
        is_indian_source=True
    )
    # Must be retained for review, but NOT confirmed fresher due to ambiguous location
    assert d.is_accepted is True
    assert d.outcome == "uncertain_review"
    assert d.category == "needs_review"
    assert "ambiguous or unrecognized" in d.reason.lower()


def test_remotive_questionable_records_downgraded_to_uncertain():
    """Verify Remote Office Assistant and Inside Sales Contractor are classified as uncertain."""
    # 1. Remote Office Assistant: Worldwide, administrative, entry-level bookkeeping tasks mentioned
    d_roa = evaluate_job_relevance(
        title="Remote Office Assistant",
        raw_location="Worldwide",
        description=(
            "Coalition Technologies is seeking a Remote Office Assistant. "
            "Assist with entry-level bookkeeping tasks, organizing documents. "
            "Experience preferred but not required."
        ),
        is_indian_source=False
    )
    assert d_roa.is_accepted is True
    assert d_roa.outcome == "uncertain_review"
    assert d_roa.category == "needs_review"

    # 2. Inside Sales Contractor: Worldwide, mentions trainees and seasoned sales professional
    d_isc = evaluate_job_relevance(
        title="Inside Sales Contractor",
        raw_location="Worldwide",
        description=(
            "During our training period we offer a stipend while our trainees are acclimating. "
            "If you are a seasoned sales professional looking for autonomy, we want to hear from you!"
        ),
        is_indian_source=False
    )
    assert d_isc.is_accepted is True
    assert d_isc.outcome == "uncertain_review"
    assert d_isc.category == "needs_review"

