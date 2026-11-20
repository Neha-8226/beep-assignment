"""Pydantic Validation Schemas.

Enforces strict request/response data contracts for:
- API job search and filtering
- LLM structured JSON output validation
- Pipeline run telemetry
- Cost tracking and ground-truth evaluation reports
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# ---------------------------------------------------------------------------
# LLM Structured Output Schemas
# ---------------------------------------------------------------------------

class LLMClassificationItem(BaseModel):
    """Pydantic model enforcing strict schema for LLM-classified job items."""
    job_id: int
    role_category: str = Field(
        description="Standardized role e.g. Frontend, Backend, Full Stack, Mobile, Data & Analytics, AI/ML, DevOps & Cloud, QA & Testing, Other Tech"
    )
    standardized_city: str = Field(
        description="Standardized Indian tech hub e.g. Bengaluru, Hyderabad, Pune, Mumbai, Delhi-NCR, Chennai, Kolkata, Remote, Other India"
    )
    job_type: str = Field(
        description="'Full-Time Fresher', 'Internship', or 'Contract'"
    )
    is_fresher_friendly: bool = Field(
        description="True if explicitly suitable for 0-1 years experience or college graduates"
    )
    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model self-reported confidence score between 0.0 and 1.0"
    )


class LLMBatchClassificationResponse(BaseModel):
    """Batch container for LLM output."""
    items: List[LLMClassificationItem]


# ---------------------------------------------------------------------------
# Canonical Job Schemas
# ---------------------------------------------------------------------------

class JobBase(BaseModel):
    source: str
    external_id: str
    title: str
    company: Optional[str] = None
    posting_organization: Optional[str] = None
    hiring_organization: Optional[str] = None
    raw_location: Optional[str] = None
    description: Optional[str] = None
    apply_url: str


class JobCreate(JobBase):
    canonical_url_hash: str
    content_hash: str
    posted_at: Optional[datetime] = None


class JobResponse(JobBase):
    id: int
    canonical_url_hash: str
    content_hash: str
    role_category: Optional[str] = None
    standardized_city: Optional[str] = None
    job_type: Optional[str] = None
    fresher_eligibility_status: Optional[str] = None  # 'fresher_friendly', 'not_fresher_friendly', 'uncertain'
    is_fresher_friendly: Optional[bool] = None  # None = pending classification
    model_confidence: Optional[float] = None
    classification_error: Optional[str] = None
    posted_at: Optional[datetime] = None
    created_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    jobs: List[JobResponse]


# ---------------------------------------------------------------------------
# Duplicate & Pipeline Schemas
# ---------------------------------------------------------------------------

class DuplicateRecordResponse(BaseModel):
    id: int
    source: str
    external_id: str
    title: str
    company: Optional[str] = None
    duplicate_type: str
    duplicate_reason: str
    evidence: Optional[str] = None
    canonical_job_id: int
    detected_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineRunResponse(BaseModel):
    run_id: str
    source: str
    requests_made: int
    fetch_count: int
    records_rejected_count: int
    unique_count: int
    duplicate_count: int
    potential_duplicate_count: int
    classification_success_count: int
    classification_failure_count: int
    execution_duration_seconds: float
    run_status: str
    error_details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Analytics & Telemetry Schemas
# ---------------------------------------------------------------------------

class FresherBreakdown(BaseModel):
    fresher_friendly: int
    not_fresher_friendly: int
    pending_or_uncertain: int


class SourceBreakdown(BaseModel):
    source: str
    canonical_jobs: int
    duplicates_detected: int


class DatasetMetrics(BaseModel):
    total_canonical_jobs: int
    total_duplicates_prevented: int
    confirmed_duplicates: int
    potential_duplicates: int
    total_pipeline_runs: int
    fresher_breakdown: FresherBreakdown
    sources: List[SourceBreakdown]


class AIProcessingCost(BaseModel):
    total_batches: int
    total_jobs_processed: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_actual_cost_usd: float
    total_nominal_cost_usd: float
    nominal_cost_per_1000_posts_usd: Optional[float] = None
    pricing_tier: str


class BinaryMetrics(BaseModel):
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    unresolved_cases: int = 0
    precision: float
    recall: float
    f1_score: float


class GroundTruthAccuracyReport(BaseModel):
    sample_size: int
    decisive_sample_size: int
    excluded_uncertain_ground_truth_count: int
    excluded_uncertain_percentage: float
    role_classification_accuracy_pct: float
    city_standardization_accuracy_pct: float
    fresher_three_class_accuracy_pct: float
    three_class_confusion_matrix: dict
    binary_metrics_on_decisive_cases: BinaryMetrics


class AnalyticsResponse(BaseModel):
    dataset_metrics: DatasetMetrics
    ai_processing_cost: AIProcessingCost
    ground_truth_accuracy: Optional[GroundTruthAccuracyReport] = None
