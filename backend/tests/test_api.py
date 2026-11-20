"""Unit and Integration Tests for FastAPI Endpoints.

Tests:
1. Root service discovery (GET /)
2. Health check (GET /api/health) - 200 on healthy, 503 on database outage
3. CORS policy validation - No wildcard origin with credentials
4. Search engine - Keyword search, literal wildcard escaping (%, _), empty/whitespace query
5. Multi-select filters - Role, City, Job Type, Source (comma-separated & repeated)
6. Fresher eligibility filtering - fresher_only=true, explicit 3-state fresher_status
7. Combined multi-filter queries
8. Inactive job exclusion across jobs, filters, and analytics
9. Pagination boundaries & validation (page >= 1, limit <= 100, page=999)
10. Deterministic sorting with Job.id tie-breaking
11. Job detail retrieval & 404 handling
12. Filter facets aggregation
13. Analytics with and without Ground Truth evaluations
14. Ground-truth 3-class preservation & confusion matrix verification
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.config import settings
from app.database import Base, get_db
from app.models import Job, DuplicateRecord, PipelineRun, GroundTruthEval


@pytest.fixture(scope="function")
def test_db():
    """Create isolated in-memory SQLite database with StaticPool for cross-thread test client."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    session = TestingSession()
    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(test_db):
    """FastAPI test client fixture."""
    return TestClient(app)


def seed_sample_jobs(db):
    """Seed sample canonical jobs covering diverse roles, cities, and fresher states."""
    now = datetime.now(timezone.utc)
    jobs = [
        Job(
            source="hasjob",
            external_id="hasjob-001",
            title="Junior Backend Engineer",
            company="Tech Corp India",
            raw_location="Bengaluru, Karnataka",
            standardized_city="Bengaluru",
            description="Python backend engineer working with FastAPI and SQL databases.",
            apply_url="https://hasjob.co/tc-001",
            canonical_url_hash="hash001",
            content_hash="chash001",
            role_category="Backend",
            job_type="Full-Time",
            fresher_eligibility_status="fresher_friendly",
            is_fresher_friendly=True,
            model_confidence=0.95,
            posted_at=now,
            is_active=True
        ),
        Job(
            source="remotive",
            external_id="remotive-002",
            title="Senior Frontend Architect",
            company="Global SaaS",
            raw_location="Remote - Worldwide",
            standardized_city="Remote",
            description="Architect React and TypeScript design systems. Requires 7+ years experience.",
            apply_url="https://remotive.com/jobs/002",
            canonical_url_hash="hash002",
            content_hash="chash002",
            role_category="Frontend",
            job_type="Full-Time",
            fresher_eligibility_status="not_fresher_friendly",
            is_fresher_friendly=False,
            model_confidence=0.98,
            posted_at=now,
            is_active=True
        ),
        Job(
            source="hasjob",
            external_id="hasjob-003",
            title="Machine Learning Intern",
            company="AI Innovations",
            raw_location="Hyderabad",
            standardized_city="Hyderabad",
            description="6-month internship building PyTorch models. Open to 2026 graduates.",
            apply_url="https://hasjob.co/ai-003",
            canonical_url_hash="hash003",
            content_hash="chash003",
            role_category="AI/ML",
            job_type="Internship",
            fresher_eligibility_status="fresher_friendly",
            is_fresher_friendly=True,
            model_confidence=0.92,
            posted_at=now,
            is_active=True
        ),
        Job(
            source="hasjob",
            external_id="hasjob-004",
            title="Junior Backend Engineer",  # Duplicate title to test tie-breaking
            company="Alpha Systems",
            raw_location="Bengaluru",
            standardized_city="Bengaluru",
            description="Java backend developer with 100% test coverage.",
            apply_url="https://hasjob.co/as-004",
            canonical_url_hash="hash004",
            content_hash="chash004",
            role_category="Backend",
            job_type="Full-Time",
            fresher_eligibility_status="uncertain",
            is_fresher_friendly=None,  # Pending / Uncertain
            model_confidence=0.60,
            posted_at=now,
            is_active=True
        ),
        Job(
            source="hasjob",
            external_id="hasjob-005",
            title="Inactive Legacy Listing",
            company="Old Company",
            raw_location="Mumbai",
            standardized_city="Mumbai",
            description="Soft deleted job that should never appear in active queries.",
            apply_url="https://hasjob.co/old-005",
            canonical_url_hash="hash005",
            content_hash="chash005",
            role_category="DevOps & Cloud",
            job_type="Full-Time",
            fresher_eligibility_status="fresher_friendly",
            is_fresher_friendly=True,
            model_confidence=0.90,
            posted_at=now,
            is_active=False  # INACTIVE JOB
        )
    ]
    for j in jobs:
        db.add(j)
    db.commit()
    return jobs


# ---------------------------------------------------------------------------
# Core Service & Health Tests
# ---------------------------------------------------------------------------

def test_root_endpoint(client):
    """Verify root / returns metadata and documentation routes."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "Beep Job Aggregator API"
    assert data["status"] == "online"
    assert "/api/jobs" in data["endpoints"]["jobs"]


def test_health_check_healthy(client):
    """Verify /api/health confirms database connectivity with HTTP 200."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_health_check_database_failure(client):
    """Verify /api/health returns HTTP 503 when database connectivity fails."""
    def broken_get_db():
        class MockBrokenSession:
            def execute(self, statement):
                raise ConnectionError("Database connection lost.")
            def close(self):
                pass
        yield MockBrokenSession()

    app.dependency_overrides[get_db] = broken_get_db
    try:
        resp = client.get("/api/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert "unhealthy" in data["database"]
    finally:
        app.dependency_overrides.clear()


def test_cors_configuration():
    """Verify CORS configuration does not contain wildcard '*' and credentials are not enabled."""
    assert "*" not in settings.CORS_ORIGINS
    assert settings.CORS_ALLOW_CREDENTIALS is False
    assert "http://localhost:3000" in settings.CORS_ORIGINS


# ---------------------------------------------------------------------------
# Search & Filtering Tests
# ---------------------------------------------------------------------------

def test_jobs_list_empty(client):
    """Verify empty database returns structured empty pagination response."""
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["jobs"] == []


def test_jobs_search_query(client, test_db):
    """Verify free-text search across title, company, and description."""
    seed_sample_jobs(test_db)

    # Search by title keyword
    r1 = client.get("/api/jobs?q=backend")
    assert r1.status_code == 200
    assert r1.json()["total"] == 2

    # Search by company
    r2 = client.get("/api/jobs?q=Global")
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["jobs"][0]["company"] == "Global SaaS"

    # Search by description
    r3 = client.get("/api/jobs?q=PyTorch")
    assert r3.status_code == 200
    assert r3.json()["total"] == 1
    assert r3.json()["jobs"][0]["title"] == "Machine Learning Intern"


def test_jobs_search_literal_wildcards(client, test_db):
    """Verify searching for literal '%' or '_' does not act as wildcards."""
    seed_sample_jobs(test_db)

    # Searching for literal '%' should match only descriptions containing '%' (job 4 has "100% test coverage")
    resp_pct = client.get("/api/jobs?q=%")
    assert resp_pct.status_code == 200
    assert resp_pct.json()["total"] == 1
    assert resp_pct.json()["jobs"][0]["external_id"] == "hasjob-004"

    # Searching for '_' when no titles contain literal underscore should return 0
    resp_underscore = client.get("/api/jobs?q=_")
    assert resp_underscore.status_code == 200
    assert resp_underscore.json()["total"] == 0


def test_jobs_search_empty_and_whitespace(client, test_db):
    """Verify empty and whitespace queries return all active jobs without error."""
    seed_sample_jobs(test_db)

    resp_empty = client.get("/api/jobs?q=")
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total"] == 4  # All 4 active jobs

    resp_space = client.get("/api/jobs?q=   ")
    assert resp_space.status_code == 200
    assert resp_space.json()["total"] == 4


def test_jobs_filter_role_multi_select(client, test_db):
    """Verify multi-select role filtering via comma-separated and repeated params."""
    seed_sample_jobs(test_db)

    # Comma-separated: ?role=Backend,Frontend
    r1 = client.get("/api/jobs?role=Backend,Frontend")
    assert r1.status_code == 200
    assert r1.json()["total"] == 3  # 2 backend + 1 frontend

    # Repeated query params: ?role=Backend&role=AI/ML
    r2 = client.get("/api/jobs?role=Backend&role=AI/ML")
    assert r2.status_code == 200
    assert r2.json()["total"] == 3  # 2 backend + 1 AI/ML


def test_jobs_filter_job_type_and_source_multi_select(client, test_db):
    """Verify multi-select support for job_type and source."""
    seed_sample_jobs(test_db)

    # Job type comma-separated
    r1 = client.get("/api/jobs?job_type=Internship,Full-Time")
    assert r1.status_code == 200
    assert r1.json()["total"] == 4

    # Source comma-separated
    r2 = client.get("/api/jobs?source=hasjob,remotive")
    assert r2.status_code == 200
    assert r2.json()["total"] == 4

    # Source single
    r3 = client.get("/api/jobs?source=remotive")
    assert r3.status_code == 200
    assert r3.json()["total"] == 1


def test_jobs_filter_fresher_only(client, test_db):
    """Verify fresher_only=true returns strictly is_fresher_friendly == True positions."""
    seed_sample_jobs(test_db)

    resp = client.get("/api/jobs?fresher_only=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2  # job 1 and job 3 (job 5 is inactive)
    for job in data["jobs"]:
        assert job["is_fresher_friendly"] is True


def test_jobs_filter_explicit_fresher_status(client, test_db):
    """Verify explicit 3-state filtering via ?fresher_status=."""
    seed_sample_jobs(test_db)

    # Filter for non-fresher positions
    r_non = client.get("/api/jobs?fresher_status=not_fresher_friendly")
    assert r_non.status_code == 200
    assert r_non.json()["total"] == 1
    assert r_non.json()["jobs"][0]["external_id"] == "remotive-002"

    # Filter for uncertain positions (strictly returns model-evaluated uncertain cases)
    r_unc = client.get("/api/jobs?fresher_status=uncertain")
    assert r_unc.status_code == 200
    assert r_unc.json()["total"] == 1
    assert r_unc.json()["jobs"][0]["external_id"] == "hasjob-004"

    # Filter for unstated / pending positions (none seeded in seed_sample_jobs)
    r_pen = client.get("/api/jobs?fresher_status=pending")
    assert r_pen.status_code == 200
    assert r_pen.json()["total"] == 0


def test_24_pending_jobs_return_24_results(client, test_db):
    """Verify that querying for pending status returns all 24 unclassified canonical jobs."""
    now = datetime.now(timezone.utc)
    for i in range(1, 25):
        test_db.add(Job(
            source="hasjob" if i % 2 == 0 else "remotive",
            external_id=f"pending-job-{i}",
            title=f"Software Engineer Track {i}",
            company=f"Tech Venture {i}",
            raw_location="Bengaluru, Karnataka",
            standardized_city="Bengaluru",
            description="Engineering position pending AI verification.",
            apply_url=f"https://example.com/apply/{i}",
            canonical_url_hash=f"hash_pen_{i}",
            content_hash=f"chash_pen_{i}",
            role_category=None,
            job_type="Full-Time",
            fresher_eligibility_status=None,  # Genuinely unclassified / pending
            is_fresher_friendly=None,
            posted_at=now,
            is_active=True
        ))
    test_db.commit()

    # Query with ?fresher_status=pending
    resp_pending = client.get("/api/jobs?fresher_status=pending&limit=50")
    assert resp_pending.status_code == 200
    data = resp_pending.json()
    assert data["total"] == 24
    assert len(data["jobs"]) == 24
    for j in data["jobs"]:
        assert j["fresher_eligibility_status"] is None
        assert j["is_fresher_friendly"] is None

    # Query with ?fresher_status=unstated
    resp_unstated = client.get("/api/jobs?fresher_status=unstated&limit=50")
    assert resp_unstated.status_code == 200
    assert resp_unstated.json()["total"] == 24

    # Query with ?fresher_status=fresher_friendly should return 0
    resp_ff = client.get("/api/jobs?fresher_status=fresher_friendly")
    assert resp_ff.status_code == 200
    assert resp_ff.json()["total"] == 0

    # Query with ?fresher_status=not_fresher_friendly should return 0
    resp_nff = client.get("/api/jobs?fresher_status=not_fresher_friendly")
    assert resp_nff.status_code == 200
    assert resp_nff.json()["total"] == 0

    # Query with ?fresher_status=uncertain should return 0 (no jobs evaluated as uncertain)
    resp_unc = client.get("/api/jobs?fresher_status=uncertain")
    assert resp_unc.status_code == 200
    assert resp_unc.json()["total"] == 0

    # Query with all listings (no filter) returns all 24
    resp_all = client.get("/api/jobs?limit=50")
    assert resp_all.status_code == 200
    assert resp_all.json()["total"] == 24


def test_explicitly_uncertain_distinguishable_from_pending(client, test_db):
    """Verify that explicitly uncertain jobs are strictly distinguishable from unclassified pending jobs."""
    now = datetime.now(timezone.utc)
    # 1. Two explicitly uncertain jobs (model ran, returned uncertain)
    for i in (1, 2):
        test_db.add(Job(
            source="hasjob",
            external_id=f"uncertain-job-{i}",
            title=f"Ambiguous Role {i}",
            company="Alpha Corp",
            raw_location="Bengaluru",
            apply_url=f"https://example.com/u/{i}",
            canonical_url_hash=f"u_hash_{i}",
            content_hash=f"u_chash_{i}",
            fresher_eligibility_status="uncertain",
            is_fresher_friendly=None,
            model_confidence=0.55,
            posted_at=now,
            is_active=True
        ))

    # 2. Three genuinely unclassified pending jobs (model has not run)
    for i in (1, 2, 3):
        test_db.add(Job(
            source="remotive",
            external_id=f"pending-job-{i}",
            title=f"Pending Role {i}",
            company="Beta Corp",
            raw_location="Remote",
            apply_url=f"https://example.com/p/{i}",
            canonical_url_hash=f"p_hash_{i}",
            content_hash=f"p_chash_{i}",
            fresher_eligibility_status=None,  # Pending
            is_fresher_friendly=None,
            model_confidence=None,
            posted_at=now,
            is_active=True
        ))

    # 3. Two confirmed fresher-friendly jobs
    for i in (1, 2):
        test_db.add(Job(
            source="hasjob",
            external_id=f"fresher-job-{i}",
            title=f"Fresher Graduate Role {i}",
            company="Gamma Corp",
            raw_location="Hyderabad",
            apply_url=f"https://example.com/f/{i}",
            canonical_url_hash=f"f_hash_{i}",
            content_hash=f"f_chash_{i}",
            fresher_eligibility_status="fresher_friendly",
            is_fresher_friendly=True,
            model_confidence=0.95,
            posted_at=now,
            is_active=True
        ))

    # 4. One confirmed experienced job
    test_db.add(Job(
        source="hasjob",
        external_id="experienced-job-1",
        title="Principal Lead Engineer",
        company="Delta Corp",
        raw_location="Pune",
        apply_url="https://example.com/e/1",
        canonical_url_hash="e_hash_1",
        content_hash="e_chash_1",
        fresher_eligibility_status="not_fresher_friendly",
        is_fresher_friendly=False,
        model_confidence=0.99,
        posted_at=now,
        is_active=True
    ))
    test_db.commit()

    # Total jobs = 2 + 3 + 2 + 1 = 8
    assert client.get("/api/jobs?limit=50").json()["total"] == 8

    # Pending query must return exactly 3 jobs (no uncertain, no confirmed)
    res_pending = client.get("/api/jobs?fresher_status=pending&limit=50")
    assert res_pending.status_code == 200
    assert res_pending.json()["total"] == 3
    for j in res_pending.json()["jobs"]:
        assert j["fresher_eligibility_status"] is None
        assert "pending-job" in j["external_id"]

    # Uncertain query must return exactly 2 jobs (no pending, no confirmed)
    res_uncertain = client.get("/api/jobs?fresher_status=uncertain&limit=50")
    assert res_uncertain.status_code == 200
    assert res_uncertain.json()["total"] == 2
    for j in res_uncertain.json()["jobs"]:
        assert j["fresher_eligibility_status"] == "uncertain"
        assert "uncertain-job" in j["external_id"]

    # Fresher friendly query must return exactly 2 jobs
    res_fresher = client.get("/api/jobs?fresher_status=fresher_friendly&limit=50")
    assert res_fresher.status_code == 200
    assert res_fresher.json()["total"] == 2
    for j in res_fresher.json()["jobs"]:
        assert j["fresher_eligibility_status"] == "fresher_friendly"
        assert j["is_fresher_friendly"] is True

    # Experienced query must return exactly 1 job
    res_exp = client.get("/api/jobs?fresher_status=not_fresher_friendly&limit=50")
    assert res_exp.status_code == 200
    assert res_exp.json()["total"] == 1
    assert res_exp.json()["jobs"][0]["external_id"] == "experienced-job-1"

    # Confirmed fresher-only toggle must match fresher_friendly
    res_fo = client.get("/api/jobs?fresher_only=true&limit=50")
    assert res_fo.status_code == 200
    assert res_fo.json()["total"] == 2


def test_combined_search_and_fresher_status(client, test_db):
    """Verify combining search queries with fresher status filters."""
    now = datetime.now(timezone.utc)
    test_db.add(Job(
        source="hasjob",
        external_id="py-pending-1",
        title="Python Data Analyst",
        company="PyVenture",
        raw_location="Bengaluru",
        apply_url="https://example.com/pyd/1",
        canonical_url_hash="pyd_h1",
        content_hash="pyd_c1",
        fresher_eligibility_status=None,
        is_fresher_friendly=None,
        posted_at=now,
        is_active=True
    ))
    test_db.add(Job(
        source="hasjob",
        external_id="py-fresher-1",
        title="Python Junior Developer",
        company="PyVenture",
        raw_location="Bengaluru",
        apply_url="https://example.com/pyj/1",
        canonical_url_hash="pyj_h1",
        content_hash="pyj_c1",
        fresher_eligibility_status="fresher_friendly",
        is_fresher_friendly=True,
        posted_at=now,
        is_active=True
    ))
    test_db.add(Job(
        source="hasjob",
        external_id="js-pending-1",
        title="JavaScript Developer",
        company="JSCorp",
        raw_location="Bengaluru",
        apply_url="https://example.com/js/1",
        canonical_url_hash="js_h1",
        content_hash="js_c1",
        fresher_eligibility_status=None,
        is_fresher_friendly=None,
        posted_at=now,
        is_active=True
    ))
    test_db.commit()

    # Search 'Python' with fresher_status=pending -> returns 1
    r1 = client.get("/api/jobs?q=Python&fresher_status=pending")
    assert r1.status_code == 200
    assert r1.json()["total"] == 1
    assert r1.json()["jobs"][0]["external_id"] == "py-pending-1"

    # Search 'Python' with fresher_status=fresher_friendly -> returns 1
    r2 = client.get("/api/jobs?q=Python&fresher_status=fresher_friendly")
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["jobs"][0]["external_id"] == "py-fresher-1"

    # Search 'Python' with fresher_status=uncertain -> returns 0
    r3 = client.get("/api/jobs?q=Python&fresher_status=uncertain")
    assert r3.status_code == 200
    assert r3.json()["total"] == 0


def test_jobs_combined_multi_filters(client, test_db):
    """Verify search combined with role, city, job_type, and fresher filters simultaneously."""
    seed_sample_jobs(test_db)

    resp = client.get("/api/jobs?q=Python&role=Backend&city=Bengaluru&job_type=Full-Time&fresher_only=true&source=hasjob")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["jobs"][0]["external_id"] == "hasjob-001"


def test_jobs_inactive_excluded_consistently(client, test_db):
    """Verify soft-deleted inactive jobs (is_active=False) are never returned in listings or facets."""
    seed_sample_jobs(test_db)

    # 1. Not in job list
    r_list = client.get("/api/jobs")
    assert r_list.status_code == 200
    assert r_list.json()["total"] == 4  # Total is 4, not 5
    for job in r_list.json()["jobs"]:
        assert job["is_active"] is True
        assert job["external_id"] != "hasjob-005"

    # 2. Not in filters facets
    r_filters = client.get("/api/jobs/filters")
    assert r_filters.status_code == 200
    assert r_filters.json()["total_jobs"] == 4
    # Mumbai was only on the inactive job
    city_names = [c["name"] for c in r_filters.json()["cities"]]
    assert "Mumbai" not in city_names


def test_jobs_pagination_boundaries_and_validation(client, test_db):
    """Verify validation on page and limit parameters, plus offset boundary handling."""
    seed_sample_jobs(test_db)

    # page < 1 should return 422
    assert client.get("/api/jobs?page=0").status_code == 422
    assert client.get("/api/jobs?page=-1").status_code == 422

    # limit > 100 should return 422
    assert client.get("/api/jobs?limit=101").status_code == 422

    # page beyond available records should return empty list
    resp_p999 = client.get("/api/jobs?page=999&limit=10")
    assert resp_p999.status_code == 200
    assert resp_p999.json()["jobs"] == []
    assert resp_p999.json()["total"] == 4


def test_jobs_deterministic_sorting(client, test_db):
    """Verify sorting includes Job.id tie-breaker for deterministic output."""
    seed_sample_jobs(test_db)

    # Sort by title: jobs 1 and 4 have the same title "Junior Backend Engineer"
    resp_title = client.get("/api/jobs?sort_by=title")
    assert resp_title.status_code == 200
    jobs = resp_title.json()["jobs"]
    # Verify titles are ascending
    titles = [j["title"] for j in jobs]
    assert titles == sorted(titles)
    # Among the two identical titles, the lower ID (1) must appear before higher ID (4)
    same_title_ids = [j["id"] for j in jobs if j["title"] == "Junior Backend Engineer"]
    assert same_title_ids == sorted(same_title_ids)


def test_get_job_by_id_success_and_not_found(client, test_db):
    """Verify single job retrieval and 404 behavior."""
    jobs = seed_sample_jobs(test_db)
    target_id = jobs[0].id

    # Success
    r1 = client.get(f"/api/jobs/{target_id}")
    assert r1.status_code == 200
    assert r1.json()["id"] == target_id

    # Inactive job should return 404
    inactive_id = jobs[4].id
    r_inactive = client.get(f"/api/jobs/{inactive_id}")
    assert r_inactive.status_code == 404

    # Non-existent ID returns 404
    r_none = client.get("/api/jobs/999999")
    assert r_none.status_code == 404


# ---------------------------------------------------------------------------
# Analytics & Ground Truth Tests
# ---------------------------------------------------------------------------

def test_analytics_summary_empty_ground_truth(client, test_db):
    """Verify /api/analytics returns accurate structure when no ground truth evals exist."""
    seed_sample_jobs(test_db)

    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()

    # Total canonical must strictly reflect active jobs
    assert data["dataset_metrics"]["total_canonical_jobs"] == 4
    # Fresher breakdown must strictly sum to active jobs: 2 fresher + 1 not fresher + 1 pending = 4
    fb = data["dataset_metrics"]["fresher_breakdown"]
    assert fb["fresher_friendly"] == 2
    assert fb["not_fresher_friendly"] == 1
    assert fb["pending_or_uncertain"] == 1
    assert data["ground_truth_accuracy"] is None


def test_analytics_summary_with_three_class_ground_truth(client, test_db):
    """Verify /api/analytics faithfully calculates 3-class matrix and excludes uncertain cases from binary metrics."""
    jobs = seed_sample_jobs(test_db)

    # Seed 3 ground-truth evaluation records covering all 3 states:
    # Job 1: Model says fresher_friendly. Ground truth says fresher_friendly -> TP
    # Job 2: Model says not_fresher_friendly. Ground truth says not_fresher_friendly -> TN
    # Job 4: Model says uncertain. Ground truth says uncertain -> Excluded from binary metrics
    gt_evals = [
        GroundTruthEval(
            job_id=jobs[0].id,
            human_role_category="Backend",
            human_city="Bengaluru",
            human_fresher_status="fresher_friendly",
            role_match=True,
            city_match=True,
            fresher_match=True,
            notes="Valid fresher entry-level role."
        ),
        GroundTruthEval(
            job_id=jobs[1].id,
            human_role_category="Frontend",
            human_city="Remote",
            human_fresher_status="not_fresher_friendly",
            role_match=True,
            city_match=True,
            fresher_match=True,
            notes="Requires 7+ years."
        ),
        GroundTruthEval(
            job_id=jobs[3].id,
            human_role_category="Backend",
            human_city="Bengaluru",
            human_fresher_status="uncertain",
            role_match=True,
            city_match=True,
            fresher_match=True,
            notes="Unstated experience requirement."
        )
    ]
    for gte in gt_evals:
        test_db.add(gte)
    test_db.commit()

    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()

    gt_report = data["ground_truth_accuracy"]
    assert gt_report is not None

    # Total sample evaluated: 3
    assert gt_report["sample_size"] == 3
    # Exactly 1 uncertain record excluded:
    assert gt_report["excluded_uncertain_ground_truth_count"] == 1
    assert gt_report["excluded_uncertain_percentage"] == 33.33
    # Decisive sample size: 3 - 1 = 2
    assert gt_report["decisive_sample_size"] == 2

    # Binary metrics: 1 TP, 0 FP, 0 FN, 1 TN -> Precision: 1.0, Recall: 1.0, F1: 1.0
    bm = gt_report["binary_metrics_on_decisive_cases"]
    assert bm["true_positives"] == 1
    assert bm["false_positives"] == 0
    assert bm["false_negatives"] == 0
    assert bm["true_negatives"] == 1
    assert bm["precision"] == 1.0
    assert bm["recall"] == 1.0
    assert bm["f1_score"] == 1.0

    # 3x3 Confusion Matrix preserved
    matrix = gt_report["three_class_confusion_matrix"]
    assert matrix["uncertain"]["uncertain"] == 1
    assert matrix["fresher_friendly"]["fresher_friendly"] == 1
    assert matrix["not_fresher_friendly"]["not_fresher_friendly"] == 1


def test_analytics_cost_per_1000_unclassified_vs_classified(client, test_db):
    """Verify nominal cost per 1k posts returns None (not $0) when unclassified, and calculates properly when token logs exist."""
    from app.models import LLMAuditLog

    # 1. When no LLM audit logs exist (unclassified)
    r1 = client.get("/api/analytics")
    assert r1.status_code == 200
    cost_data1 = r1.json()["ai_processing_cost"]
    assert cost_data1["total_batches"] == 0
    assert cost_data1["total_jobs_processed"] == 0
    assert cost_data1["total_tokens"] == 0
    assert cost_data1["total_actual_cost_usd"] == 0.0
    assert cost_data1["nominal_cost_per_1000_posts_usd"] is None  # Must NOT be 0.0!

    # 2. When LLM audit logs exist with tokens
    # E.g. batch of 10 jobs, 10,000 prompt tokens, 2,000 completion tokens
    # nominal cost = (10,000 / 1M * 0.30) + (2,000 / 1M * 2.50) = 0.003 + 0.005 = 0.008 USD
    # per 1,000 posts = (0.008 / 10) * 1000 = 0.8 USD
    audit_log = LLMAuditLog(
        batch_id="batch-test-1",
        jobs_count=10,
        status="success",
        prompt_tokens=10000,
        completion_tokens=2000,
        total_tokens=12000,
        model_name="gemini-2.5-flash",
        latency_seconds=1.2,
        pricing_tier="free",
        input_price_per_1m=0.30,
        output_price_per_1m=2.50,
        actual_cost_usd=0.0,
        nominal_cost_usd=0.008
    )
    test_db.add(audit_log)
    test_db.commit()

    r2 = client.get("/api/analytics")
    assert r2.status_code == 200
    cost_data2 = r2.json()["ai_processing_cost"]
    assert cost_data2["total_batches"] == 1
    assert cost_data2["total_jobs_processed"] == 10
    assert cost_data2["total_tokens"] == 12000
    assert cost_data2["total_actual_cost_usd"] == 0.0
    assert cost_data2["total_nominal_cost_usd"] == 0.008
    assert cost_data2["nominal_cost_per_1000_posts_usd"] == 0.8
