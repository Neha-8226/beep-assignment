import json
import re

with open('scratch_audit_24_jobs.json', 'r', encoding='utf-8') as f:
    jobs = json.load(f)

with open('scratch_url_audit.json', 'r', encoding='utf-8') as f:
    urls = {u['id']: u for u in json.load(f)}

with open('backend/data/ground_truth_benchmark.json', 'r', encoding='utf-8') as f:
    gt_map = {g['job_id']: g for g in json.load(f)}

print(f"Total jobs loaded: {len(jobs)}")

for j in jobs:
    jid = j['id']
    u = urls.get(jid, {})
    gt = gt_map.get(jid, {})
    
    desc = j.get('description') or ''
    # clean HTML tags for snippet analysis
    clean_desc = re.sub(r'<[^>]+>', ' ', desc)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
    
    print("=" * 80)
    print(f"JOB ID: {jid} | Source: {j['source']} | Ext ID: {j['external_id']}")
    print(f"Title: {j['title']}")
    print(f"Company: {j['company']}")
    print(f"Location Raw: {j['raw_location']} | Standardized City: {j['standardized_city']}")
    print(f"Apply URL: {j['apply_url']} (HTTP {u.get('http_status')})")
    print(f"Posted At: {j['posted_at']} | Created At: {j['created_at']}")
    print(f"Job Type: {j['job_type']}")
    print(f"Ground Truth Status: {gt.get('human_fresher_status')} | GT City: {gt.get('human_city')}")
    print(f"GT Notes: {gt.get('notes')}")
    print(f"Description ({len(clean_desc)} chars): {clean_desc[:300]}...")
