import urllib.request
import xml.etree.ElementTree as ET
import re

req = urllib.request.Request('https://hasjob.co/feed', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as r:
    xml_data = r.read()

root = ET.fromstring(xml_data)
ns = {'atom': 'http://www.w3.org/2005/Atom'}
entries = root.findall('atom:entry', ns)

print(f"Total entries: {len(entries)}")
for idx, e in enumerate(entries):
    title = e.findtext('atom:title', '', ns).strip()
    link = e.find('atom:link', ns).attrib.get('href', '')
    loc = e.findtext('atom:location', '', ns).strip()
    content = e.findtext('atom:content', '', ns).strip()
    
    # Try extracting company from content HTML
    comp_match = re.search(r'<strong>\s*<a\s+[^>]*href=["\'][^"\']*["\'][^>]*>([^<]+)</a>\s*</strong>', content, re.I)
    comp_name = comp_match.group(1).strip() if comp_match else None
    
    # Extract domain from URL
    url_match = re.search(r'hasjob\.co/([^/]+)/', link)
    comp_domain = url_match.group(1) if url_match else None
    
    # Fallback to Title ' - ' company if domain or content matches
    title_comp = None
    clean_title = title
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        # only accept if not promotional like $100/hr
        cand = parts[1].strip()
        if not re.search(r'(\$|€|£|hourly|per hour|remote|worldwide)', cand, re.I):
            title_comp = cand
            clean_title = parts[0].strip()
            
    final_company = comp_name or title_comp or (comp_domain.split('.')[0].title() if comp_domain else None)
    
    # HTML sanitization of content
    text_desc = re.sub(r'<[^>]+>', ' ', content)
    text_desc = re.sub(r'\s+', ' ', text_desc).strip()
    
    print(f"[{idx+1}] Title: '{clean_title[:35]}' | Comp: '{final_company}' | Loc: '{loc}' | DescLen: {len(text_desc)}")
