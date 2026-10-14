# Hirist workflow (tech roles only)

Reads Hirist with **two methods at once**, compares them, and writes the jobs inside the time window into `hirist/output/Hirist.xlsx` (tab "Hirist"). Free, no tokens, **no login**, no Docker or Firecrawl.

## Input
The shared file `job-radar-V3/input.csv`. Only **tech roles** are searched (Experience above 0; `--include-non-tech` overrides). Keywords are searched as they are by the search method; for the tag method `tags.csv` maps a keyword to Hirist tag pages (`-` = no tag page).

## The two methods
| | search method | tag method |
|---|---|---|
| Page | `/search/<keyword>-jobs?...&posting=N&page=P` | `/k/<tag>-jobs?posting=N&page=P` |
| Data | the JSON the page loads (`gladiator.hirist.tech/job/search`), read with `page.expect_response` | server-rendered HTML cards (BeautifulSoup) |
| Dates | exact (`createdTimeMs`, IST) | relative label ("Posted 3 days ago"), estimated |
| Experience | numbers (`min`, `max`) | text "10 - 12 yrs", parsed to numbers |
| Covers | every keyword (also those with no tag) | only keywords with a Hirist tag |
| Extra fields | applicants, views, company rating and reviews, all locations, work-from-home | skills chips |
| Accuracy | looser (also returns unrelated jobs) | tighter |

Both use **Hirist's own date filter in the URL** (`posting=1|3|7|15|30` days, applied on its server): Data Scientist has 887 jobs in all but 44 in the last week, so only a few pages per keyword are read.

**Comparison, first run (2026-10-11), scored against the old project's validated role title patterns:** search found 243 role-matching jobs (90% recall, 54% precision), tag found 248 (92% recall, 68% precision), 223 by both. 23 relevant jobs were found only by tag (for example "Vice President - Data Science", "Research Scientist"), 18 only by search (13 of them Architect jobs, because Hirist has no Solutions Architect tag). **Run both and keep the union** (about 6 minutes). The "Found by" column says which method found each job; `output/compare_methods.csv` has the per-role table of every run.

## Time window (no day is lost)
`--hours` is optional. By default the run reads **since midnight of the latest posted date already read** (`output/state.json`, at least 24 h, **at most 7 days**; see `common/window.py`). Hirist's `posting` filter is rounded up to 1, 3, 7, 15 or 30 days; the exact window is then applied to the exact posting time (search) or the estimated date (tag). The date only moves forward after a run that finished without an error.

## A pool of Chromes sharing one page queue
Page 1 of each list says how many pages there are (JSON `totalPages`, or "N Job Vacancies" in the title); pages 2..N go into one queue and up to 4 Chromes (`--workers`, at most 6) pull from it. **Every Chrome starts with a fresh browser state** (`browser.new_context()`), because Hirist remembers filters (experience, location, date) between visits in the same browser: a test showed an old experience filter leaking into a later page. Chromes start 3-8 s apart and pause 5-11 s before each page. A human check in any Chrome stops all of them (they keep what they read); if every Chrome fails the run ends instead of hanging.

## Experience and location
Hirist gives numbers, so the rule from `input.csv` is exact: a job stays if its maximum years reaches the role's minimum or it states none. Hirist is an India site, so there is no country filter; a **Bengaluru** column marks Bengaluru/Bangalore jobs.

## Output (all in `hirist/output/`)
`Hirist.xlsx` (result, 25 columns: Title, Company, Role, Experience, Exp min, Exp max, Location, Bengaluru, Work mode, Salary, Skills, Posted, Posted date, Posted at, Applicants, Views, Company rating, Reviews, Found by, Title matches, Search term, First seen, Link, Status, Notes), `compare_methods.csv`, `runs/hirist_*.jsonl` (raw backup, written before Excel), `last_run.log`.

## Visual explainer
Open `Hirist_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## Files
| File | Job |
|---|---|
| `config.py` | URLs, the posting filter, pauses, limits |
| `tags.csv` | keyword to Hirist tag pages |
| `session.py` | Chrome with a fresh context; human-check helper |
| `search.py` | plan, page queue and Chrome pool, window, experience, merge, compare |
| `parse.py` | search JSON and tag cards to job dicts (pure, tested) |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up |
| `__main__.py` | command line |
| `tests/` | parser tests on a saved real page and real JSON; queue, merge, window, human-check and Excel tests |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m hirist search
.venv\Scripts\python -m hirist search --hours 168 --method both
.venv\Scripts\python -m hirist search --role "AI Engineer" --method search
.venv\Scripts\python -m hirist check
.venv\Scripts\python -m pytest hirist/tests
```
Close `Hirist.xlsx` in Excel before a run (otherwise a timestamped copy is written).

## Rules
- Public pages only. Never log in. Never solve or hide a human check: the run stops, keeps what it has and shows a pop-up; `check_hirist.bat` opens the window (it did not appear in the first run, 103 pages).
- **No personal data about recruiters is read or stored** (the JSON names the recruiter; it is dropped, also in the test fixtures).
- Slow on purpose: 5-11 s between pages per Chrome.

## Measurements (2026-10-11, 7-day window)
- 8 tech roles, 14 keywords, 22 lists (14 search + 8 tag; Forward Deployed Engineer, AI Architect and Solutions Architect have no tag page). 4 Chromes read **103 pages, 1,875 jobs in 6.3 min** (25-27 pages each). Old method (Firecrawl, first 3 pages per role, no date filter): about 144 jobs over several runs.
- **417 unique jobs kept**: found by both 178, only search 150, only tag 89; 35 dropped by the experience rule. 200 in Bengaluru, 62 with a salary, 328 with the exact posting time, 33 work-from-home. Posted 2026-10-05 to 2026-10-11. By role (first role to find a job keeps it): ML Engineer 173, AI Engineer 87, Architect 61, Data Scientist 54, Data Analyst 23, Business Analyst 16, Forward Deployed Engineer 3.
- About half (202 of 417) match a role title pattern; the rest are loose matches (search is the looser). The "Title matches" column is only a rough flag; real title filtering and role routing happen in the combined pipeline.

## Not done here (combined pipeline)
Title filtering and role routing, cross-site de-duplication, full job descriptions (Hirist job pages), the daily schedule.
