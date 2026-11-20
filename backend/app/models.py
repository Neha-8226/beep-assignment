"""SQLAlchemy Database Models.

Defines schemas for:
- Unique canonical job listings (Job)
- Traceable duplicate audit records (DuplicateRecord)
- Ingestion pipeline execution history (PipelineRun)
- LLM token usage and performance telemetry (LLMAuditLog)
- Manually verified ground-truth evaluations (GroundTruthEval)
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index
)
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


class Job(Base):
    """Canonical unique job listing. Strictly deduplicated; no duplicate entries."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)  # Allowed nullable per source capability
    posting_organization = Column(String(255), nullable=True)  # Entity operating the career board/platform
    hiring_organization = Column(String(255), nullable=True)   # Actual hiring employer (nullable/ambiguous if unstated)
    raw_location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    apply_url = Column(Text, nullable=False)
    canonical_url_hash = Column(String(64), nullable=False, index=True)
    content_hash = Column(String(32), nullable=False, index=True)

    # LLM-enriched classification fields (nullable until classified)
    role_category = Column(String(50), nullable=True, index=True)
    standardized_city = Column(String(50), nullable=True, index=True)
    job_type = Column(String(50), nullable=True)  # e.g. 'Full-Time', 'Internship', 'Contract'
    fresher_eligibility_status = Column(String(30), nullable=True)  # 'fresher_friendly', 'not_fresher_friendly', 'uncertain'
    is_fresher_friendly = Column(Boolean, nullable=True, default=None)  # True if fresher_friendly, False if not, None if uncertain/pending
    model_confidence = Column(Float, nullable=True)  # Uncalibrated model self-reported confidence score (0.0 to 1.0)
    classification_error = Column(Text, nullable=True)  # Stores omitted item, duplicate ID or API error details; remains eligible for retry

    # Timestamps
    posted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    duplicates = relationship("DuplicateRecord", back_populates="canonical_job", cascade="all, delete-orphan")
    ground_truth = relationship("GroundTruthEval", back_populates="job", uselist=False)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
        Index("ix_role_city", "role_category", "standardized_city"),
    )


class DuplicateRecord(Base):
    """Traceable audit log for discarded duplicate job candidates."""

    __tablename__ = "duplicate_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    raw_location = Column(String(255), nullable=True)
    apply_url = Column(Text, nullable=False)
    canonical_url_hash = Column(String(64), nullable=False)
    content_hash = Column(String(32), nullable=False)

    # Traceability fields
    duplicate_type = Column(
        String(30),
        default="confirmed",
        nullable=False
    )  # 'confirmed' (strong match: canonical URL or source_id) vs 'potential' (similarity)
    duplicate_reason = Column(
        String(50),
        nullable=False
    )  # 'source_id_match', 'canonical_url_match', 'content_similarity_flag'
    evidence = Column(Text, nullable=True)  # Detailed evidence payload (e.g. matched hashes, similarity score)
    canonical_job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    detected_at = Column(DateTime, default=utc_now, nullable=False)

    canonical_job = relationship("Job", back_populates="duplicates")


class RejectedRecord(Base):
    """Traceable audit log for discarded candidate records during ingestion.

    Tracks non-duplicate exclusions (geo-ineligible, seniority exceeded, talent pool, invalid).
    """

    __tablename__ = "rejected_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)
    external_id = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    raw_location = Column(String(255), nullable=True)
    apply_url = Column(Text, nullable=True)
    rejection_category = Column(String(50), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    rule_version = Column(String(20), nullable=False, default="v1.0")
    confidence = Column(Float, nullable=True)
    pipeline_run_id = Column(String(64), nullable=True, index=True)
    rejected_at = Column(DateTime, default=utc_now, nullable=False)


class PipelineRun(Base):
    """Pipeline execution history recording performance and yield per run."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    source = Column(String(50), nullable=False)
    requests_made = Column(Integer, default=0, nullable=False)
    fetch_count = Column(Integer, default=0, nullable=False)
    records_rejected_count = Column(Integer, default=0, nullable=False)
    unique_count = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    potential_duplicate_count = Column(Integer, default=0, nullable=False)
    classification_success_count = Column(Integer, default=0, nullable=False)
    classification_failure_count = Column(Integer, default=0, nullable=False)
    execution_duration_seconds = Column(Float, default=0.0, nullable=False)
    run_status = Column(String(20), default="pending", nullable=False)  # 'success', 'partial', 'failed'
    error_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class LLMAuditLog(Base):
    """Token consumption, pricing telemetry and execution metrics for LLM batch calls."""

    __tablename__ = "llm_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(String(64), nullable=False, index=True)
    jobs_count = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)  # 'success', 'failed', 'partial', 'retry'
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    model_name = Column(String(50), nullable=False)
    latency_seconds = Column(Float, default=0.0, nullable=False)
    
    # Financial & pricing telemetry (distinguishes free-tier from nominal commercial baseline)
    pricing_tier = Column(String(20), nullable=False, default="free")  # 'free' or 'paid'
    input_price_per_1m = Column(Float, nullable=False, default=0.30)
    output_price_per_1m = Column(Float, nullable=False, default=2.50)
    actual_cost_usd = Column(Float, nullable=False, default=0.0)  # $0.00 if pricing_tier == 'free'
    nominal_cost_usd = Column(Float, nullable=False, default=0.0)  # Calculated standard paid baseline

    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class GroundTruthEval(Base):
    """Manually labeled ground-truth comparison for measuring classification accuracy."""

    __tablename__ = "ground_truth_evals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, unique=True, index=True)
    human_role_category = Column(String(50), nullable=False)
    human_city = Column(String(50), nullable=True)  # Supports 'Remote', 'Unknown', or NULL
    human_fresher_status = Column(String(30), nullable=False, default="uncertain")  # 'fresher_friendly', 'not_fresher_friendly', 'uncertain'

    # Computed evaluation results
    role_match = Column(Boolean, nullable=True)
    city_match = Column(Boolean, nullable=True)
    fresher_match = Column(Boolean, nullable=True)
    notes = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, default=utc_now, nullable=False)

    job = relationship("Job", back_populates="ground_truth")
