"""Base Source Adapter Interface.

Defines standard interface for all job board and feed adapters:
- Standardized dictionary format for fetched records.
- Request counting and error isolation.
- Flag indicating whether the source is intrinsically India-based.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional


class BaseSourceAdapter(ABC):
    """Abstract base class for job data source adapters."""

    source_name: str = "base"
    is_indian_source: bool = False

    @abstractmethod
    def fetch_records(self) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch raw job records from the upstream API or feed.

        Returns:
            Tuple of:
            - records: List of raw dictionaries with keys:
                - title (str, required)
                - apply_url (str, required)
                - external_id (Optional[str])
                - company (Optional[str])
                - raw_location (Optional[str])
                - description (Optional[str])
                - posted_at (Optional[datetime])
                - source (str)
            - requests_made: Number of HTTP calls executed.
            - error: Error message if fetch failed; None on success.
        """
        pass
