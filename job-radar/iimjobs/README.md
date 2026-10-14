# IIMJobs workflow (tech roles only)

Reads IIMJobs with **two methods at once**, compares them, and writes the jobs inside the time window into `iimjobs/output/IIMJobs.xlsx` (tab "IIMJobs"). Free, no tokens, **no login**.

IIMJobs is the sister site of Hirist and runs on the same kind of backend, so this workflow follows the Hirist one. It is a management and senior-role board: good for Business Analyst, Data Analyst and Architect roles. It has almost no clinical, regulatory or Ayurveda jobs ("Pharmacovigilance": 1 job in all, "Ayurveda": 4), so only tech roles are searched.

## Input
The shared file `job-radar-V3/input.csv`. Only **tech roles** are searched (Experience above 0; `--include-non-tech` overrides). Keywords are searched as they are by the search method; for the tag method `tags.csv` maps a keyword to IIMJobs tag pages (`-` = no tag page).

## The two methods
| | search method | tag method |
|---|---|---|
| Page | `/search/<keyword>-jobs?...&posting=N&page=P` | `/k/<tag>-jobs?posting=N&page=P` |
| Data | the JSON the page loads (`gladiator.iimjobs.com/job/search`) | the JSON the page loads (`gladiator.iimjobs.com/job/keyword/`), the same job format |
| Covers | every keyword | only keywords that have an IIMJobs tag (none for Business Analyst, AI Architect, Forward Deployed Engineer) |
| Accuracy | looser (also returns unrelated jobs) | tighter |

Both read the response the page requests for itself (`page.expect_response`), so dates are exact (`createdTimeMs`, converted to Indian time), experience is numeric (`min`, `max`) and every location is listed. Both use **IIMJobs' own date filter in the URL** (`posting=1|3|7|15|30` days, applied on its server): Data Scientist has 253 jobs in all but 12 in the last week.

**Page count.** IIMJobs' own `totalPages` field is wrong when the date filter is on (it said 1 for 89 jobs and 0 for 12), so pages are counted from `totalJobs` and the page size (50). A first run missed the second Business Analyst page because of this; the fix has a test.

**Comparison, first run (2026-10-11), scored against the old project's validated role title patterns:** search found 46 role-matching jobs (73% recall, 30% precision), tag found 54 (85% recall, 48% precision), 37 by both. 16 relevant jobs were found only by tag (senior data science and analytics roles), 9 only by search (mostly Business Analyst). **Run both and keep the union** (about 2 minutes). The "Found by" column says which method found each job; `output/compare_methods.csv` has the per-role table.

## Time window (no day is lost)
`--hours` is optional. By default the run reads **since midnight of the latest posted date already read** (`output/state.json`, at least 24 h, **at most 7 days**; see `common/window.py`). IIMJobs' `posting` filter is rounded up to 1, 3, 7, 15 or 30 days; the exact window is then applied to the exact posting time. The date only moves forward after a run that finished without an error.

## A pool of Chromes sharing one page queue
Page 1 of each list says how many jobs there are; pages 2..N go into one queue and up to 3 Chromes (`--workers`, at most 5) pull from it. **Every Chrome starts with a fresh browser state** (`browser.new_context()`); Hirist remembers filters between visits and nothing is kept here either. Chromes start 3-8 s apart and pause 5-11 s before each page. A human check in any Chrome stops all of them (they keep what they read); if every Chrome fails the run ends instead of hanging.

## Experience and location
IIMJobs gives numbers, so the rule from `input.csv` is exact: a job stays if its maximum years reaches the role's minimum or it states none. IIMJobs is an India site, so there is no country filter; a **Bengaluru** column marks Bengaluru/Bangalore jobs.

## Output (all in `iimjobs/output/`)
`IIMJobs.xlsx` (20 columns: Title, Company, Role, Experience, Exp min, Exp max, Location, Bengaluru, Work mode, Salary, Skills, Posted date, Posted at, Found by, Title matches, Search term, First seen, Link, Status, Notes), `compare_methods.csv`, `runs/iimjobs_*.jsonl` (raw backup, written before Excel), `state.json`. Role, Status, Notes and First seen are kept when a job is refreshed.

## Visual explainer
Open `IIMJobs_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## Files
| File | Job |
|---|---|
| `config.py` | URLs, the posting filter, pauses, limits |
| `tags.csv` | keyword to IIMJobs tag pages |
| `session.py` | Chrome with a fresh context; human-check helper |
| `search.py` | plan, page queue and Chrome pool, window, experience, merge, compare |
| `parse.py` | list JSON to job dicts, page count, job links (pure, tested) |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up |
| `__main__.py` | command line |
| `tests/` | parser tests on a saved real JSON page; queue, merge, window, human-check and Excel tests |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m iimjobs search
.venv\Scripts\python -m iimjobs search --hours 168 --method both
.venv\Scripts\python -m iimjobs search --role "Architect" --method search
.venv\Scripts\python -m iimjobs check
.venv\Scripts\python -m pytest iimjobs/tests
```
Close `IIMJobs.xlsx` in Excel before a run (otherwise a timestamped copy is written).

## Rules
- Public pages only. Never log in. Never solve or hide a human check: the run stops, keeps what it has and shows a pop-up; `check_iimjobs.bat` opens the window (it did not appear in the real runs).
- **No personal data about recruiters is read or stored** (the data names who posted a job; it is not read, also not in the test fixtures).
- Slow on purpose: 5-11 s between pages per Chrome.
- Job links are built the way the site builds them (`/j/<title words>-<id>`); the rule matches all 50 real links of a checked page.

## Measurements (2026-10-11, 7-day window)
- 8 tech roles, 14 keywords, 22 lists (14 search + 8 tag; Business Analyst, AI Architect and Forward Deployed Engineer have no tag page). 3 Chromes read **415 jobs on 21 pages in 2.1 min**.
- **196 unique jobs kept**: found by both 44, only search 94, only tag 58; 17 dropped by the experience rule. 75 in Bengaluru, 18 with a salary, 7 work-from-home, all with the exact posting time. Posted 2026-10-05 to 2026-10-11. By role (first role to find a job keeps it): Business Analyst 63, Data Analyst 37, Architect 31, AI Engineer 28, Data Scientist 27, ML Engineer 10, Forward Deployed Engineer none.
- Only 29% (58 of 196) match a role title pattern; the rest are loose matches (a management board: "Vice President - Data Delivery" and similar). Real title filtering and role routing happen in the combined pipeline.

## Not done here (combined pipeline)
Title filtering and role routing, cross-site de-duplication, job descriptions (they are on each job page, not in the list data), the daily schedule.
