"""Indeed through JobSpy: several searches in parallel, each with its own random pauses, backing off on pushback.

Indeed is gentler than LinkedIn: one request per search returns everything for the window, so no paging is needed.
Fetch and sleep are injectable so the logic is tested without touching Indeed.
"""
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from common.inputs import Query, experience_ok

from . import config
from .parse import to_jobs

log = logging.getLogger("jobradar.indeed")


class _Collector(logging.Handler):
    """JobSpy logs a block instead of raising it, and from its own helper thread. Keep (time, message) for all of them."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.events: list[tuple[float, str]] = []
        self.lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        with self.lock:
            self.events.append((record.created, record.getMessage()))

    def pushback_between(self, t0: float, t1: float) -> bool:
        with self.lock:
            return any(t0 <= t <= t1 + 0.5 and any(k in m.lower() for k in config.PUSHBACK_MARKERS) for t, m in self.events)


_collector = _Collector()


def fetch_query(q: Query, hours: int) -> tuple[list[dict], bool]:
    """One search. Returns (jobs, pushed_back); pushed_back means no jobs came back and Indeed logged a block."""
    from jobspy import scrape_jobs
    root = logging.getLogger("JobSpy")
    if _collector not in root.handlers:
        root.addHandler(_collector)
    t0 = time.time()
    try:
        kwargs = dict(site_name=["indeed"], search_term=q.keyword, location=config.place(q.location),
                      results_wanted=config.RESULTS_NO_WINDOW if not hours else config.RESULTS, country_indeed=config.COUNTRY)
        if hours:                      # hours = 0 means "no time filter": everything Indeed currently lists
            kwargs["hours_old"] = hours
        df = scrape_jobs(**kwargs)
    except Exception as exc:
        log.warning("%s failed: %s", q.keyword, type(exc).__name__)
        return [], True
    jobs = to_jobs(df) if df is not None and len(df) else []
    return jobs, (not jobs) and _collector.pushback_between(t0, time.time())


class _Run:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.gave_up = 0
        self.errors: list[str] = []
        self.dropped_experience = 0

    def stop(self) -> bool:
        return self.gave_up >= config.STOP_AFTER_BLOCKED_QUERIES

    def give_up(self, why: str) -> None:
        with self.lock:
            self.gave_up += 1
            self.errors.append(why)


def run_query(q: Query, hours: int, fetch, sleep, run: _Run) -> list[dict]:
    """One search, retried after a back-off when Indeed pushes back."""
    blocks = 0
    while not run.stop():
        jobs, pushed_back = fetch(q, hours)
        if pushed_back and not jobs:
            blocks += 1
            if blocks > config.MAX_BLOCKS_PER_QUERY:
                run.give_up(f"{q.keyword!r} in {q.location}: Indeed pushed back (HTTP 403/429), gave up")
                return []
            sleep(random.uniform(*config.BACKOFF))
            continue
        return jobs
    return []


def search(queries: list[Query], hours: int, on_query=None, fetch=fetch_query, sleep=time.sleep,
           workers: int = config.WORKERS) -> tuple[list[dict], str | None, dict]:
    """Run all searches with a small pool of workers. Returns (jobs, error, stats). Partial results are always kept."""
    run, all_jobs, fetched = _Run(), {}, 0

    def task(i_q: tuple[int, Query]) -> tuple[Query, list[dict]]:
        i, q = i_q
        if i < workers:
            sleep(i * random.uniform(*config.START_STAGGER))
        found = run_query(q, hours, fetch, sleep, run)
        low = random.uniform(*config.DELAY_LOW)       # each search draws its own pause profile
        sleep(random.uniform(low, low + random.uniform(*config.DELAY_SPREAD)))
        return q, found

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for q, found in pool.map(task, list(enumerate(queries))):
            kept = 0
            for j in found:
                fetched += 1
                if not experience_ok(j["experience"], q.min_experience):
                    run.dropped_experience += 1
                    continue
                if j["url"] not in all_jobs:
                    all_jobs[j["url"]] = dict(j, role=q.role, term=q.keyword, searched_location=q.location)
                    kept += 1
            if on_query:
                on_query(q, len(found), kept)
    error = "; ".join(run.errors) if run.errors else None
    if run.stop():
        error = (error or "") + " | run stopped early: too many pushbacks; rerun later"
    return list(all_jobs.values()), error, {"fetched": fetched, "dropped_experience": run.dropped_experience}
