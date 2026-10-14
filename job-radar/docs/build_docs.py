"""Builds the two visual decision documents from the data below.
Run: python docs/build_docs.py   ->  docs/Architecture_and_Tech.html, docs/Product_Decisions.html
Edit the data here (not the HTML), then rebuild. Sources table comes from discovery/sources.csv."""
import csv, json, pathlib, html

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs'

# ---------------------------------------------------------------- tech decisions
TECH = [
 dict(id='AD-01', title='One reader per source type, not one scraper per site', status='decided', area='Readers',
  decision='Build a small number of readers (feed, platform API, custom page) and describe each website as one line in sources.csv.',
  why='There are 123 unique sources. V2 needed a full scraper (code, README, tests, page) per site. Most sites share a handful of job platforms, so one adapter covers many companies.',
  alts=['One scraper per site (V2 style): rejected, 120 scrapers and 100+ Chromes.', 'Pure Playwright crawl of every page: rejected, 300-500 MB per Chrome and fragile.'],
  evidence='Probe of 133 rows: 16 sources return jobs through plain HTTP today; 26 more show a platform signature (Workday, Eightfold, Phenom, Avature, iCIMS...).',
  risk='Each platform adapter still needs per-company tuning (tenant ids, filters).', refs=['TR-01', 'TR-02', 'PD-01']),
 dict(id='AD-02', title='Cheapest-method ladder', status='decided', area='Readers',
  decision='For each source try in this order: 1) public feed or JSON API, 2) the job platform\'s own public API, 3) the JSON that the career page itself calls (found once in development), 4) a headless browser.',
  why='Each step down costs more memory, time and breakage. Plain HTTP is about 50 MB for everything; one Chrome is 300-500 MB.',
  alts=['Always use a browser (simplest to write, most expensive to run).', 'Only APIs (cheapest, but leaves the big custom career pages unread).'],
  evidence='Tested today: RemoteOK, Remotive, We Work Remotely, Working Nomads, Jobspresso, Greenhouse x6 (Anthropic 647 jobs, xAI 307, Databricks 897...), Ashby x3 (OpenAI 808...), Workable, Workday (Caterpillar) all return jobs.',
  risk='APIs can change without notice, so every adapter gets a saved sample and a test (AD-12).', refs=['AD-03', 'AD-04', 'AD-12']),
 dict(id='AD-03', title='Playwright Python library is the fallback; Playwright CLI and Claude browsers are dev tools only', status='decided', area='Readers',
  decision='Where a browser is unavoidable, our own Python code drives Playwright headless, at most 2 Chromes at once. The Playwright CLI, Claude\'s built-in browser and Claude in Chrome are used only while developing.',
  why='The daily run must cost no tokens and little memory. The CLI and the built-in browser are designed for an LLM to drive one step at a time, which spends tokens on every step.',
  alts=['Playwright CLI in the daily run: same memory as the library, slower, built for step-by-step LLM use.', 'Built-in Claude browser daily: costs tokens each run and breaks the "free" rule.'],
  evidence='V2 ran 7 sites with about 8 Chromes in 35-40 minutes; its first all-at-once run opened about 100 Chromes and used all 16 GB.',
  risk='A few pages (Meta, Google) may need the browser and add memory pressure.', refs=['TR-04', 'AD-06']),
 dict(id='AD-04', title='Find the page\'s JSON once in development, then call it without a browser', status='decided', area='Readers',
  decision='For custom career pages, open the page once with a browser while developing, find the network call that returns the job list, and from then on call that URL with plain HTTP.',
  why='Most modern career pages are a thin shell over a JSON call. Reading the JSON is faster, lighter and more stable than reading rendered HTML.',
  alts=['Scrape rendered HTML every day.', 'Ask the LLM to read each page every day (costs tokens, rejected).'],
  evidence='Meta page text is 12 characters (a JS shell); Microsoft page is 670,000 characters, so rendered HTML is the wrong source.',
  risk='If the site changes the endpoint, the canary (AD-08) flags it and we re-discover.', refs=['AD-02', 'AD-08']),
 dict(id='AD-05', title='Separate V3 workbook, same 16 columns plus Source/Type', status='decided', area='Data',
  decision='Write pipeline/output/Job_Radar_V3.xlsx with the same 16 columns as V2 plus a Source/Type column. V2\'s Job_Radar.xlsx is never touched.',
  why='V2 is in daily use. The Workspace UI reads a fixed set of columns, so keeping them means the dashboard code can be reused.',
  alts=['Same file as V2: risks corrupting a working daily output.', 'A new column set: breaks reuse of the Workspace code.'],
  evidence='Owner chose "separate V3 workbook, same everything".', risk='Two workbooks to look at; the dashboard can show V3 only.', refs=['PD-04']),
 dict(id='AD-06', title='Two lanes by cost with a memory gate', status='decided', area='Runner',
  decision='Lane 1: HTTP sources, up to 8 at once, 1 request per second per host. Lane 2: browser sources, at most 2 Chromes. A source starts only when 1 GB of memory is free.',
  why='The laptop has 16 GB. HTTP work is cheap and can overlap; Chromes cannot.',
  alts=['Everything in parallel: crashed the machine in V2.', 'Everything one by one: needlessly slow.'],
  evidence='V2 numbers above.', risk='A slow host can hold a lane; each source has its own time limit and stall restart (reused from V2).', refs=['TR-03', 'TR-04']),
 dict(id='AD-07', title='Incremental reads using seen job ids', status='decided', area='Runner',
  decision='Keep the set of job ids already seen per source; process only new ids. Feeds and boards that return everything in one call still cost one request.',
  why='Daily runs should do work proportional to what is new, not to the size of every board.',
  alts=['Re-read and re-filter everything daily: simple but wastes time.'], evidence='Greenhouse and Ashby return the whole board in one call (hundreds of jobs).',
  risk='A job that is edited keeps its id; we compare a hash of title+location to catch changes.', refs=['TR-02']),
 dict(id='AD-08', title='Canary per source', status='decided', area='Runner',
  decision='A source that returns zero jobs twice in a row, or an unexpected shape, is shown as "broken" on the progress page instead of silently empty.',
  why='Silent failures are the main way a radar becomes useless.', alts=['Trust a zero result: hides outages.'], evidence='V2 learned this with stalled sites; it already tracks "needs you", "stalled" and "failed".',
  risk='A small board that really has zero jobs can false-alarm; it says "check" not "failed".', refs=['TR-06']),
 dict(id='AD-09', title='Local server on 127.0.0.1 with its own port', status='decided', area='Triggers',
  decision='A small local web server serves the progress page and handles Start and Stop. It listens on 127.0.0.1 only, checks the Host header, and uses port 8771 (V2 uses 8770).',
  why='A browser page cannot start a process by itself; a local server is the safe bridge. A separate port means V2 and V3 can both run.',
  alts=['Page opened as a file with no server: cannot start runs.', 'Public server: unsafe.'], evidence='V2 does exactly this on 8770.',
  risk='Port 8771 chosen by the owner on 2026-10-13; set in radar3/config.py.', refs=['TR-07']),
 dict(id='AD-10', title='Windows Task Scheduler at 08:30 with catch-up; feeds daily, career pages weekly', status='decided', area='Triggers',
  decision='A scheduled task starts a run at 08:30 with "run as soon as available" so a missed run happens when the laptop is next on. Feeds and platform APIs run daily; custom career pages weekly (Monday).',
  why='Owner asked for 8 or 9 AM when the laptop is on. Career pages change slowly and cost more.',
  alts=['Everything daily: heavier. A cloud scheduler: breaks "free and local".'],
  evidence='V2 already runs this way (09:00, StartWhenAvailable).', risk='If the laptop never wakes that day, the dashboard shows "last updated" with the date.', refs=['PD-07', 'TR-05']),
 dict(id='AD-11', title='Dashboard is a snapshot file with data embedded', status='decided', area='Outputs',
  decision='Each run writes snapshot.json and a dashboard HTML with the data inside it, so the dashboard opens by double-click without the server.',
  why='Owner wants a page to use at the end of a run, even when nothing else is running.', alts=['Dashboard that needs the server: fails when the server is off.'],
  evidence='V2 "share --fragment" does the same for a read-only snapshot.', risk='File grows with jobs; fine for thousands of rows.', refs=['PD-08']),
 dict(id='AD-12', title='Tests run on saved samples, never on the live network', status='decided', area='Quality',
  decision='Each adapter has a saved real response and a test that parses it. The runner is tested with fake sources, as in V2.',
  why='Tests must be fast and repeatable and must not hammer other people\'s sites.', alts=['Live tests: flaky and impolite.'], evidence='V2 has 235 tests this way.',
  risk='Saved samples go stale; the canary (AD-08) covers real changes.', refs=['TR-08']),
 dict(id='AD-13', title='Parking policy: never bypass a human check, never use logins', status='decided', area='Safety',
  decision='A source that needs login, payment or answers with a bot challenge is parked with a reason. Where the same company has a public API, we use the API instead of the page.',
  why='Project rule from V2, and a legal and ethical line: no stealth, no CAPTCHA solving, no accounts.', alts=['Stealth browsers or accounts: rejected outright.'],
  evidence='34 of 123 sources parked; Perplexity HTML is challenged but its Ashby API is public.', risk='Lower coverage; accepted.', refs=['PD-06', 'TR-09']),
 dict(id='AD-14', title='Reuse V2 code; copy the Workspace UI; do not link back to V2', status='decided', area='Build',
  decision='Reuse the V2 pipeline pattern (runner, route, dedupe, build, tracker, history). Copy the Workspace code from V2\'s workspace-ui branch into V3. V3 never imports from or writes to V2.',
  why='The pattern already works and has tests. Isolation keeps V2\'s daily run safe.', alts=['Rewrite from scratch: slower.', 'Share code by link: risk of breaking V2.'],
  evidence='Owner approved the copy on 2026-10-13.', risk='Copied code can drift from V2; acceptable.', refs=['PD-09']),
 dict(id='AD-15', title='sources.csv is the single list of sources', status='decided', area='Build',
  decision='One CSV row per source with class, reader, tenant/slug, schedule and status. The runner, progress page and coverage numbers all read it.',
  why='Adding a company becomes one line, and nothing can be missing from the progress page.', alts=['Config spread over code: easy to lose a site.'],
  evidence='discovery/sources.csv already holds all 133 rows classified.', risk='None significant.', refs=['TR-01']),
 dict(id='AD-16', title='Desktop launcher with a reminder', status='decided', area='Triggers',
  decision='A launcher .bat is copied to the real Desktop folder (resolved from Windows, since Desktop may be redirected). If it is missing, the end-of-run message and the progress page remind you.',
  why='Owner asked for a Desktop copy and a reminder to make it.', alts=['Rely on memory: fails.'], evidence='On this machine ~/Desktop did not resolve, so the path must be looked up.',
  risk='Needs write access to the Desktop folder.', refs=['PD-07']),
 dict(id='AD-17', title='Re-apply the location rules when saved reads are loaded', status='decided', area='Data',
  decision='Each source saves what it read. When the workbook is built, the location and eligibility rules are run again on those saved jobs, so a rule fix takes effect without calling the sites again.',
  why='The first live run showed "Remote - California" flagged as "check eligibility". Fixing the rule should not need 16 more requests, and the sites should be called as little as possible.',
  alts=['Store the tier at read time only: needs a full re-read after every rule change.'],
  evidence='After adding US states, "check eligibility" fell from 33 to 10 and matched jobs from 101 to 78 with no new network calls.',
  risk='Workday\'s "2 Locations" flag is set at read time and is deliberately kept.', refs=['AD-18']),
 dict(id='AD-18', title='Remote eligibility rules: open to India, check, or not open', status='decided', area='Data',
  decision='Remote + worldwide/anywhere/Asia/India = rank 1. Remote with no region named = rank 2, flagged "check eligibility". Remote limited to another country, US state or region = left out and counted. Onsite outside India = left out. Then Bengaluru, Hyderabad/Chennai, rest of India.',
  why='Owner: remote roles are the top priority, but only those someone in India can take. A US-only remote job is noise.',
  alts=['Keep every remote job: most are US-only.', 'Drop every remote job with no region: loses real worldwide roles.'],
  evidence='First live run: 3,614 jobs read, 3,005 not open to India, 78 matched the ten roles, of which 34 are remote and clearly open to India.',
  risk='Location text is messy; the "check eligibility" flag is the safety valve.', refs=['PD-02', 'TR-12']),
 dict(id='AD-19', title='Platform readers ask the platform to filter to India', status='decided', area='Readers',
  decision='Each platform reader (Workday, Phenom, Eightfold, Oracle HCM) uses the platform\'s own India filter or location facet where one exists, and searches four keywords (data, machine learning, artificial intelligence, analytics). Platforms with no filter are searched unfiltered and the location rules drop the rest.',
  why='Big employers list thousands of jobs worldwide (Accenture and Citi show 2,000 each). Without the India filter the first 100 results per keyword would be mostly abroad and India roles would be missed.',
  alts=['Download everything and filter locally: slow and capped at 2,000 per search.', 'Search only "India" as a keyword: matches descriptions, not locations.'],
  evidence='Phase 2, 2026-10-13: 14 more sources enabled (5 Workday, 5 Phenom, 3 Eightfold, 1 Oracle HCM); all 30 working sources run in 43.6 s and return 307 matched jobs.',
  risk='Each platform exposes the filter differently (Workday facet id, Oracle location id, Phenom country field); each has a test on a saved sample.', refs=['AD-01', 'AD-17']),
 dict(id='AD-21', title='Add major Indian AI / data science employers to the source list', status='decided', area='Readers',
  decision='78 Indian companies were added as sources I01-I78: AI and analytics firms (Fractal, Tiger, Sigmoid, Quantiphi, Sarvam, Uniphore...), IT services (TCS, Infosys, Wipro, Genpact, EXL...), product companies (Swiggy, Paytm, Razorpay, CRED, Meesho, Groww...), banks and telecom. Each was probed: 24 have a tested public job API and are enabled; 54 are listed with their platform and wait.',
  why='Owner asked for the career pages of major Indian companies working in AI and data science, and for the list to be updated before more readers are built.',
  alts=['Add only the ones with an API: hides the rest, so coverage gaps are invisible.', 'Guess slugs without checking: two guesses (tcs on Greenhouse, eternal on Lever) were different companies and would have shown wrong jobs.'],
  evidence='Probe of 78 companies; slug hits checked against the company name; 55 sources now run in 93.7 s with 503 matched jobs.',
  risk='Some companies are not on a public platform (TCS, Infosys, Zoho, big banks) and need custom readers in Phase 3.', refs=['AD-01', 'PD-11']),
 dict(id='AD-22', title='Dead addresses were found by following each careers page', status='decided', area='Readers',
  decision='Amex moved to Oracle HCM, Morgan Stanley to Eightfold, Mistral is on Ashby (slug mistral.ai), EY and Standard Chartered are on SAP SuccessFactors (HTML), and Replicate was acquired by Cloudflare (parked).',
  why="A stale address in the owner's spreadsheet should not mean a missing company. The current address is on the company's own careers page.",
  alts=['Drop the dead rows: loses real employers.'], evidence='Amex, Morgan Stanley and Mistral now return jobs (59, 64 and 215).', risk='Companies move platforms; the check for a source that returns nothing twice in a row catches it.', refs=['AD-08']),
 dict(id='AD-23', title='HTML and page-builder readers for SuccessFactors and Avature; iCIMS, SAP and StanChart wait', status='decided', area='Readers',
  decision='Three readers: SuccessFactors Career Site Builder JSON (Wipro, HCLTech), SuccessFactors classic search pages parsed from HTML (EY), and Avature search pages parsed from HTML (MetLife, Siemens). Not enabled: iCIMS (the list shows no location, so India jobs cannot be told apart without one extra request per job; Principal also returns an empty page), SAP and Standard Chartered (JavaScript-rendered), Deloitte (its Avature sites list US roles and no way to filter India was found).',
  why='Each platform serves the same markup for every company, so one parser covers many. The ones left out would need a browser or one request per job, which breaks the cheap-first rule.',
  alts=['Fetch every iCIMS job page for its location: hundreds of extra requests per run.', 'Use a browser for SAP and StanChart now: moved to the custom-pages step where a browser is allowed.'],
  evidence='5 new sources enabled (EY 579 jobs, Wipro 346, HCLTech 357, MetLife 49, Siemens 16 before the role filter); all 60 working sources run in 98.9 s and give 648 matched jobs.',
  risk='HTML markup changes break a parser; each has a saved-sample test and the zero-jobs check.', refs=['AD-02', 'AD-20', 'AD-08']),
 dict(id='AD-24', title='Custom career sites: find the page\'s own JSON once, then read it with plain requests', status='decided', area='Readers',
  decision='For big companies with their own career site, a small reader per company calls the same JSON the page loads: Amazon (search.json), Goldman Sachs (GraphQL), Deutsche Bank (search API, India country code 81), Apple (JSON embedded in the search page). Google, Meta and IBM did not give up their JSON to plain requests and wait for the browser reader. Workday tenants for the waiting companies are found by trying the usual host numbers and site names against the tenant API.',
  why='Owner chose the smart-first approach (no browser install). Each of these four returns India jobs in seconds; a browser would cost 300 to 500 MB per page.',
  alts=['Install Playwright now and sniff every page: rejected by the owner for now.', 'Skip big companies without a public API: loses Amazon, Apple and Goldman, which hire heavily in India.'],
  evidence='Amazon 720 jobs in 11.5 s, Goldman 78 in 15.3 s, Deutsche Bank 243 in 2.4 s; the four add 198 matched jobs; 64 sources now run.',
  risk='Private JSON endpoints can change without notice; each reader has a saved-sample test and the zero-jobs check.', refs=['AD-02', 'AD-04', 'AD-08']),
 dict(id='AD-25', title='Playwright CLI installed for development, using the Edge already on the PC', status='decided', area='Readers',
  decision='@playwright/cli 0.1.22 is installed in tools/ (19 MB, dev dependency, not part of the daily run). It drives the Microsoft Edge already on this PC (--browser=msedge), so no browser was downloaded. It is used only to look at a career page once and see what it loads (open, requests, snapshot, close). Its optional "skills" install was not run (it needs the owner approval).',
  why='Owner asked for the Playwright CLI. It saves page snapshots to disk instead of putting them in the conversation, and it needs no extra browser download here.',
  alts=['Python Playwright library with its own Chromium (300 to 500 MB download).', 'The Claude built-in browser for every page: slower and spends more conversation tokens.'],
  evidence='First use: Google Careers. The CLI showed the page makes no separate job request, which led to finding the jobs inside the page data; Google now reads with plain requests (204 jobs). About 5,000 tokens for the whole discovery.',
  risk='Listing every request is verbose; filter the output (grep) to keep it short.', refs=['AD-03', 'AD-04', 'AD-24']),
 dict(id='AD-26', title='Browser tools for discovery: built-in browser to spot the data, Playwright CLI to read the request', status='decided', area='Readers',
  decision='Measured on one site (Meta Careers, same task for both: find how the India job list loads). Use the built-in browser first to see which response holds the jobs. Use the Playwright CLI when the request itself is needed (query id, headers, body) to replay the call with plain requests, and for anything run headless. The daily run uses neither.',
  why='Built-in browser: 3 steps, about 4,600 characters (about 1,200 tokens), but it shows only method and address of each request and the response body. It cannot show the request body, so it cannot give the query id. Playwright CLI: 5 steps, about 7,000 characters as I ran it (about 1,800 tokens; about 4,000 with tighter filtering), and it shows the request name, headers, body and response. Only the CLI gave the query id (doc_id) that made the Meta reader possible.',
  alts=['Built-in browser only: cheapest to spot data, but cannot capture the request side.', 'CLI only: more steps and more output unless filtered; the first unfiltered request list on Google was about 10,000 characters.'],
  evidence='Meta now reads with plain requests (26 India jobs in 6 s). Caveats: one site, and characters are only a proxy for tokens.',
  risk='Meta changes the query id from time to time; the zero-jobs check flags it and the CLI re-reads it in one step.', refs=['AD-25', 'AD-03', 'AD-04', 'AD-08']),
 dict(id='AD-27', title='Two-tool discovery on nine more companies: four readers added, five stay off for stated reasons', status='decided', area='Readers',
  decision='Using the CLI (request lists filtered to a file) and the built-in browser, nine companies were checked. Added: IBM (search API, request body copied with the CLI), Capgemini (public search API), Infosys (one unauthenticated call returns all jobs), Standard Chartered (SuccessFactors JSON, locale en_GB). Not added: SAP and Cognizant (Cloudflare human check: never solved or hidden), Tech Mahindra (a sign-in portal), TCS (403 to plain requests, old address dead) and Flipkart (no job data without a real session).',
  why='Cheapest-first, and the human-check rule is fixed: where a site asks for a check, the source is parked and the owner can pass it by hand later.',
  alts=['Bypass the Cloudflare checks with stealth tools: forbidden by project rules.', 'Install a full browser for TCS and Flipkart: the cost is high for two sources.'],
  evidence='IBM 414 jobs, Standard Chartered 197, Infosys 1,665 (0.5 s), Capgemini 496; all 75 sources now run in 164.5 s and give 1,114 matched jobs.',
  risk='Infosys returns a 5 MB list each run; fine weekly. IBM and Meta use copied request shapes that may change; the zero-jobs check flags that.', refs=['AD-26', 'AD-13', 'AD-08']),
 dict(id='AD-28', title='Automation with health checks so a changed website is caught, not silently missed', status='decided', area='Triggers',
  decision='Windows Task Scheduler starts a run at 08:30 every day (task Job Radar V3 Daily, run as soon as available if the laptop was off, one run at a time, 2 hour limit). Every source read is judged: error is retried once; 0 jobs once is "empty", twice is "broken"; far fewer jobs than usual is "shrunk" (below 30% the previous list is kept); more than half the jobs without a place is "degraded" (layout change). Problems go in the end-of-run message and in output/health.json; python -m radar3 health lists them with what to do.',
  why='Owner asked that no website extraction silently break. Sites change; the goal is to notice within a day, keep the last good data meanwhile, and make the fix one short step.',
  alts=['Trust every read: a half-loaded page would shrink the workbook without anyone noticing.', 'A paid monitoring service: breaks the free-and-local rule.'],
  evidence='End-to-end test 2026-10-13: Windows started the task itself, 29 due sources read in 99 s, result code 0, health 75 of 75. 105 offline tests cover retries, shrink, layout change, stale flags, the scheduler script, and the contract of sources.csv.',
  risk='A site can break in a way that still returns plausible jobs; the daily "new jobs" counts on the dashboard are the second line of defence.', refs=['AD-08', 'AD-10', 'TR-05', 'TR-06']),
 dict(id='AD-29', title='End-of-run message in a detached window; Desktop launcher found through Windows', status='decided', area='Triggers',
  decision='The end-of-run message box is shown by a separate detached process, so the run ends and frees its lock at once. A launcher copy (Job Radar V3.bat, calls the project launcher by full path) is written to the real Desktop folder, found through Windows because Desktop here is redirected to OneDrive. The message reminds the owner while that copy is missing.',
  why="A message box that waits for a click would keep the run open; if nobody clicks it, the next morning's run could be refused. The Desktop path is not always the usual Users folder path.",
  alts=["Blocking message box: simple, but can block tomorrow's run.", 'Guess the Desktop path: wrong on this PC (OneDrive).'],
  evidence='Desktop copy written to the OneDrive Desktop folder; the scheduled test run finished with the message shown separately.', risk='None significant.', refs=['AD-16', 'PD-07']),
 dict(id='AD-30', title='Progress page: a local server with Start/Stop, live status and the source table', status='decided', area='Outputs',
  decision='radar3/tracker.py serves one HTML page at http://127.0.0.1:8771 that reads the run state file every 2 seconds while a run is going: status pill, progress bar with elapsed time and estimate, cards (working sources, matched jobs, new today, remote open to India, Bengaluru, Hyderabad/Chennai), a coverage bar, a filterable table of all 211 sources (click one for its reader, reason, career page, last good read and a mini chart of recent counts), the event list, and banners for sources that need attention and for the missing Desktop launcher. Buttons: Run daily sources, Run everything, Stop. A run keeps going if the page is closed, and also shows when started by the scheduler.',
  why='Owner asked for an HTML page to track extraction progress and to start a run by hand. A page cannot start a process by itself, so a small local server is the safe bridge.',
  alts=['Static page opened from disk: cannot start or stop a run.', 'A server open to the network: unsafe.'],
  evidence='Tested in a real browser on 2026-10-13: the Start button began a run (Reading 20 of 29 sources, started by progress page, with an estimate); a second start was refused while one was going; Stop ended a run mid-read (18 done, 56 stopped), removed the lock, and the workbook rebuilt cleanly (1,114 rows). 113 offline tests, 7 of them for the server.',
  risk='Stopping kills the run at once; sources not finished keep their previous jobs, so nothing is lost.', refs=['AD-09', 'AD-28', 'PD-08', 'TR-07']),
 dict(id='AD-31', title='Progress page safety checks', status='decided', area='Security',
  decision='The server binds to 127.0.0.1 only; a request whose Host header is not 127.0.0.1 or localhost gets 403; a POST (start, stop) must carry the header X-Radar and, if it has an Origin, that Origin must be local. Nothing is written except through the run itself.',
  why='Without these checks, any web page open in the same browser could send a request to the local server and start or stop runs.',
  alts=['No checks: simple, but another page could trigger runs.'], evidence='Tests: wrong host refused, POST without header refused, POST with a foreign Origin refused.', risk='None significant.', refs=['TR-07', 'AD-30']),
 dict(id='AD-32', title='Batch discovery of the remaining 83 sites: 5 sources added, 14 parked, every other site has a stated reason', status='decided', area='Readers',
  decision="A script drove the Playwright CLI across all 83 waiting sites and kept only JSON responses that look like job lists; everything went to files and only a compact summary reached the conversation. Result: 22 sites showed some JSON, 14 answered with a bot or human check, 8 had errors, about 50 showed no job data in their requests. Added: four venture-capital portfolio boards on the Consider platform (Sequoia 314 India jobs, Bessemer 597, First Round 42, Kleiner Perkins 190) through one reader that uses the page's CSRF token and the sequence token for paging, and Affine. The 14 behind a check (for example TCS, Zoho, HDFC Bank, ICICI Bank, Ola, Johnson and Johnson) are parked and never bypassed. Every other site has a note saying why it waits.",
  why="The owner asked for a batch over all the remaining companies. Doing it as a script keeps the conversation cost near zero per site; the per-site 2,000 to 5,000 tokens was a one-time cost and is now mostly avoided.",
  alts=["Look at each site by hand: far more tokens.", "Bypass the human checks: forbidden by the project rules."],
  evidence="Two real problems found and fixed: the batch hung for 56 minutes on one page and left 12 browser processes (now: kill the whole process tree on a timeout, 12 response bodies and 150 seconds per site); and the first Consider run returned only 100 jobs per board because paging needs the sequence token, not an offset (a test now covers it).",
  risk="Sites with no job data in their requests (about 50) need an HTML reader or a real browser; they are listed in Sources_V3.xlsx with the reason.", refs=['AD-26', 'AD-13', 'AD-28']),
 dict(id='AD-33', title="Working through the waiting sources: plain-HTML scan found little, Getro boards and Hexaware added", status='decided', area='Readers',
  decision="A plain-request scan of the 64 waiting pages for jobs inside the HTML (JSON-LD, Next.js data, embedded JSON, job links) found almost nothing, so most of the 47 JavaScript-only sites need a real browser. Two things did pay off: Hexaware (Oracle HCM, site CX_1) and the Getro platform's public search API, which serves venture-capital portfolio boards (General Catalyst 219 India jobs, Accel 689, NFX 2). Getro serves 20 jobs per page whatever the size asked and holds thousands of jobs per board, so the reader searches three role keywords (up to 20 pages each) instead of everything. General Catalyst and Accel were added to the list beyond the spreadsheet.",
  why="Cheapest first: plain requests before a browser. The scan was fast (64 requests, no browser) and settled that the rest needs a browser, so that is now an informed decision rather than a guess.",
  alts=["Pull every India job from Accel (5,028 jobs, 250 requests): too slow for a weekly run and mostly not AI/data roles.", "Install a browser lane now for 47 sites: memory and maintenance cost; to be decided by the owner."],
  evidence="Two reader bugs caught by checking counts, not only status: Getro rejected requests without an Accept header (406), and returned 20 per page so the first loop stopped after one page. Matched jobs 1,183 to 1,343 across the Getro boards, Hexaware and the earlier boards. 117 offline tests.",
  risk="Getro and Consider can change their APIs; the zero-jobs and shrink checks flag it.", refs=['AD-32', 'AD-02', 'AD-08']),
 dict(id='AD-34', title="Browser lane tested on 59 sites; not built, because nothing needs it", status='decided', area='Readers',
  decision="The owner asked for a browser lane (about 10 sites, Y Combinator a must). Before building it, all 59 waiting sites were opened with the Playwright library (the PC's Edge, headless, one page at a time). Result: 50 rendered, 6 were refused at the connection level (McKinsey, Honeywell, Persistent, Coforge, Zomato, Tata Digital: bot protection, not bypassed), 3 had dead addresses. The browser saw no new job feed: the only job-like JSON was the five already known and rejected. Pages with many 'job' links were mostly menu links; none led to a job platform we can read except a16z (about 27 jobs in its page payload, more behind server actions). Y Combinator, the must-have, needed no browser: its own data-page JSON gives 167 India jobs (157 open to India) through the Indian city pages. Postman needed no browser either (its JSON points to a Workday board). So the lane was not built; the probe tools stay in discovery/ for later.",
  why="A lane costs 300 to 500 MB of memory per run and breaks easily (page layouts change), and the evidence shows it would unlock none of these sites. The cheaper readers already cover what is reachable.",
  alts=["Build the lane anyway and scrape page text with per-site selectors: fragile, and the sites mostly hide their jobs in search boxes or sign-in flows.", "Bypass the bot protection: forbidden by the project rules."],
  evidence="discovery/browser_batch.json (59 sites), discovery/browser_links.json (39 pages checked for links to job platforms). Added from this round: Y Combinator (167 jobs), Postman (8), General Catalyst and Accel boards earlier. 118 offline tests.",
  risk="If a specific company matters later, a one-site scraper can be added then, with its own saved-sample test.", refs=['AD-03', 'AD-26', 'AD-33', 'AD-13']),
 dict(id='AD-35', title="Recall check found most searches missed jobs; one shared list of 26 role keywords fixes it", status='decided', area='Readers',
  decision="A recall check compared the 4 keyword searches with a wider set on six sites: Accenture found only 27% of the role-matching jobs, Citi 60%, Microsoft 70%, Intel 80%, JPMorgan 90%, Cisco 94%. All keyword-search readers now share one list of 26 role keywords (data, machine learning, artificial intelligence, analytics, scientist, generative ai, data engineer, analyst, architect, mlops, llm, deep learning, nlp, ai engineer, ai, ml, bi, business intelligence, research engineer, forward deployed, prompt, python, sql, statistic, insights, modelling), and a keyword stops as soon as a page adds no new job. Goldman Sachs keeps its short list (the extra keywords gained nothing). Y Combinator stays partial by the site's own limit: it shows about 50 jobs per city page and role pages return the same 50.",
  why="Titles are matched against the ten role patterns afterwards, so a broad keyword only costs a few requests. Missing 70% of Accenture's matching jobs was the largest quality gap in the radar.",
  alts=["Keep 4 keywords: fast, but hides most roles at the biggest employers.", "Download every India job at each site: Workday caps results at 2,000 per search, and it is slow."],
  evidence="Full run before and after: matched jobs 1,351 to 1,755 (+30%). Accenture 85 to 475 role matches, Accel 288 to 434, HCLTech 56 to 170, EXL 79 to 150, Wipro 98 to 142, Citi 46 to 83. Cost: a full run grew from about 4 to 9 minutes, then the workbook build was cut from 160 s to 50 s.",
  risk="26 keywords are still a sample of what a site holds; the per-source role-match counts on the progress page show which sources deliver.", refs=['AD-19', 'AD-32', 'AD-33']),
 dict(id='AD-36', title="A locked status file must never crash a run", status='decided', area='Quality',
  decision="Replacing a file that another process has open can fail on Windows. The progress page reads run_state.json every 2 seconds, and one full run crashed with Access denied while writing it. Now all replaces retry for about a second (radar3/fsutil.py), and a failed update of the live status file is skipped, never fatal, because it is display only.",
  why="A cosmetic file took down a 9-minute run of 86 sources. Display must never be able to stop extraction.",
  alts=["Write the status file directly: not atomic, readers can see half a file.", "Stop the page from polling: loses live progress."],
  evidence="Found in the first wide-keyword full run; tests simulate a locked file (retry succeeds; persistent lock is skipped).", risk="None significant.", refs=['AD-28', 'AD-30']),
 dict(id='AD-37', title="Dashboard: one self-contained HTML file built after every run", status='decided', area='Outputs',
  decision="radar3/dashboard.py embeds the last snapshot into radar3/web/Dashboard.html and writes radar3/output/Dashboard.html (about 1.1 MB for 1,755 jobs). It opens by double-click with no server, and the progress page also serves it at /dashboard. It has: filters (text, location priority chips, role chips, date, source, work mode, status, starred only), cards (jobs in view, new today, companies hiring, remote share, Bengaluru share, starred), charts (jobs per role, per location priority, per source, top companies, skills asked, first seen per day) where a click on a bar filters the table, a sortable paged table with a detail drawer, my own status, star and note (kept in this browser), and CSV export of the current view. Location priority follows the owner's order: remote open to India, remote to check, Bengaluru, Hyderabad/Chennai, rest of India.",
  why="The owner asked for a dashboard with analytics to use at the end. V2's Workspace (67 KB page plus about ten modules for resumes, cover letters and Fit %) is tied to V2's data and goes beyond the V3 brief, so a fresh page was built; V2 is untouched.",
  alts=["Copy the V2 Workspace: heavy to adapt, brings resume and cover-letter features nobody asked for in V3.", "A page that needs the server: fails when the server is off."],
  evidence="Opened in a real browser with the real 1,755 jobs: the Remote-India filter gave 65 (matches the run total), role click, search, sort, paging, drawer, star and starred-only all worked. 126 offline tests, one of them runs node --check on the page script.",
  risk="Status and notes live in the browser, not in the Excel file; the Excel Status and Notes columns are separate.", refs=['AD-11', 'PD-08', 'PD-09']),
 dict(id='AD-38', title="Job boards integrated: V2's seven site workflows run from V3 and flow into the same workbook and dashboard", status='decided', area='Runner',
  decision="The seven site workflows (Hirist, IIMJobs, Cutshort, Wellfound, Indeed, Naukri, LinkedIn) and their runner came with the V3 clone and are identical to V2's (checked file by file, ignoring line endings and the path rename), so no site code had to be moved. What was added: python-jobspy and pandas in V3's venv; radar3/boards.py, which starts the sites with the inherited runner (lanes, memory gate, stall restart, one retry, human checks left to the owner), reports each board live into the V3 run state, reads each site's workbook and converts the jobs (location priority, source type Job board, jobs older than 60 days left out); and a change in radar3/runner.py so the boards run in a background thread while the fast API sources run. The workbook and dashboard are updated when the fast sources finish and again when the boards finish. Each site's workbook and state file were copied from V2 once (read-only; V2 untouched) so the sites continue from where they stopped; browser profiles were not copied, so the first run of a site may ask for a human check. A board that stops on a human check shows 'needs you' and keeps what it read; one that fails keeps its previous list.",
  why="The owner wants the HTML in V3 to run both the API sources and the job boards and to see integrated results in V3, without rewriting working site code.",
  alts=["Rewrite the boards as API readers: they have no public API, and the sites need a real browser.", "Read V2's finished workbook instead of running the sites: only as fresh as V2's last run, and V3 could not trigger it."],
  evidence="Offline tests with a fake site runner and fake workbooks (18 tests): conversion and age limit, status mapping, live reporting, unreadable workbook, whole run with both kinds in one workbook, boards left out, human check keeps partial jobs, failure keeps the previous list, a crashing lane never takes the run down. All seven site packages start. 144 offline tests.",
  risk="A full run with boards takes about 35 to 45 minutes and opens visible Chrome windows; the sites are slow on purpose. Not yet run live.", refs=['AD-06', 'AD-13', 'AD-28', 'PD-12']),
 dict(id='AD-39', title="The 08:30 task stays API-only until V2's own task is retired", status='decided', area='Triggers',
  decision="V2 still runs its own task at 09:00. If V3's 08:30 task also started the Chrome-based boards, the two would run the same sites at the same time (double memory, double human checks). So the scheduled V3 run uses --skip-boards by default; the progress page checkbox 'Include job boards' is on by default and starts them; python -m radar3 schedule --with-boards switches the scheduled run to include them once V2's task is disabled.",
  why="Memory is tight (16 GB) and the rules say never run many Chromes at once. The owner decides when V2's task is retired.",
  alts=["Include the boards at 08:30 now: collides with V2 at 09:00.", "Disable V2's task myself: changes V2, which needs the owner's approval."],
  evidence="Task re-registered; its arguments now end with --skip-boards.", risk="Until the switch, the boards only refresh when started from the page.", refs=['AD-38', 'AD-28']),
 dict(id='AD-40', title="Progress page redesigned as an operations console: how to run, live percent, problems with reasons, re-run per source, history", status='decided', area='Outputs',
  decision="The page now has a how-to-run panel at the top (three ways: the page, a .bat file, a terminal; each launcher file with what it does, Show in folder and Copy path; copyable commands; shortcuts to the dashboard, workbook and folders) and four tabs. LIVE RUN: a weighted percent (a job board counts as 12 fast sources because it takes about that long), elapsed time and estimate, a bar for the fast sources and one for the boards, a table of every source in the run with status, progress (for boards a real percent read from the board's own log, for example 5 of 14 searches), time and note, and a run summary (jobs read, open to India, unique, matched with the change since the previous run, new today, location split, top sources by role matches, slowest sources, what needs attention). SOURCES: parked, skipped, duplicate and not-built sources can be hidden or shown with toggles (remembered), plus filters and a re-run button per source. PROBLEMS: healthy percent, counts by kind of action, why sources did not run properly (human check, blocked by the site, address changed, rate limited, too slow, network error, file locked, broken, returned nothing, far fewer jobs, layout changed, never read, stale) with the reason from the run, what to do, how often it failed in the last 14 days, a reliability chart, and re-run for one source, selected sources, or all that a re-run may fix. HISTORY: runs logged, clean-run percent, average duration, trends of matched jobs, duration and problems.",
  why="The owner asked for instructions at the top, a better design, hiding of parked and skipped sources, analytics on what did not run and why with a re-run per site, percent complete while running, and a run summary. A DevOps view needs time, failure reasons and re-run; a product view needs what the run delivered and how it changed.",
  alts=["A static status list: cannot explain failures or act on them.", "Fake percent from a timer: misleading; the percent comes from finished sources and board logs."],
  evidence="Checked in a real browser with real data: live percent and lanes, run summary with +2,787 matched jobs against the previous run, source toggles (152 shown by default, 202 with parked, 207 with skipped, remembered), three injected problems classified correctly with a 3-in-a-row streak and fix suggestions, the reason filter, history tiles, and a real re-run of one source from the Problems tab that cleared its problem. 177 offline tests, one of them runs node --check on the page script.",
  risk="A web page cannot run a .bat file, so Show in folder opens Explorer with it selected instead; open actions come from a fixed list and never run anything.", refs=['AD-30', 'AD-31', 'AD-28', 'AD-38']),
 dict(id='AD-20', title='Platforms that only serve HTML pages wait for Phase 3', status='decided', area='Readers',
  decision='Avature (3), iCIMS (2) and SAP SuccessFactors (1) have no public JSON search, only server-rendered HTML. They are not enabled in Phase 2; one HTML reader per platform comes in Phase 3. Sites whose address no longer works (Amex, EY GDS, Morgan Stanley, Standard Chartered) and Mistral and Replicate stay off with the reason written in sources.csv.',
  why='An HTML reader is slower and breaks more easily than a JSON reader, so the JSON platforms go first.',
  alts=['Use a browser now: costs memory for 6 sources.'], evidence='Phase 2 probe: each of these returned HTML only, or a dead host.',
  risk='These 12 sources stay uncovered until Phase 3.', refs=['AD-02', 'AD-04']),
]

REQS = [
 dict(id='TR-01', title='Coverage accounting', cat='Coverage', must='Every one of the 133 rows ends in exactly one state (working, candidate, parked, skipped, duplicate). A script fails if a row has none.', measure='0 rows without a state', refs=['AD-01', 'AD-15']),
 dict(id='TR-02', title='Load per run', cat='Performance', must='A daily run of the HTTP sources finishes in 15 minutes or less. MEASURED 2026-10-13: 16 sources in 14.6 s, then all 30 working sources in 43.6 s, with no browser (V2 took 35 to 40 minutes).', measure='run time from run_state.json', refs=['AD-07']),
 dict(id='TR-03', title='Memory', cat='Performance', must='Keep at least 1 GB free; a source waits up to 20 minutes for memory, then is skipped.', measure='lowest free memory per run', refs=['AD-06']),
 dict(id='TR-04', title='Browser budget', cat='Performance', must='No more than 2 Chromes at once; none at all for A and B sources.', measure='peak Chromes per run', refs=['AD-03', 'AD-06']),
 dict(id='TR-05', title='Schedule reliability', cat='Reliability', must='95% of mornings produce a fresh workbook, counting catch-up runs; a second start while running is ignored.', measure='history.jsonl', refs=['AD-10']),
 dict(id='TR-06', title='Detect broken sources', cat='Reliability', must='Zero jobs twice in a row, or a changed shape, shows "broken" on the progress page.', measure='canary tests', refs=['AD-08']),
 dict(id='TR-07', title='Local-only server', cat='Security', must='Listens on 127.0.0.1 only; checks the Host header; Start/Stop accepted only from its own page.', measure='security test', refs=['AD-09']),
 dict(id='TR-08', title='Tests', cat='Quality', must='Every adapter has a saved sample and a parse test; runner tested with fake sources; all tests pass before a commit.', measure='pytest', refs=['AD-12']),
 dict(id='TR-09', title='No secrets, no logins, no bypass', cat='Security', must='No credentials stored; no CAPTCHA solving; respect robots.txt; one request per host per second.', measure='code review + adapter checklist', refs=['AD-13']),
 dict(id='TR-10', title='Data schema', cat='Data', must='Workbook has the 16 V2 columns plus Source/Type; Status, Notes and First seen survive rebuilds; atomic saves.', measure='workbook test', refs=['AD-05']),
 dict(id='TR-11', title='Role filter quality', cat='Quality', must='At least 90% of rows in "All" match an approved role (hand check of 50 rows); unmatched titles go to an Unmatched tab.', measure='sample review', refs=['PD-03']),
 dict(id='TR-12', title='Location ranking', cat='Data', must='Remote open to India first, then Bengaluru, then Hyderabad/Chennai, then rest of India; ambiguous remote flagged "check eligibility".', measure='rank test', refs=['PD-02']),
 dict(id='TR-13', title='Cost', cat='Cost', must='Zero tokens and zero paid services in the daily run; only free libraries.', measure='review of requirements.txt and run', refs=['AD-02', 'AD-03']),
]

# ---------------------------------------------------------------- product decisions
PROD = [
 dict(id='PD-01', title='Cover every usable site in the spreadsheet', q='How much of the spreadsheet do we read?',
  options=['Only the top 10-15 sites', 'Everything that can legally be read for free'], choice='Everything that can legally be read for free',
  because='The owner wants "all the websites in the excel". Breadth finds roles that no single board shows. The cost is controlled by technical design (AD-01, AD-02), not by cutting scope.',
  consequence='123 unique sources are classified. 16 work today, about 68 more are likely, 39 are not scraped (reasons shown).', refs=['AD-01', 'AD-02']),
 dict(id='PD-02', title='Rank remote-for-India first, then Bengaluru, then Hyderabad/Chennai', q='What order should jobs appear in?',
  options=['Bengaluru first (as V2)', 'Remote open to India first'], choice='Remote open to India first, then Bengaluru, then Hyderabad or Chennai, then rest of India',
  because='This directory is about remote AI/ML roles, so remote is the main prize. The owner is in Bengaluru, so local roles come right after. Hyderabad and Chennai are the owner\'s next preference.',
  consequence='We must judge "open to India" from messy location text; ambiguous roles are kept and flagged, not dropped.', refs=['TR-12']),
 dict(id='PD-03', title='A new AI/ML/Data role set instead of V2\'s 8 tech roles', q='Which job titles count?',
  options=['V2\'s 8 roles', 'New AI/ML/Data set', 'Both'], choice='New AI/ML/Data set (10 roles, below)',
  because='The directory is built for AI/ML/Data work; V2\'s roles would miss titles like ML Engineer or LLM Engineer.',
  consequence='Titles are matched by patterns; anything unmatched goes to an Unmatched tab so nothing disappears. Roles: AI Engineer; ML Engineer; GenAI/LLM Engineer; Data Scientist; Applied Scientist/Research Engineer; MLOps/ML Platform Engineer; Data Engineer; Data Analyst/BI Analyst; AI/Solutions Architect (data and AI); Prompt Engineer/AI Product.', refs=['TR-11']),
 dict(id='PD-04', title='Separate V3 workbook with the same columns', q='Where do results live?',
  options=['Add to V2\'s file', 'Separate file, same columns', 'New sheet in one file'], choice='Separate file, same columns',
  because='V2 runs daily and is mid-use; same columns let the Workspace UI work on V3 too.', consequence='Two outputs; the dashboard shows V3.', refs=['AD-05']),
 dict(id='PD-05', title='Include the 47 GCC career pages', q='Is the GCC sheet in scope?', options=['Remote sheet only', 'Remote plus GCC'], choice='Remote plus GCC',
  because='The owner supplied the links and asked to copy them. GCC firms in Bengaluru, Hyderabad and Chennai match the location preference.',
  consequence='47 more sources, mostly on platforms such as Workday, Eightfold, Phenom; they run weekly.', refs=['AD-10']),
 dict(id='PD-06', title='Do not scrape logins, paywalls, newsletters or challenged pages', q='What do we leave out?',
  options=['Try everything', 'Respect the V2 rules'], choice='Respect the V2 rules',
  because='No logins, no stealth and no human-check bypass is a standing rule; newsletters are digests, not job lists.',
  consequence='Parked list is visible with a reason, and can be revisited if the owner passes a check by hand.', refs=['AD-13', 'TR-09']),
 dict(id='PD-07', title='Run automatically at 08:30, manual trigger anywhere, Desktop copy with a reminder', q='How does it start?',
  options=['Manual only', 'Scheduled only', 'Scheduled plus manual'], choice='Scheduled plus manual, with catch-up',
  because='The owner wants fresh jobs by morning if the laptop is on, and the ability to run on demand from the HTML page or a .bat.',
  consequence='Task Scheduler task, a Start button on the progress page, a .bat file, and a Desktop copy with a reminder.', refs=['AD-10', 'AD-16']),
 dict(id='PD-08', title='Two HTML pages: a live progress tracker and an end-of-run dashboard', q='How does the owner see what happened?',
  options=['Excel only', 'Progress page + dashboard'], choice='Progress page + dashboard',
  because='Owner asked to see extraction progress and to have analytics at the end. Excel alone gives neither.',
  consequence='Progress page needs the local server; the dashboard works as a file.', refs=['AD-09', 'AD-11']),
 dict(id='PD-09', title='Reuse V2\'s Workspace UI for the dashboard', q='Build new or copy?', options=['Build new', 'Copy from V2\'s workspace-ui branch'], choice='Copy',
  because='It already has 10 charts, an Excel-style table and filters on the same columns. Owner said yes.', consequence='Copied code, V2 not touched.', refs=['AD-14']),
 dict(id='PD-11', title='Add major Indian AI / data science employers beyond the spreadsheet', q='Do we only read what the spreadsheet lists?',
  options=['Only the spreadsheet', 'Spreadsheet plus major Indian employers in AI and data science'], choice='Spreadsheet plus 78 Indian employers',
  because='The owner is in India and wants AI/ML/Data roles; the spreadsheet is mostly global. Indian analytics firms, IT services, product companies and banks hire most of the India-based roles.',
  consequence='Sources_V3.xlsx lists every source with its state (Working, Waiting, Parked, Skipped, Duplicate). 55 work today.', refs=['AD-21', 'AD-22']),
 dict(id='PD-12', title="One run from the HTML page runs both: the API sources and the Indian job boards", q="Should V3 also run the V2 job boards, and show them with the rest?",
  options=["Keep V2 and V3 separate", "V3 runs both and shows one set of results"], choice="V3 runs both and shows one set of results",
  because="The owner wants to start everything from the V3 page and see one workbook and one dashboard, with remote roles open to India ranked first across all sources.",
  consequence="The page has an Include job boards checkbox (on by default, about 35 minutes, Chrome windows, a human check may need you). The scheduled 08:30 run stays API-only until V2's own 09:00 task is retired.", refs=['AD-38', 'AD-39']),
 dict(id='PD-10', title='Ask before important next steps; document every architecture choice visually', q='How should we work together?',
  options=['Move fast and report', 'Ask before important steps'], choice='Ask before important steps; keep a clickable visual document for architecture, tech and product decisions',
  because='The owner wants to understand and control the big choices, and wants a place to see the reasons.', consequence='These two HTML files are updated whenever a decision changes.', refs=[]),
]

STORIES = [
 ('Cover the sources', 'As the owner, I want all usable sites in my spreadsheet read automatically so I do not open 120 sites by hand.', 'Every row has a state; adding a site is one line.'),
 ('Watch progress', 'As the owner, I want to see what is running and what needs me.', 'Each source shows waiting/reading/done/needs you/parked/failed with counts and the last log line; updates every 5 s.'),
 ('Use the dashboard', 'As the owner, I want a dashboard at the end to decide where to apply.', 'KPI cards, charts, a filterable table with links; opens without the server.'),
 ('Wake up to fresh jobs', 'As the owner, I want it to run by itself around 8-9 AM.', 'Scheduled 08:30, catches up when the laptop wakes.'),
 ('Run on demand', 'As the owner, I want to start a run from the page or a .bat file.', 'Start/Stop buttons and a launcher; second start is ignored while running.'),
 ('Never forget the Desktop copy', 'As the owner, I want a copy on the Desktop and a reminder if missing.', 'Launcher in the real Desktop folder; message until it exists.'),
]
METRICS = [
 ('Coverage', '100% of rows have a state; target 60% or more of non-skipped sources scraped in the MVP'),
 ('Speed', 'Daily HTTP run 15 minutes or less (to confirm)'),
 ('Memory', '2 Chromes or fewer, 1 GB free'),
 ('Reliability', '95% of mornings produce a fresh workbook'),
 ('Relevance', '90% of rows in All match an approved role'),
 ('Cost', '0 tokens, 0 paid services'),
]
NONGOALS = ['No logins, paid memberships, CAPTCHA solving or stealth.', 'No changes to V2; V2 pipeline is not run from V3.', 'No auto-apply, no auto-sent mail, no cover-letter writing in the MVP.', 'No LLM calls in the daily run.', 'No cloud hosting or sharing in the MVP.', 'No full job descriptions in the MVP.']
OPEN = ['Exact weekday and time for the career-page run (accepted: weekly, Monday suggested).', 'How strictly to treat remote roles with unclear India eligibility (current: keep and flag).', 'Which of the 68 candidate sources are worth a browser if no JSON is found.']

# ---------------------------------------------------------------- sources from csv
src = []
for r in csv.DictReader(open(ROOT / 'radar3' / 'data' / 'sources.csv', encoding='utf-8')):
    src.append({k: r[k] for k in ('id', 'sheet', 'name', 'url', 'cls', 'reader', 'verified', 'note', 'enabled')})

CSS = """
:root{--bg:#fafaf7;--panel:#fff;--ink:#1d1d1b;--mute:#6b6a66;--line:#e3e1da;--acc:#2f5fd0;--acc2:#e8eefc;--ok:#1a7f4b;--warn:#a86400;--bad:#b3261e;--A:#1a7f4b;--B:#2f5fd0;--C:#a86400;--D:#8a8a85;--S:#b3261e;--X:#bbb;--shadow:0 1px 3px rgba(0,0,0,.08)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--panel:#1e1e1c;--ink:#ecebe6;--mute:#9a9892;--line:#33322f;--acc:#7da2ff;--acc2:#202b45;--ok:#5fcf8f;--warn:#e6a93b;--bad:#ff7b72;--A:#5fcf8f;--B:#7da2ff;--C:#e6a93b;--D:#9a9892;--S:#ff7b72;--X:#555}}
:root[data-theme=dark]{--bg:#141413;--panel:#1e1e1c;--ink:#ecebe6;--mute:#9a9892;--line:#33322f;--acc:#7da2ff;--acc2:#202b45;--ok:#5fcf8f;--warn:#e6a93b;--bad:#ff7b72;--A:#5fcf8f;--B:#7da2ff;--C:#e6a93b;--D:#9a9892;--S:#ff7b72;--X:#555}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}
header{padding:20px 24px 0;max-width:1180px;margin:auto}h1{margin:0 0 4px;font-size:24px}.sub{color:var(--mute);margin:0 0 14px}
nav.tabs{display:flex;gap:4px;flex-wrap:wrap;border-bottom:1px solid var(--line);max-width:1180px;margin:auto;padding:0 24px}
nav.tabs button{background:none;border:0;border-bottom:3px solid transparent;color:var(--mute);padding:10px 14px;font:inherit;cursor:pointer}
nav.tabs button.on{color:var(--ink);border-color:var(--acc);font-weight:600}
main{max-width:1180px;margin:auto;padding:20px 24px 80px}section{display:none}section.on{display:block}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;box-shadow:var(--shadow)}
button.node{display:block;width:100%;text-align:left;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:8px;padding:9px 11px;margin:0 0 8px;color:var(--ink);font:inherit;cursor:pointer}
button.node:hover,.item:hover{border-color:var(--acc);background:var(--acc2)}button.node small{display:block;color:var(--mute);font-size:12px}
.flow{display:grid;grid-template-columns:repeat(6,minmax(150px,1fr));gap:14px;align-items:start}.col h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0 0 8px}
.arrow{color:var(--mute);text-align:center;font-size:12px;margin:4px 0 10px}
.pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:99px;border:1px solid var(--line);color:var(--mute);margin-right:4px}
.pill.decided{color:var(--ok);border-color:var(--ok)}.pill.proposed{color:var(--warn);border-color:var(--warn)}.pill.open{color:var(--bad);border-color:var(--bad)}
.item{display:block;width:100%;text-align:left;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:0 0 8px;color:var(--ink);font:inherit;cursor:pointer}
.item b{margin-right:6px}.item .m{color:var(--mute);font-size:13px;display:block}
.bar{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:8px 0}.bar span{display:block;color:#fff;font-size:12px;line-height:26px;text-align:center;min-width:2px}
.lg{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mute)}.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--mute);font-weight:600;position:sticky;top:0;background:var(--bg)}
tr.click{cursor:pointer}tr.click:hover{background:var(--acc2)}
input,select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 9px;font:inherit}.row{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
#drawer{position:fixed;top:0;right:0;width:min(520px,100vw);height:100vh;background:var(--panel);border-left:1px solid var(--line);box-shadow:-6px 0 20px rgba(0,0,0,.12);transform:translateX(105%);transition:transform .2s;overflow:auto;padding:18px 20px 40px;z-index:5}
#drawer.open{transform:none}#drawer h2{margin:0 0 6px;font-size:19px}#drawer h4{margin:16px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
#drawer p,#drawer ul{margin:0 0 6px}#drawer ul{padding-left:18px}.close{float:right;background:none;border:1px solid var(--line);border-radius:6px;color:var(--ink);cursor:pointer;padding:3px 9px}
a.ref{color:var(--acc);cursor:pointer;text-decoration:underline;margin-right:8px}
.tree ul{list-style:none;margin:0;padding-left:22px;border-left:2px solid var(--line)}.tree>ul{border:0;padding:0}.tree li{margin:6px 0}
.chain{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.chain div{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--acc2);font-size:13px}.chain b{display:block;font-size:11px;text-transform:uppercase;color:var(--mute)}
@media(max-width:900px){.flow{grid-template-columns:1fr 1fr}.chain{grid-template-columns:1fr}}
@media(max-width:560px){.flow{grid-template-columns:1fr}header,main,nav.tabs{padding-left:16px;padding-right:16px}}
"""

JS = """
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function show(id){document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id===id));document.querySelectorAll('nav.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===id));try{history.replaceState(null,'','#'+id)}catch(e){}}
function open_(html){$('#drawer').innerHTML='<button class="close" onclick="closeD()">Close</button>'+html;$('#drawer').classList.add('open')}
function closeD(){$('#drawer').classList.remove('open')}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeD()});
function refs(a){return (a||[]).map(r=>'<a class="ref" onclick="go(\\''+r+'\\')">'+r+'</a>').join('')||'<span class="pill">none</span>'}
function list(a){return '<ul>'+(a||[]).map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>'}
document.querySelectorAll('nav.tabs button').forEach(b=>b.onclick=()=>show(b.dataset.t));
const h=location.hash.slice(1);if(h&&document.getElementById(h))show(h);
"""

def page(title, sub, tabs, bodies, data, script, other):
    nav = ''.join(f'<button data-t="{i}"{" class=on" if n == 0 else ""}>{html.escape(t)}</button>' for n, (i, t) in enumerate(tabs))
    secs = ''.join(f'<section id="{i}"{" class=on" if n == 0 else ""}>{b}</section>' for n, ((i, _), b) in enumerate(zip(tabs, bodies)))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<header><h1>{html.escape(title)}</h1><p class="sub">{sub} &nbsp;|&nbsp; <a class="ref" href="{other[0]}">{other[1]}</a> &nbsp;|&nbsp; Updated 2026-10-13 &nbsp;|&nbsp; Click anything to see why.</p></header>
<nav class="tabs">{nav}</nav><main>{secs}</main><aside id="drawer" aria-live="polite"></aside>
<script>{JS}
const DATA={json.dumps(data)};
{script}</script></body></html>"""

# ---------------------------------------------------------------- architecture page
FLOW = [
 ('Inputs', [('sources', 'sources.csv', '133 rows -> 123 unique', ['AD-15', 'AD-01']), ('xlsx', 'Directory workbooks', 'remote (86) + GCC (47)', ['PD-05'])]),
 ('Triggers', [('sched', 'Task Scheduler 08:30', 'catch-up when laptop wakes', ['AD-10']), ('btn', 'Start button / .bat', 'manual, anytime', ['AD-09']), ('desk', 'Desktop copy + reminder', 'launcher', ['AD-16'])]),
 ('Runner', [('lanes', 'Two lanes + memory gate', 'HTTP x8, Chrome x2', ['AD-06']), ('inc', 'Incremental + canary', 'new ids only; flag broken', ['AD-07', 'AD-08'])]),
 ('Readers', [('A', 'A: feeds / APIs', 'RemoteOK, Remotive, WWR...', ['AD-02']), ('B', 'B: platform APIs', 'Greenhouse, Ashby, Workday...', ['AD-01', 'AD-02']), ('C', 'C: custom pages', 'find JSON once, then HTTP', ['AD-04']), ('pw', 'Playwright (fallback)', 'max 2 Chromes', ['AD-03']), ('D', 'Parked / skipped', 'no logins, no bypass', ['AD-13'])]),
 ('Combine', [('route', 'Role routing (10 roles)', 'AI/ML/Data patterns', ['PD-03']), ('dedupe', 'De-duplicate + rank', 'remote-India first', ['PD-02']), ('xl', 'Job_Radar_V3.xlsx', '16 cols + Source/Type', ['AD-05'])]),
 ('Outputs', [('prog', 'Progress tracker HTML', 'live, Start/Stop', ['AD-09', 'PD-08']), ('dash', 'Dashboard HTML', 'snapshot, no server needed', ['AD-11', 'PD-08']), ('tests', 'Tests on saved samples', 'no live network', ['AD-12'])]),
]

arch_flow = '<p>Read left to right. Each box is a decision: click it to see what we chose, why, what we rejected, and the evidence.</p><div class="flow">' + ''.join(
    f'<div class="col"><h3>{c}</h3>' + ''.join(f'<button class="node" onclick="node({html.escape(json.dumps(n[3]), quote=True)})"><b>{html.escape(n[1])}</b><small>{html.escape(n[2])}</small></button>' for n in nodes) + '</div>'
    for c, nodes in FLOW) + '</div>'
arch_flow += """<h3 style="margin-top:26px">Source coverage (click a colour in the table tab to filter)</h3><div id="cov"></div>
<div class="card" style="margin-top:14px"><b>One-line summary.</b> Read each site with the cheapest method that works (feed, then platform API, then the page's own JSON found once, then a browser). Browsers and tokens are never used where a plain request will do.</div>"""

arch_tech = '<div class="row"><input id="tq" placeholder="Search decisions" oninput="renderT()"><select id="ta" onchange="renderT()"><option value="">All areas</option></select><select id="ts" onchange="renderT()"><option value="">All statuses</option><option>decided</option><option>proposed</option><option>open</option></select></div><div id="tl"></div>'
arch_req = '<div class="row"><input id="rq" placeholder="Search requirements" oninput="renderR()"><select id="rc" onchange="renderR()"><option value="">All categories</option></select></div><div id="rl"></div>'
arch_src = '<div class="row"><input id="sq" placeholder="Search sources" oninput="renderS()"><select id="sc" onchange="renderS()"><option value="">All classes</option><option value="A">A: feed/API</option><option value="B">B: platform API</option><option value="C">C: custom page</option><option value="D">D: parked</option><option value="S">S: skipped</option><option value="X">X: duplicate</option></select><select id="ss" onchange="renderS()"><option value="">Remote + GCC</option><option value="remote">Remote</option><option value="gcc">GCC</option></select></div><div class="card" style="overflow:auto;max-height:70vh"><table><thead><tr><th>ID</th><th>Name</th><th>Class</th><th>Reader</th><th>Status</th><th>Note</th></tr></thead><tbody id="st"></tbody></table></div>'

arch_script = r"""
const CLS={A:'feed/API',B:'platform API',C:'custom page',D:'parked',S:'skipped',X:'duplicate'};
function dec(d){return '<h2>'+d.id+' &middot; '+esc(d.title)+'</h2><p><span class="pill '+d.status+'">'+d.status+'</span><span class="pill">'+esc(d.area)+'</span></p><h4>Decision</h4><p>'+esc(d.decision)+'</p><h4>Why</h4><p>'+esc(d.why)+'</p><h4>Alternatives rejected</h4>'+list(d.alts)+'<h4>Evidence</h4><p>'+esc(d.evidence)+'</p><h4>Risk or cost</h4><p>'+esc(d.risk)+'</p><h4>Related</h4><p>'+refs(d.refs)+'</p>'}
function req(r){return '<h2>'+r.id+' &middot; '+esc(r.title)+'</h2><p><span class="pill">'+esc(r.cat)+'</span></p><h4>Requirement</h4><p>'+esc(r.must)+'</p><h4>How we measure it</h4><p>'+esc(r.measure)+'</p><h4>Decisions behind it</h4><p>'+refs(r.refs)+'</p>'}
function go(id){const d=DATA.tech.find(x=>x.id===id);if(d)return open_(dec(d));const r=DATA.reqs.find(x=>x.id===id);if(r)return open_(req(r));window.location.href='Product_Decisions.html#'+id}
function node(ids){open_(ids.map(id=>{const d=DATA.tech.find(x=>x.id===id);return d?dec(d):'<h2>'+id+'</h2><p>See <a class="ref" href="Product_Decisions.html">Product decisions</a>.</p>'}).join('<hr>'))}
function renderT(){const q=$('#tq').value.toLowerCase(),a=$('#ta').value,s=$('#ts').value;$('#tl').innerHTML=DATA.tech.filter(d=>(!a||d.area===a)&&(!s||d.status===s)&&(!q||JSON.stringify(d).toLowerCase().includes(q))).map(d=>'<button class="item" onclick="go(\''+d.id+'\')"><b>'+d.id+'</b>'+esc(d.title)+' <span class="pill '+d.status+'">'+d.status+'</span><span class="pill">'+esc(d.area)+'</span><span class="m">'+esc(d.decision)+'</span></button>').join('')}
function renderR(){const q=$('#rq').value.toLowerCase(),c=$('#rc').value;$('#rl').innerHTML=DATA.reqs.filter(r=>(!c||r.cat===c)&&(!q||JSON.stringify(r).toLowerCase().includes(q))).map(r=>'<button class="item" onclick="go(\''+r.id+'\')"><b>'+r.id+'</b>'+esc(r.title)+' <span class="pill">'+esc(r.cat)+'</span><span class="m">'+esc(r.must)+'</span></button>').join('')}
function renderS(){const q=$('#sq').value.toLowerCase(),c=$('#sc').value,s=$('#ss').value;$('#st').innerHTML=DATA.src.filter(r=>(!c||r.cls===c)&&(!s||r.sheet===s)&&(!q||JSON.stringify(r).toLowerCase().includes(q))).map(r=>'<tr class="click" onclick="srcOpen(\''+r.id+'\')"><td>'+r.id+'</td><td>'+esc(r.name)+'</td><td>'+(CLS[r.cls]||r.cls)+'</td><td>'+esc(r.reader)+'</td><td>'+(r.enabled==='yes'?'<b>working</b>':esc(r.verified))+'</td><td>'+esc(r.note)+'</td></tr>').join('')}
function srcOpen(id){const r=DATA.src.find(x=>x.id===id);open_('<h2>'+esc(r.name)+' <small>('+r.id+')</small></h2><p><span class="pill">'+(CLS[r.cls]||r.cls)+'</span><span class="pill">'+esc(r.reader)+'</span><span class="pill">'+esc(r.verified)+'</span></p><h4>Why this reader</h4><p>'+esc(r.note)+'</p><h4>URL</h4><p><a class="ref" href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.url)+'</a></p><h4>Rule behind it</h4><p>'+refs(['AD-02','AD-13'])+'</p>')}
(function(){const areas=[...new Set(DATA.tech.map(d=>d.area))];$('#ta').innerHTML+=areas.map(a=>'<option>'+a+'</option>').join('');const cats=[...new Set(DATA.reqs.map(r=>r.cat))];$('#rc').innerHTML+=cats.map(a=>'<option>'+a+'</option>').join('');
const cnt={};DATA.src.forEach(r=>cnt[r.cls]=(cnt[r.cls]||0)+1);const col={A:'var(--A)',B:'var(--B)',C:'var(--C)',D:'var(--D)',S:'var(--S)',X:'var(--X)'},tot=DATA.src.length;
$('#cov').innerHTML='<div class="bar">'+Object.keys(CLS).map(k=>'<span style="background:'+col[k]+';width:'+(100*(cnt[k]||0)/tot)+'%" title="'+CLS[k]+'">'+(cnt[k]||0)+'</span>').join('')+'</div><div class="lg">'+Object.keys(CLS).map(k=>'<span><i style="background:'+col[k]+'"></i>'+CLS[k]+' '+(cnt[k]||0)+'</span>').join('')+'<span>'+tot+' rows, '+(tot-(cnt.X||0))+' unique</span><span><b>'+DATA.src.filter(r=>r.enabled==='yes').length+' working now</b></span></div>';
renderT();renderR();renderS();if(/^(AD|TR)-/.test(h))go(h)})();
"""

# ---------------------------------------------------------------- product page
tree = """<div class="tree"><ul>
<li><button class="item" onclick="go('PD-01')"><b>Goal</b>One place that shows me every relevant AI/ML/Data job from my 120+ sites each morning<span class="m">click: why all the sites</span></button>
<ul>
<li><button class="item" onclick="go('PD-02')"><b>Rank</b>Remote-for-India first, then Bengaluru, then Hyderabad/Chennai</button></li>
<li><button class="item" onclick="go('PD-03')"><b>Relevance</b>10 AI/ML/Data roles; unmatched titles kept in a tab</button></li>
<li><button class="item" onclick="go('PD-05')"><b>Reach</b>Remote boards, startups, AI labs and 47 GCC career pages</button></li>
<li><button class="item" onclick="go('PD-06')"><b>Limits</b>No logins, paywalls, newsletters or bypassing human checks</button></li>
</ul></li>
<li><button class="item" onclick="go('PD-07')"><b>Habit</b>Fresh results by 08:30, manual button, Desktop copy with reminder</button></li>
<li><button class="item" onclick="go('PD-08')"><b>See it</b>Progress page while running; dashboard at the end</button>
<ul><li><button class="item" onclick="go('PD-09')"><b>Reuse</b>Dashboard copied from V2's Workspace UI</button></li></ul></li>
<li><button class="item" onclick="go('PD-04')"><b>Safety for V2</b>Separate workbook, same columns; V2 untouched</button></li>
<li><button class="item" onclick="go('PD-10')"><b>Way of working</b>Ask before important steps; visual decision documents</button></li></ul></div>"""
prod_logic = '<p>The reasoning from the problem down to the choices. Click any box for the question, the options, what we chose and why.</p>' + tree + """
<h3 style="margin-top:26px">How we got here</h3><div class="chain"><div><b>1 Problem</b>About 120 job sites to check by hand every day. Not realistic.</div><div><b>2 Why V2 cannot just repeat</b>One scraper per site took 35-40 min and 8 Chromes for 7 sites.</div><div><b>3 Insight</b>Most sites share a few job platforms or free feeds; 16 already work with plain requests.</div><div><b>4 Result</b>One reader per type, cheap-first, with visible progress and a dashboard.</div></div>"""
prod_dec = '<div id="pl"></div>'
prod_stories = '<h3>User stories</h3><div id="us"></div><h3 style="margin-top:20px">Success measures</h3><div id="mt"></div>'
prod_ng = '<h3>Not building</h3><div class="card"><ul id="ng"></ul></div><h3 style="margin-top:20px">Open questions</h3><div class="card"><ul id="oq"></ul></div>'

prod_script = r"""
function pd(d){return '<h2>'+d.id+' &middot; '+esc(d.title)+'</h2><h4>Question</h4><p>'+esc(d.q)+'</p><h4>Options</h4>'+list(d.options)+'<h4>Chosen</h4><p><b>'+esc(d.choice)+'</b></p><h4>Because</h4><p>'+esc(d.because)+'</p><h4>What it means</h4><p>'+esc(d.consequence)+'</p><h4>Technical decisions behind it</h4><p>'+(d.refs.length?d.refs.map(r=>'<a class="ref" href="Architecture_and_Tech.html#'+r+'">'+r+'</a>').join(''):'<span class="pill">none</span>')+'</p>'}
function go(id){const d=DATA.prod.find(x=>x.id===id);if(d)open_(pd(d));else window.location.href='Architecture_and_Tech.html#'+id}
$('#pl').innerHTML=DATA.prod.map(d=>'<button class="item" onclick="go(\''+d.id+'\')"><b>'+d.id+'</b>'+esc(d.title)+'<span class="m">'+esc(d.choice)+'</span></button>').join('');
$('#us').innerHTML=DATA.stories.map(s=>'<div class="card" style="margin-bottom:8px"><b>'+esc(s[0])+'</b><br>'+esc(s[1])+'<br><span style="color:var(--mute)">Done when: '+esc(s[2])+'</span></div>').join('');
$('#mt').innerHTML='<div class="card"><table>'+DATA.metrics.map(m=>'<tr><td><b>'+esc(m[0])+'</b></td><td>'+esc(m[1])+'</td></tr>').join('')+'</table></div>';
if(/^PD-/.test(h))go(h);
$('#ng').innerHTML=DATA.ng.map(x=>'<li>'+esc(x)+'</li>').join('');$('#oq').innerHTML=DATA.open.map(x=>'<li>'+esc(x)+'</li>').join('');
"""

(OUT / 'Architecture_and_Tech.html').write_text(page(
    'Job Radar V3: Architecture and Tech', 'How every website is read, and why. Technical decisions and requirements.',
    [('workflow', 'Workflow'), ('decisions', 'Tech decisions'), ('requirements', 'Tech requirements'), ('sources', f'Sources ({len(src)})')],
    [arch_flow, arch_tech, arch_req, arch_src], dict(tech=TECH, reqs=REQS, src=src), arch_script,
    ('Product_Decisions.html', 'Product decisions')), encoding='utf-8')
(OUT / 'Product_Decisions.html').write_text(page(
    'Job Radar V3: Product Decisions', 'What we are building, for whom, and the reasoning behind each choice.',
    [('logic', 'Logic map'), ('decisions', 'Decision log'), ('stories', 'Stories and measures'), ('limits', 'Not building / open')],
    [prod_logic, prod_dec, prod_stories, prod_ng], dict(prod=PROD, stories=STORIES, metrics=METRICS, ng=NONGOALS, open=OPEN), prod_script,
    ('Architecture_and_Tech.html', 'Architecture and tech')), encoding='utf-8')
print('written', len(TECH), 'tech decisions,', len(REQS), 'requirements,', len(PROD), 'product decisions,', len(src), 'sources')
