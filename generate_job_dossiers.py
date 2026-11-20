import json
import re

with open('scratch_audit_24_jobs.json', 'r', encoding='utf-8') as f:
    jobs = json.load(f)

with open('scratch_page_audits.json', 'r', encoding='utf-8') as f:
    pages = {p['id']: p for p in json.load(f)}

with open('backend/data/ground_truth_benchmark.json', 'r', encoding='utf-8') as f:
    gt_map = {g['job_id']: g for g in json.load(f)}

dossiers = []

for j in jobs:
    jid = j['id']
    p = pages.get(jid, {})
    gt = gt_map.get(jid, {})
    
    # Analyze each dimension
    # 1. Authenticity:
    # HTTP 200 returned, page title matches job.
    # Check if suspicious (e.g. Job 10: company='remote, worldwide, $100/hr' which is a spammy title/company format)
    
    # 2. India Eligibility:
    # Hasjob is India-based, but is it explicitly India?
    # Remotive has "Worldwide" raw_location.
    
    # 3. Fresher Suitability:
    # Check title and descriptions for senior/lead/intern/freshers/years of experience.
    
    # 4. Freshness:
    # Active HTTP 200, no closure banner.
    
    dossiers.append({
        'id': jid,
        'title': j['title'],
        'company_db': j['company'],
        'source': j['source'],
        'external_id': j['external_id'],
        'apply_url': j['apply_url'],
        'raw_location': j['raw_location'],
        'posted_at': j['posted_at'],
        'page_title': p.get('page_title'),
        'http_status': p.get('http_status'),
        'is_closed': p.get('is_closed'),
        'gt_status': gt.get('human_fresher_status'),
        'gt_notes': gt.get('notes'),
        'exp_terms': p.get('exp_terms', []),
        'fresher_terms': p.get('fresher_terms', [])
    })

with open('scratch_audit_dossiers.json', 'w', encoding='utf-8') as f:
    json.dump(dossiers, f, indent=2)

print(f"Generated {len(dossiers)} audit dossiers.")
