"""Prompt Templates & Formatters for Gemini Batch Classification.

Enforces deterministic classification guidelines and intelligent, bounded description section extraction.
"""
import re
from typing import List, Dict, Any, Optional
from app.config import settings

SYSTEM_INSTRUCTIONS = """You are an expert AI Job Classification Engine specialized in the Indian tech hiring ecosystem.
Your task is to analyze batches of job postings and classify each job across four dimensions:
1. role_category
2. standardized_city
3. job_type
4. fresher_eligibility

TAXONOMY & ALLOWED VALUES:

1. role_category (MUST be one of):
- 'Frontend': React, Vue, Angular, HTML/CSS, UI engineering.
- 'Backend': Python, Java, Node.js, Go, C#, Django, Spring, FastAPI, REST/gRPC backend development.
- 'Full Stack': Combined frontend and backend stack responsibilities.
- 'Mobile': Android (Kotlin), iOS (Swift), Flutter, React Native mobile apps.
- 'Data & Analytics': Data Analyst, Business Analyst, BI, SQL, Tableau, PowerBI.
- 'AI / ML': Machine Learning, Data Scientist, GenAI, NLP, Computer Vision, Prompt Engineer.
- 'DevOps & Cloud': SRE, Cloud Engineer, Docker, Kubernetes, CI/CD, AWS, GCP, Azure.
- 'QA & Testing': SDET, Manual/Automation QA, Selenium, Cypress, Playwright, API testing.
- 'Cybersecurity': Security Analyst, Pentester, InfoSec, SOC Analyst.
- 'Product & Design': UI/UX Designer, Product Management.
- 'Other Tech': IT Support, Technical Writer, Developer Relations, Systems Admin.
- 'Non-Tech': Content Writing, Digital Marketing, Sales, Operations, HR.

2. standardized_city (MUST be one of):
- 'Bengaluru': Bangalore, Bengaluru, Electronic City, Whitefield, Bellandur.
- 'Hyderabad': Hyderabad, Secunderabad, HITEC City, Gachibowli, Cyberabad.
- 'Pune': Pune, Hinjewadi, Magarpatta, Kharadi.
- 'Mumbai': Mumbai, Navi Mumbai, Thane, Andheri, Powai.
- 'Delhi-NCR': New Delhi, Delhi, Gurugram, Gurgaon, Noida, Greater Noida, Faridabad.
- 'Chennai': Chennai, Madras, OMR.
- 'Kolkata': Kolkata, Calcutta, Salt Lake.
- 'Ahmedabad': Ahmedabad, Gandhinagar, GIFT City.
- 'Remote': Explicit Remote, Work from Home, WFH, Pan-India remote, Worldwide remote, or generic 'India'/'Pan-India' location postings without a specific physical city or onsite requirement.
- 'Other India': Identifiable Indian Tier-2/3 cities (e.g. Kochi, Jaipur, Indore, Chandigarh, Coimbatore).
- 'Unknown': When location is completely missing or cannot be identified. NEVER fabricate a city.

3. job_type (MUST be one of):
- 'Full-Time', 'Internship', 'Contract', 'Part-Time', 'Unknown'

4. fresher_eligibility (MUST be one of):
- 'fresher_friendly': Roles explicitly suitable for candidates with 0-1 years experience, college graduates, final-year students, freshers, genuine internships, and genuine entry-level trainee roles (including Graduate Engineer Trainee / GET, Management Trainee, Industrial Trainee, or Apprentice) with no contradictory prior experience requirements.
- 'not_fresher_friendly': Explicitly requires 2+ years experience, mid/senior level, team lead, manager, executive, or advanced tenure.
- 'uncertain': Experience requirement is unstated, ambiguous, or cannot be determined from snippet.

IMPORTANT GUIDELINES FOR FRESHER ELIGIBILITY:
- Genuine entry-level trainee/internship roles with no contradictory experience requirements should generally be 'fresher_friendly'.
- Explicit 2+ years experience, seniority, or leadership requirements override generic entry titles and must be classified as 'not_fresher_friendly'.
- Missing or empty job descriptions or ambiguous experience requirements must NOT be assumed or fabricated; classify as 'uncertain' unless the title explicitly denotes an intern/trainee role (e.g. 'Software Intern', 'GET') or senior role (e.g. 'Lead', 'Senior').
- Freelance or contract status alone does NOT determine fresher eligibility. Look strictly at required experience, skills, and seniority level.

IMPORTANT CONSTRAINTS:
- For every job in the input list, you MUST return exactly one classification matching its exact `job_id`.
- Do NOT omit any job_id from the batch.
- Do NOT repeat any job_id.
- Do NOT invent or output any foreign job_id not present in the input list.
- confidence_score: provide your self-reported confidence between 0.0 and 1.0.
- reasoning: provide a concise 1-sentence factual justification citing explicit words from the title or snippet.
"""

SECTION_HEADER_PATTERN = re.compile(
    r"(?:\n|\A)\s*(?:[-*#_ ]*)\s*("
    r"who\s+you\s+are|"
    r"what\s+you(?:'ll|\s+will)\s+(?:need|bring|do)|"
    r"what\s+we(?:'re|\s+are)\s+looking\s+for|"
    r"requirements?|"
    r"qualifications?|"
    r"experience(?:\s+and\s+skills)?|"
    r"eligibility|"
    r"key\s+responsibilities|"
    r"responsibilities|"
    r"skills\s+(?:and|&)\s+requirements"
    r")\s*(?::|—|-|\n|\Z)",
    re.IGNORECASE
)

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def clean_html(text: str) -> str:
    """Strip HTML tags and convert common HTML entities."""
    if not text:
        return ""
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_relevant_description(raw_description: Optional[str], max_chars: int = 3000) -> str:
    """Clean and extract relevant sections of job description within a bounded character limit.

    If description is within limit, returns cleaned text.
    If longer, preserves initial role overview (up to 700 chars) and stitches the highest-priority
    qualifications / requirements section, guaranteeing the model sees both role context and requirements.
    """
    if not raw_description or not raw_description.strip():
        return "N/A"

    cleaned = clean_html(raw_description)
    if len(cleaned) <= max_chars:
        return cleaned

    # Search for requirements / qualifications sections
    matches = list(SECTION_HEADER_PATTERN.finditer(cleaned))
    if not matches:
        truncated = cleaned[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > int(max_chars * 0.8):
            truncated = truncated[:last_space]
        return truncated + "..."

    # Look for qualification / requirement headers first
    qual_match = None
    for m in matches:
        header_text = m.group(1).lower()
        if any(k in header_text for k in [
            "who you are", "what you'll need", "what you need", "what you bring",
            "what we're looking for", "requirement", "qualification", "experience", "eligibility"
        ]):
            qual_match = m
            break

    if not qual_match:
        qual_match = matches[0]

    match_start = qual_match.start()

    # If the heading starts early, take from the beginning up to max_chars
    if match_start <= 700:
        truncated = cleaned[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > int(max_chars * 0.8):
            truncated = truncated[:last_space]
        return truncated + "..."

    # Heading starts deeper: combine overview + requirements
    intro_budget = 700
    intro_text = cleaned[:intro_budget]
    last_intro_space = intro_text.rfind(" ")
    if last_intro_space > int(intro_budget * 0.7):
        intro_text = intro_text[:last_intro_space]

    req_budget = max_chars - len(intro_text) - 45
    req_text = cleaned[match_start:match_start + req_budget]
    last_req_space = req_text.rfind(" ")
    if len(cleaned) > match_start + req_budget and last_req_space > int(req_budget * 0.8):
        req_text = req_text[:last_req_space] + "..."

    return f"{intro_text} ...\n\n[Key Requirements & Qualifications]:\n{req_text}"


def format_batch_prompt(jobs: List[Dict[str, Any]], max_desc_chars: Optional[int] = None) -> str:
    """Format a batch of jobs into a compact, token-efficient prompt string."""
    limit = max_desc_chars if max_desc_chars is not None else settings.CLASSIFIER_DESCRIPTION_MAX_CHARS

    prompt_lines = [
        "Classify the following batch of jobs into the structured schema.",
        f"BATCH JOB COUNT: {len(jobs)}",
        f"BATCH JOB IDs TO CLASSIFY: {[j['id'] for j in jobs]}",
        "",
        "--- JOB BATCH START ---"
    ]

    for j in jobs:
        desc_snippet = extract_relevant_description(j.get("description"), max_chars=limit)

        prompt_lines.append(
            f"Job ID: {j['id']}\n"
            f"Title: {j['title']}\n"
            f"Company: {j.get('company') or 'N/A'}\n"
            f"Location: {j.get('raw_location') or 'N/A'}\n"
            f"Description Snippet: {desc_snippet}\n"
            f"---"
        )

    prompt_lines.append("--- JOB BATCH END ---")
    prompt_lines.append("Return JSON with 'classifications' containing all items.")
    return "\n".join(prompt_lines)
