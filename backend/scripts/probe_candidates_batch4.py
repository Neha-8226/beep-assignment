"""Batch 4 Candidate Discovery & Validation Probe."""
import sys, json, time, urllib.request, requests
sys.path.insert(0, 'backend')
from app.database import SessionLocal
from app.ingestion.relevance import evaluate_job_relevance
from app.ingestion.dedup import evaluate_candidate

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeepJobAggregator/1.0', 'Accept': 'application/json'}
db = SessionLocal()

# Curated list of potential employers with GCCs or offices in India
gh_candidates = [
    'pubmatic', 'sumologic', 'bitwarden', 'glg', 'appian', 'thoughtspot', 'anydesk',
    'crunchyroll', 'innovaccer', 'leadsquared', 'cleartax', 'airmeet', 'posthog',
    'temporal', 'kong', 'retool', 'hashicorp', 'confluent', 'nutanix', 'arista',
    'snowflake', 'teradata', 'commvault', 'couchbase', 'cloudera', 'sentry', 'fastly',
    'pingidentity', 'zetaglobal', 'bold', 'gravitonresearch', 'snyk', 'dynatrace',
    'newrelic', 'splunk', 'tanium', 'crowdstrike', 'sentinelone', 'sailpoint',
    'cyberark', 'rapid7', 'tenable', 'qualcomm', 'synopsys', 'cadence', 'ansys',
    'appliedmaterials', 'arm', 'nxp', 'broadcom', 'intel', 'amd', 'nvidia',
    'servicenow', 'salesforce', 'vmware', 'redhat', 'adobe', 'intuit', 'cisco',
    'paloaltonetworks', 'juniper', 'ciena', 'mathworks', 'autodesk', 'zendesk',
    'hubspot', 'box', 'dropbox', 'slack', 'zoom', 'affirm', 'brex', 'carta',
    'gusto', 'plaid', 'robinhood', 'snap', 'uber', 'lyft', 'doordash', 'instacart',
    'pinterest', 'airbnb', 'reddit', 'canva', 'atlassian', 'freshworks', 'chargebee',
    'clevertap', 'browserstack', 'postman', 'razorpay', 'phonepe', 'swiggy', 'zepto'
]

lever_candidates = [
    'palantir', 'startree', 'apollo247', 'clevertap', 'browserstack', 'urbancompany',
    'swiggy', 'zepto', 'rapido', 'dunzo', 'shadowfax', 'porter', 'spinny', 'cars24',
    'navi', 'smallcase', 'jar', 'games24x7', 'winzo', 'pocketfm', 'sharechat',
    'dailyhunt', 'invideo', 'glance', 'scaler', 'interviewbit', 'udaan', 'kuvera',
    'mamaearth', 'boat', 'delhivery', 'bharatpe', 'sourcegraph', 'vercel', 'netlify',
    'flyio', 'render', 'supabase', 'prisma', 'hasura', 'neon', 'linear', 'notion',
    'airtable', 'miro', 'figma', 'canva', 'atlassian', 'hotstar', 'upstox',
    'khatabook', 'lenskart', 'curefit', 'mpl', 'groww', 'postman', 'razorpay',
    'phonepe', 'cred', 'meesho', 'paytm', 'zeta', 'hevodata'
]

gh_hits = []
print('=== PROBING GREENHOUSE CANDIDATES ===')
for s in gh_candidates:
    url = f'https://boards-api.greenhouse.io/v1/boards/{s}/jobs?content=true'
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                jobs = data.get('jobs', [])
                net_new = 0
                for j in jobs:
                    rel = evaluate_job_relevance(j.get('title', ''), j.get('location', {}).get('name', ''), j.get('content', ''), False)
                    if rel.is_accepted:
                        ext_id = f"gh_{s}_{j.get('id')}"
                        d = evaluate_candidate(db, 'greenhouse', j.get('title', ''), j.get('absolute_url', ''), ext_id, s, j.get('location', {}).get('name', ''), j.get('content', ''))
                        if d.is_unique:
                            net_new += 1
                if net_new > 0:
                    gh_hits.append((s, len(jobs), net_new))
                    print(f'GH HIT: {s} (total: {len(jobs)}, net_new: {net_new})')
    except Exception:
        pass
    time.sleep(0.03)

lever_hits = []
print('\n=== PROBING LEVER CANDIDATES ===')
for s in lever_candidates:
    url = f'https://api.lever.co/v0/postings/{s}?mode=json'
    try:
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200 and isinstance(r.json(), list):
            jobs = r.json()
            net_new = 0
            for j in jobs:
                loc = j.get('categories', {}).get('location', '')
                rel = evaluate_job_relevance(j.get('text', ''), loc, j.get('descriptionPlain', ''), False)
                if rel.is_accepted:
                    ext_id = f"lever_{s}_{j.get('id')}"
                    d = evaluate_candidate(db, 'lever', j.get('text', ''), j.get('hostedUrl', ''), ext_id, s, loc, j.get('descriptionPlain', ''))
                    if d.is_unique:
                        net_new += 1
            if net_new > 0:
                lever_hits.append((s, len(jobs), net_new))
                print(f'LEVER HIT: {s} (total: {len(jobs)}, net_new: {net_new})')
    except Exception:
        pass
    time.sleep(0.03)

db.close()
print('\n================ SUMMARY ================')
print('Greenhouse Hits:', gh_hits)
print('Total GH net-new:', sum(h[2] for h in gh_hits))
print('Lever Hits:', lever_hits)
print('Total Lever net-new:', sum(h[2] for h in lever_hits))
print('Grand Total net-new:', sum(h[2] for h in gh_hits) + sum(h[2] for h in lever_hits))
