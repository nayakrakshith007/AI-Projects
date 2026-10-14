# Naukri workflow

Reads the newest Naukri jobs for search terms with a real, visible Chrome and a saved session, and writes them into `naukri/output/Naukri.xlsx` (tab "Naukri"). Free, no tokens, no login.

## Input
One shared file for every site: `job-radar-V3/input.csv` with columns Role, Keywords (semicolon-separated), Experience (minimum years, 0 = no filter) and Location (semicolon-separated). Then `python -m naukri search` (all roles) or `--role "AI Engineer"`; `--hours N` overrides the automatic window. Loader and experience rule: `common/inputs.py`.

## Time window (no day is lost)
`--hours` is optional. By default the run reads everything posted **since midnight of the latest posted date already read** (state file `output/state.json`, never less than 24 h, at most 30 days). Example: latest read date 2026-10-11 and a run at 09:00 on 2026-10-12 uses 33 h; if the PC was off for two days the next run uses 81 h and catches up. The same day is read again on purpose (late postings); known jobs are skipped by link. The date only moves forward after a run that finished **without an error** and saved to the main workbook, so a stopped or partial run never skips a day. Before a state file exists the newest `Posted date` in the workbook is used. An explicit `--hours N` always wins (Naukri's own filter rounds the window up to 1, 3, 7, 15 or 30 days). Code: `common/window.py`.

## Output (all in `naukri/output/`)
`Naukri.xlsx` (result), `runs/naukri_*.jsonl` (raw backup per run), `last_run.log`.

## Visual explainer
Open `Naukri_Workflow.html` in a browser: an n8n-style flow; click any node for the technical detail.

## Flow
1. **check** (once in a while): opens Chrome on Naukri; you pass the human check by hand; the session is saved in `data/naukri_profile`. Double-click `check.bat`.
2. **search**: for each term, open `<term>-jobs-in-india[-N]?jobAge=D`, scroll like a reader, parse the cards, go to the next page until a page adds no new jobs.
3. **excel**: new jobs are added by link; known jobs get their posted label refreshed; your Status and Notes are kept. If Excel has the file open, a timestamped copy is written.

## Files
| File | Job |
|---|---|
| `config.py` | URLs, pauses, selectors, limits |
| `session.py` | Chrome with the saved profile; the human-check helper |
| `search.py` | paging loop, scrolling, human-check detection |
| `parse.py` | card HTML to dict (pure, tested) |
| `excel.py` | merge into the workbook |
| `notify.py` | Windows pop-up when you are needed |
| `__main__.py` | command line |
| `Naukri_Workflow.html` | visual explainer |
| `tests/` | parser and Excel tests on a saved real card |

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m naukri check
.venv\Scripts\python -m naukri search --role "AI Engineer" --hours 24
.venv\Scripts\python -m pytest naukri/tests
```

## Rules
- Never solve or evade the human check. If it shows, the run stops, keeps what it has, shows a pop-up and says so.
- Slow on purpose: random 9-20 s between pages, 25-55 s between terms.
- No login and no credentials in code. Only you pass checks, in the visible window.

## Columns
Title, Company, Experience, Location, Skills, Snippet, Posted, Posted date, Search term, First seen, Link, Status (dropdown), Notes.

## Not done yet
- Full job descriptions (not required).
- Joining the combined pipeline (done at the end).
- Role routing and the 5+ years filter (done in the combined pipeline).
