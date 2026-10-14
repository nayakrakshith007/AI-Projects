# What was done in V2 (reference for V3)

Snapshot of 2026-10-13. V3 was cloned from V2 at commit 8d2ff6c, before the work below. The documents are copied into `docs/from-v2/` so V3 can read them without leaving the folder; V2 is the earlier, single-workbook version of this project and is not part of this repository.

## In V3 already (inherited from V2 up to 8d2ff6c)

- Seven site workflows (Hirist, IIMJobs, Cutshort, Wellfound, Indeed, Naukri, LinkedIn), each with code, README, tests and a workflow HTML page.
- The `pipeline` package: lanes runner with a memory gate and stall restart, combined workbook `pipeline/output/Job_Radar.xlsx`, role routing, cross-site de-duplication, run history, the live tracker and the Performance tab (`pipeline/Pipeline_Workflow.html`), per-site Restart and Stop buttons, atomic Excel saves, tech-only scope.
- Read `docs/from-v2/v2-pipeline-README.md` for how these work. A new source in V3 should follow the same pattern as an existing site folder (see `hirist/` as the smallest example) and be registered in `pipeline/config.py` (SITES, LANES) and the page's friendly names.

## Done in V2 after the clone (NOT in V3)

All of this is on V2's branch `workspace-ui` (not merged to V2's main):

- **The Workspace UI** on top of `Job_Radar.xlsx`: Analytics (10 charts), an Excel-style Jobs table (filters, min-max experience range, saved views), an Applications board, My Profile (resume reading, Fit %, cover letters). Code in `pipeline/radar/`, page served at `/workspace` by the tracker.
- **Read-only shareable snapshot**: `python -m pipeline share --fragment` (jobs and analytics only, nothing personal), published as a private Artifact.
- 235 tests pass in V2 (V3 has the older 161).
- Design: `docs/from-v2/2026-10-13-job-radar-workspace-design.md`. Plan: `docs/from-v2/2026-10-13-job-radar-workspace.md`. Decisions and the reasons: `docs/from-v2/v2-decisions.md`.

## Things learned in V2 that matter for V3

- The workbook's Link column shows "Open"; the real URL is the cell's hyperlink. Read hyperlinks with openpyxl in normal mode (not read-only).
- Indeed links differ only by the `jk` query parameter; do not strip it when making a job key.
- The Roles cell can hold several roles separated by `;`.
- Salary text is messy (INR yearly, INR hourly, bare monthly rupees, dollars). Only lakh-per-year amounts are reliable. Work mode is filled for about 5% of jobs and skills for about 60%; there are no job descriptions.
- Fit % from title alone must be capped (it was capped at 55) or it looks falsely certain.
- Any new source should end up in a workbook with the same 16 columns (Roles, Title, Company, Location, Bengaluru, Work mode, Experience, Salary, Posted date, Sites, Skills, First seen, Link, Other links, Status, Notes) so the Workspace works with it, with a Source or Type column if the owner agrees.
- Do not use `git add -A` at the repo root: the daily run modifies tracked site output files.

## If V3 needs the Workspace code

V3 has no remote link to V2 by design. To bring the code over, copy `pipeline/radar/`, the routes in `pipeline/tracker.py`, `open_workspace.bat` and the `share` command from V2's `workspace-ui` branch, or merge that branch once the owner has approved and merged it. Ask the owner first.
