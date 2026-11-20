"""Job board and feed source adapters."""
from app.ingestion.sources.base import BaseSourceAdapter
from app.ingestion.sources.hasjob import HasjobAdapter
from app.ingestion.sources.remotive import RemotiveAdapter
from app.ingestion.sources.adzuna import AdzunaAdapter
from app.ingestion.sources.company_registry import (
    ATSCompany,
    VERIFIED_COMPANIES,
    get_verified_companies,
    get_company_by_slug,
    resolve_employer_identity
)
from app.ingestion.sources.greenhouse import GreenhouseAdapter
from app.ingestion.sources.lever import LeverAdapter

__all__ = [
    "BaseSourceAdapter",
    "HasjobAdapter",
    "RemotiveAdapter",
    "AdzunaAdapter",
    "ATSCompany",
    "VERIFIED_COMPANIES",
    "get_verified_companies",
    "get_company_by_slug",
    "resolve_employer_identity",
    "GreenhouseAdapter",
    "LeverAdapter",
]
