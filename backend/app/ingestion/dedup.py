"""Multi-Layer Deduplication Engine.

Implements traceable, tiered duplicate detection:
1. Tier 1 (Strong Match): Exact (source, external_id) duplicate in database.
2. Tier 2 (Strong Match): Exact canonical URL hash match across any source.
3. Tier 3 (Potential Duplicate): Normalized Title + Company + Location match.
   Performs additional checks: preserves evidence, records candidate details,
   and flags potential duplicates without destructive data loss.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models import Job, DuplicateRecord
from app.ingestion.normalizer import (
    normalize_url,
    hash_url,
    compute_content_hash,
    generate_fallback_external_id,
    normalize_text
)


@dataclass
class DeduplicationResult:
    """Detailed result of duplicate evaluation with auditable evidence."""
    is_unique: bool
    duplicate_type: Optional[str]  # 'confirmed', 'potential', or None
    duplicate_reason: Optional[str]  # 'source_id_match', 'canonical_url_match', 'content_similarity_flag'
    canonical_job: Optional[Job]
    evidence: Optional[str]


def evaluate_candidate(
    db: Session,
    source: str,
    title: str,
    apply_url: str,
    external_id: Optional[str] = None,
    company: Optional[str] = None,
    raw_location: Optional[str] = None,
    description: Optional[str] = None
) -> DeduplicationResult:
    """Evaluate whether a candidate job is unique, a confirmed duplicate, or a potential duplicate.

    Guarantees:
    - Never mutates the database on inspection; returns structured decision.
    - Preserves evidence string for traceability.
    """
    clean_url = normalize_url(apply_url)
    url_hash = hash_url(clean_url)

    # Generate fallback ID if not supplied by the source
    eff_external_id = external_id or generate_fallback_external_id(
        source=source,
        title=title,
        company=company,
        clean_url=clean_url
    )

    content_hash = compute_content_hash(
        title=title,
        company=company,
        raw_location=raw_location
    )

    # -------------------------------------------------------------------------
    # Tier 1: Strong Match - Exact Source + External ID
    # -------------------------------------------------------------------------
    existing_by_source_id = db.query(Job).filter(
        Job.source == source,
        Job.external_id == eff_external_id
    ).first()

    if existing_by_source_id:
        return DeduplicationResult(
            is_unique=False,
            duplicate_type="confirmed",
            duplicate_reason="source_id_match",
            canonical_job=existing_by_source_id,
            evidence=f"Matched existing job #{existing_by_source_id.id} by source='{source}' and external_id='{eff_external_id}'"
        )

    # -------------------------------------------------------------------------
    # Tier 2: Strong Match - Canonical URL Hash
    # -------------------------------------------------------------------------
    existing_by_url = db.query(Job).filter(
        Job.canonical_url_hash == url_hash
    ).first()

    if existing_by_url:
        return DeduplicationResult(
            is_unique=False,
            duplicate_type="confirmed",
            duplicate_reason="canonical_url_match",
            canonical_job=existing_by_url,
            evidence=f"Matched canonical URL hash '{url_hash[:12]}...' of job #{existing_by_url.id} ('{existing_by_url.title}' at {existing_by_url.company})"
        )

    # -------------------------------------------------------------------------
    # Tier 3: Potential Duplicate - Normalized Content Similarity
    # -------------------------------------------------------------------------
    existing_by_content = db.query(Job).filter(
        Job.content_hash == content_hash
    ).first()

    if existing_by_content:
        # Additional inspection: Same title + company + location, but different URL
        evidence_msg = (
            f"Content similarity flag: Job #{existing_by_content.id} matches normalized "
            f"title='{normalize_text(title)}', company='{normalize_text(company)}', "
            f"location='{normalize_text(raw_location)}'. URLs differ: "
            f"existing='{existing_by_content.apply_url[:60]}...' vs incoming='{clean_url[:60]}...'"
        )
        return DeduplicationResult(
            is_unique=False,
            duplicate_type="potential",
            duplicate_reason="content_similarity_flag",
            canonical_job=existing_by_content,
            evidence=evidence_msg
        )

    # Unique candidate
    return DeduplicationResult(
        is_unique=True,
        duplicate_type=None,
        duplicate_reason=None,
        canonical_job=None,
        evidence=None
    )


def record_duplicate(
    db: Session,
    source: str,
    title: str,
    apply_url: str,
    result: DeduplicationResult,
    external_id: Optional[str] = None,
    company: Optional[str] = None,
    raw_location: Optional[str] = None
) -> DuplicateRecord:
    """Record duplicate candidate into the traceable audit table duplicate_records."""
    clean_url = normalize_url(apply_url)
    url_hash = hash_url(clean_url)
    eff_id = external_id or generate_fallback_external_id(
        source=source, title=title, company=company, clean_url=clean_url
    )
    content_hash = compute_content_hash(
        title=title, company=company, raw_location=raw_location
    )

    dup = DuplicateRecord(
        source=source,
        external_id=eff_id,
        title=title,
        company=company,
        raw_location=raw_location,
        apply_url=apply_url,
        canonical_url_hash=url_hash,
        content_hash=content_hash,
        duplicate_type=result.duplicate_type or "confirmed",
        duplicate_reason=result.duplicate_reason or "unknown",
        evidence=result.evidence,
        canonical_job_id=result.canonical_job.id if result.canonical_job else None
    )
    db.add(dup)
    db.flush()
    return dup
