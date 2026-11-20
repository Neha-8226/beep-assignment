"""ATS Company Registry.

Central registry for verified company ATS endpoints (Greenhouse & Lever).
Only verified companies from Phase 1 & 2 pilots are registered here.
Unverified sources (e.g. GitLab, Porter) are strictly excluded until audited.
"""
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple


@dataclass(frozen=True)
class ATSCompany:
    """Configuration and identity definition for a company ATS board."""
    token_or_slug: str                  # Board token (Greenhouse) or slug (Lever)
    provider: str                       # 'greenhouse' or 'lever'
    name: str                           # Display name
    posting_organization: str          # Board owner / posting organization
    client_staffing_agency: bool = False # True if company hosts gigs on behalf of third-party clients
    is_active: bool = True
    default_location_context: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Initial Verified Registry (Milestone 6B Pilot Verified Companies Only)
# ---------------------------------------------------------------------------

VERIFIED_COMPANIES: List[ATSCompany] = [
    # Greenhouse boards verified in Phase 1 & 2
    ATSCompany(
        token_or_slug="inmobi",
        provider="greenhouse",
        name="InMobi",
        posting_organization="InMobi",
        client_staffing_agency=False,
        default_location_context="India / Global",
        notes="Verified in Phase 1 pilot. Direct employer."
    ),
    ATSCompany(
        token_or_slug="instawork",
        provider="greenhouse",
        name="Instawork",
        posting_organization="Instawork",
        client_staffing_agency=True,
        default_location_context="India / Global",
        notes="Verified in Phase 1 pilot. Staffing platform; hosts gigs on behalf of robotics/AI clients."
    ),
    ATSCompany(
        token_or_slug="6sense",
        provider="greenhouse",
        name="6sense",
        posting_organization="6sense",
        client_staffing_agency=False,
        default_location_context="India / Global",
        notes="Verified in Phase 1 pilot. Direct employer."
    ),
    ATSCompany(
        token_or_slug="devrev",
        provider="greenhouse",
        name="DevRev",
        posting_organization="DevRev",
        client_staffing_agency=False,
        default_location_context="India / Global",
        notes="Verified in Phase 1 pilot. Direct employer."
    ),
    # Lever postings verified in Phase 1 & 2
    ATSCompany(
        token_or_slug="meesho",
        provider="lever",
        name="Meesho",
        posting_organization="Meesho",
        client_staffing_agency=False,
        default_location_context="India",
        notes="Verified in Phase 1 & 2 pilot. Direct employer with transient latency."
    ),
    ATSCompany(
        token_or_slug="coupa",
        provider="lever",
        name="Coupa Software",
        posting_organization="Coupa Software",
        client_staffing_agency=False,
        default_location_context="India / Global",
        notes="Verified in Phase 1 pilot. Direct employer."
    ),
    ATSCompany(
        token_or_slug="keyloop",
        provider="lever",
        name="Keyloop",
        posting_organization="Keyloop",
        client_staffing_agency=False,
        default_location_context="India / Global",
        notes="Verified in Phase 1 pilot. Direct employer."
    ),
    # Phase 5 Batch 1 Approved Additions
    ATSCompany(
        token_or_slug="sigmoid",
        provider="greenhouse",
        name="Sigmoid",
        posting_organization="Sigmoid",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Phase 5 Batch 1. Direct employer."
    ),
    ATSCompany(
        token_or_slug="gitlab",
        provider="greenhouse",
        name="GitLab",
        posting_organization="GitLab",
        client_staffing_agency=False,
        default_location_context="India / Global Remote",
        notes="Verified in Phase 5 Batch 1. Direct employer."
    ),
    ATSCompany(
        token_or_slug="100ms",
        provider="lever",
        name="100ms",
        posting_organization="100ms",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Phase 5 Batch 1. Direct employer."
    ),
    # Phase 7 Batch 2 Approved Additions
    ATSCompany(
        token_or_slug="hackerrank",
        provider="greenhouse",
        name="HackerRank",
        posting_organization="HackerRank",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Phase 6 Batch 2. Direct employer."
    ),
    ATSCompany(
        token_or_slug="cred",
        provider="lever",
        name="CRED",
        posting_organization="CRED",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Phase 6 Batch 2. Direct employer."
    ),
    ATSCompany(
        token_or_slug="mindtickle",
        provider="lever",
        name="Mindtickle",
        posting_organization="Mindtickle",
        client_staffing_agency=False,
        default_location_context="Pune / Bengaluru, India",
        notes="Verified in Phase 6 Batch 2. Direct employer."
    ),
    ATSCompany(
        token_or_slug="jumpcloud",
        provider="lever",
        name="JumpCloud",
        posting_organization="JumpCloud",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India - Remote",
        notes="Verified in Phase 6 Batch 2. Direct employer."
    ),
    # Milestone 8 Phase 2 Batch 3 Approved Additions
    ATSCompany(
        token_or_slug="capco",
        provider="greenhouse",
        name="Capco",
        posting_organization="Capco",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="purestorage",
        provider="greenhouse",
        name="Pure Storage",
        posting_organization="Pure Storage",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="zscaler",
        provider="greenhouse",
        name="Zscaler",
        posting_organization="Zscaler",
        client_staffing_agency=False,
        default_location_context="Bengaluru / Chandigarh, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="rubrik",
        provider="greenhouse",
        name="Rubrik",
        posting_organization="Rubrik",
        client_staffing_agency=False,
        default_location_context="Bengaluru / Pune, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="stripe",
        provider="greenhouse",
        name="Stripe",
        posting_organization="Stripe",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="okta",
        provider="greenhouse",
        name="Okta",
        posting_organization="Okta",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="mongodb",
        provider="greenhouse",
        name="MongoDB",
        posting_organization="MongoDB",
        client_staffing_agency=False,
        default_location_context="Bengaluru / Gurugram, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="enterpret",
        provider="greenhouse",
        name="Enterpret",
        posting_organization="Enterpret",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="cordance",
        provider="greenhouse",
        name="Cordance",
        posting_organization="Cordance",
        client_staffing_agency=False,
        default_location_context="Pune, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="celonis",
        provider="greenhouse",
        name="Celonis",
        posting_organization="Celonis",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="datadog",
        provider="greenhouse",
        name="Datadog",
        posting_organization="Datadog",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="elastic",
        provider="greenhouse",
        name="Elastic",
        posting_organization="Elastic",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="groww",
        provider="greenhouse",
        name="Groww",
        posting_organization="Groww",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="roblox",
        provider="greenhouse",
        name="Roblox",
        posting_organization="Roblox",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="agoda",
        provider="greenhouse",
        name="Agoda",
        posting_organization="Agoda",
        client_staffing_agency=False,
        default_location_context="Gurugram, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="twilio",
        provider="greenhouse",
        name="Twilio",
        posting_organization="Twilio",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="point72",
        provider="greenhouse",
        name="Point72",
        posting_organization="Point72",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="figma",
        provider="greenhouse",
        name="Figma",
        posting_organization="Figma",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="paytm",
        provider="lever",
        name="Paytm",
        posting_organization="Paytm",
        client_staffing_agency=False,
        default_location_context="Noida / Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="zeta",
        provider="lever",
        name="Zeta",
        posting_organization="Zeta",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    ATSCompany(
        token_or_slug="hevodata",
        provider="lever",
        name="Hevo Data",
        posting_organization="Hevo Data",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 3. Direct employer."
    ),
    # Milestone 8 Phase 2 Batch 4 Approved Additions
    ATSCompany(
        token_or_slug="canonical",
        provider="greenhouse",
        name="Canonical",
        posting_organization="Canonical",
        client_staffing_agency=False,
        default_location_context="India - Remote / Worldwide",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="fivetran",
        provider="greenhouse",
        name="Fivetran",
        posting_organization="Fivetran",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="cloudsek",
        provider="greenhouse",
        name="CloudSEK",
        posting_organization="CloudSEK",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="twinhealth",
        provider="greenhouse",
        name="Twin Health",
        posting_organization="Twin Health",
        client_staffing_agency=False,
        default_location_context="Chennai / Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="prodigal",
        provider="greenhouse",
        name="Prodigal",
        posting_organization="Prodigal",
        client_staffing_agency=False,
        default_location_context="Mumbai, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="zetaglobal",
        provider="greenhouse",
        name="Zeta Global",
        posting_organization="Zeta Global",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="worldquant",
        provider="greenhouse",
        name="WorldQuant",
        posting_organization="WorldQuant",
        client_staffing_agency=False,
        default_location_context="Mumbai / Gurugram, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="imc",
        provider="greenhouse",
        name="IMC Trading",
        posting_organization="IMC Trading",
        client_staffing_agency=False,
        default_location_context="Mumbai, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="squarepointcapital",
        provider="greenhouse",
        name="Squarepoint Capital",
        posting_organization="Squarepoint Capital",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="exoduspoint",
        provider="greenhouse",
        name="ExodusPoint",
        posting_organization="ExodusPoint",
        client_staffing_agency=False,
        default_location_context="Bengaluru / Mumbai, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="towerresearchcapital",
        provider="greenhouse",
        name="Tower Research Capital",
        posting_organization="Tower Research Capital",
        client_staffing_agency=False,
        default_location_context="Gurugram, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="starburst",
        provider="greenhouse",
        name="Starburst",
        posting_organization="Starburst",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="anydesk",
        provider="greenhouse",
        name="AnyDesk",
        posting_organization="AnyDesk",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="binance",
        provider="greenhouse",
        name="Binance",
        posting_organization="Binance",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="bitgo",
        provider="greenhouse",
        name="BitGo",
        posting_organization="BitGo",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="nice",
        provider="greenhouse",
        name="NICE Systems",
        posting_organization="NICE Systems",
        client_staffing_agency=False,
        default_location_context="Pune / Mumbai, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="aqr",
        provider="greenhouse",
        name="AQR Capital",
        posting_organization="AQR Capital",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="akunacapital",
        provider="greenhouse",
        name="Akuna Capital",
        posting_organization="Akuna Capital",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="adyen",
        provider="greenhouse",
        name="Adyen",
        posting_organization="Adyen",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="deliveroo",
        provider="greenhouse",
        name="Deliveroo",
        posting_organization="Deliveroo",
        client_staffing_agency=False,
        default_location_context="Hyderabad, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="dialpad",
        provider="greenhouse",
        name="Dialpad",
        posting_organization="Dialpad",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="five9",
        provider="greenhouse",
        name="Five9",
        posting_organization="Five9",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="anthropic",
        provider="greenhouse",
        name="Anthropic",
        posting_organization="Anthropic",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="scaleai",
        provider="greenhouse",
        name="Scale AI",
        posting_organization="Scale AI",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="cyderes",
        provider="lever",
        name="Cyderes",
        posting_organization="Cyderes",
        client_staffing_agency=False,
        default_location_context="Bengaluru, India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="collabora",
        provider="lever",
        name="Collabora",
        posting_organization="Collabora",
        client_staffing_agency=False,
        default_location_context="India - Remote / Worldwide",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="crypto",
        provider="lever",
        name="Crypto.com",
        posting_organization="Crypto.com",
        client_staffing_agency=False,
        default_location_context="India - Remote / Worldwide",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
    ATSCompany(
        token_or_slug="outreach",
        provider="lever",
        name="Outreach",
        posting_organization="Outreach",
        client_staffing_agency=False,
        default_location_context="India - Remote",
        notes="Verified in Milestone 8 Phase 2 Batch 4. Direct employer."
    ),
]


def get_verified_companies(provider: Optional[str] = None, active_only: bool = True) -> List[ATSCompany]:
    """Retrieve verified companies, optionally filtered by ATS provider."""
    companies = VERIFIED_COMPANIES
    if provider:
        prov = provider.lower().strip()
        companies = [c for c in companies if c.provider == prov]
    if active_only:
        companies = [c for c in companies if c.is_active]
    return list(companies)


def get_company_by_slug(token_or_slug: str, provider: Optional[str] = None) -> Optional[ATSCompany]:
    """Find a company by token/slug and optional provider."""
    slug = token_or_slug.lower().strip()
    for c in VERIFIED_COMPANIES:
        if c.token_or_slug.lower() == slug:
            if provider is None or c.provider == provider.lower().strip():
                return c
    return None


# ---------------------------------------------------------------------------
# Employer Identity Extraction
# ---------------------------------------------------------------------------

CLIENT_EXTRACTION_REGEX = re.compile(
    r"\b(?:hiring\s+(?:on\s+behalf\s+of|for)|partner(?:ed)?\s+with|client(?:\s+is)?)\s+([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*)*)\b"
)


def resolve_employer_identity(
    company: ATSCompany,
    title: str,
    description: Optional[str]
) -> Tuple[str, Optional[str], str]:
    """Resolve employer identity distinctions with strict client protection.

    Distinguishes:
    - posting_org: entity operating the ATS job board (e.g. 'Instawork')
    - hiring_org: actual organization hiring the worker (e.g. named client or None if unstated)
    - display_company: company label stored in database (never falsely labels staffing platform as employer)

    Returns:
        Tuple of (posting_org, hiring_org, display_company)
    """
    posting_org = company.posting_organization or company.name

    if not company.client_staffing_agency:
        # Standard direct employer
        return posting_org, company.name, company.name

    # Client/staffing platform (e.g. Instawork hosting AI robotics data collection gigs)
    hiring_org = None
    combined_text = f"{title} {description or ''}"
    match = CLIENT_EXTRACTION_REGEX.search(combined_text)
    if match:
        cand = match.group(1).strip()
        # Clean trailing punctuation
        cand = re.sub(r"[\.,;:!\(\)]+$", "", cand).strip()
        if cand and len(cand) > 2 and not re.search(r"\b(?:our|an?|the|team|project)\b", cand, re.I):
            hiring_org = cand

    if hiring_org:
        display_company = f"{hiring_org} (via {posting_org})"
    else:
        # Client name is unstated/ambiguous in posting; preserve None and do NOT fabricate
        display_company = f"{posting_org} (Client Project)"

    return posting_org, hiring_org, display_company
