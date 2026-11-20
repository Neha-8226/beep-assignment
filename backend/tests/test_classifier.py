"""Comprehensive Unit Tests for Classifier, Guardrails, Cost Telemetry, and Evaluator.

Tests:
1. Pydantic schema validation (enums, confidence bounds).
2. Consistent description truncation at exactly 250 characters.
3. Actual vs. nominal cost calculation logic.
4. Batch processing with duplicate ID rejection guardrail.
5. Batch processing with foreign ID rejection guardrail.
6. Batch processing with omitted item error logging.
7. Location preservation guarantee (raw_location remains unchanged).
8. Transient vs. permanent error classification and backoff.
9. Ground-truth evaluation calculation (3-class accuracy and filtered binary metrics).
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError

from app.database import Base
from app.models import Job, LLMAuditLog, GroundTruthEval
from app.ai.schemas import ClassifiedJobItem, BatchClassificationResponse
from app.ai.prompts import (
    format_batch_prompt,
    extract_relevant_description,
    clean_html
)
from app.ai.cost_tracker import calculate_batch_costs, get_cost_summary
from app.ai.classifier import (
    process_classification_batch,
    PermanentAPIError,
    TransientAPIError,
    execute_gemini_call_with_retry
)
from app.ai.evaluator import evaluate_classifications


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
# 1. Schema Validation Tests
# ---------------------------------------------------------------------------

def test_classified_job_item_valid():
    """Verify valid classification item passes validation."""
    item = ClassifiedJobItem(
        job_id=1,
        role_category="Backend",
        standardized_city="Bengaluru",
        job_type="Full-Time",
        fresher_eligibility="fresher_friendly",
        confidence_score=0.95,
        reasoning="Junior Python backend developer role specifying freshers welcome."
    )
    assert item.job_id == 1
    assert item.role_category == "Backend"
    assert item.standardized_city == "Bengaluru"
    assert item.confidence_score == 0.95


def test_classified_job_item_invalid_confidence():
    """Verify confidence score outside [0.0, 1.0] raises ValidationError."""
    with pytest.raises(ValidationError):
        ClassifiedJobItem(
            job_id=1,
            role_category="Backend",
            standardized_city="Bengaluru",
            job_type="Full-Time",
            fresher_eligibility="fresher_friendly",
            confidence_score=1.5,  # Invalid
            reasoning="Valid reasoning"
        )


def test_classified_job_item_invalid_role_enum():
    """Verify unlisted role category raises ValidationError."""
    with pytest.raises(ValidationError):
        ClassifiedJobItem(
            job_id=1,
            role_category="Astronaut",  # Invalid
            standardized_city="Bengaluru",
            job_type="Full-Time",
            fresher_eligibility="fresher_friendly",
            confidence_score=0.9,
            reasoning="Valid reasoning"
        )


# ---------------------------------------------------------------------------
# 2. Description Truncation Test
# ---------------------------------------------------------------------------

def test_format_batch_prompt_truncation():
    """Verify prompt builder consistently truncates descriptions at configured limit."""
    long_desc = "X" * 500
    jobs = [
        {
            "id": 101,
            "title": "Backend Intern",
            "company": "Tech Corp",
            "raw_location": "Bengaluru",
            "description": long_desc
        }
    ]
    prompt = format_batch_prompt(jobs, max_desc_chars=250)

    # Prompt must contain 250 'X' characters followed by '...'
    expected_snippet = ("X" * 250) + "..."
    assert expected_snippet in prompt
    assert ("X" * 251) not in prompt


# ---------------------------------------------------------------------------
# 3. Cost Calculation Tests
# ---------------------------------------------------------------------------

def test_calculate_batch_costs_free_vs_paid():
    """Verify free tier reports $0.00 actual cost while computing nominal baseline."""
    # Free tier test
    free_costs = calculate_batch_costs(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        pricing_tier="free",
        input_price_per_1m=0.30,
        output_price_per_1m=2.50
    )
    assert free_costs["actual_cost_usd"] == 0.0
    assert free_costs["nominal_cost_usd"] == 2.80  # 0.30 + 2.50

    # Paid tier test
    paid_costs = calculate_batch_costs(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        pricing_tier="paid",
        input_price_per_1m=0.30,
        output_price_per_1m=2.50
    )
    assert paid_costs["actual_cost_usd"] == 2.80
    assert paid_costs["nominal_cost_usd"] == 2.80


# ---------------------------------------------------------------------------
# 4. Guardrail: Duplicate Response ID Rejection
# ---------------------------------------------------------------------------

def test_batch_processor_rejects_duplicate_ids(db_session):
    """Verify that if LLM returns a duplicated job_id, ALL occurrences are rejected."""
    job1 = Job(
        source="hasjob",
        external_id="hj_1",
        title="Python Dev",
        apply_url="https://hasjob.co/1",
        canonical_url_hash="h1",
        content_hash="c1",
        raw_location="Bengaluru"
    )
    job2 = Job(
        source="hasjob",
        external_id="hj_2",
        title="React Dev",
        apply_url="https://hasjob.co/2",
        canonical_url_hash="h2",
        content_hash="c2",
        raw_location="Pune"
    )
    db_session.add_all([job1, job2])
    db_session.commit()

    # Mock response returning job1 twice (duplicate ID!)
    mock_response_data = {
        "classifications": [
            {
                "job_id": job1.id,
                "role_category": "Backend",
                "standardized_city": "Bengaluru",
                "job_type": "Full-Time",
                "fresher_eligibility": "fresher_friendly",
                "confidence_score": 0.9,
                "reasoning": "Python role"
            },
            {
                "job_id": job1.id,  # Duplicate!
                "role_category": "Frontend",
                "standardized_city": "Bengaluru",
                "job_type": "Full-Time",
                "fresher_eligibility": "fresher_friendly",
                "confidence_score": 0.85,
                "reasoning": "Duplicate entry"
            },
            {
                "job_id": job2.id,  # Valid unique entry
                "role_category": "Frontend",
                "standardized_city": "Pune",
                "job_type": "Full-Time",
                "fresher_eligibility": "fresher_friendly",
                "confidence_score": 0.95,
                "reasoning": "React role"
            }
        ]
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_response_data)
    mock_resp.usage_metadata.prompt_token_count = 500
    mock_resp.usage_metadata.candidates_token_count = 150
    mock_client.models.generate_content.return_value = mock_resp

    res = process_classification_batch(db=db_session, jobs=[job1, job2], client=mock_client)

    # Job 1 must have been rejected because its ID was duplicated
    db_session.refresh(job1)
    db_session.refresh(job2)

    assert job1.role_category is None  # Left pending!
    assert "duplicate job_id" in job1.classification_error
    assert res["duplicate_ids"] == [job1.id]

    # Job 2 should be successfully classified
    assert job2.role_category == "Frontend"
    assert job2.standardized_city == "Pune"
    assert job2.classification_error is None


# ---------------------------------------------------------------------------
# 5. Guardrail: Foreign ID Rejection and Location Preservation
# ---------------------------------------------------------------------------

def test_batch_processor_foreign_id_and_location_preservation(db_session):
    """Verify foreign IDs are ignored and raw_location is permanently preserved."""
    orig_raw_loc = "Bengaluru, Karnataka (near Electronic City)"
    job = Job(
        source="hasjob",
        external_id="hj_10",
        title="ML Engineer",
        apply_url="https://hasjob.co/10",
        canonical_url_hash="h10",
        content_hash="c10",
        raw_location=orig_raw_loc
    )
    db_session.add(job)
    db_session.commit()

    mock_response_data = {
        "classifications": [
            {
                "job_id": job.id,
                "role_category": "AI / ML",
                "standardized_city": "Bengaluru",
                "job_type": "Full-Time",
                "fresher_eligibility": "not_fresher_friendly",
                "confidence_score": 0.92,
                "reasoning": "ML Engineer role"
            },
            {
                "job_id": 999999,  # Foreign ID not in current batch!
                "role_category": "Backend",
                "standardized_city": "Hyderabad",
                "job_type": "Full-Time",
                "fresher_eligibility": "fresher_friendly",
                "confidence_score": 0.5,
                "reasoning": "Foreign item"
            }
        ]
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(mock_response_data)
    mock_resp.usage_metadata.prompt_token_count = 300
    mock_resp.usage_metadata.candidates_token_count = 80
    mock_client.models.generate_content.return_value = mock_resp

    res = process_classification_batch(db=db_session, jobs=[job], client=mock_client)

    db_session.refresh(job)
    # Check that job was updated
    assert job.role_category == "AI / ML"
    assert job.standardized_city == "Bengaluru"
    # CRITICAL: raw_location must NOT be overwritten
    assert job.raw_location == orig_raw_loc
    assert job.fresher_eligibility_status == "not_fresher_friendly"
    assert job.is_fresher_friendly is False

    # Foreign ID was not inserted or updated
    assert db_session.query(Job).filter(Job.id == 999999).first() is None


# ---------------------------------------------------------------------------
# 6. Error Handling: Transient vs. Permanent Error Classification
# ---------------------------------------------------------------------------

def test_error_handling_permanent_abort():
    """Verify permanent 401 Unauthorized aborts immediately without retry."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("401 Unauthorized API key invalid")

    with pytest.raises(PermanentAPIError):
        execute_gemini_call_with_retry("test prompt", mock_client, "gemini-3.8-flash", max_retries=3)


def test_error_handling_permanent_abort_404_not_found():
    """Verify permanent 404 Model Not Found aborts immediately without retry."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("404 NOT_FOUND. Model models/gemini-2.5-flash is no longer available to new users.")

    with pytest.raises(PermanentAPIError):
        execute_gemini_call_with_retry("test prompt", mock_client, "gemini-2.5-flash", max_retries=3)
    assert mock_client.models.generate_content.call_count == 1


def test_error_handling_transient_retry():
    """Verify transient 429 triggers retry logic."""
    mock_client = MagicMock()
    # First 2 calls fail with 429, third succeeds
    mock_success = MagicMock()
    mock_success.text = '{"classifications": []}'
    mock_success.usage_metadata.prompt_token_count = 10
    mock_success.usage_metadata.candidates_token_count = 5

    mock_client.models.generate_content.side_effect = [
        Exception("429 ResourceExhausted"),
        mock_success
    ]

    with patch("time.sleep"):  # Mock sleep so test runs instantly
        text, p, c, lat = execute_gemini_call_with_retry(
            "test prompt", mock_client, "gemini-2.5-flash", max_retries=2, base_delay=0.01
        )
        assert text == '{"classifications": []}'
        assert mock_client.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# 7. Evaluator Calculations (3-Class and Filtered Binary)
# ---------------------------------------------------------------------------

def test_evaluator_metrics_with_excluded_uncertain():
    """Verify evaluator computes 3-class matrix and excludes uncertain cases from binary metrics."""
    ground_truth = [
        {"job_id": 1, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "fresher_friendly"},
        {"job_id": 2, "human_role": "Frontend", "human_city": "Pune", "human_fresher_status": "not_fresher_friendly"},
        {"job_id": 3, "human_role": "AI / ML", "human_city": "Remote", "human_fresher_status": "uncertain"},  # Uncertain!
        {"job_id": 4, "human_role": "QA & Testing", "human_city": "Chennai", "human_fresher_status": "fresher_friendly"},
    ]

    predictions = [
        {"job_id": 1, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},   # TP
        {"job_id": 2, "model_role": "Frontend", "model_city": "Pune", "model_fresher_status": "not_fresher_friendly"},  # TN
        {"job_id": 3, "model_role": "AI / ML", "model_city": "Remote", "model_fresher_status": "uncertain"},            # Excluded from binary!
        {"job_id": 4, "model_role": "QA & Testing", "model_city": "Chennai", "model_fresher_status": "uncertain"},       # FN
    ]

    metrics = evaluate_classifications(ground_truth, predictions)

    assert metrics["sample_size"] == 4
    assert metrics["decisive_sample_size"] == 3
    assert metrics["excluded_uncertain_ground_truth_count"] == 1
    assert metrics["excluded_uncertain_percentage"] == 25.0

    assert metrics["role_classification_accuracy_pct"] == 100.0
    assert metrics["city_standardization_accuracy_pct"] == 100.0
    assert metrics["fresher_three_class_accuracy_pct"] == 75.0  # 3 of 4 match

    # Binary metrics check:
    # Decisive ground-truth cases: Job 1 (fresher_friendly), Job 2 (not_fresher_friendly), Job 4 (fresher_friendly)
    # Model predictions:
    # Job 1: fresher_friendly -> TP
    # Job 2: not_fresher_friendly -> TN
    # Job 4: uncertain -> FN (Human said fresher_friendly, model did not predict fresher_friendly)
    b = metrics["binary_metrics_on_decisive_cases"]
    assert b["true_positives"] == 1
    assert b["false_positives"] == 0
    assert b["false_negatives"] == 1
    assert b["true_negatives"] == 1

    # Precision = TP / (TP + FP) = 1 / (1 + 0) = 1.0
    assert b["precision"] == 1.0
    # Recall = TP / (TP + FN) = 1 / (1 + 1) = 0.5
    assert b["recall"] == 0.5
    # F1 = 2 * (1.0 * 0.5) / (1.0 + 0.5) = 1.0 / 1.5 = 0.6667
    assert b["f1_score"] == 0.6667

    # Enhanced Metrics: FPR, FNR, Specificity
    # FPR = FP / (FP + TN) = 0 / (0 + 1) = 0.0
    assert b["false_positive_rate"] == 0.0
    # FNR = FN / (FN + TP) = 1 / (1 + 1) = 0.5
    assert b["false_negative_rate"] == 0.5
    # Specificity = TN / (TN + FP) = 1 / (1 + 0) = 1.0
    assert b["specificity"] == 1.0


# ---------------------------------------------------------------------------
# 8. Description Cleaning & Relevant Section Extraction Tests
# ---------------------------------------------------------------------------

def test_extract_relevant_description_with_headers():
    """Verify that section headers (Requirements/Qualifications) are prioritized for long descriptions."""
    long_overview = "Overview: We are a leading platform building tools. " * 30  # ~1500 chars
    qual_section = "\nRequirements:\n- Must have 2+ years of Python.\n- Experience with FastAPI and SQL.\n- Bachelor's degree."
    full_desc = long_overview + qual_section + ("\nPerks and benefits: Health insurance." * 20)

    extracted = extract_relevant_description(full_desc, max_chars=1000)

    # Must preserve initial overview snippet
    assert "Overview: We are a leading platform" in extracted
    # Must preserve the Requirements section
    assert "[Key Requirements & Qualifications]:" in extracted
    assert "Requirements:" in extracted
    assert "2+ years of Python" in extracted
    assert len(extracted) <= 1000


def test_extract_relevant_description_html_cleaning():
    """Verify HTML tags and entities are stripped cleanly."""
    html_desc = "<p>Join <strong>TechCorp</strong> as a <em>Backend Intern</em>.</p><ul><li>Python &amp; Django</li><li>SQL &lt;Pro&gt;</li></ul>"
    cleaned = clean_html(html_desc)
    assert "<p>" not in cleaned
    assert "<strong>" not in cleaned
    assert "<ul>" not in cleaned
    assert "&amp;" not in cleaned
    assert "Python & Django" in cleaned
    assert "SQL <Pro>" in cleaned


def test_extract_relevant_description_empty_and_short():
    """Verify handling of None, empty strings, and descriptions shorter than max_chars."""
    assert extract_relevant_description(None) == "N/A"
    assert extract_relevant_description("") == "N/A"
    assert extract_relevant_description("   ") == "N/A"

    short_desc = "Short job description without headers."
    assert extract_relevant_description(short_desc, max_chars=3000) == short_desc


# ---------------------------------------------------------------------------
# 9. Evaluator Zero Denominator & Edge Cases Tests
# ---------------------------------------------------------------------------

def test_evaluator_zero_denominators():
    """Verify evaluator handles zero denominators gracefully without ZeroDivisionError."""
    # Case 1: All ground truth records are uncertain (decisive_sample_size == 0)
    ground_truth = [
        {"job_id": 1, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "uncertain"},
        {"job_id": 2, "human_role": "Frontend", "human_city": "Pune", "human_fresher_status": "uncertain"},
    ]
    predictions = [
        {"job_id": 1, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "uncertain"},
        {"job_id": 2, "model_role": "Frontend", "model_city": "Pune", "model_fresher_status": "uncertain"},
    ]

    metrics = evaluate_classifications(ground_truth, predictions)
    assert metrics["sample_size"] == 2
    assert metrics["decisive_sample_size"] == 0
    assert metrics["excluded_uncertain_ground_truth_count"] == 2
    b = metrics["binary_metrics_on_decisive_cases"]
    assert b["true_positives"] == 0
    assert b["false_positives"] == 0
    assert b["false_negatives"] == 0
    assert b["true_negatives"] == 0
    assert b["precision"] == 0.0
    assert b["recall"] == 0.0
    assert b["f1_score"] == 0.0
    assert b["false_positive_rate"] == 0.0
    assert b["false_negative_rate"] == 0.0
    assert b["specificity"] == 0.0

    # Case 2: Empty ground truth
    empty_metrics = evaluate_classifications([], [])
    assert empty_metrics["sample_size"] == 0


def test_evaluator_fpr_fnr_specificity_calculation():
    """Verify FPR, FNR, and Specificity with known counts."""
    # 2 TP, 1 FP, 1 FN, 2 TN
    ground_truth = [
        # Decisive positives (3)
        {"job_id": 1, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "fresher_friendly"},
        {"job_id": 2, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "fresher_friendly"},
        {"job_id": 3, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "fresher_friendly"},
        # Decisive negatives (3)
        {"job_id": 4, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
        {"job_id": 5, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
        {"job_id": 6, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
    ]
    predictions = [
        # Predictions for positives: 2 TP (job 1, 2), 1 FN (job 3)
        {"job_id": 1, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},
        {"job_id": 2, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},
        {"job_id": 3, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "not_fresher_friendly"},
        # Predictions for negatives: 1 FP (job 4), 2 TN (job 5, 6)
        {"job_id": 4, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},
        {"job_id": 5, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "not_fresher_friendly"},
        {"job_id": 6, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "not_fresher_friendly"},
    ]

    metrics = evaluate_classifications(ground_truth, predictions)
    b = metrics["binary_metrics_on_decisive_cases"]
    assert b["true_positives"] == 2
    assert b["false_positives"] == 1
    assert b["false_negatives"] == 1
    assert b["true_negatives"] == 2

    # Precision = 2 / (2 + 1) = 0.6667
    assert b["precision"] == 0.6667
    # Recall = 2 / (2 + 1) = 0.6667
    assert b["recall"] == 0.6667
    # F1 = 0.6667
    assert b["f1_score"] == 0.6667

    # FPR = FP / (FP + TN) = 1 / (1 + 2) = 0.3333
    assert b["false_positive_rate"] == 0.3333
    # FNR = FN / (FN + TP) = 1 / (1 + 2) = 0.3333
    assert b["false_negative_rate"] == 0.3333
    # Specificity = TN / (TN + FP) = 2 / (2 + 1) = 0.6667
    assert b["specificity"] == 0.6667


# ---------------------------------------------------------------------------
# 10. Milestone 10B: City Normalization & Aliases Tests
# ---------------------------------------------------------------------------

from app.ingestion.normalizer import normalize_standardized_city
from typing import get_args
from app.ai.schemas import CityType

VALID_CITY_ENUMS = set(get_args(CityType))


def test_normalize_city_bengaluru_aliases():
    """Verify Bengaluru, Bangalore, and regional tech cluster aliases map to 'Bengaluru'."""
    test_cases = [
        "Bengaluru", "bengaluru", "Bangalore", "bangalore",
        "Bangalore, India", "Bengaluru, Karnataka, India",
        "Electronic City, Bangalore", "Whitefield", "Bellandur, Bengaluru",
        "Bangalore - EC", "Bangalore, Karnataka", "Hybrid in Bengaluru, India",
        "Bengaluru-VTP, India"
    ]
    for loc in test_cases:
        res = normalize_standardized_city(loc)
        assert res == "Bengaluru", f"Failed for loc='{loc}', got '{res}'"
        assert res in VALID_CITY_ENUMS


def test_normalize_city_delhi_ncr_subcities():
    """Verify Delhi, New Delhi, Gurugram, Gurgaon, Noida, Greater Noida, Faridabad map to 'Delhi-NCR'."""
    test_cases = [
        "Delhi", "Delhi, Delhi", "New Delhi", "New Delhi, India",
        "Gurugram", "Gurgaon", "Gurugram, Haryana", "Gurugram, Haryana, India",
        "Noida", "Noida, Uttar Pradesh", "Greater Noida", "Faridabad", "Sonipat, Haryana"
    ]
    for loc in test_cases:
        res = normalize_standardized_city(loc)
        assert res == "Delhi-NCR", f"Failed for loc='{loc}', got '{res}'"
        assert res in VALID_CITY_ENUMS


def test_normalize_city_metro_locations():
    """Verify other standard Tier-1 metros map cleanly to their respective enums."""
    metro_cases = {
        "Hyderabad": ["Hyderabad", "hyderabad", "Hyderabad, Telangana", "India (Hyderabad)", "Gachibowli, Hyderabad", "HITEC City"],
        "Pune": ["Pune", "Pune, Maharashtra", "Pune, India", "Hinjewadi, Pune", "India - Pune"],
        "Mumbai": ["Mumbai", "mumbai", "Mumbai, Maharashtra", "Navi Mumbai", "Thane", "Andheri", "India - Mumbai"],
        "Chennai": ["Chennai", "Chennai, Tamil Nadu", "Madras", "OMR, Chennai"],
        "Kolkata": ["Kolkata", "Calcutta", "Salt Lake, Kolkata"],
        "Ahmedabad": ["Ahmedabad", "Gandhinagar", "GIFT City"]
    }
    for expected_city, loc_list in metro_cases.items():
        for loc in loc_list:
            res = normalize_standardized_city(loc)
            assert res == expected_city, f"Failed for loc='{loc}', expected '{expected_city}', got '{res}'"
            assert res in VALID_CITY_ENUMS


def test_normalize_city_explicit_remote_indicators():
    """Verify explicit remote indicators map to 'Remote'."""
    remote_cases = [
        "Remote", "remote", "Remote, India", "Remote - India", "India Remote",
        "Work from home", "WFH", "Worldwide", "Home based - Worldwide",
        "Anywhere", "Global Remote", "Pan-India Remote"
    ]
    for loc in remote_cases:
        res = normalize_standardized_city(loc)
        assert res == "Remote", f"Failed for loc='{loc}', got '{res}'"
        assert res in VALID_CITY_ENUMS


def test_normalize_city_india_convention_and_title_override():
    """Verify benchmark convention: generic 'India' -> 'Remote', but title physical city -> mapped metro."""
    # Generic India without physical city
    assert normalize_standardized_city("India") == "Remote"
    assert normalize_standardized_city("Pan-India") == "Remote"

    # India with physical city in title
    assert normalize_standardized_city("India", title="Software Engineer (Mumbai)") == "Mumbai"
    assert normalize_standardized_city("India", title="Developer - Chennai Office") == "Chennai"
    assert normalize_standardized_city("India", company="NeuroNetworks AI Ed, Pune") == "Pune"
    assert normalize_standardized_city("India", title="Backend Engineer (Bengaluru)") == "Bengaluru"

    # Generic India with generic title
    assert normalize_standardized_city("India", title="Generalist AI Trainer") == "Remote"
    assert normalize_standardized_city("India", title="Java Technical Lead") == "Remote"


def test_normalize_city_tier2_and_ambiguous_fallback():
    """Verify Tier-2 Indian cities map to 'Other India', and multi-metro conflicts return None."""
    # Tier-2 cities / states
    assert normalize_standardized_city("Coimbatore, Tamil Nadu") == "Other India"
    assert normalize_standardized_city("Patna, Bihar") == "Other India"
    assert normalize_standardized_city("Surat, Gujarat") == "Other India"
    assert normalize_standardized_city("Jaipur") == "Other India"
    assert normalize_standardized_city("tamil nadu") == "Other India"

    # Multi-metro conflicts should return None for downstream LLM resolution
    assert normalize_standardized_city("Chennai/Bangalore") is None
    assert normalize_standardized_city("Mumbai / Bangalore") is None
    assert normalize_standardized_city("India - Bengaluru; India - Mumbai") is None

    # Empty / None location with no title context returns Unknown
    assert normalize_standardized_city(None) == "Unknown"
    assert normalize_standardized_city("") == "Unknown"


# ---------------------------------------------------------------------------
# 11. Milestone 10B: Fresher Prompt Hardening Tests
# ---------------------------------------------------------------------------

def test_fresher_prompt_trainee_guidance():
    """Verify system instructions explicitly mention trainee designations and guidelines."""
    from app.ai.prompts import SYSTEM_INSTRUCTIONS

    # Trainee keywords
    assert "Graduate Engineer Trainee" in SYSTEM_INSTRUCTIONS or "GET" in SYSTEM_INSTRUCTIONS
    assert "Management Trainee" in SYSTEM_INSTRUCTIONS
    assert "Industrial Trainee" in SYSTEM_INSTRUCTIONS

    # Missing description guidance
    assert "Missing or empty job descriptions" in SYSTEM_INSTRUCTIONS
    assert "uncertain" in SYSTEM_INSTRUCTIONS

    # Freelance / contract status guidance
    assert "Freelance or contract status alone" in SYSTEM_INSTRUCTIONS


# ---------------------------------------------------------------------------
# 12. Milestone 10B: Evaluator Uncertainty Correction Tests
# ---------------------------------------------------------------------------

def test_evaluator_uncertain_model_prediction_not_counted_as_tn():
    """Verify model predicting 'uncertain' on human 'not_fresher_friendly' does NOT increment TN."""
    ground_truth = [
        {"job_id": 1, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
    ]
    # Model predicts 'uncertain' on a non-fresher role
    predictions = [
        {"job_id": 1, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "uncertain"},
    ]

    metrics = evaluate_classifications(ground_truth, predictions)
    b = metrics["binary_metrics_on_decisive_cases"]

    # Must NOT count as True Negative
    assert b["true_negatives"] == 0
    assert b["false_positives"] == 0
    assert b["unresolved_cases"] == 1


def test_evaluator_exact_decisive_accounting():
    """Verify complete binary accounting across TP, FP, FN, TN, and unresolved cases."""
    ground_truth = [
        # 2 Positive cases
        {"job_id": 1, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "fresher_friendly"},
        {"job_id": 2, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "fresher_friendly"},
        # 3 Negative cases
        {"job_id": 3, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
        {"job_id": 4, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
        {"job_id": 5, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "not_fresher_friendly"},
        # 1 Uncertain ground-truth case (excluded from binary)
        {"job_id": 6, "human_role": "Backend", "human_city": "Bengaluru", "human_fresher_status": "uncertain"},
    ]

    predictions = [
        {"job_id": 1, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},      # TP
        {"job_id": 2, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "not_fresher_friendly"},  # FN
        {"job_id": 3, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "not_fresher_friendly"},  # TN
        {"job_id": 4, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},      # FP
        {"job_id": 5, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "uncertain"},             # Unresolved!
        {"job_id": 6, "model_role": "Backend", "model_city": "Bengaluru", "model_fresher_status": "fresher_friendly"},      # Excluded
    ]

    metrics = evaluate_classifications(ground_truth, predictions)
    assert metrics["sample_size"] == 6
    assert metrics["decisive_sample_size"] == 5
    assert metrics["excluded_uncertain_ground_truth_count"] == 1

    b = metrics["binary_metrics_on_decisive_cases"]
    assert b["true_positives"] == 1
    assert b["false_negatives"] == 1
    assert b["true_negatives"] == 1
    assert b["false_positives"] == 1
    assert b["unresolved_cases"] == 1

    # Precision = TP / (TP + FP) = 1 / 2 = 0.5
    assert b["precision"] == 0.5
    # Recall = TP / (TP + FN) = 1 / 2 = 0.5
    assert b["recall"] == 0.5
    # F1 = 0.5
    assert b["f1_score"] == 0.5
    # Specificity = TN / (TN + FP) = 1 / 2 = 0.5
    assert b["specificity"] == 0.5
