"""Adzuna India Source Adapter.

Fetches India fresher/internship listings from the official Adzuna Developer API (/in).
Activates only when ADZUNA_APP_ID and ADZUNA_APP_KEY are present in configuration.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from app.config import settings
from app.ingestion.sources.base import BaseSourceAdapter


class AdzunaAdapter(BaseSourceAdapter):
    """Adapter for Adzuna India Developer API."""

    source_name: str = "adzuna"
    is_indian_source: bool = True
    base_url: str = "https://api.adzuna.com/v1/api/jobs/in/search"

    def is_configured(self) -> bool:
        """Check if required API credentials exist."""
        return bool(settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY)

    def fetch_records(self, max_pages: int = 2) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch jobs from Adzuna India API across multiple search queries."""
        if not self.is_configured():
            return [], 0, "Adzuna credentials (ADZUNA_APP_ID / ADZUNA_APP_KEY) not configured; skipped."

        requests_made = 0
        records: List[Dict[str, Any]] = []
        queries = ["fresher software engineer", "intern", "junior developer"]

        try:
            for query in queries:
                for page in range(1, max_pages + 1):
                    params = {
                        "app_id": settings.ADZUNA_APP_ID,
                        "app_key": settings.ADZUNA_APP_KEY,
                        "results_per_page": 50,
                        "what": query,
                        "content-type": "application/json"
                    }
                    encoded_params = urllib.parse.urlencode(params)
                    url = f"{self.base_url}/{page}?{encoded_params}"

                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeepJobAggregator/1.0"}
                    )
                    requests_made += 1

                    with urllib.request.urlopen(req, timeout=12) as response:
                        data = json.loads(response.read().decode("utf-8"))

                    results = data.get("results", [])
                    if not results:
                        break

                    for item in results:
                        job_id = str(item.get("id", ""))
                        title = item.get("title", "").strip()
                        company = item.get("company", {}).get("display_name", "").strip() or None
                        location_data = item.get("location", {})
                        raw_loc = location_data.get("display_name", "") or None
                        description = item.get("description", "").strip() or None
                        apply_url = item.get("redirect_url", "").strip()
                        created_str = item.get("created", "").strip()

                        if not title or not apply_url:
                            continue

                        posted_at = None
                        if created_str:
                            try:
                                posted_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
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
            return records, requests_made, f"Adzuna fetch failed: {str(e)}"
