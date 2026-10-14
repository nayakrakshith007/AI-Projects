# Job Radar: the storyboard

A two-minute tour in six frames. Each frame answers one question.

## 1. What hurts?

<img src="storyboard/frame-1.svg" alt="Frame 1: the problem" width="100%">

Looking for a job means checking dozens of boards and career pages. Every site has its own layout and breaks without warning. Checking by hand does not scale, and writing one scraper per site does not either.

## 2. What is the idea?

<img src="storyboard/frame-2.svg" alt="Frame 2: the idea" width="100%">

Read each site with the cheapest method that works: a public feed or API, then the hiring platform's API, then the JSON the page itself calls (found once during development), and a real browser only as the last resort. Most companies sit on a few shared platforms, so one reader per platform covers many companies.
*Why:* plain HTTP needs about 50 MB in total, a Chrome per site needs 300 to 500 MB each. See [decision 2](engineering-decisions.md#2-read-each-site-with-the-cheapest-method-that-works).

## 3. What happens at 08:30?

<img src="storyboard/frame-3.svg" alt="Frame 3: the morning run" width="100%">

The scheduler starts the runner. It reads every source with 8 parallel workers and at most one request per host per second. It uses no LLM, no logins and no stealth tricks.

## 4. How do I know it did not silently break?

<img src="storyboard/frame-4.svg" alt="Frame 4: trust" width="100%">

Every source ends a run as done, empty, broken, failed or "needs you". A reader reports how many items it scanned, so a page with no match today is told apart from a page that changed. A human check (CAPTCHA) is never solved or hidden; the source is flagged for you.
*Why:* a scraper that quietly returns nothing is worse than one that fails loudly. See [decision 5](engineering-decisions.md#5-a-sources-health-is-more-than-its-job-count).

## 5. What do I get?

<img src="storyboard/frame-5.svg" alt="Frame 5: the payoff" width="100%">

A live progress page (start, stop, re-run one source), an analytics dashboard, and one Excel workbook. Status, Notes and First seen survive every rebuild, so your own edits are never lost.

## 6. Why should I trust the code?

<img src="storyboard/frame-6.svg" alt="Frame 6: the proof" width="100%">

354 tests run offline against saved fixtures. Twelve engineering decisions are written down with the reason and the rejected alternatives, including the bugs that were found and fixed along the way. Read them in [engineering-decisions.md](engineering-decisions.md).

---

[Back to the project README](../README.md)
