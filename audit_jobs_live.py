import urllib.request
import urllib.error
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with open('scratch_audit_24_jobs.json', 'r', encoding='utf-8') as f:
    jobs = json.load(f)

results = []
for j in jobs:
    url = j['apply_url']
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    status_code = None
    final_url = None
    err_msg = None
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            status_code = resp.getcode()
            final_url = resp.geturl()
    except urllib.error.HTTPError as e:
        status_code = e.code
        final_url = e.geturl()
        err_msg = f"HTTP {e.code}"
    except Exception as e:
        err_msg = str(e)
    
    print(f"Job {j['id']}: [{j['source']}] {j['title'][:35]} -> HTTP {status_code} ({err_msg or 'OK'}) Final: {final_url}")
    results.append({
        'id': j['id'],
        'title': j['title'],
        'apply_url': url,
        'http_status': status_code,
        'final_url': final_url,
        'error': err_msg
    })

with open('scratch_url_audit.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)
print("Finished checking URLs.")
