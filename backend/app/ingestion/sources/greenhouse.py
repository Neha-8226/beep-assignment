"""Greenhouse Job Board Source Adapter.

Reusable provider adapter for companies hosting career boards on Greenhouse.
Connects to the official public Greenhouse Job Board API:
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

Features:
- Configurable company registry iteration.
- Polite request pacing.
- HTML description sanitization.
- Stable external IDs (gh_{board_token}_{job_id}).
- Employer identity preservation (posting org vs. hiring org).
- Preserves distinct shifts and office locations.
- Active posting tracking (detects disappeared/closed jobs).
"""
import time
import html
import json
import logging
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Tuple, Optional, Set
from sqlalchemy.orm import Session

from app.ingestion.sources.base import BaseSourceAdapter
from app.ingestion.sources.hasjob import sanitize_html
from app.ingestion.sources.company_registry import (
    ATSCompany,
    get_verified_companies,
    resolve_employer_identity
)

logger = logging.getLogger(__name__)


def parse_iso_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 or RFC-2822 datetime string to UTC datetime."""
    if not date_str or not isinstance(date_str, str):
        return None
    clean_str = date_str.strip()
    if not clean_str:
        return None
    try:
        # Standard ISO 8601: 2026-03-01T10:00:00Z or with offset
        dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return parsedate_to_datetime(clean_str).astimezone(timezone.utc)
    except Exception:
        return None


class GreenhouseAdapter(BaseSourceAdapter):
    """Reusable source adapter for Greenhouse ATS boards."""

    source_name: str = "greenhouse"
    is_indian_source: bool = False  # Location-checked via geographic eligibility

    def __init__(
        self,
        companies: Optional[List[ATSCompany]] = None,
        timeout: float = 15.0,
        request_pacing_seconds: float = 0.25,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeepJobAggregator/1.0"
    ):
        """Initialize adapter with specific or default verified Greenhouse companies."""
        if companies is not None:
            self.companies = companies
        else:
            self.companies = get_verified_companies(provider="greenhouse", active_only=True)
        self.timeout = timeout
        self.request_pacing_seconds = request_pacing_seconds
        self.user_agent = user_agent

    def fetch_company_records(
        self, company: ATSCompany
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch and parse all job postings for a single Greenhouse company board.

        Returns:
            Tuple of (records, requests_made, error_msg)
        """
        token = company.token_or_slug.strip()
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        requests_made = 1
        records: List[Dict[str, Any]] = []

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                status_code = getattr(response, "status", 200)
                if status_code != 200:
                    return [], requests_made, f"Greenhouse board '{token}' returned HTTP {status_code}"
                raw_body = response.read().decode("utf-8")
                data = json.loads(raw_body)

        except urllib.error.HTTPError as he:
            return [], requests_made, f"HTTP Error {he.code} fetching Greenhouse board '{token}': {he.reason}"
        except urllib.error.URLError as ue:
            return [], requests_made, f"URL Error fetching Greenhouse board '{token}': {str(ue.reason)}"
        except json.JSONDecodeError as je:
            return [], requests_made, f"Invalid JSON from Greenhouse board '{token}': {str(je)}"
        except Exception as ex:
            return [], requests_made, f"Unexpected error fetching Greenhouse board '{token}': {str(ex)}"

        raw_jobs = data.get("jobs", [])
        if not isinstance(raw_jobs, list):
            return [], requests_made, f"Invalid 'jobs' payload from Greenhouse board '{token}'"

        for job in raw_jobs:
            if not isinstance(job, dict):
                continue

            raw_id = job.get("id")
            job_id = str(raw_id).strip() if raw_id is not None else ""
            raw_title = job.get("title")
            title = str(raw_title).strip() if raw_title is not None else ""
            raw_url = job.get("absolute_url")
            apply_url = str(raw_url).strip() if raw_url is not None else ""

            if not job_id or job_id == "None" or not title or not apply_url:
                continue

            # Location extraction (location name or fallback to offices)
            raw_loc = None
            loc_obj = job.get("location")
            if isinstance(loc_obj, dict):
                raw_loc = loc_obj.get("name")
            if not raw_loc:
                offices = job.get("offices", [])
                if isinstance(offices, list) and offices:
                    office_names = [
                        o.get("name") or o.get("location")
                        for o in offices
                        if isinstance(o, dict) and (o.get("name") or o.get("location"))
                    ]
                    if office_names:
                        raw_loc = ", ".join(office_names)

            if raw_loc:
                raw_loc = raw_loc.strip() or None

            # Description extraction and sanitization (Greenhouse content is entity-encoded HTML)
            raw_content = job.get("content", "")
            if raw_content and isinstance(raw_content, str):
                decoded_html = html.unescape(raw_content)
                description = sanitize_html(decoded_html)
            else:
                description = None

            # Timestamp parsing
            posted_at = parse_iso_datetime(job.get("updated_at"))

            # Employer identity resolution
            posting_org, hiring_org, display_company = resolve_employer_identity(
                company=company,
                title=title,
                description=description
            )

            record: Dict[str, Any] = {
                "title": title,
                "apply_url": apply_url,
                "external_id": f"gh_{token}_{job_id}",
                "company": display_company,
                "raw_location": raw_loc,
                "description": description,
                "posted_at": posted_at,
                "source": self.source_name,
                # Extended employer identity attributes
                "posting_organization": posting_org,
                "hiring_organization": hiring_org,
                "board_token": token,
            }
            records.append(record)

        return records, requests_made, None

    def fetch_records(self) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch records across all registered Greenhouse companies with polite pacing.

        Returns:
            Tuple of (aggregated_records, total_requests, composite_error)
        """
        all_records: List[Dict[str, Any]] = []
        total_requests = 0
        errors: List[str] = []

        for i, company in enumerate(self.companies):
            if i > 0 and self.request_pacing_seconds > 0:
                time.sleep(self.request_pacing_seconds)

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
        board_token: str,
        active_external_ids: Set[str]
    ) -> List[int]:
        """Detect and mark inactive postings that disappeared from a Greenhouse board.

        Args:
            db: Active database session.
            board_token: Greenhouse company token (e.g. 'inmobi').
            active_external_ids: Set of external_ids currently present in feed.

        Returns:
            List of Job IDs that were marked inactive.
        """
        from app.models import Job

        prefix = f"gh_{board_token.lower().strip()}_"
        stored_jobs = db.query(Job).filter(
            Job.source == "greenhouse",
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
