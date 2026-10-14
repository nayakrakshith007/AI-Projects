# Cutshort workflow (tech roles, data science lists)

Reads Cutshort's **public** data science job lists (India, Bengaluru, remote) and writes the jobs inside the time window into `cutshort/output/Cutshort.xlsx` (tab "Cutshort"). Free, no tokens, **no login**.

## What Cutshort offers without a login
- The personal link `cutshort.io/profile/all-jobs?matchesfor=...` needs a login (it redirects to the sign-up page). It is **not used**.
- Public category pages `cutshort.io/jobs/<category>-jobs` show the **newest 50 jobs** of the list, newest first, with the full data. Cutshort's own "page 2" returns the same 50 again.
- Only broad categories exist (data science, backend, frontend, DevOps, product manager ...). There is **no page for machine learning, AI, data analyst, business analyst or architect roles**, so only data science is covered.
- The keyword search (`/search-jobs`) is ranked by relevance, matches loosely (3,948 hits for "machine learning engineer") and each response is about 20 MB. It is **not used**.
- Because a list shows its newest 50 jobs, a daily run sees every new job as long as fewer than 50 are posted per list per day (a list gains a few jobs a week). The command line warns if all 50 are inside the window.

## Input
`cutshort/lists.csv` names the lists (`slug`, `label`): `datascience-jobs` (330 jobs in India), `datascience-jobs-in-bangalore-bengaluru` (138), `remote-datascience-jobs` (68). One line adds another category. The shared `input.csv` only sets the experience rule: the lowest minimum of the tech roles in it (5). Role routing (which job is an AI Engineer, a Data Analyst ...) happens later in the combined pipeline; the Role column stays empty here.

## How a page is read
Each page is a Next.js page that ships its job list as JSON inside `<script id="__NEXT_DATA__">`. One visible Chrome opens the three lists one after another (3 to 6 s after each load, 6 to 12 s between lists, a fresh browser state each run) and `parse_page()` reads that JSON: no scrolling, no clicking, no screen scraping. The run takes under a minute.

## Fields per job
Title, company, "Hiring for client" (staffing agencies post as "Hiring for ..."), experience range (numbers), location (all cities), Bengaluru flag, work mode (Onsite, Remote, Onsite or remote), job type, salary text, skills, exact posting time (UTC converted to Indian time), company type, size, stage, founded year, company website and LinkedIn, the **full description** as plain text (up to 32,000 characters) and the job link. The recruiter who posted a job is named in the data; **it is never read or stored**, not even in the test fixtures.

## Time window (no day is lost)
`--hours` is optional. By default the run reads **since midnight of the latest posted date already read** (`output/state.json`, at least 24 h, **at most 7 days**; see `common/window.py`). The window is applied to the exact posting time. The date only moves forward after a run that finished without an error.

## Rules applied
- Posted inside the window.
- Jobs that are only internships are dropped.
- Experience (`common/inputs.py : experience_ok`): a job stays if the top of its range reaches the minimum (5) or it states none.
- A job on several lists is kept once; the "Found in" column names every list (and only grows in Excel).

## Output (all in `cutshort/output/`)
`Cutshort.xlsx` (28 columns: Title, Company, Hiring for client, Role, Experience, Exp min, Exp max, Location, Bengaluru, Work mode, Job type, Salary, Skills, Posted, Posted date, Posted at, Company type, Company size, Company stage, Founded, Company website, Company LinkedIn, Found in, Description, First seen, Link, Status, Notes), `runs/cutshort_*.jsonl` (raw backup, written before Excel), `state.json`. Role, Status, Notes and First seen are kept when a job is refreshed.

## Visual explainer
Open `Cutshort_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## Files
| File | Job |
|---|---|
| `config.py` | URLs, pauses, limits, list loader |
| `lists.csv` | the Cutshort lists that are read |
| `session.py` | Chrome with a fresh context; human-check helper |
| `search.py` | read the lists, window, internship and experience rules, one record per job |
| `parse.py` | page JSON to job dicts (pure, tested) |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up |
| `__main__.py` | command line |
| `tests/` | parser tests on a saved real page; window, rules, run (Chrome faked), human-check and Excel tests |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m cutshort search
.venv\Scripts\python -m cutshort search --hours 168
.venv\Scripts\python -m cutshort check
.venv\Scripts\python -m pytest cutshort/tests
```
Close `Cutshort.xlsx` in Excel before a run (otherwise a timestamped copy is written).

## Rules
- Public pages only. Never log in. Never solve or hide a human check: the run stops, keeps what it has and shows a pop-up; `check_cutshort.bat` opens the window (it did not appear in the real runs).
- Slow on purpose: pauses between pages, one Chrome.

## Measurements (2026-10-11)
- 3 pages, 150 jobs read in about 45 s. No human check.
- **7-day window: 2 jobs kept. 30-day window (`--hours 720`): 9 jobs** (India 9, Bengaluru 2 of them also in India, remote 0). 4 internships dropped. Cutshort adds only a few data science jobs a week.

## Not done here (combined pipeline)
Role routing and title filtering, cross-site de-duplication, roles that have no Cutshort category (Business Analyst, Architect), the daily schedule.
