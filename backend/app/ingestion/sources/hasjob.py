"""Hasjob (HasGeek India) Source Adapter.

Fetches tech openings from the official public Atom feed of Hasjob.
Hasjob is an India-native startup job board, so is_indian_source = True.
"""
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from email.utils import parsedate_to_datetime

from app.ingestion.sources.base import BaseSourceAdapter


def sanitize_html(raw_html: Optional[str]) -> Optional[str]:
    """Convert HTML content into readable, clean plain-text.

    Preserves paragraph and list boundaries while removing markup and excess whitespace.
    """
    if not raw_html or not isinstance(raw_html, str):
        return None

    text = raw_html
    # Convert block line breaks
    text = re.sub(r"<(?:br\s*/?|/p|/li|/div|/h[1-6])>", "\n", text, flags=re.IGNORECASE)
    # Strip HTML tags before unescaping entities to prevent entity-encoded text from tag-stripping
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities
    text = html.unescape(text)
    # Normalize horizontal whitespace
    text = re.sub(r"[ \t]+", " ", text)
    # Normalize vertical whitespace
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    cleaned = text.strip()
    return cleaned if cleaned else None


def extract_company_and_title(
    raw_title: str,
    content_html: Optional[str],
    apply_url: str
) -> Tuple[Optional[str], str]:
    """Extract company name and clean job title with structured fallback hierarchy.

    Hierarchy:
    1. Content header anchor: <strong><a href="...">CompanyName</a></strong>
    2. Clean title suffix ('Title - Company') if suffix is not promotional/location text
    3. URL domain prefix: https://hasjob.co/<company-domain>/<post-id>
    """
    clean_title = raw_title.strip()
    company = None

    # Priority 1: Check content HTML for primary company link
    if content_html:
        anchor_match = re.search(
            r"<strong>\s*<a\s+[^>]*href=[\"'][^\"']*[\"'][^>]*>([^<]+)</a>\s*</strong>",
            content_html,
            re.IGNORECASE
        )
        if anchor_match:
            cand = anchor_match.group(1).strip()
            # Verify candidate is not promotional or generic location
            if cand and not re.search(r"(\$|€|£|₹|hourly|per\s*hour|remote|worldwide)", cand, re.I):
                company = cand

    # Priority 2: Title format 'Title - Company'
    if " - " in clean_title:
        parts = clean_title.rsplit(" - ", 1)
        cand_suffix = parts[1].strip()
        # Reject promotional, compensation, or generic strings
        is_promo = bool(re.search(
            r"(\$|€|£|₹|hourly|per\s*hour|per\s*month|lpa|ctc|\b\d+k\b|\b\d+/\b|remote|worldwide|full[- ]*time|contract)",
            cand_suffix,
            re.IGNORECASE
        ))
        if not is_promo and len(cand_suffix) >= 2:
            if not company:
                company = cand_suffix
            clean_title = parts[0].strip()

    # Priority 3: Extract organization slug from URL domain if structured domain present
    if not company and apply_url:
        domain_match = re.search(r"hasjob\.co/([^/]+)/", apply_url)
        if domain_match:
            slug = domain_match.group(1).strip()
            # Only use as domain fallback if an actual domain extension is present
            if "." in slug:
                clean_slug = re.sub(r"\.(com|in|co\.uk|org|net|io|tech|ai|xyz)$", "", slug, flags=re.IGNORECASE)
                if clean_slug and len(clean_slug) >= 2:
                    company = clean_slug.replace("-", " ").replace("_", " ").title()

    return company, clean_title


class HasjobAdapter(BaseSourceAdapter):
    """Adapter for Hasjob public Atom feed."""

    source_name: str = "hasjob"
    is_indian_source: bool = True
    feed_url: str = "https://hasjob.co/feed"

    def fetch_records(self) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Fetch and parse Atom XML feed from Hasjob."""
        requests_made = 0
        records: List[Dict[str, Any]] = []

        try:
            req = urllib.request.Request(
                self.feed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeepJobAggregator/1.0"}
            )
            requests_made += 1

            with urllib.request.urlopen(req, timeout=12) as response:
                content = response.read()

            root = ET.fromstring(content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)

            for entry in entries:
                raw_title = entry.findtext("atom:title", default="", namespaces=ns).strip()
                link_elem = entry.find("atom:link", ns)
                apply_url = link_elem.attrib.get("href", "").strip() if link_elem is not None else ""
                entry_id = entry.findtext("atom:id", default="", namespaces=ns).strip()
                updated_str = entry.findtext("atom:updated", default="", namespaces=ns).strip()

                if not raw_title or not apply_url:
                    continue

                # 1. Native Location extraction from feed
                loc_elem = entry.findtext("atom:location", default="", namespaces=ns).strip()
                raw_location = loc_elem if loc_elem else "India"

                # 2. Content extraction (prioritize atom:content over atom:summary)
                content_elem = entry.find("atom:content", ns)
                raw_content = (content_elem.text if content_elem is not None and content_elem.text else "").strip()
                if not raw_content:
                    summary_elem = entry.find("atom:summary", ns)
                    raw_content = (summary_elem.text if summary_elem is not None and summary_elem.text else "").strip()

                description = sanitize_html(raw_content)

                # 3. Robust Company and Title extraction
                company, title = extract_company_and_title(
                    raw_title=raw_title,
                    content_html=raw_content,
                    apply_url=apply_url
                )

                posted_at = None
                if updated_str:
                    try:
                        posted_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                records.append({
                    "source": self.source_name,
                    "external_id": entry_id or apply_url,
                    "title": title,
                    "company": company,
                    "raw_location": raw_location,
                    "description": description,
                    "apply_url": apply_url,
                    "posted_at": posted_at
                })

            return records, requests_made, None

        except Exception as e:
            return records, requests_made, f"Hasjob fetch failed: {str(e)}"
