"""Ingestion Pipeline Orchestrator.

Orchestrates multi-source ingestion with complete fault isolation:
1. Runs each source adapter independently; failure in one source does not abort others.
2. Validates raw record integrity (non-empty title, valid URL).
3. Applies India geographic eligibility filtering.
4. Performs 3-tier traceable deduplication.
5. Inserts canonical jobs with is_fresher_friendly=None (classification deferred to Milestone 3).
6. Records per-source telemetry and metrics to pipeline_runs.
"""
import time
import uuid
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models import Job, PipelineRun, RejectedRecord, utc_now
from app.ingestion.sources.base import BaseSourceAdapter
from app.ingestion.sources.hasjob import HasjobAdapter
from app.ingestion.sources.remotive import RemotiveAdapter
from app.ingestion.sources.adzuna import AdzunaAdapter
from app.ingestion.normalizer import (
    validate_raw_record,
    is_india_eligible,
    normalize_url,
    hash_url,
    compute_content_hash,
    generate_fallback_external_id
)
from app.ingestion.relevance import evaluate_job_relevance
from app.ingestion.dedup import evaluate_candidate, record_duplicate


def get_default_adapters() -> List[BaseSourceAdapter]:
    """Return default registered source adapters."""
    adapters: List[BaseSourceAdapter] = [
        HasjobAdapter(),
        RemotiveAdapter(),
    ]
    # Include Adzuna if credentials exist
    adzuna = AdzunaAdapter()
    if adzuna.is_configured():
        adapters.append(adzuna)
    return adapters


def run_ingestion_pipeline(
    db: Session,
    adapters: Optional[List[BaseSourceAdapter]] = None,
    batch_run_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute ingestion across all specified adapters with complete fault isolation.

    Returns:
        Structured summary with per-source metrics and aggregate results.
    """
    active_adapters = adapters if adapters is not None else get_default_adapters()
    master_run_id = batch_run_id or f"run_{uuid.uuid4().hex[:12]}"

    summary: Dict[str, Any] = {
        "run_id": master_run_id,
        "sources": {},
        "totals": {
            "requests_made": 0,
            "records_fetched": 0,
            "records_rejected": 0,
            "unique_inserted": 0,
            "confirmed_duplicates": 0,
            "potential_duplicates": 0,
            "errors_count": 0
        }
    }

    for adapter in active_adapters:
        source_name = adapter.source_name
        source_run_id = f"{master_run_id}_{source_name}"
        start_time = time.time()
        requests_made = 0
        fetched_count = 0
        rejected_count = 0
        rejection_reasons: Dict[str, int] = {}
        unique_count = 0
        confirmed_dup_count = 0
        potential_dup_count = 0
        error_msg: Optional[str] = None
        run_status = "success"

        try:
            # 1. Fetch records from upstream source
            raw_records, requests_made, fetch_err = adapter.fetch_records()
            fetched_count = len(raw_records)

            if fetch_err:
                error_msg = fetch_err
                run_status = "partial" if fetched_count > 0 else "failed"

            # 2. Process each raw record through validation, relevance filtering and deduplication
            for raw in raw_records:
                # Validation check
                is_valid, val_err = validate_raw_record(raw)
                if not is_valid:
                    rejected_count += 1
                    reason = f"invalid_record: {val_err}"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    val_ext_id = raw.get("external_id") or raw.get("apply_url") or "unknown"
                    existing_rejection = db.query(RejectedRecord).filter(
                        RejectedRecord.source == source_name,
                        RejectedRecord.external_id == val_ext_id
                    ).first()
                    if not existing_rejection:
                        db.add(RejectedRecord(
                            source=source_name,
                            external_id=val_ext_id,
                            title=raw.get("title") or "Unknown Title",
                            company=raw.get("company"),
                            raw_location=raw.get("raw_location"),
                            apply_url=raw.get("apply_url"),
                            rejection_category="invalid_record",
                            reason=val_err or "Invalid schema",
                            rule_version="v1.0",
                            confidence=1.0,
                            pipeline_run_id=source_run_id
                        ))
                    continue

                title = raw["title"].strip()
                apply_url = raw["apply_url"].strip()
                company = raw.get("company")
                raw_loc = raw.get("raw_location")
                description = raw.get("description")
                posted_at = raw.get("posted_at")
                ext_id = raw.get("external_id") or apply_url

                # Unified relevance & suitability assessment (India eligibility, vacancy type, seniority)
                relevance = evaluate_job_relevance(
                    title=title,
                    raw_location=raw_loc,
                    description=description,
                    is_indian_source=adapter.is_indian_source
                )

                if not relevance.is_accepted:
                    rejected_count += 1
                    reason_key = f"{relevance.category}: {relevance.reason}"
                    rejection_reasons[reason_key] = rejection_reasons.get(reason_key, 0) + 1
                    # Record traceable rejection telemetry in rejected_records table if not already recorded
                    existing_rejection = db.query(RejectedRecord).filter(
                        RejectedRecord.source == source_name,
                        RejectedRecord.external_id == ext_id
                    ).first()
                    if not existing_rejection:
                        db.add(RejectedRecord(
                            source=source_name,
                            external_id=ext_id,
                            title=title,
                            company=company,
                            raw_location=raw_loc,
                            apply_url=apply_url,
                            rejection_category=relevance.category,
                            reason=relevance.reason,
                            rule_version=relevance.rule_version,
                            confidence=relevance.confidence,
                            pipeline_run_id=source_run_id
                        ))
                    continue

                # Deduplication check
                dedup_result = evaluate_candidate(
                    db=db,
                    source=source_name,
                    title=title,
                    apply_url=apply_url,
                    external_id=raw.get("external_id"),
                    company=company,
                    raw_location=raw_loc,
                    description=description
                )

                if not dedup_result.is_unique:
                    # Record duplicate in audit table
                    record_duplicate(
                        db=db,
                        source=source_name,
                        title=title,
                        apply_url=apply_url,
                        result=dedup_result,
                        external_id=raw.get("external_id"),
                        company=company,
                        raw_location=raw_loc
                    )
                    if dedup_result.duplicate_type == "potential":
                        potential_dup_count += 1
                    else:
                        confirmed_dup_count += 1
                    continue

                # Unique job -> Insert canonical listing
                clean_url = normalize_url(apply_url)
                canonical_hash = hash_url(clean_url)
                eff_id = raw.get("external_id") or generate_fallback_external_id(
                    source=source_name, title=title, company=company, clean_url=clean_url
                )
                content_hash = compute_content_hash(
                    title=title, company=company, raw_location=raw_loc
                )

                posting_org = raw.get("posting_organization")
                hiring_org = raw.get("hiring_organization")

                new_job = Job(
                    source=source_name,
                    external_id=eff_id,
                    title=title,
                    company=company,
                    posting_organization=posting_org,
                    hiring_organization=hiring_org,
                    raw_location=raw_loc,
                    description=description,
                    apply_url=clean_url,
                    canonical_url_hash=canonical_hash,
                    content_hash=content_hash,
                    # Classification strictly deferred to Milestone 3
                    role_category=None,
                    standardized_city=None,
                    job_type=None,
                    is_fresher_friendly=None,  # Nullable / pending classification
                    model_confidence=None,
                    posted_at=posted_at
                )
                db.add(new_job)
                db.flush()
                unique_count += 1

            # Detect disappeared postings for ATS boards
            if hasattr(adapter, "track_disappeared_postings") and hasattr(adapter, "companies"):
                for company in getattr(adapter, "companies", []):
                    token = getattr(company, "token_or_slug", None)
                    if token:
                        active_ext_ids = {
                            raw["external_id"]
                            for raw in raw_records
                            if raw.get("external_id") and (
                                raw.get("board_token") == token or
                                raw.get("board_slug") == token or
                                raw.get("external_id", "").startswith(f"gh_{token}_") or
                                raw.get("external_id", "").startswith(f"lever_{token}_")
                            )
                        }
                        adapter.track_disappeared_postings(db, token, active_ext_ids)

            # Commit changes for this source
            db.commit()

        except Exception as ex:
            db.rollback()
            error_msg = f"Unhandled exception in source {source_name}: {str(ex)}"
            run_status = "failed"

        duration = round(time.time() - start_time, 2)

        # Log to pipeline_runs table
        source_run_id = f"{master_run_id}_{source_name}"
        run_record = PipelineRun(
            run_id=source_run_id,
            source=source_name,
            requests_made=requests_made,
            fetch_count=fetched_count,
            records_rejected_count=rejected_count,
            unique_count=unique_count,
            duplicate_count=confirmed_dup_count,
            potential_duplicate_count=potential_dup_count,
            classification_success_count=0,
            classification_failure_count=0,
            execution_duration_seconds=duration,
            run_status=run_status,
            error_details=error_msg or (json.dumps(rejection_reasons) if rejection_reasons else None)
        )
        db.add(run_record)
        db.commit()

        # Update per-source summary
        summary["sources"][source_name] = {
            "run_id": source_run_id,
            "requests_made": requests_made,
            "fetched_count": fetched_count,
            "rejected_count": rejected_count,
            "rejection_reasons": rejection_reasons,
            "unique_inserted": unique_count,
            "confirmed_duplicates": confirmed_dup_count,
            "potential_duplicates": potential_dup_count,
            "duration_seconds": duration,
            "status": run_status,
            "error": error_msg
        }

        # Update totals
        summary["totals"]["requests_made"] += requests_made
        summary["totals"]["records_fetched"] += fetched_count
        summary["totals"]["records_rejected"] += rejected_count
        summary["totals"]["unique_inserted"] += unique_count
        summary["totals"]["confirmed_duplicates"] += confirmed_dup_count
        summary["totals"]["potential_duplicates"] += potential_dup_count
        if error_msg:
            summary["totals"]["errors_count"] += 1

    return summary
