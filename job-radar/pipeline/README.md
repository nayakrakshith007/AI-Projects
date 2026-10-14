# Pipeline: all site workflows, one combined workbook, one daily schedule

`python -m pipeline run` starts the seven site workflows in four lanes (so only about 8 Chromes are open at once), waits for them, then builds **`pipeline/output/Job_Radar.xlsx`**: title-filtered, routed to roles, de-duplicated across sites and ranked (Bengaluru first). A Windows Task Scheduler task runs it every day at **09:00**. Free, no tokens, no logins.

## The daily run
1. **Task Scheduler** starts `python -m pipeline run` at 09:00, as you, on your desktop (so Chrome windows and pop-ups can show). If the PC was off or asleep at 09:00 it **runs as soon as the PC is available** (`StartWhenAvailable`). A second start while one is still running is ignored.
2. **Four lanes run side by side** (sites inside a lane run one after another), each site as its own process with its own log (`output/logs/<date_time>/<site>.log`): `linkedin` | `indeed` | `naukri` | `hirist > iimjobs > cutshort > wellfound`. The three long single-Chrome sites start at once; the short, wider ones take turns, so the peak is about 8 Chromes (a first all-at-once run opened about 100 and used all 16 GB). The PC is kept awake while the run is going. Expect about 35 to 40 minutes, set by LinkedIn.
3. **Each site chooses its own time window** from its saved latest posted date (`<site>/output/state.json`): from midnight of the latest posted date it has fully read to now, at least 24 h. A missed day is never lost; a site that stopped with an error does not move its date.
4. **A site that stops** (a human check, a rate limit) keeps what it read and shows its own pop-up; the pipeline records `needs you` and carries on with the others. A site still running after 90 minutes, is stopped (its saved results stay). A site whose log has not changed for **90 seconds** is stuck: it is stopped and **started again at once** (up to 2 times, each with its own log `<site>_rerun1.log`); after that it is marked **stalled**. A site starts only when 1 GB of memory is free (it waits up to 20 minutes, then is skipped). A stalled, timed-out, failed or skipped site gets **one more try, alone, at the end**; a site that needs you is not retried. Chromes the workflows left behind are stopped at the end (your own Chrome is never touched). The code never solves or hides a check; a `check_<site>.bat` in the project root opens a visible Chrome for you to pass it by hand.
5. **Build** (`python -m pipeline build` does just this step): read all seven site workbooks, route, de-duplicate, rank, write `Job_Radar.xlsx`.
6. **A message box** at the end says how many new jobs came in today (and how many in Bengaluru), which sites need you, and the file name. `last_run.json` has the same in detail.

## What the build does
- **Title filtering and role routing** (`route.py`): each job title is tested against the old project's validated role title patterns (`role_patterns.csv`, 15 roles). A job can fit more than one role (an AI Architect is an Architect and an AI Engineer). A title that fits none goes to the `Unmatched` tab, so nothing disappears silently.
- **De-duplication across sites** (`dedupe.py`): the same link, or the same normalised title at the same company at an overlapping place. Company names are compared without legal suffixes and a whole-word prefix counts as the same ('Tredence' = 'Tredence Analytics Solutions Private Limited'). A job with no company is never merged by title. Places overlap when they share a city; 'India' or 'Remote' overlaps with anything. Each field of the merged row comes from the richest site that has it; the row lists every site and keeps the other links. A known limit: a company that posts several identical openings in one city shows them as one row.
- **Ranking** (`dedupe.rank_key`): Bengaluru first, then remote, then the rest of India; newest first inside each.
- **Tabs**: `New today` (first seen today), `All` (every matched job), one tab per role (15), `Unmatched`.
- **Your edits survive**: Status, Notes and First seen are kept between builds, matched by any of the job's links. Edit them in any tab; if two tabs disagree the `All` tab wins. If Excel has the file open a timestamped copy is written and the screen says so.

## Columns
Roles, Title, Company, Location, Bengaluru, Work mode, Experience, Salary, Posted date, Sites, Skills, First seen, Link, Other links, Status, Notes. (Full descriptions and all site-specific fields stay in the site workbooks.)

## The live tracker (start a run and watch it)
Double-click **`start_tracker.bat`** (or `python -m pipeline tracker`). It opens `http://127.0.0.1:8770`, a page that only works on this PC. The page is the dark **pipeline diagram** (`Pipeline_Workflow.html`) with the tracker built in: a **Start workflow** button in the toolbar, a live status pill, three tabs (**Workflow**: the diagram, whose nodes light up as the run moves; **Live run**; **Performance**). Opened straight from the file it still works as a static diagram, and hands over to the server if that is running. The first, plainer tracker page is kept at `http://127.0.0.1:8770/classic` (`Tracker.html`).
- **Start workflow** runs `python -m pipeline run` in the background (tick "Tech roles only" / "One site at a time"); **Stop** ends it. A run keeps going if you close the page or the tracker window.
- It shows each site live: waiting, reading, done, needs you, restarting, with searches done out of planned, new jobs, jobs in the workbook, time and the last log line. Click a site to see its last 80 log lines.
- Below: the combine-and-build step with the final numbers, a timeline of events, and the problems from `errors.log`.
- It also shows a run started by the 09:00 task or the command line, because the pipeline writes its live state to `pipeline/output/run_state.json`.
- **Performance tab:** the history of every run (`pipeline/output/history.jsonl`, one line per site per run, written at the end of each run and when a run is stopped). It shows, per site: runs, share of clean runs, median / fastest / slowest / p90 minutes, last run, average new jobs per run and per minute, restarts and a trend line; per run: wall time, site time, parallelism (site time / wall time), new jobs, slowest site, peak Chromes and lowest free memory; and a bar chart (Gantt) of any run. Filters: role scope, how the run was started, clean runs only. The runs of 2026-10-12 before the history existed were rebuilt from their logs (`python -m pipeline history --backfill`), and `pipeline/experiments.json` holds the hand-run timing tests. Durations depend on the time window and the role scope, so compare like with like; runs stopped by hand are kept but left out of timing and reliability.
- Safety: the server listens on 127.0.0.1 only, checks the Host header, and only accepts Start/Stop from its own page.

## Commands (from `job-radar-V3`)
```
.venv\Scripts\python -m pipeline run
.venv\Scripts\python -m pipeline run --only hirist iimjobs cutshort
.venv\Scripts\python -m pipeline run --skip linkedin --no-popup
.venv\Scripts\python -m pipeline build
.venv\Scripts\python -m pipeline schedule
.venv\Scripts\python -m pipeline schedule --time 08:30
.venv\Scripts\python -m pipeline schedule --show
.venv\Scripts\python -m pipeline schedule --remove
.venv\Scripts\python -m pytest pipeline/tests
```
You can also start the task from the Task Scheduler app ("Job Radar V2 Daily") or run `Start-ScheduledTask 'Job Radar V2 Daily'` in PowerShell.

## Files
| File | Job |
|---|---|
| `config.py` | the seven sites (workbook, options, priority), lanes, limits, paths, task name and time |
| `runner.py` | run the lanes, one log per site, memory wait, stall and time limits, one retry, report how each ended |
| `load.py` | read a site workbook into the common job format (by header name, links from hyperlinks) |
| `route.py` + `role_patterns.csv` | title filtering and role routing |
| `dedupe.py` | de-duplication and ranking |
| `build.py` | the combined workbook, keeping your edits |
| `schedule.py` | register, show or remove the Windows task |
| `notify.py` | the message box at the end |
| `state.py` | the live state of a run (`output/run_state.json`) |
| `tracker.py` + `Tracker.html` | the local web server and the live tracker page (Live and Performance tabs) |
| `history.py` | the run history, backfill from old logs, and the Performance numbers |
| `monitor.py` | samples free memory and Chrome count during a run |
| `__main__.py` | command line |
| `tests/` | routing, de-duplication, ranking, workbook build with edits kept, runner (fake sites: ok, needs you, failed, timed out), scheduler script |

## Rules
Everything stays free and local: no Claude tokens, no logins, no stealth. Close `Job_Radar.xlsx` in Excel before the 09:00 run, or you get a timestamped copy. Close the site workbooks too (a site writes a timestamped copy if its file is open).

## Not in the pipeline yet
Ayurveda and government-site readers (CCRAS, AIIA, NIA, UPSC, state commissions), Glassdoor, company career pages, remote-job feeds; full job descriptions in the combined file.
