# Wellfound workflow (tech roles only)

Reads Wellfound's public role pages with a real, visible Chrome and writes the jobs inside the time window into `wellfound/output/Wellfound.xlsx` (tab "Wellfound"). Free, no tokens, **no login**, no Docker or Firecrawl.

## Input
The shared file `job-radar-V3/input.csv`. Only **tech roles** are searched: roles whose Experience is above 0 (`--include-non-tech` overrides). Keywords become Wellfound role pages through `slugs.csv` (keyword -> role slug, `-` = no page), falling back to the keyword's own slug. Several keywords can share one page (Machine Learning Engineer and ML Engineer both read `machine-learning-engineer`).

## Time window (no day is lost)
`--hours` is optional. By default the run keeps jobs whose posted date is **since midnight of the latest posted date already read** (`output/state.json`, at least 24 h, **at most 7 days** (`MAX_WINDOW_HOURS = 168`): only jobs posted within the last week are wanted, however long a run was missed; see `common/window.py`). `--hours 0` removes the window. Wellfound has **no time filter and no date sort**, and its posted label is coarse ("6 days ago", "1 month ago", "3 years ago"), so every page of each role is read and the window is applied afterwards to the estimated date. The date only moves forward after a run that finished without an error.

## Location rule
Kept: **India** (a city, or a job on the India list), **Remote - India**, **Remote - anywhere**, and **Remote - location not stated** (a remote-list job showing no place). Dropped: remote jobs that name a place outside India (United States, Toronto ...); `--keep-all-locations` keeps them as "Outside India: place". Matching: `common/geo.py` (India, states, about 80 cities) and `parse.py: classify_location()`. A Bengaluru column marks Bengaluru/Bangalore jobs.

## A pool of Chromes sharing one page queue
Pages of one list are independent (`?page=N`). Page 1 of every list is read first; it says "Page 1 of 24" and tells a real role page from the generic one. Pages 2..N then go into one shared queue and up to 8 Chromes (`--workers N`, default and maximum 8) pull from it, so a long list such as `ai-engineer` remote is spread over every Chrome instead of making one Chrome the slowest. Each Chrome has its own profile folder (`data/wellfound_profiles/w0`, `w1` ...; Chrome allows one process per profile), starts a random 4-10 s after the previous one, and pauses 7-15 s before each page. A human check in any Chrome sets a shared stop flag and all Chromes stop and keep what they have; if every Chrome fails the run ends instead of hanging. The load on Wellfound is roughly the number of Chromes times one slow reader.

## Output (all in `wellfound/output/`)
`Wellfound.xlsx` (result), `runs/wellfound_*.jsonl` (raw backup per run, written before Excel), `last_run.log`.

## Visual explainer
Open `Wellfound_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## How it works
1. **plan** (`search.py: plan()`): each keyword to a slug; one India list (`/role/l/<slug>/india`) and one remote list (`/role/r/<slug>`) per distinct slug. Keywords with no Wellfound page are skipped and reported.
2. **read** (`search.py: _worker()`): page 1 of each list first, then pages 2..N from the shared queue (a list that does not say its page count is read page by page until one is empty). The only ceiling is 100 pages per list, Wellfound's own maximum. **Wellfound answers an unknown role name with its generic "India Jobs" page (thousands of unrelated jobs), so the page title must contain the role's words or the list is skipped.** (The old Firecrawl pipeline never detected this; its Forward Deployed Engineer and AI Scientist slugs silently read the generic page.)
3. **parse** (`parse.py`): per company block and per job row: title, link, job type, salary, equity, work mode, location (+N more), experience (shown as a minimum, kept as "N+ years"), posted label and estimated date, company name, size, stage tags, tagline, page, actively hiring.
4. **filter**: estimated posted date inside the window; experience rule from input.csv (open-ended "N+" always passes).
5. **eligibility**: India list = "India"; remote list = "Unclear (remote list, mostly US-based)" unless the location says India. Remote-World jobs are kept and flagged.
6. **backup, then Excel**: new jobs added by link; Role, Status, Notes and First seen are never overwritten.

## Files
| File | Job |
|---|---|
| `config.py` | URLs, pauses, selectors, limits |
| `slugs.csv` | keyword to Wellfound role page |
| `session.py` | Chrome with the saved profile (`data/wellfound_profile`); human-check helper |
| `search.py` | plan, shared page queue and Chrome pool, window, location, experience |
| `parse.py` | page HTML to job dicts (pure, tested) |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up |
| `__main__.py` | command line |
| `tests/` | parser, planner, window and Excel tests on a saved real page |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m wellfound search
.venv\Scripts\python -m wellfound search --role "AI Engineer" --hours 48
.venv\Scripts\python -m wellfound check
.venv\Scripts\python -m pytest wellfound/tests
```
Close `Wellfound.xlsx` in Excel before a run (otherwise a timestamped copy is written).

## Rules
- Public pages only. Never log in. Never solve or hide a human check: the run stops, keeps what it has and shows a pop-up; `check_wellfound.bat` opens the window so you can pass it by hand (it did not appear in the first tests).
- Slow on purpose: 7-15 s between pages, 20-40 s between role lists, per Chrome.

## Decision log
- Tested the new method (real Chrome) first: Wellfound loaded with no human check, so the old Docker/Firecrawl method was **not needed**. The Firecrawl adapter stays in the old `job-radar` project if it is ever required again.
- Probed role slugs on 2026-10-11: existing pages: data-scientist (58 India results), data-analyst (161), business-analyst (158), machine-learning-engineer (130), ai-engineer (791), data-architect (244), solutions-architect (200), machine-learning-scientist (39), artificial-intelligence-engineer (2,649), data-engineer (806). No page (generic fallback): ml-engineer, generative-ai-engineer, llm-engineer, ai-scientist, applied-scientist, research-scientist, forward-deployed-engineer, ai-architect.

## Measurements (2026-10-11, 7-day window, location rule on)
- 8 tech roles, 14 keywords, 16 page lists (Forward Deployed Engineer and AI Architect have no Wellfound page and are skipped). First version, one Chrome per role, 30-page ceiling: 171 pages, 4,134 jobs in 18.9 min, 210 kept.
- **Current version, shared page queue, no ceiling of mine: 8 Chromes read 178 pages and 4,668 jobs in 7.9 min** (pages per Chrome 20 to 24, evenly shared), no human check. `ai-engineer` remote turned out to have 51 pages, so the old ceiling had cut off 21 of them. **220 unique jobs kept** (10 new over the first run): India 127, Remote - anywhere 48, Remote - location not stated 25, Remote - India 20; Bengaluru 62. Dropped: 3,928 outside the week, 351 outside India, 0 by the experience rule.
- Kept by role (first role to find a job keeps it): AI Engineer 129, Data Analyst 37, Data Scientist 17, Architect 16, ML Engineer 14, Business Analyst 7. The ai-engineer page also carries the LLM and Generative AI keywords and is broad.
- Known limit: 92 of the 220 are labelled "1 week ago", which on Wellfound means 7 to 13 days, so they sit on the window edge.

## Not done here (combined pipeline)
Title filtering and role routing, India/Bengaluru ranking, cross-site de-duplication, full job descriptions (Wellfound job pages), the daily schedule.
