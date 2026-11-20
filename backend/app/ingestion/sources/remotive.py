"""Remotive Source Adapter.

Fetches remote tech openings from the official public JSON API of Remotive.
is_indian_source = False; records must pass strict India/Worldwide geographic filtering.
"""
import json
import urllib.request
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from app.ingestion.sources.base import BaseSourceAdapter
from app.ingestion.sources.hasjob import sanitize_html


class RemotiveAdapter(BaseSourceAdapter):
    """Adapter for Remotive public REST API."""

    source_name: str = "remotive"
    is_indian_source: bool = False
    api_url: str = "https://remotive.com/api/remote-jobs"

    def fetch_records(self) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch remote jobs from Remotive API."""
        requests_made = 0
        records: List[Dict[str, Any]] = []

        try:
            req = urllib.request.Request(
                self.api_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeepJobAggregator/1.0"}
            )
            requests_made += 1

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            raw_jobs = data.get("jobs", [])

            for job in raw_jobs:
                job_id = str(job.get("id", ""))
                title = job.get("title", "").strip()
                company = job.get("company_name", "").strip() or None
                raw_loc = job.get("candidate_required_location", "").strip() or None
                raw_desc = job.get("description", "").strip() or None
                description = sanitize_html(raw_desc) if raw_desc else None
                apply_url = job.get("url", "").strip()
                pub_date_str = job.get("publication_date", "").strip()

                if not title or not apply_url:
                    continue

                posted_at = None
                if pub_date_str:
                    try:
                        posted_at = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                records.append({
                    "source": self.source_name,
                    "external_id": job_id or apply_url,
                    "title": title,
                    "company": company,
                    "raw_location": raw_loc,
                    "description": description,
                    "apply_url": apply_url,
                    "posted_at": posted_at
                })

            return records, requests_made, None

        except Exception as e:
            return records, requests_made, f"Remotive fetch failed: {str(e)}"
