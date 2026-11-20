"""Analytics & Telemetry Router.

Exposes verified system metrics:
1. Canonical job count and duplicates prevented.
2. Ingestion pipeline runs history.
3. Actual vs. nominal LLM processing cost per 1,000 posts.
4. Live ground-truth accuracy metrics and 3-class fresher evaluation.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Job, DuplicateRecord, PipelineRun, GroundTruthEval
from app.schemas import AnalyticsResponse
from app.ai.cost_tracker import get_cost_summary
from app.ai.evaluator import evaluate_classifications

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("", response_model=AnalyticsResponse)
def get_analytics_summary(db: Session = Depends(get_db)):
    """Return high-level operational, financial, and AI accuracy metrics."""
    # Canonical job count and pipeline runs
    total_canonical = db.query(Job).filter(Job.is_active.is_(True)).count()
    total_duplicates = db.query(DuplicateRecord).count()
    total_pipeline_runs = db.query(PipelineRun).count()

    # Fresher status breakdown (consistently filtered by is_active == True)
    fresher_friendly_cnt = (
        db.query(Job)
        .filter(Job.is_active.is_(True), Job.is_fresher_friendly.is_(True))
        .count()
    )
    not_fresher_cnt = (
        db.query(Job)
        .filter(Job.is_active.is_(True), Job.is_fresher_friendly.is_(False))
        .count()
    )
    pending_cnt = (
        db.query(Job)
        .filter(Job.is_active.is_(True), Job.is_fresher_friendly.is_(None))
        .count()
    )

    # Deduplication breakdown by type
    confirmed_dups = (
        db.query(DuplicateRecord)
        .filter(DuplicateRecord.duplicate_type == "confirmed")
        .count()
    )
    potential_dups = (
        db.query(DuplicateRecord)
        .filter(DuplicateRecord.duplicate_type == "potential")
        .count()
    )

    # Sources breakdown - Grouped aggregation eliminating N+1 queries
    can_by_source = dict(
        db.query(Job.source, func.count(Job.id))
        .filter(Job.is_active.is_(True))
        .group_by(Job.source)
        .all()
    )
    dup_by_source = dict(
        db.query(DuplicateRecord.source, func.count(DuplicateRecord.id))
        .group_by(DuplicateRecord.source)
        .all()
    )
    all_sources = sorted(set(can_by_source.keys()).union(dup_by_source.keys()))
    sources_stats = [
        {
            "source": src,
            "canonical_jobs": can_by_source.get(src, 0),
            "duplicates_detected": dup_by_source.get(src, 0)
        }
        for src in all_sources
    ]

    # AI cost metrics
    cost_metrics = get_cost_summary(db)

    # Ground-truth accuracy metrics - Bulk retrieval eliminating N+1 queries
    eval_records = db.query(GroundTruthEval).all()
    accuracy_data: Optional[Dict[str, Any]] = None

    if eval_records:
        gt_list = []
        pred_list = []

        # Bulk fetch all corresponding jobs in one query
        job_ids = [er.job_id for er in eval_records]
        jobs_in_db = db.query(Job).filter(Job.id.in_(job_ids)).all()
        jobs_by_id = {j.id: j for j in jobs_in_db}

        for er in eval_records:
            gt_list.append({
                "job_id": er.job_id,
                "human_role": er.human_role_category,
                "human_city": er.human_city,
                "human_fresher_status": er.human_fresher_status  # Preserves 3-class label: fresher_friendly, not_fresher_friendly, uncertain
            })
            job = jobs_by_id.get(er.job_id)
            if job:
                pred_list.append({
                    "job_id": er.job_id,
                    "model_role": job.role_category,
                    "model_city": job.standardized_city,
                    "model_fresher_status": job.fresher_eligibility_status or (
                        "fresher_friendly" if job.is_fresher_friendly is True else (
                            "not_fresher_friendly" if job.is_fresher_friendly is False else "uncertain"
                        )
                    )
                })

        accuracy_data = evaluate_classifications(gt_list, pred_list)

    return {
        "dataset_metrics": {
            "total_canonical_jobs": total_canonical,
            "total_duplicates_prevented": total_duplicates,
            "confirmed_duplicates": confirmed_dups,
            "potential_duplicates": potential_dups,
            "total_pipeline_runs": total_pipeline_runs,
            "fresher_breakdown": {
                "fresher_friendly": fresher_friendly_cnt,
                "not_fresher_friendly": not_fresher_cnt,
                "pending_or_uncertain": pending_cnt
            },
            "sources": sources_stats
        },
        "ai_processing_cost": cost_metrics,
        "ground_truth_accuracy": accuracy_data
    }
