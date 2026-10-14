# Architecture: how each website is read

Status: DRAFT, 2026-10-13. Based on a read-only probe of all 133 rows (86 remote + 47 GCC): one polite GET each, plus test calls to the public job APIs. Evidence is in `discovery/probe.csv`; the per-row decision is in `discovery/sources.csv`. Nothing in the daily pipeline is built yet.

## The decision in one paragraph

Read each site with the **cheapest method that works, in this order**: (1) public feed or JSON API, (2) the job-platform's own public API (Greenhouse, Ashby, Lever, Workable, Workday), (3) the JSON that a career page itself calls, found **once during development** with a browser and then called with plain HTTP, (4) a real browser (Playwright, Python library) only for pages where nothing else works. The daily run uses **no Playwright CLI, no built-in Claude browser, and no LLM**. Those tools are for development only (discovering endpoints, writing tests), because the daily run must be free and light on memory.

## Why not Playwright for everything

| Option | Memory | Speed | Tokens | Verdict |
|---|---|---|---|---|
| Plain HTTP to feeds and ATS APIs (`requests`/`httpx`) | about 50 MB total | seconds per source | 0 | **Default.** 16 sources were tested today and all returned jobs. |
| Playwright Python library, headless, driven by our code | 300 to 500 MB per Chrome | 10 to 60 s per page | 0 | **Fallback** for the few pages with no usable JSON. Max 2 at once, one Chrome per lane. |
| Playwright CLI | same as the library | slower (process per command) | 0 for the run, but it is built for an LLM to drive step by step | **Dev tool only.** Not for the daily run. |
| Claude built-in browser / Claude in Chrome | a full app Chrome | slow | spends tokens on every step | **Dev tool only**, to look at a page and find its API. Violates "no tokens in daily use" if used daily. |
| One scraper per site (V2 style) | high | slow | 0 | **Rejected.** About 120 sites would mean 120 scrapers and 100+ Chromes. |

V2 took 35 to 40 minutes with about 8 Chromes for 7 sites. The same hardware can read the verified API sources below in seconds each, so the browser budget goes only to the few sites that need it.

## The five reader types

| Type | What it is | Rows | Verified today |
|---|---|---|---|
| **A: feed/API** | RemoteOK, Remotive (API), We Work Remotely (RSS), Working Nomads, Jobspresso (RSS) | 5 | 5 of 5 return jobs |
| **B: platform API** | Greenhouse (6 companies), Ashby (4), Workable (1), Lever (1), Workday CxS (6), Eightfold (6), Phenom (4), Oracle HCM (1), Avature (3), iCIMS (2), SuccessFactors (1), Taleo (2) | 37 | 11 of 37 return jobs today. The other 26 have a platform signature; the tenant or endpoint is still to be tested |
| **C: custom page** | Google, Meta, Amazon, Apple, Nvidia, DeepMind, VC portfolio boards, specialist boards, most GCC companies | 42 | none yet. Plan: sniff the page's JSON once in dev, then call it directly |
| **D: parked** | Needs login or paid (FlexJobs, Upwork, Fiverr, Crunchbase); LinkedIn and Wellfound (V2 covers them); talent marketplaces with no public list; sites that answer with a bot challenge; domains that did not load | 34 | n/a |
| **S: skip** | Newsletters | 5 | n/a |
| **X: duplicate** | Same site listed twice (Wellfound, Hugging Face, Hired, Toptal, Google, Microsoft, Apple, Meta, Amazon) | 10 | n/a |

Total 133 rows = 123 unique sources + 10 duplicates. Realistic coverage: about **16 working now**, about **68 more** (rest of type B plus type C) once their endpoints are found, and **39 not scraped** (34 parked + 5 newsletters). Treat the 68 as a target, not a promise, until each is tested in Phase 1.

## Why parked sites are parked

- LinkedIn: `robots.txt` disallows it, a bot challenge answers the first request, V2 already covers it.
- Rows with a bot challenge or 403 on the first request (Pfizer, DataScienceJobs, icrunchdata, Perplexity's HTML page, Remote.co, Kaggle): the rule is never to solve or hide a human check. Where the same company has a public API (Perplexity on Ashby) we use the API instead of the page.
- Talent marketplaces (Toptal, Hired, Karat, 10x, Gun.io, Crossover, Lemon.io, Contra, Braintrust, Deel, Otta): they match people to clients; there is no public list of jobs to radar.
- Five domains did not load at all (mljobs.co, llm.jobs, machinelearningjobs.co, pangian.com, jobs.analyticsvidhya.com): recheck once, then drop.

## Efficiency design (what makes it faster than V2)

1. **Lanes by cost, not by site.** Lane 1: HTTP sources, up to 8 at once, each host rate-limited to 1 request per second. Lane 2: at most 2 Chromes. Memory gate (1 GB free) stays from V2.
2. **Ask the API to filter.** Send the AI/ML/Data keywords and location where the API supports it (Workday, Eightfold, Ashby location); otherwise filter by title after download.
3. **Incremental reads.** Keep the set of job IDs seen per source; only new IDs get processed. Greenhouse, Ashby and Lever return everything in one call anyway (Anthropic 647 jobs, OpenAI 808, Databricks 897), so the cost is one request.
4. **One adapter per platform, one line per company.** Adding Palantir (Lever, 311 jobs, verified) is a config line: `lever,palantir`.
5. **Canary per source.** A source that returns zero jobs twice in a row shows as "broken" on the progress page instead of silently empty.
6. **Playwright only when a source is marked `browser` in `sources.csv`.** The progress page shows how many Chromes are open.

## Location and ranking (owner's rules)

Remote roles open to India rank first. Then Bengaluru, then Hyderabad or Chennai, then the rest of India. Remote has to be "open to India": a posting limited to "US only" or "EU only" is excluded, and a posting with no restriction is kept and flagged "worldwide". Ambiguous ones go in the table with a "check eligibility" flag instead of being thrown away.

## Role set (the list to approve; this is the "section 2" you asked about)

It is under **User Experience & Functionality** in [PRD-job-radar-v3.md](PRD-job-radar-v3.md), the paragraph "Role scope". The ten roles: AI Engineer; Machine Learning Engineer; Generative AI / LLM Engineer; Data Scientist; Applied Scientist / Research Engineer; MLOps / ML Platform Engineer; Data Engineer; Data Analyst / BI Analyst; AI Architect / Solutions Architect (data and AI); Prompt Engineer / AI Product roles.

## Build order

1. **Phase 1:** adapters for type A and the verified type B sources, V3 workbook, role routing, de-duplication, rank by the location rules. Test on saved sample responses (no network in tests).
2. **Phase 2:** test the 26 platform candidates (tenant IDs, endpoints) and turn each into "working" or "parked with reason".
3. **Phase 3:** type C. For each page, one dev-time look for the JSON; Playwright only if none.
4. **Phase 4:** progress tracker HTML with Start/Stop, then dashboard HTML, then launcher `.bat`, Desktop copy with reminder, and the scheduled task at 08:30 (you said yes to creating it).
5. Throughout: `sources.csv` is the single list; the progress page reads it.

## Risks specific to this design

- APIs can change without notice. Each adapter has a saved sample and a test; a changed shape fails loudly.
- Public APIs have terms. RemoteOK asks for a link back to the job; we keep the source link on every row. Keep to one request per host per second.
- Eightfold, Phenom and Oracle HCM need per-company tuning, which is the real work in Phase 2.
- "Open to India" for remote roles depends on location text that is messy; expect a manual review column at first.
