# PRD: Job Radar V3 (remote AI/ML/Data sources)

Status: DRAFT 1, 2026-10-13. Waiting for the owner's feedback on the open items in section 5. Anything marked TBD was not decided by the owner.

## 1. Executive Summary

**Problem Statement.** The owner has a spreadsheet of about 70 unique remote and AI/ML job sites. Checking them by hand every day is not realistic, and V2's approach (one browser scraper per site, about 8 Chromes at once, 35 to 40 minutes a run) would not scale to that many sites.

**Proposed Solution.** Build V3 as a separate pipeline. It uses one reader per source type (public feeds and APIs first, shared job-platform readers next, a browser only where nothing else works). It runs automatically each morning, shows live progress in one HTML page, and ends in a dashboard HTML page with analytics and a jobs table. It can also be started by hand from the HTML page or a `.bat` file.

**Success Criteria.**
1. Coverage: every one of the 86 rows in the new workbook ends in exactly one state (scraped, parked with a reason, or skipped with a reason). Zero rows silently missing. Target: at least 60% of the non-skipped sites scraped successfully in the MVP, and the rest listed with a reason on the progress page.
2. Efficiency (compared with V2's 35 to 40 minutes and about 8 Chromes): a daily run finishes in 15 minutes or less (TBD, to be confirmed after the first measured run), with no more than 2 Chromes open at once and 1 GB of free memory kept.
3. Reliability: at least 95% of scheduled mornings produce a fresh workbook, counting a catch-up run after the laptop wakes as a success.
4. Relevance: at least 90% of rows in the "All" tab match one of the approved AI/ML/Data roles (checked by hand on a sample of 50 rows after the first full run).
5. Zero cost: no LLM tokens, no logins, no human-check bypass in any daily run.

## 2. User Experience & Functionality

**User Persona.** The owner: a single user, in Bengaluru, on a Windows 11 laptop with 16 GB of memory, looking for AI/ML/Data roles. Prefers terse status messages. Cannot leave the laptop on all day.

**User Stories and Acceptance Criteria.**

1. *As the owner, I want all usable sites in my spreadsheet read automatically so that I don't open 70 sites by hand.*
   - Each of the 86 rows is classified: public feed or API, Greenhouse/Lever/Ashby board, custom page needing a browser, parked (needs login, paid, or no job list), or skipped (newsletter).
   - The classification is stored in one config file; adding a company or site is one line.
   - Results are saved in a separate V3 workbook, `pipeline/output/Job_Radar_V3.xlsx` (name TBD), with the same 16 columns as V2 (Roles, Title, Company, Location, Bengaluru, Work mode, Experience, Salary, Posted date, Sites, Skills, First seen, Link, Other links, Status, Notes) plus a Source/Type column.
   - V2's `Job_Radar.xlsx` is never read for writing or changed.

2. *As the owner, I want to see progress while a run is going so that I know what is happening and what needs me.*
   - One HTML file (the progress tracker) shows each source with a state: waiting, reading, done, needs you, parked, skipped, failed.
   - For each source it shows jobs found, new jobs, time taken, and the last log line. The page updates at least every 5 seconds while a run is active.
   - It also shows runs started by the scheduler or the command line, not only runs started from the page.
   - A source that hits a human check shows "needs you", keeps what it read, and the run continues with the other sources.

3. *As the owner, I want a dashboard at the end of each run so that I can see what came in and decide where to apply.*
   - One HTML file (the dashboard) with: KPI cards (jobs in view, new today, companies hiring, Bengaluru share, remote share), charts (jobs per role, per day, per source, work mode, top skills, top companies, experience asked), and a sortable, filterable jobs table with a link to each job.
   - Filters (time range, role, location tier, source) apply to every chart and the table.
   - Location order everywhere: Bengaluru first, then Hyderabad or Chennai, then the rest of India, then India-friendly remote (exact order within the last two TBD, see section 5).
   - The page works from a snapshot file with the data embedded, so it opens without the server running.

4. *As the owner, I want the run to start by itself each morning so that fresh jobs are waiting when I sit down.*
   - A Windows Task Scheduler task starts at 08:30 (inside the owner's 8 to 9 AM window) and has "run as soon as available" turned on, so a run missed because the laptop was off starts when it is next on.
   - Feeds and APIs run daily. Company career pages run weekly (day TBD). A manual run can run everything.
   - A second start while one is running is ignored.
   - The task is created only after the owner says yes (project rule).

5. *As the owner, I want to start a run by hand from the HTML page or a `.bat` file.*
   - A "Start run" button on the progress tracker starts the same run as the schedule and a "Stop" button ends it. It works only through the local server on 127.0.0.1.
   - `start_job_radar_v3.bat` starts the local server if needed, opens the progress page and begins a run.
   - Buttons offer "Daily sources only" and "Everything".

6. *As the owner, I want a copy of the launcher on my Desktop and a reminder if it is missing so that I never forget it.*
   - After setup, a `Job Radar V3.bat` launcher (or shortcut) exists in the real Desktop folder (resolved from Windows, because a OneDrive-redirected Desktop is possible).
   - If the launcher is not on the Desktop, the end-of-run message box and the progress page both say so until it is there.
   - The reminder at setup is shown in the final message of the build and written in the README.

**Role scope (draft for the owner to approve).** The owner chose a new AI/ML/Data set instead of V2's 8 tech roles. Proposed list: AI Engineer, Machine Learning Engineer, Generative AI / LLM Engineer, Data Scientist, Applied Scientist / Research Engineer, MLOps / ML Platform Engineer, Data Engineer, Data Analyst / BI Analyst, AI Architect / Solutions Architect (data and AI), Prompt Engineer / AI Product roles. Title patterns follow V2's `role_patterns.csv` approach. A title that matches none goes to an `Unmatched` tab, so nothing disappears silently.

**Non-Goals.**
- No logins, no paid memberships, no CAPTCHA solving or hiding. FlexJobs, Upwork, Fiverr and Crunchbase are parked. Newsletters (TLDR AI, Ben's Bites, Latent Space, AI Breakfast, The Batch) are skipped.
- No changes to V2 and no running of the V2 pipeline from V3.
- No automatic applying, no auto-sent mail, no cover-letter writing in the MVP.
- No LLM calls in the daily run.
- No cloud hosting or sharing in the MVP.
- No full job descriptions in the MVP (V2 does not have them either).

## 3. AI System Requirements

Not applicable to the daily run, which uses rules only. Optional later use of an LLM (for example, to guess a site's platform) must stay out of the daily path.

**Evaluation Strategy (for the extraction itself).**
- Coverage check: a source-by-source table of the 86 rows, each with its final state. A script fails the build if a row has no state.
- Accuracy check: for each reader type, compare 10 jobs read against the live site by hand.
- Role filter check: 50 random rows from "All" and 50 from "Unmatched", counted by hand for wrong matches.
- Regression: unit tests with saved sample feeds (no network), plus fake-site tests for the runner as in V2.

## 4. Technical Specifications

**Architecture Overview.**

```
sources.csv (from the workbook, classified)
   -> runner (lanes by type, memory gate, stall restart, per-source log)
        lane A: feed/API readers, no browser (RemoteOK, Remotive, We Work Remotely, Working Nomads, ...)
        lane B: platform readers (Greenhouse, Lever, Ashby, and similar; company = one config line)
        lane C: custom browser pages, one Chrome at a time, only if worth it
   -> combine: route to roles, de-duplicate, rank (Bengaluru first)
   -> Job_Radar_V3.xlsx  +  run_state.json  +  snapshot.json
   -> Progress tracker HTML (live, via local server)   |   Dashboard HTML (snapshot)
```

- Reuses the V2 pipeline pattern: lanes runner, memory gate, stall restart, atomic Excel saves, run history, `route.py`, `dedupe.py`, `build.py`, `tracker.py`. The Workspace/analytics code lives only on V2's branch `workspace-ui`, so copying it into V3 needs the owner's OK (section 5).
- Efficiency levers compared with V2: no browser for feeds and platform boards; one shared HTTP client with per-host politeness delays; conditional requests where a site supports them; only new jobs processed after the first run; parallelism limited to network lanes, not Chromes.
- Programming language and libraries: Python with the same `requirements.txt` as V2 (Playwright only for lane C). Anything else TBD.

**Integration Points.**
- Input: `Remote_AI_ML_Jobs_Directory (1).xlsx` (86 rows on "All Remote AI Jobs" plus category sheets; duplicates: LinkedIn, Wellfound, Hugging Face, Hired, Toptal).
- Output: V3 workbook, `run_state.json`, `history.jsonl`, `snapshot.json`, the two HTML pages.
- Local server on 127.0.0.1:8770 (V2 uses the same port; V3 must use a different port, TBD, so the two never clash).
- Windows Task Scheduler for the morning start; a message box at the end of a run.
- No databases and no authentication.

**Security & Privacy.**
- Server listens on 127.0.0.1 only, checks the Host header, accepts Start/Stop only from its own page (as in V2).
- No credentials stored. Browser profiles are fresh and local and are not committed to git (`.gitignore`).
- The dashboard snapshot holds job data only, nothing personal.
- Polite use: respect robots.txt and terms for each source; sites that forbid scraping are parked, not bypassed.

## 5. Risks & Roadmap

**Open items needing the owner's answer.**
1. **The new workbook has no GCC sheet.** `Remote_AI_ML_Jobs_Directory (1).xlsx` has the 86 remote rows only; the "GCC Companies Hiring in India" sheet (47 career pages) from the earlier file is not in it. Do you want the GCC companies in V3 now (add that file) or left out?
2. Copy the Workspace code (analytics, jobs table, applications board, profile) from V2's `workspace-ui` branch into V3 for the dashboard? V3 would take a copy, and V2 is not changed.
3. Location order after Bengaluru: Hyderabad and Chennai tied, or Hyderabad first? And where do India-friendly remote roles rank (above or below Hyderabad/Chennai)?
4. Approve or edit the role list in section 2.
5. Weekly day and time for career pages (suggest Monday 08:30).
6. Approve creating the Task Scheduler task (needed before the automation exists).

**Phased Rollout.**
- **Phase 0 (probe, no code in the pipeline):** classify all 86 rows by trying each one: is there a public feed, a JSON API, a known platform board, or only a rendered page? Output: `sources.csv` with type, method and reason. This turns the "about 60%" target into a real number.
- **MVP:** lane A (feeds/APIs) and lane B for the Tier 1 and AI-lab companies; V3 workbook; progress tracker HTML with Start/Stop; `.bat` launcher; Desktop copy and reminder; Task Scheduler at 08:30 (after the owner's yes).
- **v1.1:** dashboard HTML with charts and jobs table; weekly career-page lane; run history and Performance tab.
- **v2.0:** custom browser pages (Google, Meta, Apple, Amazon) if worth the memory; GCC career pages if added; Workspace extras (applications board, Fit %).

**Technical Risks.**
- Many listed sites have no public job list (talent marketplaces such as Hired, Toptal, Otta, Karat, 10x Management, Vettery). They will be parked, so the 86 rows will not all produce jobs.
- Sites can change layout or block requests; each reader needs a canary test and an alert on the progress page when a source returns zero jobs twice in a row.
- A site that shows a human check stops that source until the owner passes it by hand.
- 16 GB memory: keep Chromes to 2 or fewer; V2's first all-at-once run opened about 100 Chromes.
- A laptop that is off at 08:30 relies on catch-up; if it never wakes that day, the run is missing and the dashboard says "last updated" with the date.
- Many of the listed sites repeat the same jobs (VC boards list company jobs from Greenhouse/Lever/Ashby), so de-duplication is essential.
