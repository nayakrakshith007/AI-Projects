"""Phase 0 classification: one decision per source row. 'verified' = I called the endpoint and got jobs; 'candidate' = signature seen, not yet tested."""
import csv
raw = {r['id']: r for r in csv.DictReader(open('discovery/sources_raw.csv', encoding='utf-8'))}
C = {}
def put(ids, cls, reader, verified, note=''):
    for i in ids.split():
        C[i] = dict(cls=cls, reader=reader, verified=verified, note=note)
# T1 feeds / APIs, no browser
put('R33', 'A', 'json_feed', 'verified', 'remoteok.com/api, 100 jobs')
put('R34', 'A', 'json_feed', 'verified', 'remotive.com/api/remote-jobs (HTML page is 403, API works)')
put('R32', 'A', 'rss', 'verified', 'weworkremotely.com/remote-jobs.rss')
put('R36', 'A', 'json_feed', 'verified', 'workingnomads.com/api/exposed_jobs/, 50 jobs')
put('R37', 'A', 'rss', 'verified', 'jobspresso.co/feed/?post_type=job_listing')
# T2 ATS public APIs
put('R44 R47 R53 R55 R56 R59', 'B', 'greenhouse_api', 'verified', 'boards-api.greenhouse.io/v1/boards/<slug>/jobs')
put('R43 R46 R54', 'B', 'ashby_api', 'verified', 'api.ashbyhq.com/posting-api/job-board/<slug>')
put('R05', 'B', 'workable_api', 'verified', 'apply.workable.com/api/v1/widget/accounts/huggingface, 6 jobs')
put('R45', 'B', 'lever_api', 'candidate', 'lever slug "mistral" returned 0 jobs; check real slug or ATS')
put('R60', 'B', 'ashby_api', 'candidate', 'slug "replicate" 404; find the real board')
put('G40', 'B', 'workday_cxs', 'verified', 'POST /wday/cxs/cat/CaterpillarCareers/jobs works')
# T3 platform candidates (signature seen, tenant to be tested)
put('G17 G41 G21 G10 G05', 'B', 'workday_cxs', 'candidate', 'Workday signature; find tenant/site id')
put('G06 G18 G23 G31 G24', 'B', 'eightfold_api', 'candidate', 'Eightfold; amex /api/apply/v2 returned 404 so endpoint or domain param needs work')
put('R49 G12', 'B', 'eightfold_api', 'candidate', 'Microsoft careers (Eightfold PCSX); heavy page, use JSON')
put('G01', 'B', 'oracle_hcm_api', 'candidate', 'JPMorgan on Oracle HCM; REST recruitingCEJobRequisitions to test')
put('G19 G34 G42 R57', 'B', 'phenom_widget', 'candidate', 'Phenom People; search widget JSON')
put('G25 G37 G46', 'B', 'avature', 'candidate', 'Avature search pages (server-rendered HTML likely)')
put('G45 G47', 'B', 'icims', 'candidate', 'iCIMS; server-rendered search')
put('G20', 'B', 'successfactors', 'candidate', 'SAP SuccessFactors search')
put('G03 G08', 'B', 'taleo', 'candidate', 'Taleo hosts did not resolve from here; recheck, may be retired')
# T4 custom pages: find the JSON behind the page once with Playwright, then call it without a browser
put('R41 G11', 'C', 'custom_json_sniff', 'candidate', 'Google Careers; sniff XHR in dev, then plain HTTP')
put('R42 G15', 'C', 'custom_json_sniff', 'candidate', 'Meta Careers; GraphQL, page is a JS shell (12 chars of text)')
put('R50 G13 G29', 'C', 'custom_json_sniff', 'candidate', 'amazon.jobs has a public search.json style endpoint to confirm')
put('R51 G14', 'C', 'custom_json_sniff', 'candidate', 'Apple jobs; JSON behind the page')
put('R48 R52 G02 G04 G07 G09 G16 G22 G26 G27 G28 G30 G32 G33 G36 G38 G39 G43 G44', 'C', 'custom_json_sniff', 'candidate', 'Own career site; confirm JSON/XHR or fall back to Playwright')
put('G35', 'D', 'park', 'candidate', 'Bot challenge on first request; never bypass, park until owner passes by hand')
# VC portfolio boards
put('R14 R13 R15 R17 R18 R19 R16', 'C', 'vc_board', 'candidate', 'VC portfolio board (usually Getro/Consider widget); one reader may cover several')
put('R04 R11', 'C', 'yc_jobs', 'candidate', 'YC jobs; ycombinator.com/jobs is public, workatastartup is gated')
# specialist boards
put('R21 R61 R64 R66 R69 R38 R25 R29 R79', 'C', 'html_or_sitemap', 'candidate', 'Public HTML or JSON-LD; small sites, check robots')
put('R02', 'C', 'custom_json_sniff', 'candidate', 'Levels.fyi (Next.js data); challenge page seen once')
put('R24 R31 R65 R30', 'D', 'park', 'candidate', 'Challenge, 403 or 404 on first request')
# dead or unreachable from here
put('R22 R27 R28 R40 R63', 'D', 'recheck_once', 'candidate', 'Domain unreachable or parked from here; recheck, then drop')
# login, paid, marketplaces without a public job list
put('R35 R71 R73 R20', 'D', 'park', 'rule', 'Login or paid membership (project rule)')
put('R01', 'D', 'park', 'rule', 'LinkedIn: V2 already covers it; robots disallow, bot challenge; not repeated in V3')
put('R03', 'D', 'park', 'rule', 'Wellfound: V2 already covers it')
put('R06 R07 R08 R26 R39 R67 R68 R70 R74 R75 R76 R78 R81 R10 R09 R23 R62 R72', 'D', 'park', 'candidate', 'Talent marketplace, freelance bid board or no public job list; low value for a daily job radar')
put('R82 R83 R84 R85 R86', 'S', 'skip', 'rule', 'Newsletter digest (project rule)')
DUP = {'R12': 'R03', 'R58': 'R05', 'R77': 'R08', 'R80': 'R07', 'G11': 'R41', 'G12': 'R49', 'G14': 'R51', 'G15': 'R42', 'G13': 'R50', 'G29': 'R50'}
missing = [i for i in raw if i not in C and i not in DUP]
print('unclassified:', missing)
out = []
for i, r in raw.items():
    c = dict(C.get(i, {})) if i not in DUP else dict(cls='X', reader='duplicate', verified='n/a', note=f'same as {DUP[i]}')
    out.append(dict(id=i, sheet=r['sheet'], name=r['name'], url=r['url'], **c))
with open('discovery/sources.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
from collections import Counter
print(Counter(o['cls'] for o in out))
print(Counter((o['cls'], o['verified']) for o in out if o['cls'] in 'ABC'))
print(Counter(o['reader'] for o in out))
