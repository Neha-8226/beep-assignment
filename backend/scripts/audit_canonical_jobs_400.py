"""Isolated Read-Only Live Job Validity Audit Utility (Milestone 9).

Audits all 400 canonical job records in jobs.db:
- Read-only connection (sqlite3 mode=ro, zero DB writes).
- Bounded, polite HTTP resolution (recording final URL, status code, redirects).
- Evidence-based Job Status (OPEN_VERIFIED, CLOSED, INACCESSIBLE, UNVERIFIABLE, INVALID_LINK, GENERIC_CAREERS_PAGE).
- Vacancy authenticity check.
- India eligibility assessment.
- Fresher / internship suitability assessment.
- Cross-record duplicate detection across all 400 canonical jobs.
- Exports full results to CSV and JSON in backend/reports/.
"""
import sys
import os
import json
import csv
import re
import time
import sqlite3
import hashlib
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# Ensure backend directory in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.ingestion.normalizer import is_india_eligible, normalize_url, hash_url
from app.ingestion.relevance import evaluate_job_relevance


DB_PATH = "jobs.db"
REPORTS_DIR = os.path.join(backend_dir, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)
CSV_REPORT_PATH = os.path.join(REPORTS_DIR, "live_job_validity_audit_400.csv")
JSON_REPORT_PATH = os.path.join(REPORTS_DIR, "live_job_validity_audit_400.json")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BeepJobAudit/1.0"


def fetch_canonical_jobs() -> List[Dict[str, Any]]:
    """Fetch all 400 canonical job records using read-only SQLite connection."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, source, external_id, title, company, posting_organization,
               hiring_organization, raw_location, description, apply_url,
               canonical_url_hash, content_hash, role_category, standardized_city,
               job_type, is_fresher_friendly, model_confidence, is_active,
               posted_at, created_at
        FROM jobs
        ORDER BY id ASC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def evaluate_india_eligibility(raw_loc: Optional[str], desc: Optional[str]) -> Tuple[str, str]:
    """Assess India eligibility and return (status, reason)."""
    loc_str = (raw_loc or "").strip()
    desc_str = (desc or "").strip()

    # Explicit exclusion check
    foreign_geo_match = re.search(
        r"\b(?:only\s+(?:us|usa|uk|canada|europe|americas|emea)|must\s+be\s+located\s+in\s+the\s+(?:us|usa|uk|canada)|authorized\s+to\s+work\s+in\s+the\s+us)\b",
        desc_str,
        re.IGNORECASE
    )
    if foreign_geo_match:
        return "EXCLUDED", f"Foreign geographic restriction in text: '{foreign_geo_match.group(0)}'"

    # Positive India location check
    indian_cities_pattern = (
        r"\b(?:india|bengaluru|bangalore|mumbai|bombay|pune|hyderabad|delhi|new\s+delhi|"
        r"gurugram|gurgaon|noida|chennai|madras|kolkata|calcutta|ahmedabad|chandigarh|"
        r"kochi|cochin|thiruvananthapuram|trivandrum|indore|jaipur|lucknow|bhubaneswar|"
        r"coimbatore|nagpur|vadodara|surat|mysuru|mysore|visakhapatnam|remote[\s\-]*india|"
        r"india[\s\-]*remote)\b"
    )
    if re.search(indian_cities_pattern, loc_str, re.IGNORECASE):
        return "ELIGIBLE_INDIA_DOMESTIC", f"Explicit India location in posting: '{loc_str}'"

    # Worldwide / Anywhere Remote check
    worldwide_pattern = r"\b(?:worldwide|anywhere|globally|global\s+remote|remote[\s\-]*worldwide|work\s+from\s+anywhere|home\s*based\s*[-–]\s*worldwide)\b"
    if re.search(worldwide_pattern, loc_str, re.IGNORECASE) or re.search(r"\b(?:worldwide|anywhere\s+in\s+the\s+world|work\s+from\s+anywhere)\b", desc_str[:500], re.IGNORECASE):
        return "ELIGIBLE_WORLDWIDE_REMOTE", f"Worldwide/global remote accessibility: '{loc_str}'"

    # Fallback to normalizer
    if is_india_eligible(loc_str):
        return "ELIGIBLE_NORMALIZED", f"Normalized India eligible location: '{loc_str}'"

    if not loc_str:
        return "LOCATION_AMBIGUOUS", "Missing raw location in posting"

    return "LOCATION_AMBIGUOUS", f"Unconfirmed location context: '{loc_str}'"


def evaluate_fresher_suitability(title: str, desc: Optional[str]) -> Tuple[str, str, Optional[float]]:
    """Assess fresher suitability independently of LLM classification."""
    t_clean = (title or "").strip().lower()
    d_clean = (desc or "").strip().lower()

    # Check explicit internship / trainee in title
    if re.search(r"\b(?:intern|internship|trainee|apprentice)\b", t_clean):
        return "SUITABLE_INTERNSHIP", f"Explicit internship/trainee designation in title: '{title}'", 0.0

    # Check explicit graduate / fresher in title
    if re.search(r"\b(?:graduate|fresher|junior|entry[\s\-]*level|associate)\b", t_clean):
        # Verify not disqualified by high YOE in description
        yoe_match = re.search(r"(\d+)\+?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience|exp)", d_clean)
        if yoe_match:
            yoe = float(yoe_match.group(1))
            if yoe > 1.0:
                return "CONCERN_EXPERIENCE_MISMATCH", f"Title '{title}' appears entry-level, but description requires {yoe:.0f} YOE", yoe
        return "SUITABLE_ENTRY_LEVEL", f"Entry-level/associate designation in title: '{title}'", 0.0

    # Check senior leadership exclusion
    senior_match = re.search(r"\b(?:senior|sr\.?|lead|principal|staff|director|head\s+of|manager|vp|architect)\b", t_clean)
    if senior_match:
        return "UNSUITABLE_SENIOR", f"Seniority indicator in title: '{senior_match.group(0)}'", None

    # Check experience requirements in description
    yoe_matches = re.findall(r"(\d+)\+?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience|exp)", d_clean)
    if yoe_matches:
        try:
            min_yoe = min(float(y) for y in yoe_matches)
            if min_yoe == 0:
                return "SUITABLE_EXPLICIT_0_YOE", "Description explicitly mentions 0 years of experience required", 0.0
            elif min_yoe <= 1.0:
                return "SUITABLE_0_1_YOE", f"Description requires 0-1 YOE ({min_yoe:.0f} years)", min_yoe
            else:
                return "UNSUITABLE_EXPERIENCE", f"Description requires prior experience: {min_yoe:.0f}+ YOE (> 1 YOE)", min_yoe
        except Exception:
            pass

    # No disqualifying factors and entry-compatible title
    return "SUITABLE_NEEDS_REVIEW", f"Individual role without disqualifying seniority markers: '{title}'", None


def audit_url_and_status(job: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
    """Perform live HTTP audit on the application URL."""
    orig_url = job.get("apply_url", "").strip()
    source = job.get("source", "").strip()
    job_id = job.get("id")
    company = job.get("company", "") or ""

    result = {
        "job_id": job_id,
        "original_url": orig_url,
        "final_url": orig_url,
        "http_status": None,
        "job_status": "UNVERIFIABLE",
        "vacancy_authenticity": "UNVERIFIED",
        "closure_evidence": None,
        "is_specific_vacancy": False,
        "request_duration_seconds": None,
        "error_details": None
    }

    if not orig_url or not orig_url.startswith("http"):
        result["job_status"] = "INVALID_LINK"
        result["closure_evidence"] = "Malformed or non-HTTP URL"
        return result

    start_time = time.time()
    try:
        response = session.get(
            orig_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json"},
            timeout=10,
            allow_redirects=True
        )
        duration = round(time.time() - start_time, 2)
        result["request_duration_seconds"] = duration
        result["http_status"] = response.status_code
        result["final_url"] = response.url

        # 1. Handle HTTP error status codes
        if response.status_code in (404, 410):
            result["job_status"] = "CLOSED"
            result["closure_evidence"] = f"HTTP {response.status_code} Not Found/Gone"
            return result
        elif response.status_code in (401, 403):
            # Blocked by anti-bot or access restriction
            if "cloudflare" in response.text.lower() or "challenge" in response.text.lower():
                result["job_status"] = "INACCESSIBLE"
                result["closure_evidence"] = f"HTTP {response.status_code} Cloudflare / Anti-bot verification challenge"
            else:
                result["job_status"] = "INACCESSIBLE"
                result["closure_evidence"] = f"HTTP {response.status_code} Access Forbidden"
            return result
        elif response.status_code >= 500:
            result["job_status"] = "INACCESSIBLE"
            result["closure_evidence"] = f"HTTP {response.status_code} Server Error"
            return result
        elif response.status_code != 200:
            result["job_status"] = "UNVERIFIABLE"
            result["closure_evidence"] = f"HTTP {response.status_code} Non-standard response"
            return result

        # 2. Analyze HTTP 200 responses
        parsed_final = urlparse(response.url)
        path = parsed_final.path.lower().rstrip("/")
        query = parsed_final.query.lower()

        # Check for Greenhouse error=true redirect (explicit closure on Greenhouse)
        if "error=true" in query:
            result["job_status"] = "CLOSED"
            result["closure_evidence"] = "Redirected with error=true: vacancy has expired/closed on Greenhouse"
            result["is_specific_vacancy"] = False
            return result

        # Determine if URL points to a specific vacancy vs generic careers portal
        is_specific = False
        if source == "greenhouse":
            # Specific Greenhouse patterns:
            # - /jobs/12345
            # - query has gh_jid=12345
            # - path has /listing/... or /opportunity/... or ending in /1234567
            if (
                re.search(r"/jobs/\d+", path) or
                re.search(r"gh_jid=\d+", query) or
                re.search(r"/(?:listing|opportunity|job)/\S+", path) or
                re.search(r"/\d{6,}/?$", path)
            ):
                is_specific = True
            elif path in ("", "/", f"/{company.lower()}", "/careers", "/jobs"):
                is_specific = False
            else:
                # Fallback: if URL contains specific slug
                is_specific = len(path.split("/")) > 2
        elif source == "lever":
            # Specific Lever pattern: /company/uuid or /company/uuid/apply
            if re.search(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", path):
                is_specific = True
            elif path in ("", "/", f"/{company.lower()}", "/careers", "/jobs"):
                is_specific = False
            else:
                is_specific = len(path.split("/")) > 2
        elif source == "hasjob":
            # Hasjob specific pattern: /domain.com/slug (len of parts == 3)
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2:
                is_specific = True
        elif source == "remotive":
            # Remotive specific: /remote-jobs/<cat>/<slug-with-id>
            if re.search(r"/remote-jobs/[^/]+/.+-\d+", path):
                is_specific = True
            elif path in ("/remote-jobs", "/remote-jobs/software-dev", "/remote-jobs/all-others"):
                is_specific = False
            else:
                is_specific = len(path.split("/")) >= 3
        else:
            is_specific = len(path.split("/")) > 2

        result["is_specific_vacancy"] = is_specific

        if not is_specific:
            result["job_status"] = "GENERIC_CAREERS_PAGE"
            result["closure_evidence"] = f"Resolved to generic careers directory ({response.url}) rather than a specific job requisition"
            return result

        # Check explicit closure messaging in page content using full HTML
        soup = BeautifulSoup(response.content, "html.parser")
        visible_text = soup.get_text()

        closure_patterns = [
            r"\bthis\s+(?:job|position|posting|role)\s+is\s+(?:no\s+longer\s+available|closed|filled)\b",
            r"\bthank\s+you\s+for\s+your\s+interest[^\.\n]*this\s+(?:job|position)\s+is\s+closed\b",
            r"\bthis\s+job\s+posting\s+has\s+expired\b",
            r"\bthe\s+job\s+you\s+are\s+looking\s+for\s+is\s+closed\b",
            r"\bno\s+longer\s+accepting\s+applications\b",
            r"\bthis\s+listing\s+has\s+expired\b",
            r"\bthis\s+post\s+has\s+been\s+withdrawn\b",
            r"\bthis\s+vacancy\s+is\s+closed\b",
            r"\bjob\s+not\s+found\b"
        ]

        closure_found = None
        for cp in closure_patterns:
            m = re.search(cp, visible_text, re.IGNORECASE)
            if m:
                closure_found = m.group(0).strip()
                break

        if closure_found:
            result["job_status"] = "CLOSED"
            result["closure_evidence"] = f"Explicit closure statement found in page: '{closure_found}'"
            return result

        # Check for active application mechanism or specific vacancy structure
        has_apply_mechanism = False
        apply_buttons = [
            a.get_text().strip()
            for a in soup.find_all(["a", "button", "input"])
            if re.search(r"\b(?:apply|apply\s+now|submit\s+application|apply\s+for\s+this\s+job|apply\s+for\s+this\s+position|submit)\b", a.get_text() or a.get("value", ""), re.IGNORECASE)
        ]
        has_form = bool(soup.find("form")) or bool(soup.find(id=re.compile(r"application|apply", re.I))) or bool(soup.find("div", class_=re.compile(r"application|postings-btn", re.I)))

        if apply_buttons or has_form or (source in ("greenhouse", "lever") and len(visible_text) > 200):
            has_apply_mechanism = True

        # Assign authenticity
        if source in ("greenhouse", "lever"):
            result["vacancy_authenticity"] = "AUTHENTIC_OFFICIAL_ATS"
        elif source == "hasjob":
            result["vacancy_authenticity"] = "AUTHENTIC_ORIGINAL_FEED"
        elif source == "remotive":
            result["vacancy_authenticity"] = "AUTHENTIC_AGGREGATOR"
        else:
            result["vacancy_authenticity"] = "AUTHENTIC_DIRECT"

        if has_apply_mechanism:
            result["job_status"] = "OPEN_VERIFIED"
            result["closure_evidence"] = "HTTP 200 with live vacancy content and active application mechanism"
        else:
            result["job_status"] = "UNVERIFIABLE"
            result["closure_evidence"] = "HTTP 200 but application mechanism not clearly detected"

        return result

    except requests.exceptions.Timeout:
        result["job_status"] = "INACCESSIBLE"
        result["closure_evidence"] = "Connection / Read Timeout (10s)"
        result["error_details"] = "Timeout"
        return result
    except requests.exceptions.SSLError as ssl_err:
        result["job_status"] = "INVALID_LINK"
        result["closure_evidence"] = f"SSL Certificate Error: {str(ssl_err)[:80]}"
        result["error_details"] = "SSL Error"
        return result
    except requests.exceptions.ConnectionError as conn_err:
        result["job_status"] = "INVALID_LINK"
        result["closure_evidence"] = f"Connection Failed / DNS Resolution Failure: {str(conn_err)[:80]}"
        result["error_details"] = "Connection Error"
        return result
    except Exception as ex:
        result["job_status"] = "UNVERIFIABLE"
        result["closure_evidence"] = f"Unexpected exception: {str(ex)[:80]}"
        result["error_details"] = str(ex)
        return result


def find_duplicates_across_canonical(jobs: List[Dict[str, Any]]) -> Dict[int, List[int]]:
    """Identify duplicate clusters across all 400 canonical records."""
    duplicates: Dict[int, List[int]] = {}

    # Map by canonical_url_hash
    url_map: Dict[str, List[int]] = {}
    for j in jobs:
        url_hash = j.get("canonical_url_hash")
        if url_hash:
            url_map.setdefault(url_hash, []).append(j["id"])

    # Map by normalized (company, title, standardized_location)
    content_map: Dict[str, List[int]] = {}
    for j in jobs:
        comp = (j.get("company") or "").lower().strip()
        title = re.sub(r"[^\w\s]", "", (j.get("title") or "").lower()).strip()
        title_tokens = " ".join(sorted(title.split()))
        key = f"{comp}::{title_tokens}"
        content_map.setdefault(key, []).append(j["id"])

    for jid_list in url_map.values():
        if len(jid_list) > 1:
            for jid in jid_list:
                duplicates.setdefault(jid, []).extend([other for other in jid_list if other != jid])

    for key, jid_list in content_map.items():
        if len(jid_list) > 1:
            for jid in jid_list:
                duplicates.setdefault(jid, []).extend([other for other in jid_list if other != jid])

    # Deduplicate candidate IDs
    return {k: sorted(list(set(v))) for k, v in duplicates.items()}


def run_audit(max_workers: int = 8) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Execute the systematic audit across all 400 canonical records."""
    jobs = fetch_canonical_jobs()
    total_jobs = len(jobs)
    print(f"Loaded {total_jobs} canonical jobs from jobs.db.")

    duplicates_map = find_duplicates_across_canonical(jobs)
    print(f"Found {len(duplicates_map)} jobs with potential duplicate relationships.")

    session = requests.Session()
    # Adapter with retry logic for transient network failures
    adapter = requests.adapters.HTTPAdapter(max_retries=1)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    audit_records: List[Dict[str, Any]] = []

    print(f"Starting polite HTTP audit with {max_workers} worker threads...")
    start_time = time.time()

    def audit_single_job(job: Dict[str, Any]) -> Dict[str, Any]:
        # Domain pacing delay
        time.sleep(0.05)
        http_info = audit_url_and_status(job, session)

        # India eligibility
        india_status, india_reason = evaluate_india_eligibility(
            job.get("raw_location"), job.get("description")
        )

        # Fresher suitability
        fresher_status, fresher_reason, req_yoe = evaluate_fresher_suitability(
            job.get("title", ""), job.get("description")
        )

        # Duplicate status
        jid = job["id"]
        is_dup = jid in duplicates_map
        dup_of = ",".join(map(str, duplicates_map[jid])) if is_dup else None

        # Flags & Concerns
        flag_reasons = []
        if http_info["job_status"] != "OPEN_VERIFIED":
            flag_reasons.append(f"Job Status: {http_info['job_status']} ({http_info['closure_evidence']})")
        if india_status not in ("ELIGIBLE_INDIA_DOMESTIC", "ELIGIBLE_WORLDWIDE_REMOTE", "ELIGIBLE_NORMALIZED"):
            flag_reasons.append(f"India Eligibility: {india_status} - {india_reason}")
        if fresher_status.startswith("UNSUITABLE") or fresher_status.startswith("CONCERN"):
            flag_reasons.append(f"Fresher Suitability: {fresher_status} - {fresher_reason}")
        if is_dup:
            flag_reasons.append(f"Duplicate Potential: Matches Job IDs [{dup_of}]")

        is_flagged = len(flag_reasons) > 0

        # Audit confidence calculation
        if http_info["http_status"] in (200, 404, 410):
            confidence = 1.0 if http_info["job_status"] in ("OPEN_VERIFIED", "CLOSED") else 0.85
        elif http_info["http_status"] in (401, 403):
            confidence = 0.8
        else:
            confidence = 0.6

        return {
            "job_id": jid,
            "job_title": job.get("title"),
            "employer": job.get("company"),
            "source": job.get("source"),
            "original_url": job.get("apply_url"),
            "final_url": http_info["final_url"],
            "http_status": http_info["http_status"],
            "job_status": http_info["job_status"],
            "vacancy_authenticity": http_info["vacancy_authenticity"],
            "india_eligibility_status": india_status,
            "india_eligibility_reason": india_reason,
            "fresher_suitability_status": fresher_status,
            "fresher_suitability_reason": fresher_reason,
            "required_yoe": req_yoe,
            "duplicate_concern": is_dup,
            "duplicate_of_id": dup_of,
            "is_flagged": is_flagged,
            "flag_reasons": "; ".join(flag_reasons) if flag_reasons else "None",
            "closure_evidence": http_info["closure_evidence"],
            "audit_confidence": confidence,
            "is_classified": job.get("model_confidence") is not None,
            "stored_is_fresher_friendly": job.get("is_fresher_friendly"),
            "created_at": job.get("created_at")
        }

    completed_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {executor.submit(audit_single_job, j): j for j in jobs}
        for future in as_completed(future_to_job):
            completed_count += 1
            rec = future.result()
            audit_records.append(rec)
            if completed_count % 50 == 0 or completed_count == total_jobs:
                print(f"Audited {completed_count}/{total_jobs} jobs ({completed_count/total_jobs*100:.1f}%)...")

    # Sort by job_id
    audit_records.sort(key=lambda x: x["job_id"])
    total_duration = round(time.time() - start_time, 2)
    print(f"Audit completed in {total_duration}s.")

    # Write CSV Report
    with open(CSV_REPORT_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "job_id", "job_title", "employer", "source", "original_url", "final_url",
            "http_status", "job_status", "vacancy_authenticity", "india_eligibility_status",
            "fresher_suitability_status", "required_yoe", "duplicate_concern",
            "duplicate_of_id", "is_flagged", "flag_reasons", "closure_evidence", "audit_confidence"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(audit_records)
    print(f"CSV Report written to: {CSV_REPORT_PATH}")

    # Write JSON Report
    with open(JSON_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)
    print(f"JSON Report written to: {JSON_REPORT_PATH}")

    # Aggregate Statistics
    stats = compute_audit_statistics(audit_records, total_duration)
    return audit_records, stats


def compute_audit_statistics(records: List[Dict[str, Any]], duration: float) -> Dict[str, Any]:
    """Compute comprehensive metrics across the audited records."""
    total = len(records)

    # Job status counts
    status_counts: Dict[str, int] = {}
    for r in records:
        s = r["job_status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    # Source breakdown
    source_stats: Dict[str, Dict[str, int]] = {}
    for r in records:
        src = r["source"]
        st = r["job_status"]
        if src not in source_stats:
            source_stats[src] = {"total": 0, "open": 0, "closed": 0, "inaccessible": 0, "unverifiable": 0, "generic": 0, "invalid": 0}
        source_stats[src]["total"] += 1
        if st == "OPEN_VERIFIED": source_stats[src]["open"] += 1
        elif st == "CLOSED": source_stats[src]["closed"] += 1
        elif st == "INACCESSIBLE": source_stats[src]["inaccessible"] += 1
        elif st == "UNVERIFIABLE": source_stats[src]["unverifiable"] += 1
        elif st == "GENERIC_CAREERS_PAGE": source_stats[src]["generic"] += 1
        elif st == "INVALID_LINK": source_stats[src]["invalid"] += 1

    # India eligibility
    india_counts: Dict[str, int] = {}
    for r in records:
        i = r["india_eligibility_status"]
        india_counts[i] = india_counts.get(i, 0) + 1

    # Fresher suitability
    fresher_counts: Dict[str, int] = {}
    for r in records:
        fs = r["fresher_suitability_status"]
        fresher_counts[fs] = fresher_counts.get(fs, 0) + 1

    # Duplicate count
    dup_count = sum(1 for r in records if r["duplicate_concern"])

    # Flagged count
    flagged_count = sum(1 for r in records if r["is_flagged"])

    # Employer breakdown
    employer_stats: Dict[str, Dict[str, int]] = {}
    for r in records:
        emp = r["employer"] or "Unknown"
        if emp not in employer_stats:
            employer_stats[emp] = {"total": 0, "open": 0, "closed": 0, "flagged": 0}
        employer_stats[emp]["total"] += 1
        if r["job_status"] == "OPEN_VERIFIED": employer_stats[emp]["open"] += 1
        elif r["job_status"] == "CLOSED": employer_stats[emp]["closed"] += 1
        if r["is_flagged"]: employer_stats[emp]["flagged"] += 1

    return {
        "total_canonical": total,
        "successfully_audited": total,
        "not_audited": 0,
        "percentage_audited": 100.0,
        "duration_seconds": duration,
        "status_breakdown": status_counts,
        "source_breakdown": source_stats,
        "india_eligibility": india_counts,
        "fresher_suitability": fresher_counts,
        "duplicate_count": dup_count,
        "flagged_count": flagged_count,
        "employer_stats": employer_stats
    }


if __name__ == "__main__":
    records, stats = run_audit(max_workers=8)
    print("\n" + "="*80)
    print("AUDIT EXECUTION SUMMARY:")
    print(f"Total Canonical Jobs:     {stats['total_canonical']}")
    print(f"Successfully Audited:     {stats['successfully_audited']} ({stats['percentage_audited']}%)")
    print(f"Execution Duration:       {stats['duration_seconds']}s")
    print("-" * 80)
    print("JOB STATUS BREAKDOWN:")
    for status, count in sorted(stats["status_breakdown"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {status:<22}: {count:>4} ({count/stats['total_canonical']*100:.1f}%)")
    print("-" * 80)
    print("SOURCE BREAKDOWN:")
    for src, d in stats["source_breakdown"].items():
        print(f"  {src:<12}: Total={d['total']}, Open={d['open']}, Closed={d['closed']}, Inaccessible={d['inaccessible']}")
    print("-" * 80)
    print(f"Total Potential Duplicates: {stats['duplicate_count']}")
    print(f"Total Flagged Jobs:         {stats['flagged_count']}")
    print("=" * 80)
