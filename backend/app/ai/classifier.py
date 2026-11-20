"""Batch Job Classification Engine using Google Gemini 2.5 Flash.

Key guarantees:
1. Pydantic-enforced structured JSON schema.
2. Exponential backoff with jitter on transient errors (429, 503); immediate abort on permanent errors (400, 401, 403).
3. Strict batch membership validation: rejects foreign IDs.
4. Duplicate ID guardrail: rejects ALL occurrences if an ID is duplicated in the response.
5. Location preservation: writes strictly to standardized_city; raw_location is never touched.
6. Error persistence: records item-level errors to job.classification_error while keeping them eligible for retry.
7. Token telemetry: extracts usage_metadata and logs to llm_audit_logs.
"""
import time
import json
import uuid
import random
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Job
from app.ai.schemas import BatchClassificationResponse, ClassifiedJobItem
from app.ai.prompts import SYSTEM_INSTRUCTIONS, format_batch_prompt
from app.ai.cost_tracker import record_llm_audit_log
from app.ingestion.normalizer import normalize_standardized_city


class LLMClassificationError(Exception):
    """Base exception for classification errors."""
    pass


class PermanentAPIError(LLMClassificationError):
    """Non-retryable error (e.g. 401 Unauthorized, 400 Bad Request)."""
    pass


class TransientAPIError(LLMClassificationError):
    """Retryable error (e.g. 429 Rate Limit, 503 Unavailable)."""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


def execute_gemini_call_with_retry(
    prompt_text: str,
    client: Any,
    model_name: str,
    max_retries: int = 4,
    base_delay: float = 2.0
) -> Tuple[str, int, int, float]:
    """Execute API call with jittered exponential backoff and Retry-After inspection.

    Returns:
        Tuple of (response_text, prompt_tokens, completion_tokens, latency_seconds)
    """
    attempt = 0
    start_time = time.time()

    while attempt <= max_retries:
        call_start = time.time()
        try:
            # Invoking google-genai client
            # The client supports generate_content with response_schema
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_text,
                config={
                    "system_instruction": SYSTEM_INSTRUCTIONS,
                    "temperature": settings.GEMINI_TEMPERATURE,
                    "response_mime_type": "application/json",
                    "response_schema": BatchClassificationResponse
                }
            )
            latency = time.time() - call_start

            # Extract actual token counts
            prompt_tokens = 0
            comp_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                comp_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            return response.text, prompt_tokens, comp_tokens, latency

        except Exception as ex:
            latency = time.time() - call_start
            err_str = str(ex).lower()

            # Inspect for permanent failures
            if "401" in err_str or "unauthorized" in err_str or "api_key" in err_str:
                raise PermanentAPIError(f"Permanent Authentication Failure: {ex}")
            if "400" in err_str or "invalid argument" in err_str:
                raise PermanentAPIError(f"Permanent Request Format Error: {ex}")
            if "403" in err_str or "permission denied" in err_str:
                raise PermanentAPIError(f"Permanent Permission Error: {ex}")
            if "404" in err_str or "not_found" in err_str or "not found" in err_str:
                raise PermanentAPIError(f"Permanent Model Not Found / Availability Error: {ex}")

            # Inspect for transient failures (429 rate limit or 503 unavailable)
            attempt += 1
            if attempt > max_retries:
                raise TransientAPIError(f"Max retries ({max_retries}) exceeded: {ex}")

            retry_after = None
            # Check if exception has retry_after attribute or header
            if hasattr(ex, "retry_after") and ex.retry_after:
                try:
                    retry_after = float(ex.retry_after)
                except Exception:
                    pass

            if retry_after is not None:
                wait_time = retry_after + random.uniform(0.1, 0.5)
            else:
                # Exponential backoff with jitter
                wait_time = min(60.0, base_delay * (2 ** (attempt - 1))) + random.uniform(0.1, 1.0)

            time.sleep(wait_time)


def process_classification_batch(
    db: Session,
    jobs: List[Job],
    client: Any,
    batch_index: int = 1
) -> Dict[str, Any]:
    """Process a single batch of jobs through Gemini classification with strict guardrails."""
    if not jobs:
        return {"batch_id": "empty", "processed": 0, "success": 0, "errors": 0, "classifications": []}

    batch_id = f"batch_{uuid.uuid4().hex[:10]}"
    batch_job_ids = {j.id for j in jobs}
    jobs_by_id = {j.id: j for j in jobs}

    # Prepare serialized job dicts with consistent truncation
    jobs_data = [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "raw_location": j.raw_location,
            "description": j.description
        }
        for j in jobs
    ]

    prompt = format_batch_prompt(jobs_data, max_desc_chars=settings.CLASSIFIER_DESCRIPTION_MAX_CHARS)

    try:
        raw_text, p_tokens, c_tokens, latency = execute_gemini_call_with_retry(
            prompt_text=prompt,
            client=client,
            model_name=settings.GEMINI_MODEL,
            max_retries=settings.GEMINI_MAX_RETRIES,
            base_delay=settings.GEMINI_BASE_RETRY_DELAY
        )
    except Exception as ex:
        # Batch-level API failure
        record_llm_audit_log(
            db=db,
            batch_id=batch_id,
            model_name=settings.GEMINI_MODEL,
            jobs_count=len(jobs),
            prompt_tokens=0,
            completion_tokens=0,
            latency_seconds=0.0,
            status="failed",
            error_message=str(ex)
        )
        for j in jobs:
            j.classification_error = f"Batch API failure: {str(ex)[:150]}"
        db.commit()
        return {
            "batch_id": batch_id,
            "processed": len(jobs),
            "success": 0,
            "errors": len(jobs),
            "error": str(ex),
            "classifications": []
        }

    # Validate JSON via Pydantic
    try:
        parsed_json = json.loads(raw_text)
        validated_response = BatchClassificationResponse.model_validate(parsed_json)
    except Exception as val_ex:
        record_llm_audit_log(
            db=db,
            batch_id=batch_id,
            model_name=settings.GEMINI_MODEL,
            jobs_count=len(jobs),
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            latency_seconds=latency,
            status="failed",
            error_message=f"Pydantic Validation Error: {val_ex}"
        )
        for j in jobs:
            j.classification_error = f"Malformed LLM JSON: {str(val_ex)[:150]}"
        db.commit()
        return {
            "batch_id": batch_id,
            "processed": len(jobs),
            "success": 0,
            "errors": len(jobs),
            "error": str(val_ex),
            "classifications": []
        }

    # -------------------------------------------------------------------------
    # Response ID Audit & Validation Guardrails
    # -------------------------------------------------------------------------
    returned_ids = [item.job_id for item in validated_response.classifications]
    id_counts = Counter(returned_ids)

    # Rule: If an ID appears more than once, reject ALL occurrences associated with that duplicate ID
    duplicate_ids = {jid for jid, cnt in id_counts.items() if cnt > 1}

    success_count = 0
    error_count = 0
    processed_ids: Set[int] = set()

    for item in validated_response.classifications:
        jid = item.job_id

        # Guardrail 1: Check if ID is duplicated in response
        if jid in duplicate_ids:
            if jid in jobs_by_id:
                job = jobs_by_id[jid]
                job.classification_error = f"Validation failure: duplicate job_id ({jid}) returned by LLM; rejected all occurrences."
                # Left pending for re-processing
                job.role_category = None
                error_count += 1
            continue

        # Guardrail 2: Reject foreign IDs not in current batch
        if jid not in batch_job_ids:
            # Foreign ID warning; cannot update non-existent or foreign job
            continue

        job = jobs_by_id[jid]
        processed_ids.add(jid)

        # Apply classification to job
        job.role_category = item.role_category
        # PRESERVATION: raw_location is NEVER touched; only standardized_city is updated
        # Deterministic normalization takes precedence for unambiguous locations;
        # falls back to LLM item.standardized_city for ambiguous or unresolved locations.
        det_city = normalize_standardized_city(job.raw_location, title=job.title, company=job.company)
        if det_city is not None:
            job.standardized_city = det_city
        else:
            job.standardized_city = item.standardized_city
        job.job_type = item.job_type
        job.fresher_eligibility_status = item.fresher_eligibility

        # Map 3-state fresher eligibility
        if item.fresher_eligibility == "fresher_friendly":
            job.is_fresher_friendly = True
        elif item.fresher_eligibility == "not_fresher_friendly":
            job.is_fresher_friendly = False
        else:  # 'uncertain'
            job.is_fresher_friendly = None

        job.model_confidence = item.confidence_score
        job.classification_error = None  # Clear any previous error
        success_count += 1

    # Guardrail 3: Handle omitted items from the batch
    omitted_ids = batch_job_ids - processed_ids - duplicate_ids
    for oid in omitted_ids:
        job = jobs_by_id[oid]
        job.classification_error = "Omitted by LLM in batch response; remains pending for re-processing."
        job.role_category = None
        error_count += 1

    # Record telemetry
    status = "success" if error_count == 0 else ("partial" if success_count > 0 else "failed")
    record_llm_audit_log(
        db=db,
        batch_id=batch_id,
        model_name=settings.GEMINI_MODEL,
        jobs_count=len(jobs),
        prompt_tokens=p_tokens,
        completion_tokens=c_tokens,
        latency_seconds=latency,
        status=status,
        error_message=f"Duplicate IDs: {len(duplicate_ids)}, Omitted: {len(omitted_ids)}" if error_count > 0 else None
    )

    db.commit()

    return {
        "batch_id": batch_id,
        "processed": len(jobs),
        "success": success_count,
        "errors": error_count,
        "duplicate_ids": list(duplicate_ids),
        "omitted_ids": list(omitted_ids),
        "prompt_tokens": p_tokens,
        "completion_tokens": c_tokens,
        "latency_seconds": latency,
        "status": status,
        "classifications": [item.model_dump() for item in validated_response.classifications]
    }


def classify_pending_jobs(
    db: Session,
    client: Any,
    batch_size: int = 15,
    max_jobs: Optional[int] = None,
    job_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """Orchestrate classification across pending jobs, optionally targeting specific job_ids."""
    if job_ids is not None:
        query = db.query(Job).filter(Job.id.in_(job_ids)).filter(Job.role_category.is_(None))
        jobs_map = {j.id: j for j in query.all()}
        pending_jobs = [jobs_map[jid] for jid in job_ids if jid in jobs_map]
    else:
        query = db.query(Job).filter(Job.role_category.is_(None))
        if max_jobs:
            query = query.limit(max_jobs)
        pending_jobs = query.all()

    total_to_process = len(pending_jobs)

    if total_to_process == 0:
        return {"total_jobs": 0, "batches": 0, "success": 0, "errors": 0}

    results = {
        "total_jobs": total_to_process,
        "batches": 0,
        "success": 0,
        "errors": 0,
        "batch_reports": []
    }

    # Process in batches
    for i in range(0, total_to_process, batch_size):
        batch = pending_jobs[i:i + batch_size]
        batch_idx = (i // batch_size) + 1

        batch_res = process_classification_batch(
            db=db,
            jobs=batch,
            client=client,
            batch_index=batch_idx
        )

        results["batches"] += 1
        results["success"] += batch_res["success"]
        results["errors"] += batch_res["errors"]
        results["batch_reports"].append(batch_res)

        # Apply configurable pacing between batches (does not sleep after final batch)
        if i + batch_size < total_to_process:
            time.sleep(settings.GEMINI_REQUEST_DELAY_SECONDS)

    return results
