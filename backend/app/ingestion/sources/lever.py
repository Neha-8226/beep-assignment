"""Lever Postings Source Adapter.

Reusable provider adapter for companies hosting careers on Lever.
Connects to the official public Lever Postings API:
https://api.lever.co/v0/postings/{slug}?mode=json

Features:
- Configurable 20-second timeout.
- Exponential backoff with jitter on socket timeouts, connection errors, HTTP 429, and HTTP 5xx.
- Strict compliance with Retry-After headers.
- Immediate failure without retry on permanent client errors (HTTP 401, 403, 404).
- Distinguishes empty responses from failed requests.
- HTML and plain-text description normalization.
- Stable external IDs (lever_{slug}_{job_id}).
- Employer identity preservation.
- Active posting tracking (detects disappeared/closed jobs).
"""
import time
import random
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Tuple, Optional, Set
import requests
from requests.exceptions import Timeout, ConnectionError, RequestException
from sqlalchemy.orm import Session

from app.ingestion.sources.base import BaseSourceAdapter
from app.ingestion.sources.hasjob import sanitize_html
from app.ingestion.sources.company_registry import (
    ATSCompany,
    get_verified_companies,
    resolve_employer_identity
)

logger = logging.getLogger(__name__)


def parse_retry_after(header_value: Optional[str], default_backoff: float = 2.0, max_wait: float = 30.0) -> float:
    """Parse HTTP Retry-After header into sleep seconds.

    Supports integer seconds or RFC-2822 date formats, capped at max_wait.
    """
    if not header_value or not isinstance(header_value, str):
        return default_backoff

    clean_val = header_value.strip()
    # Case 1: Integer seconds
    if clean_val.isdigit():
        sec = float(clean_val)
        return min(max(sec, 0.5), max_wait)

    # Case 2: HTTP date
    try:
        retry_date = parsedate_to_datetime(clean_val)
        now = datetime.now(timezone.utc)
        diff = (retry_date - now).total_seconds()
        return min(max(diff, 0.5), max_wait)
    except Exception:
        return default_backoff


class LeverAdapter(BaseSourceAdapter):
    """Reusable source adapter for Lever Postings API."""

    source_name: str = "lever"
    is_indian_source: bool = False  # Location-checked via geographic eligibility

    def __init__(
        self,
        companies: Optional[List[ATSCompany]] = None,
        timeout: float = 20.0,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeepJobAggregator/1.0",
        session: Optional[requests.Session] = None
    ):
        """Initialize adapter with specific or default verified Lever companies."""
        if companies is not None:
            self.companies = companies
        else:
            self.companies = get_verified_companies(provider="lever", active_only=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.user_agent = user_agent
        self.session = session or requests.Session()

    def fetch_company_records(
        self, company: ATSCompany
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch and parse all job postings for a single Lever company.

        Implements retry loop with exponential backoff, jitter, and Retry-After handling.
        Never retries permanent client errors (401, 403, 404).

        Returns:
            Tuple of (records, requests_made, error_msg)
        """
        slug = company.token_or_slug.strip()
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json"
        }

        requests_made = 0
        last_error: Optional[str] = None
        data: Optional[List[Dict[str, Any]]] = None

        for attempt in range(1, self.max_retries + 1):
            requests_made += 1
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)

                # Permanent client errors: fail immediately without retry
                if resp.status_code in (401, 403, 404):
                    return (
                        [],
                        requests_made,
                        f"Permanent client error HTTP {resp.status_code} for Lever slug '{slug}' (no retry)"
                    )

                # Rate limited (429) or transient server errors (5xx)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    retry_after_sec = parse_retry_after(
                        resp.headers.get("Retry-After"),
                        default_backoff=self.base_backoff * (2 ** (attempt - 1))
                    )
                    jitter = random.uniform(0.1, 0.5)
                    wait_time = retry_after_sec + jitter
                    last_error = f"HTTP {resp.status_code} on attempt {attempt}/{self.max_retries}"
                    if attempt < self.max_retries:
                        logger.warning(
                            f"Lever slug '{slug}' encountered {last_error}; sleeping {wait_time:.2f}s before retry"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        return [], requests_made, f"Exhausted retries for Lever slug '{slug}': {last_error}"

                # Successful HTTP 200
                if resp.status_code == 200:
                    try:
                        parsed = resp.json()
                        if isinstance(parsed, list):
                            data = parsed
                            last_error = None
                            break
                        else:
                            return [], requests_made, f"Unexpected non-list JSON payload for Lever slug '{slug}'"
                    except Exception as je:
                        last_error = f"JSON decode error for Lever slug '{slug}': {str(je)}"
                        if attempt < self.max_retries:
                            time.sleep(self.base_backoff * attempt)
                            continue
                        return [], requests_made, last_error

                # Other unexpected HTTP status codes
                last_error = f"Unexpected HTTP status {resp.status_code} for Lever slug '{slug}'"
                if attempt < self.max_retries:
                    time.sleep(self.base_backoff * attempt)
                    continue
                return [], requests_made, last_error

            except (Timeout, ConnectionError) as net_err:
                err_type = "Timeout" if isinstance(net_err, Timeout) else "ConnectionError"
                last_error = f"{err_type} on attempt {attempt}/{self.max_retries} for Lever slug '{slug}': {str(net_err)}"
                if attempt < self.max_retries:
                    backoff = (self.base_backoff * (2 ** (attempt - 1))) + random.uniform(0.1, 0.5)
                    logger.warning(f"Lever transient network issue: {last_error}; sleeping {backoff:.2f}s")
                    time.sleep(backoff)
                    continue
                return [], requests_made, f"Exhausted retries after network errors for Lever slug '{slug}': {str(net_err)}"

            except RequestException as req_err:
                last_error = f"RequestException for Lever slug '{slug}': {str(req_err)}"
                return [], requests_made, last_error

        if data is None:
            return [], requests_made, last_error or f"Failed to retrieve data for Lever slug '{slug}'"

        # Parsing postings
        records: List[Dict[str, Any]] = []
        for post in data:
            if not isinstance(post, dict):
                continue

            raw_id = post.get("id")
            post_id = str(raw_id).strip() if raw_id is not None else ""
            raw_title = post.get("text")
            title = str(raw_title).strip() if raw_title is not None else ""
            raw_apply = post.get("applyUrl") or post.get("hostedUrl")
            apply_url = str(raw_apply).strip() if raw_apply is not None else ""

            if not post_id or post_id == "None" or not title or not apply_url:
                continue

            # Location extraction
            categories = post.get("categories") or {}
            raw_loc = None
            if isinstance(categories, dict):
                raw_loc = categories.get("location")
                if not raw_loc:
                    all_locs = categories.get("allLocations")
                    if isinstance(all_locs, list) and all_locs:
                        raw_loc = ", ".join(str(l) for l in all_locs if l)

            if raw_loc:
                raw_loc = str(raw_loc).strip() or None

            # Description extraction (plain text preferred, otherwise sanitized HTML)
            description = None
            desc_plain = post.get("descriptionPlain")
            if desc_plain and isinstance(desc_plain, str) and desc_plain.strip():
                description = desc_plain.strip()
            else:
                raw_html = post.get("description")
                if raw_html and isinstance(raw_html, str):
                    description = sanitize_html(raw_html)

            # Timestamp parsing (createdAt epoch ms)
            posted_at = None
            created_at_ms = post.get("createdAt")
            if isinstance(created_at_ms, (int, float)) and created_at_ms > 0:
                try:
                    posted_at = datetime.fromtimestamp(created_at_ms / 1000.0, tz=timezone.utc)
                except Exception:
                    posted_at = None

            # Employer identity resolution
            posting_org, hiring_org, display_company = resolve_employer_identity(
                company=company,
                title=title,
                description=description
            )

            record: Dict[str, Any] = {
                "title": title,
                "apply_url": apply_url,
                "external_id": f"lever_{slug}_{post_id}",
                "company": display_company,
                "raw_location": raw_loc,
                "description": description,
                "posted_at": posted_at,
                "source": self.source_name,
                # Extended employer identity attributes
                "posting_organization": posting_org,
                "hiring_organization": hiring_org,
                "board_slug": slug,
            }
            records.append(record)

        return records, requests_made, None

    def fetch_records(self) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch records across all registered Lever companies.

        Returns:
            Tuple of (aggregated_records, total_requests, composite_error)
        """
        all_records: List[Dict[str, Any]] = []
        total_requests = 0
        errors: List[str] = []

        for company in self.companies:
            records, reqs, err = self.fetch_company_records(company)
            total_requests += reqs
            if err:
                errors.append(err)
            all_records.extend(records)

        composite_error = "; ".join(errors) if errors else None
        return all_records, total_requests, composite_error

    @staticmethod
    def track_disappeared_postings(
        db: Session,
        slug: str,
        active_external_ids: Set[str]
    ) -> List[int]:
        """Detect and mark inactive postings that disappeared from a Lever board.

        Args:
            db: Active database session.
            slug: Lever company slug (e.g. 'meesho').
            active_external_ids: Set of external_ids currently present in feed.

        Returns:
            List of Job IDs that were marked inactive.
        """
        from app.models import Job

        prefix = f"lever_{slug.lower().strip()}_"
        stored_jobs = db.query(Job).filter(
            Job.source == "lever",
            Job.external_id.startswith(prefix),
            Job.is_active == True
        ).all()

        disappeared_ids: List[int] = []
        for job in stored_jobs:
            if job.external_id not in active_external_ids:
                job.is_active = False
                disappeared_ids.append(job.id)

        if disappeared_ids:
            db.commit()

        return disappeared_ids
