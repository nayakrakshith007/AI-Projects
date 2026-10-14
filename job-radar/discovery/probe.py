"""Phase 0 probe: one polite GET per source. Records status, platform signature, feed/JSON-LD hints, JS-shell guess, robots.txt verdict."""
import csv, re, sys, json, urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import requests
UA = 'Mozilla/5.0 (compatible; JobRadarV3-probe/0.1; personal use)'
SIG = {
 'greenhouse': r'boards\.greenhouse\.io|job-boards\.greenhouse\.io|greenhouse\.io/embed',
 'lever': r'jobs\.lever\.co',
 'ashby': r'jobs\.ashbyhq\.com|ashbyhq',
 'workday': r'myworkdayjobs\.com|workday',
 'eightfold': r'eightfold\.ai',
 'taleo': r'taleo\.net',
 'icims': r'icims\.com',
 'smartrecruiters': r'smartrecruiters',
 'successfactors': r'successfactors|jobs\.sap\.com',
 'phenom': r'phenompeople|phenom\.com|cdn\.phenompeople',
 'avature': r'avature',
 'oracle_hcm': r'oraclecloud\.com/hcmUI|candidateexperience',
 'jobvite': r'jobvite',
 'workable': r'workable\.com',
 'recruitee': r'recruitee\.com',
 'teamtailor': r'teamtailor',
 'comeet': r'comeet',
 'rss': r'application/(rss|atom)\+xml',
 'jsonld_job': r'"@type"\s*:\s*"JobPosting"',
 'nextdata': r'__NEXT_DATA__',
 'nuxt': r'__NUXT__',
}
def probe(row):
    out = dict(id=row['id'], name=row['name'], url=row['url'])
    u = row['url']
    try:
        p = urlparse(u)
        rp = urllib.robotparser.RobotFileParser()
        try:
            rr = requests.get(f"{p.scheme}://{p.netloc}/robots.txt", headers={'User-Agent': UA}, timeout=10)
            rp.parse(rr.text.splitlines() if rr.status_code == 200 else [])
            out['robots_ok'] = rp.can_fetch(UA, u)
        except Exception:
            out['robots_ok'] = 'unknown'
        r = requests.get(u, headers={'User-Agent': UA, 'Accept-Language': 'en'}, timeout=20, allow_redirects=True)
        t = r.text or ''
        out.update(status=r.status_code, final=r.url, ctype=r.headers.get('content-type', '')[:40], bytes=len(r.content),
                   server=r.headers.get('server', ''), cf=('cf-ray' in r.headers) or ('cloudflare' in r.headers.get('server', '').lower()))
        out['sigs'] = ','.join(k for k, v in SIG.items() if re.search(v, t, re.I))
        text = re.sub(r'<script.*?</script>|<style.*?</style>|<[^>]+>', ' ', t, flags=re.S)
        out['visible_text'] = len(re.sub(r'\s+', ' ', text).strip())
        out['challenge'] = bool(re.search(r'just a moment|attention required|verify you are human|captcha|access denied|cf-chl', t[:6000], re.I))
        out['login_wall'] = bool(re.search(r'sign in to|log in to continue|create an account to', t[:20000], re.I))
    except Exception as e:
        out.update(status='ERR', err=str(e)[:80])
    return out
rows = list(csv.DictReader(open('discovery/sources_raw.csv', encoding='utf-8')))
seen, uniq = {}, []
for r in rows:
    uniq.append(r)
with ThreadPoolExecutor(6) as ex:
    res = list(ex.map(probe, uniq))
keys = ['id','name','url','status','final','ctype','bytes','visible_text','server','cf','challenge','login_wall','robots_ok','sigs','err']
with open('discovery/probe.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore'); w.writeheader(); w.writerows(res)
print('done', len(res))
