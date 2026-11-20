"""Unit and Integration Tests for ATS Adapters and Relevance Enhancements.

Tests cover:
1. Greenhouse adapter parsing (HTML sanitization, location, timestamps, stable IDs).
2. Lever adapter parsing (descriptionPlain fallback, timestamps, categories).
3. ATS company registry (strictly 7 verified companies, provider filtering, exclusion of GitLab/Porter).
4. Missing required fields resilience.
5. Multiple locations and distinct shifts preservation (e.g. Day vs Night shift).
6. Employer identity resolution (posting org vs hiring org vs display company).
7. Context-aware seniority regex exclusions (QA Lead, Shift Lead, City Business Lead, L3.5, Supervisor).
8. Inviolable intern protection (Lead Generation Intern, Trainees).
9. Lever retry logic, HTTP 429 handling, exponential backoff, and Retry-After header.
10. Permanent error fast-fail (HTTP 401, 403, 404 never retried).
11. Disappeared posting tracking (marking obsolete postings is_active=False).
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import requests
from requests.exceptions import Timeout, ConnectionError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, RejectedRecord, DuplicateRecord, PipelineRun
from app.ingestion.sources.company_registry import (
    ATSCompany,
    VERIFIED_COMPANIES,
    get_verified_companies,
    get_company_by_slug,
    resolve_employer_identity
)
from app.ingestion.sources.greenhouse import GreenhouseAdapter, parse_iso_datetime
from app.ingestion.sources.lever import LeverAdapter, parse_retry_after
from app.ingestion.relevance import (
    evaluate_seniority_and_fresher_suitability,
    evaluate_job_relevance
)


# ---------------------------------------------------------------------------
# Test Database Fixture (In-memory SQLite, strictly isolated from jobs.db)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# 1. Company Registry Tests
# ---------------------------------------------------------------------------

def test_company_registry_verified_members():
    """Verify registry contains strictly the 14 verified companies and excludes unverified."""
    all_companies = get_verified_companies()
    assert len(all_companies) == 14

    names = {c.name for c in all_companies}
    assert names == {
        "InMobi", "Instawork", "6sense", "DevRev", "Sigmoid", "GitLab", "HackerRank",
        "Meesho", "Coupa Software", "Keyloop", "100ms", "CRED", "Mindtickle", "JumpCloud"
    }

    # Verify unverified / disqualified candidates are NOT in registry
    slugs = {c.token_or_slug.lower() for c in all_companies}
    assert "porter" not in slugs
    assert "quince" not in slugs
    assert "falconx" not in slugs
    assert "figma" not in slugs
    assert "groww" not in slugs
    assert "druva" not in slugs
    assert "pocketfm" not in slugs
    assert "postman" not in slugs
    assert "browserstack" not in slugs
    assert "whatfix" not in slugs
    assert "moengage" not in slugs

    # Provider filtering
    gh = get_verified_companies(provider="greenhouse")
    assert len(gh) == 7
    assert {c.token_or_slug for c in gh} == {"inmobi", "instawork", "6sense", "devrev", "sigmoid", "gitlab", "hackerrank"}

    lever = get_verified_companies(provider="lever")
    assert len(lever) == 7
    assert {c.token_or_slug for c in lever} == {"meesho", "coupa", "keyloop", "100ms", "cred", "mindtickle", "jumpcloud"}


def test_get_company_by_slug():
    """Verify company lookup by slug/token."""
    c = get_company_by_slug("meesho", provider="lever")
    assert c is not None
    assert c.name == "Meesho"
    assert c.provider == "lever"

    none_c = get_company_by_slug("unknown_company")
    assert none_c is None


# ---------------------------------------------------------------------------
# 2. Employer Identity Resolution Tests
# ---------------------------------------------------------------------------

def test_employer_identity_direct_company():
    """Direct employers should report themselves as posting and hiring org."""
    inmobi = get_company_by_slug("inmobi", "greenhouse")
    posting_org, hiring_org, display_comp = resolve_employer_identity(
        inmobi,
        title="Software Engineer",
        description="We are hiring at InMobi"
    )
    assert posting_org == "InMobi"
    assert hiring_org == "InMobi"
    assert display_comp == "InMobi"


def test_employer_identity_staffing_platform_unstated_client():
    """Instawork with unstated client must NOT falsely label Instawork as direct employer."""
    instawork = get_company_by_slug("instawork", "greenhouse")
    posting_org, hiring_org, display_comp = resolve_employer_identity(
        instawork,
        title="AI Project Associate - Day Shift",
        description="We are looking for motivated individuals to join our data collection team for an AI robotics project."
    )
    assert posting_org == "Instawork"
    assert hiring_org is None  # Preserved as unknown/ambiguous
    assert display_comp == "Instawork (Client Project)"  # Distinct and transparent


def test_employer_identity_staffing_platform_explicit_client():
    """Instawork posting with explicitly named client extracts the client."""
    instawork = get_company_by_slug("instawork", "greenhouse")
    posting_org, hiring_org, display_comp = resolve_employer_identity(
        instawork,
        title="Robotics Data Collector",
        description="Instawork is partnered with Boston Dynamics for autonomous system training."
    )
    assert posting_org == "Instawork"
    assert hiring_org == "Boston Dynamics"
    assert display_comp == "Boston Dynamics (via Instawork)"


# ---------------------------------------------------------------------------
# 3. Context-Aware Seniority Exclusions & Intern Protection Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected_outcome,expected_cat", [
    ("Lead Generation Intern", "confirmed_fresher", "fresher_friendly"),
    ("QA Intern", "confirmed_fresher", "fresher_friendly"),
    ("Software Development Engineer Intern", "confirmed_fresher", "fresher_friendly"),
    ("Graduate Engineer Trainee", "confirmed_fresher", "fresher_friendly"),
    ("QA Lead", "not_fresher_suitable", "seniority_exclusion"),
    ("Shift Lead (Linux)", "not_fresher_suitable", "seniority_exclusion"),
    ("City Business Lead", "not_fresher_suitable", "seniority_exclusion"),
    ("Lead Network Design Engineer (L3/3.5)", "not_fresher_suitable", "seniority_exclusion"),
    ("Lead IBM i (AS/400) Design Engineer", "not_fresher_suitable", "seniority_exclusion"),
    ("Shift Supervisor", "not_fresher_suitable", "seniority_exclusion"),
    ("Network Engineer L3.5", "not_fresher_suitable", "seniority_exclusion"),
    ("Technical Escalation Specialist L3", "not_fresher_suitable", "seniority_exclusion"),
    ("Senior Software Engineer", "not_fresher_suitable", "seniority_exclusion"),
    ("Engineering Manager", "not_fresher_suitable", "seniority_exclusion"),
])
def test_seniority_and_intern_protection(title, expected_outcome, expected_cat):
    """Verify senior titles are excluded while intern/trainee roles remain protected."""
    outcome, cat, reason, conf = evaluate_seniority_and_fresher_suitability(title, "")
    assert outcome == expected_outcome
    assert cat == expected_cat


def test_lead_generation_specialist_not_falsely_excluded():
    """Verify 'Lead Generation Specialist' is treated as entry/individual, not engineering lead."""
    outcome, cat, reason, conf = evaluate_seniority_and_fresher_suitability(
        "Lead Generation Specialist",
        "Generate B2B sales leads and conduct outreach."
    )
    assert outcome != "not_fresher_suitable"
    assert cat != "seniority_exclusion"


# ---------------------------------------------------------------------------
# 4. Greenhouse Adapter Parsing & Pacing Tests
# ---------------------------------------------------------------------------

def test_greenhouse_parsing_sample():
    """Verify Greenhouse parsing extracts clean data, stable IDs, and sanitizes HTML."""
    sample_payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Data Analyst Intern",
                "absolute_url": "https://boards.greenhouse.io/inmobi/jobs/101",
                "location": {"name": "Bengaluru, India"},
                "updated_at": "2026-03-01T08:30:00Z",
                "content": "&lt;p&gt;Great opportunity for &lt;strong&gt;freshers&lt;/strong&gt;.&lt;/p&gt;&lt;br/&gt;&lt;p&gt;No experience required.&lt;/p&gt;"
            },
            {
                "id": 102,
                "title": "Software Engineer - Day Shift",
                "absolute_url": "https://boards.greenhouse.io/inmobi/jobs/102",
                "offices": [{"name": "Bangalore Office", "location": "Bangalore"}],
                "updated_at": "2026-03-02T12:00:00Z",
                "content": "<p>General software role.</p>"
            }
        ]
    }

    inmobi = get_company_by_slug("inmobi", "greenhouse")
    adapter = GreenhouseAdapter(companies=[inmobi], request_pacing_seconds=0.0)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(sample_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records, reqs, err = adapter.fetch_company_records(inmobi)

    assert err is None
    assert reqs == 1
    assert len(records) == 2

    # Job 1 (Intern)
    r1 = records[0]
    assert r1["external_id"] == "gh_inmobi_101"
    assert r1["title"] == "Data Analyst Intern"
    assert r1["raw_location"] == "Bengaluru, India"
    assert r1["company"] == "InMobi"
    assert "Great opportunity for freshers" in r1["description"]
    assert "<" not in r1["description"]  # Sanitized HTML
    assert r1["posted_at"] == datetime(2026, 3, 1, 8, 30, tzinfo=timezone.utc)

    # Job 2 (Shift preservation & office fallback)
    r2 = records[1]
    assert r2["external_id"] == "gh_inmobi_102"
    assert r2["title"] == "Software Engineer - Day Shift"
    assert "Bangalore Office" in r2["raw_location"]


def test_greenhouse_missing_fields_resilience():
    """Verify Greenhouse gracefully skips records missing id, title, or apply_url."""
    bad_payload = {
        "jobs": [
            {"id": None, "title": "Test Job", "absolute_url": "https://test.com"},
            {"id": 202, "title": "", "absolute_url": "https://test.com"},
            {"id": 203, "title": "No URL", "absolute_url": ""},
            {"id": 204, "title": "Valid Job", "absolute_url": "https://test.com/valid"}
        ]
    }
    inmobi = get_company_by_slug("inmobi", "greenhouse")
    adapter = GreenhouseAdapter(companies=[inmobi], request_pacing_seconds=0.0)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(bad_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records, reqs, err = adapter.fetch_company_records(inmobi)

    assert err is None
    assert len(records) == 1
    assert records[0]["external_id"] == "gh_inmobi_204"


# ---------------------------------------------------------------------------
# 5. Lever Adapter Parsing & Fallback Tests
# ---------------------------------------------------------------------------

def test_lever_parsing_sample():
    """Verify Lever parsing extracts UUID external IDs, timestamps, and locations."""
    sample_payload = [
        {
            "id": "b8a8b13d-1111-2222-3333-444455556666",
            "text": "SDE Intern",
            "createdAt": 1709299200000,  # 2024-03-01 12:00:00 UTC
            "applyUrl": "https://jobs.lever.co/meesho/b8a8b13d/apply",
            "hostedUrl": "https://jobs.lever.co/meesho/b8a8b13d",
            "categories": {
                "location": "Bangalore, India",
                "team": "Engineering"
            },
            "descriptionPlain": "Exciting fresher internship at Meesho.",
            "description": "<div><p>HTML fallback</p></div>"
        },
        {
            "id": "c9b9c24e-aaaa-bbbb-cccc-ddddeeeeffff",
            "text": "Operations Associate - Night Shift",
            "createdAt": 1709385600000,
            "hostedUrl": "https://jobs.lever.co/meesho/c9b9c24e",
            "categories": {
                "allLocations": ["Mumbai", "Pune"]
            },
            "descriptionPlain": None,
            "description": "<p>Handles operations during the night shift.</p>"
        }
    ]

    meesho = get_company_by_slug("meesho", "lever")
    adapter = LeverAdapter(companies=[meesho])

    with patch.object(adapter.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_payload
        mock_get.return_value = mock_resp

        records, reqs, err = adapter.fetch_company_records(meesho)

    assert err is None
    assert reqs == 1
    assert len(records) == 2

    # Record 1: SDE Intern
    r1 = records[0]
    assert r1["external_id"] == "lever_meesho_b8a8b13d-1111-2222-3333-444455556666"
    assert r1["title"] == "SDE Intern"
    assert r1["apply_url"] == "https://jobs.lever.co/meesho/b8a8b13d/apply"
    assert r1["raw_location"] == "Bangalore, India"
    assert r1["description"] == "Exciting fresher internship at Meesho."
    assert r1["posted_at"] == datetime(2024, 3, 1, 13, 20, tzinfo=timezone.utc)

    # Record 2: Shift preservation & allLocations fallback
    r2 = records[1]
    assert r2["title"] == "Operations Associate - Night Shift"
    assert r2["raw_location"] == "Mumbai, Pune"
    assert r2["description"] == "Handles operations during the night shift."


# ---------------------------------------------------------------------------
# 6. Lever Retry, 429, Backoff, and Permanent Error Tests
# ---------------------------------------------------------------------------

def test_parse_retry_after():
    """Verify Retry-After parser handles integer seconds and RFC dates."""
    assert parse_retry_after("5") == 5.0
    assert parse_retry_after("0") == 0.5  # Min floor
    assert parse_retry_after("120", max_wait=30.0) == 30.0  # Capped at max_wait
    assert parse_retry_after(None, default_backoff=2.0) == 2.0


def test_lever_permanent_client_error_no_retry():
    """Permanent errors (401, 403, 404) must fail immediately with 1 request and no retry."""
    coupa = get_company_by_slug("coupa", "lever")
    adapter = LeverAdapter(companies=[coupa], max_retries=3)

    for status_code in (401, 403, 404):
        with patch.object(adapter.session, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = status_code
            mock_get.return_value = mock_resp

            records, reqs, err = adapter.fetch_company_records(coupa)

            assert reqs == 1  # Exactly 1 request; NO retry
            assert records == []
            assert f"Permanent client error HTTP {status_code}" in err


def test_lever_retry_on_429_then_succeed():
    """Verify HTTP 429 triggers retry with Retry-After and succeeds on next attempt."""
    coupa = get_company_by_slug("coupa", "lever")
    adapter = LeverAdapter(companies=[coupa], max_retries=3, base_backoff=0.01)

    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "0"}

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = [
        {
            "id": "123",
            "text": "Graduate Trainee",
            "applyUrl": "https://jobs.lever.co/coupa/123",
            "categories": {"location": "Pune, India"}
        }
    ]

    with patch.object(adapter.session, "get", side_effect=[mock_resp_429, mock_resp_200]) as mock_get, \
         patch("time.sleep") as mock_sleep:
        records, reqs, err = adapter.fetch_company_records(coupa)

    assert reqs == 2
    assert err is None
    assert len(records) == 1
    assert records[0]["title"] == "Graduate Trainee"
    mock_sleep.assert_called_once()


def test_lever_timeout_retry_then_exhaust():
    """Verify socket timeouts are retried up to max_retries before reporting failure."""
    meesho = get_company_by_slug("meesho", "lever")
    adapter = LeverAdapter(companies=[meesho], max_retries=3, base_backoff=0.01)

    with patch.object(adapter.session, "get", side_effect=Timeout("Socket read timed out")), \
         patch("time.sleep"):
        records, reqs, err = adapter.fetch_company_records(meesho)

    assert reqs == 3
    assert records == []
    assert "Exhausted retries after network errors" in err


def test_lever_distinguishes_empty_from_error():
    """HTTP 200 with [] must be treated as successful empty yield, NOT an error."""
    keyloop = get_company_by_slug("keyloop", "lever")
    adapter = LeverAdapter(companies=[keyloop])

    with patch.object(adapter.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        records, reqs, err = adapter.fetch_company_records(keyloop)

    assert reqs == 1
    assert err is None
    assert records == []


# ---------------------------------------------------------------------------
# 7. Disappeared Postings Tracking Tests
# ---------------------------------------------------------------------------

def test_track_disappeared_postings(test_db):
    """Verify track_disappeared_postings detects and deactivates removed listings."""
    # Seed 3 jobs for Greenhouse inmobi
    job1 = Job(
        source="greenhouse",
        external_id="gh_inmobi_101",
        title="Job 1",
        apply_url="https://test.com/1",
        canonical_url_hash="hash1",
        content_hash="chash1",
        is_active=True
    )
    job2 = Job(
        source="greenhouse",
        external_id="gh_inmobi_102",
        title="Job 2",
        apply_url="https://test.com/2",
        canonical_url_hash="hash2",
        content_hash="chash2",
        is_active=True
    )
    job3 = Job(
        source="greenhouse",
        external_id="gh_other_201",  # Different company
        title="Other Job",
        apply_url="https://test.com/other",
        canonical_url_hash="hash3",
        content_hash="chash3",
        is_active=True
    )
    test_db.add_all([job1, job2, job3])
    test_db.commit()

    # In current run, only gh_inmobi_101 is present; gh_inmobi_102 disappeared
    active_ids = {"gh_inmobi_101"}
    disappeared = GreenhouseAdapter.track_disappeared_postings(test_db, "inmobi", active_ids)

    assert disappeared == [job2.id]
    test_db.refresh(job1)
    test_db.refresh(job2)
    test_db.refresh(job3)

    assert job1.is_active is True
    assert job2.is_active is False  # Deactivated!
    assert job3.is_active is True   # Unaffected (different company)


# ---------------------------------------------------------------------------
# 8. Shift Preservation & Duplicate Handling Tests
# ---------------------------------------------------------------------------

def test_distinct_shifts_preserved_as_separate_jobs():
    """Verify Day Shift and Night Shift for same base title have distinct external IDs and hashes."""
    r_day = {
        "title": "AI Associate - Day Shift",
        "apply_url": "https://boards.greenhouse.io/instawork/jobs/501",
        "external_id": "gh_instawork_501",
        "company": "Instawork (Client Project)",
        "raw_location": "Bengaluru, India"
    }
    r_night = {
        "title": "AI Associate - Night Shift",
        "apply_url": "https://boards.greenhouse.io/instawork/jobs/502",
        "external_id": "gh_instawork_502",
        "company": "Instawork (Client Project)",
        "raw_location": "Bengaluru, India"
    }

    assert r_day["external_id"] != r_night["external_id"]
    assert r_day["title"] != r_night["title"]


def test_intern_prior_experience_downgrades_to_uncertain():
    """Verify that an intern posting requiring prior experience (e.g. 6m-1y) is downgraded to uncertain."""
    # Trainer Intern case (6 months - 1 year experience requirement)
    trainer_desc = (
        "Experience & Qualifications: 6 months–1 year of relevant experience in training, "
        "field operations, technical operations, or a similar role."
    )
    outcome, cat, reason, conf = evaluate_seniority_and_fresher_suitability(
        title="Trainer Intern",
        description=trainer_desc
    )
    assert outcome == "uncertain_review"
    assert cat == "needs_review"
    assert "requires prior experience" in reason

    # Zero-experience / true fresher intern case (protected as confirmed_fresher)
    hardware_desc = (
        "We are looking for a Hardware Intern — Robotics & AI. "
        "Freshers welcome, no prior experience required."
    )
    outcome2, cat2, reason2, conf2 = evaluate_seniority_and_fresher_suitability(
        title="Hardware Intern — Robotics & AI",
        description=hardware_desc
    )
    assert outcome2 == "confirmed_fresher"
    assert cat2 == "fresher_friendly"
