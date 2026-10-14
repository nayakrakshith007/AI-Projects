# Indeed workflow

Reads the newest Indeed India jobs for the roles in `input.csv` and writes them into `indeed/output/Indeed.xlsx` (tab "Indeed"). Free, no tokens, no login, no browser.

## Input
The shared file `job-radar-V3/input.csv`: Role, Keywords (semicolon-separated), Experience (minimum years, 0 = no filter), Location (semicolon-separated). Loader and experience rule: `common/inputs.py`. Indeed sends descriptions, so experience is read from the title or description and the minimum is applied (unstated is kept).

## Time window (no day is lost)
`--hours` is optional. By default the run reads everything posted **since midnight of the latest posted date already read** (state file `output/state.json`, never less than 24 h, at most 30 days). Example: latest read date 2026-10-11 and a run at 09:00 on 2026-10-12 uses 33 h; if the PC was off for two days the next run uses 81 h and catches up. The same day is read again on purpose (late postings); known jobs are skipped by link. The date only moves forward after a run that finished **without an error** and saved to the main workbook, so a stopped or partial run never skips a day. Before a state file exists the newest `Posted date` in the workbook is used. An explicit `--hours N` always wins; `--hours 0` means no time filter at all (first backlog run only). Code: `common/window.py`.

## Output (all in `indeed/output/`)
`Indeed.xlsx` (result), `runs/indeed_*.jsonl` (raw backup per run, written before Excel), `last_run.log`.

## Visual explainer
Open `Indeed_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## How it works
`engine.py`: JobSpy (`site_name=["indeed"]`, `country_indeed="India"`, `hours_old`), **three searches in parallel** (`ThreadPoolExecutor`), each search with **its own random pause profile** (3-7 s low, +4-9 s) and a staggered start. One request chain per search returns everything for the window (no paging). If Indeed pushes back (403/429 logged by JobSpy, detected by a logging handler) the worker waits 60-120 s and retries; after 2 pushbacks that search gives up; after 3 searches give up the run stops and keeps partial results.
`parse.py`: rows to job dicts (link kept whole: `viewjob?jk=...`) and everything that can be read from the text: `experience_from_text()` (ranges, plus, minimum, "2 to 4 years", "Experience: 3-5", freshers; title trusted, description needs "experience" nearby), `qualifications()` (BAMS, MD/MS Ayurveda, B.Pharm, M.Sc, MBA, PhD ... 21 groups), `detect_skills()` (about 120 tech, clinical/pharma/regulatory and Ayurveda terms), `emails_in()`, `phones_in()`, walk-in, number of openings, and `salary_fields()` (shown text plus numbers per month in INR). Company details, the direct apply link and the full description come straight from Indeed.

## Files
| File | Job |
|---|---|
| `config.py` | all settings |
| `engine.py` | parallel, paced JobSpy engine (injectable fetch/sleep, tested) |
| `parse.py` | rows to jobs; experience from text |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up |
| `__main__.py` | command line |
| `Indeed_Workflow.html` | visual explainer |
| `tests/` | parser, engine and Excel tests |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m indeed search
.venv\Scripts\python -m indeed search --role "AI Engineer" --hours 48 --workers 2
.venv\Scripts\python -m pytest indeed/tests
```
Close `Indeed.xlsx` in Excel before a run (otherwise a timestamped copy is written).

## Columns in Indeed.xlsx (33)
Title, Company, Role, Experience, Exp min, Exp max, Qualification, Location, Work mode, Job type, Salary, Salary min /month, Salary max /month, Posted date, Skills, Walk-in, Openings, Emails, Phones, Rating, Reviews, Industry, Company size, Company info, Search term, First seen, Link, Status, Notes, Apply link, Company website, Company page, Description (full text, up to 32,000 characters). Role, Status, Notes and First seen are yours and are never overwritten; every other column is filled in or refreshed when a job is seen again.

## Rules
Public data only, no login. Never hide or work around a block: slow down, back off, stop.

## Measurements (2026-10-11, 24 h window)
- One search for "Data Scientist": 13 jobs whether 50 or 150 were requested.
- Full run, 15 roles, 44 searches, 3 workers: **94 unique jobs in 2.2 min** (51 posted yesterday, 43 today); 196 fetched, 15 dropped by the experience rule; no pushback. 29 of 44 searches found nothing (Ayurveda, drug and pharma-regulatory roles: Indeed barely carries them; they need the official sites). 60 of 94 state experience, 36 show a salary, 11 are remote.

- **First run without a time filter** (`--hours 0`) for the 7 non-tech roles (30 searches, 3 workers): fetched 2,717, kept **2,208 unique jobs in 1.9 min**, no pushback. The 24-hour window had hidden almost everything for these roles: for example "Ayurvedic Doctor" 83 jobs and "BAMS Doctor" 201, against nearly none in 24 h. By role: Clinical Research 1,097, Drug and Regulatory 584, Ayurveda Consultant 260, Ayurveda Pharma 161, Drug Inspector 60, Ayurveda Research 43, Ayurveda Faculty 4. 1,850 of the jobs are older than 7 days (oldest Nov 2024). Three searches hit the 300-job cap (Regulatory Affairs, Drug Safety and one more), so they may have more. Many are loose matches (title filtering happens in the combined pipeline).
- **Rule for the schedule:** `--hours 0` is for a first backlog run only. The daily automation uses the default `--hours 24` for all roles.

- **Details run (2026-10-11):** the cap for runs without a time filter is now 1,000 per search (the largest search found 734, so none hit it). Non-tech roles, no time filter: fetched 3,734, **2,993 unique jobs in 3.0 min** (810 new). Tech roles, last 24 h: 76 kept, 33 dropped by the 5+ years rule. The workbook now has **3,105 jobs** (4.7 MB). Fill rates: description 98%, company page 92%, skills 81%, qualification 71%, experience 69%, apply link 58%, rating 54%, company website 45%, company info 44%, company size 42%, salary 40%, emails 11%, industry 8%, phones 6%, walk-in 1%, openings 1%.
- Indeed never returns skills, experience, job level or vacancy count as fields, so those are read from the description text.

## Not done here (combined pipeline)
Title filtering and role routing, India/Bengaluru ranking, cross-site de-duplication, full descriptions, the daily schedule.
