"""Data Normalization & Validation Engine.

Provides deterministic cleaning and sanitization:
1. Canonical URL cleaning: strips UTM and tracking parameters; lowercases scheme and host.
2. Hash generation: SHA-256 for canonical URLs, MD5 for content similarity.
3. Fallback identifier generation for sources lacking external IDs.
4. India geographic accessibility filtering: distinguishes genuine Indian/Worldwide roles from foreign-restricted positions.
5. Incomplete record validation: rejects records missing mandatory fields (title, URL).
"""
import hashlib
import re
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


# Query parameters strictly stripped during URL canonicalization
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid",
    "sc_channel", "trk", "trkCampaign", "src"
}

# Recognized Indian tech centers, cities, and historical aliases
INDIAN_CITIES = {
    # Tier-1 metros and IT capitals
    "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "bombay", "delhi",
    "new delhi", "delhi-ncr", "ncr", "gurgaon", "gurugram", "noida", "greater noida",
    "chennai", "madras", "kolkata", "calcutta", "ahmedabad", "jaipur", "kochi", "cochin",
    "coimbatore", "indore", "chandigarh", "mohali", "trivandrum", "thiruvananthapuram",
    # Specific audited Indian hubs and Tier-2 centers
    "ghaziabad", "madurai", "agra", "mysore", "mysuru", "bhopal", "nagpur", "patna",
    "vadodara", "baroda", "ludhiana", "nashik", "faridabad", "meerut", "rajkot",
    "varanasi", "banaras", "kashi", "srinagar", "aurangabad", "dhanbad", "amritsar",
    "navi mumbai", "allahabad", "prayagraj", "howrah", "ranchi", "gwalior", "jabalpur",
    "vijayawada", "jodhpur", "raipur", "kota", "guwahati", "hubli", "dharwad",
    "bareilly", "moradabad", "tiruchirappalli", "trichy", "tiruppur", "salem",
    "dehradun", "visakhapatnam", "vizag", "mangalore", "mangaluru", "surat",
    "kanpur", "calicut", "kozhikode", "shimla", "panaji", "puducherry", "pondicherry"
}

# Recognized Indian states and union territories
INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "chandigarh", "puducherry", "pondicherry", "jammu and kashmir", "ladakh"
}

# Explicitly foreign restriction keywords that disqualify a remote job from being India-accessible
FOREIGN_RESTRICTIONS = {
    "us only", "usa only", "united states only", "north america only",
    "canada only", "uk only", "united kingdom only", "europe only",
    "eu only", "emea only", "latam only", "australia only", "apac only (excluding india)"
}

# Explicit foreign locations (cities, states, countries) that disqualify candidates on global sources
FOREIGN_LOCATIONS = {
    "austin", "berlin", "london", "paris", "toronto", "vancouver", "sydney",
    "melbourne", "san francisco", "new york", "seattle", "boston", "chicago",
    "los angeles", "california", "texas", "washington", "colorado",
    "germany", "united kingdom", "canada", "australia", "france", "netherlands"
}

# Standardized city mappings for Tier-1 Indian tech metros (Milestone 10B)
METRO_MAPPINGS = {
    "Bengaluru": [
        "bengaluru", "bangalore", "whitefield", "electronic city", "bellandur",
        "marathahalli", "koramangala", "indiranagar", "bengaluru-vtp"
    ],
    "Hyderabad": [
        "hyderabad", "secunderabad", "hitec city", "hitech city", "gachibowli",
        "cyberabad", "madhapur", "kondapur"
    ],
    "Pune": [
        "pune", "hinjewadi", "hinjawadi", "magarpatta", "kharadi", "hadapsar", "viman nagar"
    ],
    "Mumbai": [
        "mumbai", "bombay", "navi mumbai", "thane", "andheri", "powai", "bandra", "worli"
    ],
    "Delhi-NCR": [
        "delhi", "new delhi", "gurgaon", "gurugram", "noida", "greater noida",
        "faridabad", "ghaziabad", "delhi-ncr", "delhi ncr", "ncr", "sonipat"
    ],
    "Chennai": [
        "chennai", "madras", "omr", "guindy", "taramani"
    ],
    "Kolkata": [
        "kolkata", "calcutta", "salt lake", "rajarhat", "new town"
    ],
    "Ahmedabad": [
        "ahmedabad", "gandhinagar", "gift city"
    ]
}

REMOTE_INDICATORS = [
    "remote", "work from home", "wfh", "worldwide", "home based",
    "anywhere", "pan-india remote", "pan india remote", "global remote",
    "remote india", "remote - india", "remote, india", "india remote"
]

OTHER_INDIAN_CITIES = {
    c for c in INDIAN_CITIES
    if not any(c in aliases for aliases in METRO_MAPPINGS.values())
}

OTHER_INDIAN_STATES = {
    s for s in INDIAN_STATES
    if s not in ["delhi", "chandigarh"]
}


def normalize_standardized_city(
    raw_location: Optional[str],
    title: Optional[str] = None,
    company: Optional[str] = None
) -> Optional[str]:
    """Deterministically normalize raw location into a standardized CityType enum.

    Follows project conventions:
    1. Explicit remote indicators -> 'Remote'
    2. Recognized metro locations and aliases -> mapped metro enum
    3. India Tier-2/3 cities or states -> 'Other India'
    4. 'India' or 'Pan-India' without specific city -> 'Remote' (checks title/company for physical city first)
    5. Ambiguous / multi-metro conflicts -> returns None for downstream LLM resolution
    6. Empty/missing location with no title/company clues -> 'Unknown'

    Returns:
        One of 'Bengaluru', 'Hyderabad', 'Pune', 'Mumbai', 'Delhi-NCR', 'Chennai',
        'Kolkata', 'Ahmedabad', 'Remote', 'Other India', 'Unknown', or None if ambiguous.
    """
    if not raw_location or not raw_location.strip():
        combined = f"{title or ''} {company or ''}".lower()
        if not combined.strip():
            return "Unknown"
        # Check metros in title/company fallback
        for metro, aliases in METRO_MAPPINGS.items():
            for a in aliases:
                if re.search(rf"\b{re.escape(a)}\b", combined):
                    return metro
        # Check remote in title/company fallback
        for r in REMOTE_INDICATORS:
            if re.search(rf"\b{re.escape(r)}\b", combined):
                return "Remote"
        return "Unknown"

    loc = raw_location.lower().strip()

    # 1. Pure remote strings without physical city
    has_remote_indicator = any(re.search(rf"\b{re.escape(r)}\b", loc) for r in REMOTE_INDICATORS)
    has_metro_indicator = any(
        any(re.search(rf"\b{re.escape(a)}\b", loc) for a in aliases)
        for aliases in METRO_MAPPINGS.values()
    )

    if has_remote_indicator and not has_metro_indicator:
        return "Remote"

    # 2. Check for physical metros in raw_location
    matched_metros = []
    for metro, aliases in METRO_MAPPINGS.items():
        for a in aliases:
            if re.search(rf"\b{re.escape(a)}\b", loc):
                matched_metros.append(metro)
                break

    if len(matched_metros) == 1:
        return matched_metros[0]
    elif len(matched_metros) > 1:
        # Multiple conflicting metros (e.g. 'Chennai/Bangalore') -> leave for LLM resolution
        return None

    # 3. Check for Tier-2 Indian cities or states
    for c in OTHER_INDIAN_CITIES:
        if re.search(rf"\b{re.escape(c)}\b", loc):
            return "Other India"
    for s in OTHER_INDIAN_STATES:
        if re.search(rf"\b{re.escape(s)}\b", loc):
            return "Other India"

    # 4. Handle 'India' or 'Pan-India'
    if re.search(r"\b(india|pan[\s\-]india)\b", loc):
        combined = f"{title or ''} {company or ''}".lower()
        # Check if title or company mentions an explicit physical metro
        for metro, aliases in METRO_MAPPINGS.items():
            for a in aliases:
                if re.search(rf"\b{re.escape(a)}\b", combined):
                    return metro
        # Check Tier-2 cities in title/company
        for c in OTHER_INDIAN_CITIES:
            if re.search(rf"\b{re.escape(c)}\b", combined):
                return "Other India"
        # Benchmark-aligned convention: generic 'India' without specific city -> 'Remote'
        return "Remote"

    # 5. Unrecognized or foreign text (e.g. 'Singapore') -> return None for LLM resolution
    return None


def normalize_url(raw_url: str) -> str:
    """Normalize and sanitize a job URL.

    - Strips whitespace.
    - Lowers scheme and domain.
    - Removes tracking parameters (UTM, ref, fbclid, etc.).
    - Strips trailing slash on path if path is not root.
    - Removes URL fragments (#...).
    """
    if not raw_url or not isinstance(raw_url, str):
        return ""

    parsed = urlparse(raw_url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Filter out tracking query parameters while preserving meaningful application parameters
    clean_query_params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    # Sort query parameters deterministically
    clean_query_params.sort(key=lambda x: x[0])
    query = urlencode(clean_query_params)

    path = parsed.path.lower()
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def hash_url(clean_url: str) -> str:
    """Compute SHA-256 hash of a normalized canonical URL."""
    return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()


def normalize_text(text: Optional[str]) -> str:
    """Normalize text by stripping whitespace and extra internal spaces."""
    if not text:
        return ""
    # Replace any sequence of whitespace with a single space
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    # Remove leading/trailing punctuation commonly found in titles
    return cleaned.strip(" -|,.")


def generate_fallback_external_id(
    source: str,
    title: str,
    company: Optional[str],
    clean_url: str
) -> str:
    """Generate deterministic external_id for sources lacking native IDs.

    Uses MD5 of source + normalized title + company + canonical URL.
    Ensures repeated ingestion runs produce the exact same external_id.
    """
    raw_key = f"{source.lower()}|{normalize_text(title)}|{normalize_text(company)}|{clean_url}"
    return f"gen_{hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:16]}"


def compute_content_hash(
    title: str,
    company: Optional[str],
    raw_location: Optional[str]
) -> str:
    """Compute MD5 hash representing normalized title, company, and location.

    Used for Tier-3 duplicate candidate detection.
    """
    norm_title = normalize_text(title)
    norm_company = normalize_text(company)
    norm_loc = normalize_text(raw_location)
    content_key = f"{norm_title}|{norm_company}|{norm_loc}"
    return hashlib.md5(content_key.encode("utf-8")).hexdigest()


def check_geographic_eligibility(
    raw_location: Optional[str],
    title: Optional[str] = None,
    is_indian_source: bool = False
) -> Tuple[str, str]:
    """Assess geographic accessibility for applicants located in India.

    Returns:
        (status, reason):
        - 'eligible': Confirmed accessible in India.
        - 'ineligible': Explicit foreign-only restriction or foreign location on global source.
        - 'ambiguous': Unrecognized location or ambiguous geographic context; requires review.
    """
    loc_text = (raw_location or "").lower().strip()
    title_text = (title or "").lower().strip()
    combined_text = f"{loc_text} {title_text}"

    # 1. Reject if any explicit foreign-only restriction is present
    for restriction in FOREIGN_RESTRICTIONS:
        if restriction in combined_text:
            return "ineligible", f"Foreign-only restriction detected: '{restriction}'"

    # Specific common pattern: 'remote - us', 'remote, us', 'remote (us applicants only)'
    if re.search(r"\bremote\b.*\b(us|usa|united states|uk|canada|europe|emea|latam)\b", combined_text):
        return "ineligible", "Remote role restricted to foreign applicants (US/UK/Canada/Europe)"

    # Check for explicit foreign locations on non-Indian sources
    if not is_indian_source and loc_text:
        for foreign_loc in FOREIGN_LOCATIONS:
            if re.search(rf"\b{re.escape(foreign_loc)}\b", combined_text):
                return "ineligible", f"Foreign location detected: '{foreign_loc.title()}'"

    # 2. Check for explicit India keywords
    if re.search(r"\b(india|pan[\s\-]india|remote\s*\(india\)|remote\s*[-–]\s*india|india\s*remote)\b", combined_text):
        return "eligible", "Explicit India location detected"

    # 3. Check for specific Indian tech cities and aliases
    for city in INDIAN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", combined_text):
            return "eligible", f"Indian city detected: '{city.title()}'"

    # 4. Check for Indian states and union territories
    for state in INDIAN_STATES:
        if re.search(rf"\b{re.escape(state)}\b", combined_text):
            return "eligible", f"Indian state detected: '{state.title()}'"

    # 5. Check for globally open remote indicators
    worldwide_indicators = ["worldwide", "anywhere in the world", "global remote"]
    for indicator in worldwide_indicators:
        if indicator in combined_text:
            return "eligible", f"Worldwide accessible remote role: '{indicator}'"

    # 6. Handle source-context for Indian-native sources
    if is_indian_source:
        # Plain Remote or empty location on Indian platform defaults to India
        if "remote" in combined_text or not loc_text:
            return "eligible", "India-native source: Remote/Pan-India role"
        # Non-empty location on Indian platform that didn't match known cities/states is ambiguous
        return "ambiguous", f"Indian platform location unrecognized: '{raw_location}'; retained for review"

    # 7. Non-Indian sources without India/Worldwide indicators
    if loc_text:
        # Check if 'anywhere' is used without explicit foreign restrictions
        if "anywhere" in combined_text:
            return "ambiguous", f"Global source location ambiguous: '{raw_location}'; retained for review"
        return "ineligible", "Unspecified remote or non-Indian location without global/India accessibility"

    return "ineligible", "Missing location on non-Indian source without worldwide accessibility"


def is_india_eligible(
    raw_location: Optional[str],
    title: Optional[str] = None,
    is_indian_source: bool = False
) -> Tuple[bool, str]:
    """Verify if a job is genuinely accessible to applicants located in India.

    Backward-compatible wrapper around check_geographic_eligibility returning (bool, str).
    """
    status, reason = check_geographic_eligibility(raw_location, title, is_indian_source)
    return (status == "eligible", reason)


def validate_raw_record(raw: dict) -> Tuple[bool, Optional[str]]:
    """Validate minimum schema requirements before any processing.

    Requires non-empty title and valid HTTP/HTTPS URL.
    Company and location are permitted to be null (never fabricated).
    """
    title = raw.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        return False, "Missing or empty job title"

    url = raw.get("apply_url")
    if not url or not isinstance(url, str) or not url.strip():
        return False, "Missing or empty apply URL"

    clean_url = normalize_url(url)
    if not clean_url:
        return False, f"Malformed apply URL: '{url}'"

    return True, None
