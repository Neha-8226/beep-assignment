import urllib.request
import urllib.error
import json
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with open('scratch_audit_24_jobs.json', 'r', encoding='utf-8') as f:
    jobs = json.load(f)

page_audits = []

for j in jobs:
    jid = j['id']
    url = j['apply_url']
    source = j['source']
    
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    
    html_text = ""
    status = None
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            status = resp.getcode()
            html_text = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        status = str(e)
    
    # Check for closed/expired indicators
    is_closed = False
    closed_evidence = []
    
    lower_html = html_text.lower()
    if "this job has been withdrawn" in lower_html:
        is_closed = True
        closed_evidence.append("withdrawn")
    if "this listing has expired" in lower_html or "this job has expired" in lower_html:
        is_closed = True
        closed_evidence.append("expired")
    if "applications are no longer being accepted" in lower_html or "job is no longer available" in lower_html:
        is_closed = True
        closed_evidence.append("closed")
    if "this position has been filled" in lower_html:
        is_closed = True
        closed_evidence.append("position filled")
        
    # Check for apply button / link
    has_apply_action = bool(re.search(r'apply|submit application', lower_html))
    
    # Extract title from html if present
    page_title_match = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
    page_title = page_title_match.group(1).strip() if page_title_match else ""
    page_title = re.sub(r'\s+', ' ', page_title)
    
    # Check text snippets for experience requirements
    exp_matches = re.findall(r'(\d+[\s\-\+]*(?:to\s*\d+)?\s*(?:years?|yrs?)(?:\s*of)?\s*experience)', lower_html)
    fresher_matches = re.findall(r'(fresher[s]?|intern[s]?|entry[\s\-]level|0[\s\-]1\s*years?)', lower_html)
    
    print(f"Job {jid} [{source}]: Status={status} | Closed={is_closed} ({closed_evidence}) | Title: {page_title[:45]}")
    print(f"   Exp terms: {list(set(exp_matches))[:3]} | Fresher terms: {list(set(fresher_matches))[:3]}")
    
    page_audits.append({
        'id': jid,
        'title': j['title'],
        'company': j['company'],
        'source': source,
        'apply_url': url,
        'http_status': status,
        'page_title': page_title,
        'is_closed': is_closed,
        'closed_evidence': closed_evidence,
        'has_apply_action': has_apply_action,
        'exp_terms': list(set(exp_matches)),
        'fresher_terms': list(set(fresher_matches))
    })

with open('scratch_page_audits.json', 'w', encoding='utf-8') as f:
    json.dump(page_audits, f, indent=2)

print("Saved scratch_page_audits.json")
