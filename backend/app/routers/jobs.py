"""Jobs Search & Filtering Router.

Provides fast, indexed REST endpoints for:
1. Paginated job listings with keyword search and multi-select filters.
2. Single job detail retrieval.
3. Dynamic filter facets (available roles, cities, and counts).
"""
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc, func

from app.database import get_db
from app.models import Job
from app.schemas import JobResponse, JobListResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def parse_comma_separated(param: Optional[List[str]]) -> List[str]:
    """Support both repeated query params (?role=A&role=B) and comma-separated (?role=A,B)."""
    if not param:
        return []
    items = []
    for p in param:
        for sub in p.split(","):
            cleaned = sub.strip()
            if cleaned:
                items.append(cleaned)
    return items


@router.get("", response_model=JobListResponse)
def list_jobs(
    q: Optional[str] = Query(None, description="Free-text search across title, company, and description"),
    role: Optional[List[str]] = Query(None, description="Filter by role category (multi-select supported)"),
    city: Optional[List[str]] = Query(None, description="Filter by standardized city (multi-select supported)"),
    job_type: Optional[List[str]] = Query(None, description="Filter by job type (multi-select supported, e.g. 'Full-Time', 'Internship')"),
    fresher_only: bool = Query(False, description="If true, returns only confirmed fresher-friendly positions"),
    fresher_status: Optional[str] = Query(None, description="Filter by explicit 3-state status: 'fresher_friendly', 'not_fresher_friendly', 'uncertain', or 'pending'"),
    source: Optional[List[str]] = Query(None, description="Filter by upstream source (multi-select supported, e.g. 'hasjob', 'remotive')"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("recent", description="'recent', 'title', or 'company'"),
    db: Session = Depends(get_db)
):
    """Search and filter canonical job listings with pagination."""
    query = db.query(Job).filter(Job.is_active.is_(True))

    # Free-text keyword search with wildcard escaping
    if q and q.strip():
        cleaned_q = q.strip().lower()
        # Escape SQL LIKE wildcard characters '%', '_', and the escape character '/'
        escaped_q = (
            cleaned_q
            .replace("/", "//")
            .replace("%", "/%")
            .replace("_", "/_")
        )
        term = f"%{escaped_q}%"
        query = query.filter(
            or_(
                func.lower(Job.title).like(term, escape="/"),
                func.lower(Job.company).like(term, escape="/"),
                func.lower(Job.description).like(term, escape="/")
            )
        )

    # Multi-select Role Filter
    roles = parse_comma_separated(role)
    if roles:
        query = query.filter(Job.role_category.in_(roles))

    # Multi-select City Filter
    cities = parse_comma_separated(city)
    if cities:
        query = query.filter(Job.standardized_city.in_(cities))

    # Multi-select Job Type Filter
    job_types = parse_comma_separated(job_type)
    if job_types:
        query = query.filter(Job.job_type.in_(job_types))

    # Fresher Filters: Backward compatible fresher_only + explicit status filters
    if fresher_only:
        query = query.filter(Job.is_fresher_friendly.is_(True))
    elif fresher_status and fresher_status.strip():
        status_clean = fresher_status.strip().lower()
        if status_clean in ("fresher_friendly", "not_fresher_friendly", "uncertain"):
            query = query.filter(Job.fresher_eligibility_status == status_clean)
        elif status_clean in ("pending", "unstated"):
            # Strictly matches genuinely unclassified/pending jobs (where classification has not occurred)
            query = query.filter(Job.fresher_eligibility_status.is_(None))

    # Multi-select Source Filter
    sources = [s.lower() for s in parse_comma_separated(source)]
    if sources:
        query = query.filter(Job.source.in_(sources))

    # Total matching records count
    total_count = query.count()

    # Sorting with deterministic tie-breaking on Job.id
    if sort_by == "title":
        query = query.order_by(asc(Job.title), asc(Job.id))
    elif sort_by == "company":
        query = query.order_by(asc(Job.company), asc(Job.id))
    else:  # default 'recent'
        # Sort by posted_at descending, fallback to created_at, with Job.id tie-breaker
        query = query.order_by(desc(Job.posted_at), desc(Job.created_at), desc(Job.id))

    # Pagination calculation
    offset = (page - 1) * limit
    jobs_records = query.offset(offset).limit(limit).all()
    total_pages = math.ceil(total_count / limit) if total_count > 0 else 0

    return {
        "total": total_count,
        "page": page,
        "limit": limit,
        "pages": total_pages,
        "jobs": jobs_records
    }


@router.get("/filters", response_model=dict)
def get_filter_facets(db: Session = Depends(get_db)):
    """Return available filter options with active counts to populate UI filter chips."""
    base_query = db.query(Job).filter(Job.is_active.is_(True))

    # Role counts
    role_counts = db.query(
        Job.role_category, func.count(Job.id)
    ).filter(
        Job.is_active.is_(True),
        Job.role_category.isnot(None)
    ).group_by(Job.role_category).all()

    # City counts
    city_counts = db.query(
        Job.standardized_city, func.count(Job.id)
    ).filter(
        Job.is_active.is_(True),
        Job.standardized_city.isnot(None)
    ).group_by(Job.standardized_city).all()

    # Job type counts
    type_counts = db.query(
        Job.job_type, func.count(Job.id)
    ).filter(
        Job.is_active.is_(True),
        Job.job_type.isnot(None)
    ).group_by(Job.job_type).all()

    # Sources counts
    source_counts = db.query(
        Job.source, func.count(Job.id)
    ).filter(
        Job.is_active.is_(True)
    ).group_by(Job.source).all()

    total_jobs = base_query.count()
    fresher_jobs_count = base_query.filter(Job.is_fresher_friendly.is_(True)).count()

    return {
        "total_jobs": total_jobs,
        "fresher_friendly_count": fresher_jobs_count,
        "roles": [{"name": r[0], "count": r[1]} for r in role_counts],
        "cities": [{"name": c[0], "count": c[1]} for c in city_counts],
        "job_types": [{"name": t[0], "count": t[1]} for t in type_counts],
        "sources": [{"name": s[0], "count": s[1]} for s in source_counts]
    }


@router.get("/{job_id}", response_model=JobResponse)
def get_job_by_id(job_id: int, db: Session = Depends(get_db)):
    """Fetch details of a single canonical job listing."""
    job = db.query(Job).filter(Job.id == job_id, Job.is_active.is_(True)).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id {job_id} not found."
        )
    return job
