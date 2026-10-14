# LinkedIn workflow

Reads the newest **public** LinkedIn jobs for the roles in `input.csv` and writes them into `linkedin/output/LinkedIn.xlsx` (tab "LinkedIn"). Free, no tokens, **no login**.

## Input
The shared file `job-radar-V3/input.csv`: Role, Keywords (semicolon-separated), Experience, Location. Experience is not applied here (LinkedIn cards carry no experience text; unstated is kept). Loader: `common/inputs.py`.

## Time window (no day is lost)
`--hours` is optional. By default the run reads everything posted **since midnight of the latest posted date already read** (state file `output/state.json`, never less than 24 h, at most 30 days). Example: latest read date 2026-10-11 and a run at 09:00 on 2026-10-12 uses 33 h; if the PC was off for two days the next run uses 81 h and catches up. The same day is read again on purpose (late postings); known jobs are skipped by link. The date only moves forward after a run that finished **without an error** and saved to the main workbook, so a stopped or partial run never skips a day. Before a state file exists the newest `Posted date` in the workbook is used. An explicit `--hours N` always wins. Code: `common/window.py`.

## Output (all in `linkedin/output/`)
`LinkedIn.xlsx` (result), `runs/linkedin_*.jsonl` (raw backup per run, written before Excel), `last_run.log`.

## Visual explainer
Open `LinkedIn_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## Engines
1. **jobspy (default)** - `engine_jobspy.py`. LinkedIn's public guest API through JobSpy, **ten jobs per request** (`offset` 0, 10, 20 ...), **three searches in parallel** (`ThreadPoolExecutor`), each search with **its own random pause profile** (low 8-15 s, spread +10-20 s) and a staggered start. On HTTP 429 (logged by JobSpy, detected by a logging handler) it waits 60-120 s and retries the same page; after 2 pushbacks that search gives up; after 3 searches give up the whole run stops and keeps partial results.
2. **browser (fallback)** - `search.py`, `parse.py`, `session.py`. Real Chrome on the public search pages, scrolling and pressing "See more jobs", one search at a time. If LinkedIn shows a wall, the run stops with a pop-up; `check_linkedin.bat` opens the window (do not sign in).

## Files
| File | Job |
|---|---|
| `config.py` | all settings for both engines |
| `engine_jobspy.py` | parallel, paced JobSpy engine (injectable fetch/sleep, tested) |
| `search.py` / `parse.py` / `session.py` | browser fallback engine |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up |
| `__main__.py` | command line |
| `LinkedIn_Workflow.html` | visual explainer |
| `tests/` | engine, parser and Excel tests |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m linkedin search
.venv\Scripts\python -m linkedin search --role "AI Engineer" --hours 48 --workers 2
.venv\Scripts\python -m linkedin search --engine browser
.venv\Scripts\python -m pytest linkedin/tests
```
Close `LinkedIn.xlsx` in Excel before a run (otherwise a timestamped copy is written).

## Rules
- Public data only. Never log in: automated use of an account breaks LinkedIn's terms and risks the account.
- Never solve or hide a check or a rate limit: slow down, back off, stop.
- Pauses are random; three workers by default (more raises the chance of HTTP 429).

## Not done here (combined pipeline)
Job descriptions and experience, title filtering and role routing (LinkedIn's keyword match is loose), India/Bengaluru ranking, cross-site de-duplication, the daily schedule.

## Measurements
- JobSpy, one call asking for 100 jobs: 10 jobs, then HTTP 429.
- JobSpy, ten per request, 3 parallel searches, random 15-35 s pauses: 15 requests, 122 unique jobs, 162 s, no 429.
- Full 15-role run (2026-10-11, 24 h window, 44 searches, 3 workers): **1,096 unique jobs in 30.9 min** (555 posted today, 541 yesterday), about 250 requests, 33 HTTP 429 hits that were backed off and retried, no search gave up. Log: `output/last_run.log`.
- First search to find a job keeps it, so many AI jobs sit under ML Engineer; the combined pipeline re-routes by title.
