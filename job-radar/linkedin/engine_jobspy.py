"""Engine 1: LinkedIn through JobSpy, ten jobs per request, several searches in parallel, random pauses.

Why this shape: asking for many jobs in one call makes LinkedIn answer HTTP 429 after the first ten. Asking for ten
at a time (the `offset` setting) with a random pause between requests, and spreading the work over a few workers
that each use their own pause profile, gets a lot more jobs without being rate limited. A 429 makes the worker
back off for a minute or two and retry; repeated pushback ends that search, and several ends the whole run.
All of it is injectable (fetch, sleep) so it is tested without touching LinkedIn.
"""
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common.inputs import Query

from . import config

log = logging.getLogger("jobradar.linkedin")


class _Collector(logging.Handler):
    """JobSpy logs a 429 instead of raising it, and from its own helper thread. Keep (time, message) for all of them."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.events: list[tuple[float, str]] = []
        self.lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        with self.lock:
            self.events.append((record.created, record.getMessage()))

    def pushback_between(self, t0: float, t1: float) -> bool:
        with self.lock:
            return any(t0 <= t <= t1 + 0.5 and ("429" in m or "rate limit" in m.lower()) for t, m in self.events)


_collector = _Collector()


def _to_jobs(df: pd.DataFrame) -> list[dict]:
    jobs = []
    for r in df.to_dict("records"):
        url = str(r.get("job_url") or "").split("?")[0]
        if not url:
            continue
        posted = pd.to_datetime(r.get("date_posted"), errors="coerce")
        jobs.append({
            "title": str(r.get("title") or ""), "company": str(r.get("company") or ""),
            "location": str(r.get("location") or ""), "posted_text": "",
            "posted_date": posted.date() if pd.notna(posted) else None, "url": url,
        })
    return jobs


def fetch_batch(q: Query, hours: int, offset: int) -> tuple[list[dict], bool]:
    """One request of ten jobs. Returns (jobs, pushed_back). pushed_back means LinkedIn answered 429 for this call."""
    from jobspy import scrape_jobs
    root = logging.getLogger("JobSpy")
    if _collector not in root.handlers:
        root.addHandler(_collector)
    t0 = time.time()
    try:
        df = scrape_jobs(site_name=["linkedin"], search_term=q.keyword, location=config.place(q.location),
                         results_wanted=config.BATCH, hours_old=hours, offset=offset)
    except Exception as exc:
        log.warning("%s offset %s failed: %s", q.keyword, offset, type(exc).__name__)
        return [], True
    jobs = _to_jobs(df) if df is not None and len(df) else []
    return jobs, (not jobs) and _collector.pushback_between(t0, time.time())


class _Run:
    """State shared by the workers of one run."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.gave_up = 0
        self.errors: list[str] = []

    def stop(self) -> bool:
        return self.gave_up >= config.STOP_AFTER_BLOCKED_QUERIES

    def give_up(self, why: str) -> None:
        with self.lock:
            self.gave_up += 1
            self.errors.append(why)


def run_query(q: Query, hours: int, fetch, sleep, run: _Run, on_batch=None) -> list[dict]:
    """Page through one search: ten jobs at a time with this search's own random pause profile."""
    low = random.uniform(*config.DELAY_LOW)
    high = low + random.uniform(*config.DELAY_SPREAD)
    jobs: dict[str, dict] = {}
    offset, blocks = 0, 0
    for _ in range(config.MAX_BATCHES):
        if run.stop():
            break
        batch, pushed_back = fetch(q, hours, offset)
        if pushed_back and not batch:
            blocks += 1
            if blocks > config.MAX_BLOCKS_PER_QUERY:
                run.give_up(f"{q.keyword!r} in {q.location}: LinkedIn rate limit (HTTP 429), gave up at offset {offset}")
                break
            sleep(random.uniform(*config.BACKOFF))
            continue                      # same offset again
        blocks = 0
        if not batch:                     # a clean empty batch: the results have run out
            break
        new = 0
        for j in batch:
            if j["url"] not in jobs:
                jobs[j["url"]] = j
                new += 1
        if on_batch:
            on_batch(q, offset, len(batch), new)
        if new == 0:
            break
        offset += config.BATCH
        sleep(random.uniform(low, high))
    return list(jobs.values())


def search(queries: list[Query], hours: int, on_batch=None, fetch=fetch_batch, sleep=time.sleep,
           workers: int = config.WORKERS, on_query_done=None) -> tuple[list[dict], str | None]:
    """Run all queries with a small pool of workers. Returns (jobs, error). Partial results are always kept.
    `on_query_done(jobs)` is called (one call at a time) as soon as a search ends, with the jobs that were new to this run."""
    run, all_jobs = _Run(), {}
    seen, seen_lock = set(), threading.Lock()

    def task(i_q: tuple[int, Query]) -> list[dict]:
        i, q = i_q
        if i < workers:                   # stagger the first workers so they do not all start in the same second
            sleep(i * random.uniform(*config.START_STAGGER))
        found = run_query(q, hours, fetch, sleep, run, on_batch)
        # LinkedIn cards carry no experience text, so the experience rule cannot apply here; unstated is always kept.
        out = [dict(j, role=q.role, term=q.keyword, searched_location=q.location) for j in found]
        if on_query_done:
            with seen_lock:
                fresh = [j for j in out if j["url"] not in seen]
                seen.update(j["url"] for j in fresh)
                if fresh:
                    on_query_done(fresh)
        return out

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for found in pool.map(task, list(enumerate(queries))):
            for j in found:
                all_jobs.setdefault(j["url"], j)
    error = "; ".join(run.errors) if run.errors else None
    if run.stop():
        error = (error or "") + " | run stopped early: too many rate limits; rerun later"
    return list(all_jobs.values()), error
