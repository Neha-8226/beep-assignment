"""Job Relevance & Seniority Assessment Engine.

Separates orthogonal decision dimensions:
1. Vacancy Type: Individual specific job vacancy vs. broad talent pool / network registration.
2. Seniority & Experience: Context-aware screening to protect freshers while filtering out senior/lead/management roles.
3. India Accessibility: Confirmed via geographic eligibility normalizer.

Every decision returns an auditable RelevanceDecision with category, reason, confidence, and rule version.
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import re

from app.ingestion.normalizer import is_india_eligible, check_geographic_eligibility


@dataclass
class RelevanceDecision:
    """Structured, auditable relevance decision for an ingested candidate."""
    is_accepted: bool      # True if eligible for pipeline ingestion (fresher or uncertain review)
    outcome: str           # 'confirmed_fresher', 'uncertain_review', 'not_fresher_suitable', 'not_individual_vacancy', 'india_ineligible', 'invalid_record'
    category: str          # 'fresher_friendly', 'needs_review', 'seniority_exclusion', 'talent_pool_exclusion', 'geo_ineligible', 'invalid'
    reason: str            # Human-readable explanation with evidence
    confidence: float      # Heuristic confidence score (0.0 to 1.0)
    rule_version: str = "v1.0"


# ---------------------------------------------------------------------------
# Heuristic Patterns
# ---------------------------------------------------------------------------

# Keywords indicating explicit fresher, entry-level, or internship status in job description
# Requires explicit role targeting statements or explicit 0 YOE / no experience statements.
EXPLICIT_FRESHER_DESCRIPTION_PATTERNS = [
    # Explicit fresher statements
    r"\bfreshers?\s+(?:welcome|eligible|can\s+apply|preferred|only|friendly|considered)\b",
    r"\b(?:open\s+to|suitable\s+for|ideal\s+for|great\s+for|designed\s+for)\s+freshers?\b",
    # Explicit entry-level role statements (role/position/opportunity, not merely "entry-level tasks")
    r"\bentry[\s\-]level\s+(?:role|job|position|opportunity|developer|engineer|analyst|candidate|hire|opening|contractor)\b",
    r"\b(?:this\s+is\s+an?|seeking\s+an?|hiring\s+an?)\s+entry[\s\-]level\b",
    # Explicit zero experience / no prior experience required
    r"\bno\s+(?:prior\s+)?experience\s+(?:is\s+)?(?:required|needed|necessary)\b",
    r"\b(?:0[\s\-]1|0\s*to\s*1)\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience|exp)?\b",
    r"\b(?:0|zero)\s+years?(?:\s*of)?\s*experience\b",
    # Explicit graduate hiring programs
    r"\b(?:recent|new|college|university|202[4-6])\s+graduates?\s+(?:welcome|eligible|can\s+apply|hiring|program)\b",
    r"\b(?:graduate|internship|trainee|apprenticeship)\s+(?:program|scheme|intake|batch)\b",
]

# Alias for backward-compatibility
FRESHER_POSITIVE_PATTERNS = EXPLICIT_FRESHER_DESCRIPTION_PATTERNS

# Unambiguous senior leadership / management titles (strictly excluded unless qualified as intern/trainee)
SENIOR_TITLE_PATTERNS = [
    (r"\bhead\s+of\b", "Head-level executive position"),
    (r"\bdirector\b", "Director-level leadership position"),
    (r"\bprincipal\b", "Principal-level senior role"),
    (r"\bstaff\s+(?:\w+\s+)?(?:engineer|developer|architect|designer)\b", "Staff-level engineering role"),
    (r"\barchitect\b", "Architecture-level senior technical role"),
    (r"\b(?:qa|test|quality|shift|team|business|city\s+business|operations|tech|technical|project|module|squad|practice)\s+lead\b", "Leadership/lead position"),
    (r"\blead\s+(?:(?!\bgeneration\b)[\w\(\)\/\.\-]+\s+){0,4}(?:engineer|developer|architect|designer|manager|consultant|specialist)\b", "Senior team lead position"),
    (r"\bengineering\s+manager\b", "Engineering management role"),
    (r"\bvice\s+president\b|\bvp\b", "Vice President executive position"),
    (r"\b(?:cto|cpo|coo|ceo)\b", "C-suite executive position"),
    (r"\b(?:l3|l3\.5|tier\s*(?:iii|3|3\.5))\b", "L3/Tier III escalation position"),
    (r"\b(?:supervisor|superintendent)\b", "Supervisory role"),
    (r"\bsenior\b|\bsr\.?\b", "Senior-level role"),
]

# Broad talent pools, matching networks, resume databases, and generic open submissions
TALENT_POOL_PATTERNS = [
    (r"\b(?:talent|matching|referral|specialist)\s+network\b", "Non-specific talent/matching network"),
    (r"\ball\s+industries\s+&\s+skill\s+levels\b", "Generic all-skill recruitment pool"),
    (r"\bjoin\s+our\s+(?:talent|candidate)\s+(?:pool|community|network)\b", "Talent pool registration"),
    (r"\b(?:register|submit\s+your\s+resume|express\s+interest)\s+for\s+future\b", "General future interest registration"),
    (r"\bopen\s+(?:submission|pool|roster)\b", "Continuous open talent pool"),
]

# Explicit experience requirements exceeding 1 year (e.g. '2+ years', '3-5 years', 'at least 3 years')
EXPERIENCE_EXCEEDED_REGEX = re.compile(
    r"\b(?:(?:minimum|at\s*least|requires?)\s*)?([2-9]|\d{2})\+?\s*(?:to\s*\d+)?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience|exp)?\b",
    re.IGNORECASE
)

# Prior experience requirement patterns that disqualify an intern/entry-level posting from confirmed zero-experience status
INTERN_PRIOR_EXPERIENCE_PATTERNS = [
    r"\b(?:[6-9]|1[0-1])\s*(?:months?|mos?)(?:\s*(?:[\-–]|to)\s*(?:1|one)\s*(?:years?|yrs?))?(?:\s*of)?\s*(?:relevant\s+)?(?:experience|exp)\b",
    r"\b(?:minimum|at\s*least|requires?)\s+(?:(?:[6-9]|1[0-1])\s*(?:months?|mos?)|(?:1|one)\s*(?:years?|yrs?))\b",
    r"(?<!0-)(?<!0–)(?<!0\s)\b1\+?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:relevant\s+)?(?:experience|exp)\b",
    r"\b(?:[2-9]|\d{2})\+?\s*(?:(?:[\-–]|to)\s*\d+)?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience|exp)?\b"
]


def extract_intern_prior_experience_requirement(text: str) -> Optional[str]:
    """Detect if description specifies prior experience (> 0 YOE) for an intern/entry role."""
    for pattern in INTERN_PRIOR_EXPERIENCE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = match.start()
            prefix = text[max(0, start - 6):start].lower()
            if "0 to" in prefix or "0-" in prefix or "0–" in prefix:
                continue
            return match.group(0)
    return None


def evaluate_vacancy_type(title: str, description: Optional[str]) -> Tuple[bool, str, float]:
    """Determine whether the posting is an individual vacancy or a broad talent pool.

    Returns:
        (is_individual_vacancy: bool, reason: str, confidence: float)
    """
    combined = f"{title} {description or ''}".lower()

    for pattern, label in TALENT_POOL_PATTERNS:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            return False, f"{label} detected: '{match.group(0)}'", 0.95

    return True, "Specific individual job vacancy", 1.0


def evaluate_seniority_and_fresher_suitability(
    title: str,
    description: Optional[str]
) -> Tuple[str, str, str, float]:
    """Context-aware assessment of seniority vs. fresher suitability.

    Avoids false positives by evaluating context (e.g. 'Lead Generation Intern' is an intern).

    Returns:
        Tuple of (outcome, category, reason, confidence):
        - outcome: 'confirmed_fresher' | 'uncertain_review' | 'not_fresher_suitable'
        - category: 'fresher_friendly' | 'needs_review' | 'seniority_exclusion'
        - reason: Human-readable explanation
        - confidence: 0.0 - 1.0
    """
    clean_title = title.strip().lower()
    clean_desc = (description or "").strip().lower()

    # Step 1: Check for explicit internship / fresher title markers
    # Even if title contains words like 'lead' (e.g. 'Lead Generation Intern'), intern context wins
    is_title_intern = bool(re.search(r"\b(?:intern|internship|interns)\b", clean_title))
    is_title_trainee = bool(re.search(r"\b(?:trainee|trainees|apprentice)\b", clean_title))
    is_title_fresher = bool(re.search(r"\bfreshers?\b|\bentry[\s\-]level\b", clean_title))

    if is_title_intern or is_title_trainee or is_title_fresher:
        # Check for explicit prior experience requirement in description
        # Under strict zero-experience standards, intern postings requiring prior experience (>0 YOE) are downgraded to uncertain
        if clean_desc:
            prior_exp_req = extract_intern_prior_experience_requirement(clean_desc)
            if prior_exp_req:
                return (
                    "uncertain_review",
                    "needs_review",
                    f"Title indicates intern/entry-level but description requires prior experience: '{prior_exp_req}'",
                    0.70
                )

        fresher_label = "Internship" if is_title_intern else "Entry-level / Fresher"
        return (
            "confirmed_fresher",
            "fresher_friendly",
            f"{fresher_label} role identified from title",
            0.95
        )

    # Step 2: Check for unambiguous senior leadership titles
    for pattern, reason_desc in SENIOR_TITLE_PATTERNS:
        match = re.search(pattern, clean_title, re.IGNORECASE)
        if match:
            return (
                "not_fresher_suitable",
                "seniority_exclusion",
                f"{reason_desc} in title: '{match.group(0)}'",
                0.95
            )

    # Step 3: Check for explicit experience requirements exceeding 1 year in title or description
    title_exp_match = EXPERIENCE_EXCEEDED_REGEX.search(clean_title)
    if title_exp_match:
        return (
            "not_fresher_suitable",
            "seniority_exclusion",
            f"Title explicitly requires prior experience: '{title_exp_match.group(0)}'",
            0.95
        )

    if clean_desc:
        desc_exp_match = EXPERIENCE_EXCEEDED_REGEX.search(clean_desc)
        if desc_exp_match:
            # Verify if description also contains an explicit fresher override (e.g. 'or freshers welcome')
            has_fresher_override = any(
                re.search(p, clean_desc) for p in [
                    r"\bfreshers?\s+(?:welcome|eligible|can\s+apply)\b",
                    r"\b0[\s\-]1\s*(?:years?|yrs?)\b",
                    r"\bno\s+experience\s+required\b"
                ]
            )
            if not has_fresher_override:
                return (
                    "not_fresher_suitable",
                    "seniority_exclusion",
                    f"Description requires prior experience: '{desc_exp_match.group(0)}' (> 1 YOE)",
                    0.90
                )

    # Step 4: Check if description explicitly declares fresher friendliness
    if clean_desc:
        for pattern in FRESHER_POSITIVE_PATTERNS:
            match = re.search(pattern, clean_desc)
            if match:
                return (
                    "confirmed_fresher",
                    "fresher_friendly",
                    f"Description explicitly welcomes freshers/entry-level: '{match.group(0)}'",
                    0.90
                )

    # Step 5: Ambiguous / Unstated experience without senior markers
    # Must remain available for review, but NOT counted as confirmed fresher
    return (
        "uncertain_review",
        "needs_review",
        "Experience requirements unstated without senior markers; retained for review",
        0.60
    )


def evaluate_job_relevance(
    title: str,
    raw_location: Optional[str],
    description: Optional[str],
    is_indian_source: bool = False
) -> RelevanceDecision:
    """Evaluate candidate job against orthogonal dimensions:

    1. Geographic Accessibility (India)
    2. Vacancy Authenticity (Individual vs. Pool)
    3. Seniority & Fresher Suitability (0-1 YOE vs. Senior vs. Uncertain)

    Returns:
        RelevanceDecision with structured outcome, category, reason, and confidence.
    """
    # 1. Geographic accessibility check
    geo_status, geo_reason = check_geographic_eligibility(
        raw_location=raw_location,
        title=title,
        is_indian_source=is_indian_source
    )
    if geo_status == "ineligible":
        return RelevanceDecision(
            is_accepted=False,
            outcome="india_ineligible",
            category="geo_ineligible",
            reason=f"Geographic exclusion: {geo_reason}",
            confidence=0.95
        )

    # 2. Vacancy type check (individual vacancy vs. talent pool)
    is_individual, pool_reason, pool_conf = evaluate_vacancy_type(title, description)
    if not is_individual:
        return RelevanceDecision(
            is_accepted=False,
            outcome="not_individual_vacancy",
            category="talent_pool_exclusion",
            reason=pool_reason,
            confidence=pool_conf
        )

    # 3. Context-aware seniority and fresher suitability check
    outcome, category, reason, confidence = evaluate_seniority_and_fresher_suitability(
        title=title,
        description=description
    )

    if outcome == "not_fresher_suitable":
        return RelevanceDecision(
            is_accepted=False,
            outcome="not_fresher_suitable",
            category="seniority_exclusion",
            reason=reason,
            confidence=confidence
        )

    # 4. If location is ambiguous or unrecognized:
    # Treat as uncertain/review rather than automatically accepting as confirmed fresher
    if geo_status == "ambiguous":
        return RelevanceDecision(
            is_accepted=True,
            outcome="uncertain_review",
            category="needs_review",
            reason=f"Ambiguous or unrecognized location ('{raw_location}'); retained for review",
            confidence=0.60
        )

    # If confirmed fresher or uncertain review -> Accepted for ingestion
    return RelevanceDecision(
        is_accepted=True,
        outcome=outcome,
        category=category,
        reason=reason,
        confidence=confidence
    )
