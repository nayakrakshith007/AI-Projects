# Engineering decisions

The main choices behind Job Radar V3, each with the reason and what was rejected. Numbers come from real runs during development.

## 1. One reader per source type, not one scraper per site

About 200 sources would mean about 200 scrapers. Most sites share a few platforms (Greenhouse, Ashby, Lever, Workday, Eightfold, SuccessFactors and others), so one reader per platform covers many companies, and adding a company is a one-line change in `sources.csv`.
**Rejected:** a scraper per site (too much code to keep alive).

## 2. Read each site with the cheapest method that works

Order: public feed or API, then the platform's own API, then the JSON a career page calls itself (found once during development, then replayed with plain HTTP), then a real browser.
A probe showed 16 sources already returned jobs through plain HTTP. Plain HTTP needs about 50 MB in total. A Chrome per site needs 300 to 500 MB each, which does not fit a 16 GB laptop. A full run of 80 API sources took about 3 minutes.
**Rejected:** Playwright for everything (memory, speed, fragility).

## 3. No LLM and no tokens in the daily run

Browser tools and AI assistants were used only during development, to discover endpoints and write tests. The daily run is plain code, so it is free and repeatable.
A comparison on one site showed the Claude browser needed about 3 steps and 1,200 tokens to spot the data, and the Playwright CLI needed about 5 steps and 1,800 tokens but exposed the request headers that made a replay possible. Conclusion: use the first to look, the second to capture, and neither in production.

## 4. Never solve or hide a human check

A source that answers with a CAPTCHA or a bot challenge is marked "needs you" and skipped. Fourteen such sites were parked with the reason recorded. Sites that require a login or a paid plan are not scraped.
**Rejected:** stealth plugins and CAPTCHA solvers (against the project's rules, and brittle).

## 5. A source's health is more than its job count

Every source ends a run as done, empty, broken, failed or "needs you". A reader returns how many items it scanned, so a page with no matching job today (a true zero) is told apart from a page that changed and now yields nothing. Rules: retry once, flag a source that is empty twice in a row (the canary), keep the previous list when a source suddenly returns under 30% of its usual size, and flag a source where over half of the jobs have no place.

## 6. Recall check on keywords

With 4 search keywords, Accenture returned only 27% of the jobs that matched the roles, Citi 60% and Microsoft 70%. One shared list of 26 role keywords, with an early stop per keyword, raised matched jobs from 1,351 to 1,755 (+30%). The full run grew from about 4 to about 9 minutes, and the workbook build was cut from 160 to 50 seconds by not re-styling the unmatched tab cell by cell.

## 7. Failures that were found and fixed

- A locked `run_state.json` (the progress page reads it every 2 seconds) crashed a full run with "Access denied". File replaces now retry, and a failed status write is skipped.
- A batch discovery job hung for 56 minutes because a timeout killed only the shell, not the browser processes holding the pipes. The fix is a hard timeout that kills the whole process tree, a cap on response bodies per site, and a per-site limit. Lesson: every long background job needs a watchdog and a "last progress" check.
- A broad name-guessing scan of Workday tenants ran past 14 minutes without finishing, so it was cut back to known tenants.
- Two slug guesses were different companies than expected and were rejected rather than kept.

## 8. The browser lane was tested and not built

All 59 remaining sites were opened in a real browser through the Playwright library. 50 rendered, 6 were refused at the connection level (bot protection, not bypassed), and 3 were dead. No new job feed turned up. A lane would cost 300 to 500 MB per run, break easily and unlock almost nothing, so the evidence said to skip it. The probe scripts stay in `discovery/` for later.

## 9. State survives rebuilds

Status, Notes and First seen are carried from one workbook build to the next, matched by job link, so edits made by hand are never lost. If Excel has the workbook open, the build writes a timestamped copy instead of crashing.

## 10. Local-only progress page

The page binds to 127.0.0.1 only, checks the Host header, and requires a custom header and a local origin on every POST. A fixed list of "open this file" targets is the only file access; the page never runs a `.bat` file.

## 11. One scheduler, one progress page, one output

The seven job-board workflows (LinkedIn, Naukri, Indeed and others) run inside the same system as the API sources, so there is one scheduled task, one progress page and one workbook. A one-time import carries earlier Status, Notes and First seen values forward (2,711 links).
**Rejected:** reading the old workbook on every build (slow), and keeping the boards as a separate manual run (two schedulers, two views).

## 12. Tests without the network

Every reader is tested against saved page and API fixtures. 354 tests run offline in about a minute. Tests never write to real output files: an early bug let a test overwrite the run log, and the fix was to look up file paths at call time and isolate them in fixtures.
