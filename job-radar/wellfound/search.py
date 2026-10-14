"""Read Wellfound role pages with a pool of Chromes that share one queue of pages.

Wellfound has no time filter and does not sort by date (page 1 mixes '2 days ago' with '3 years ago'), so every page of
a role list has to be read. Pages of one list are independent (?page=N): page 1 is read first, it says 'Page 1 of 24', and
pages 2..24 go into a shared queue that all Chromes pull from, so a long list is spread over every Chrome instead of
making one Chrome the slowest. The window (if any), the India location rule and the experience rule are applied afterwards.
"""
import csv
import queue
import random
import threading
import time
from datetime import datetime, timedelta
from typing import NamedTuple

from common.geo import is_bengaluru
from common.inputs import Query, experience_ok

from . import config
from .parse import KEEP_LOCATIONS, classify_location, is_generic_page, page_title, parse_page, total_pages
from .session import HumanCheckPending, Session


class Target(NamedTuple):
    role: str
    keyword: str
    slug: str
    kind: str            # "india" or "remote"


def _pause(rng: tuple[float, float]) -> None:
    time.sleep(random.uniform(*rng))


def load_slugs(path=config.SLUGS_FILE) -> dict[str, str]:
    """keyword (lower case) -> Wellfound role slug; '-' means the keyword has no Wellfound page."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["keyword"].strip().lower(): r["slug"].strip() for r in csv.DictReader(f) if r.get("keyword")}


def plan(queries: list[Query], slugs: dict[str, str] | None = None) -> tuple[list[Target], list[str]]:
    """Pages to read: one India list and one remote list per distinct Wellfound role slug. Returns (targets, notes)."""
    slugs = load_slugs() if slugs is None else slugs
    targets, seen, notes = [], set(), []
    for q in queries:
        slug = slugs.get(q.keyword.lower(), config.slug(q.keyword))
        if slug == "-":
            notes.append(f"{q.keyword!r}: no Wellfound page for this keyword, skipped")
            continue
        for kind in ("india", "remote"):
            if (slug, kind) not in seen:
                seen.add((slug, kind))
                targets.append(Target(q.role, q.keyword, slug, kind))
    return targets, notes


def _url(t: Target, page: int) -> str:
    base = (config.INDIA_PAGE if t.kind == "india" else config.REMOTE_PAGE).format(slug=t.slug)
    return base + (f"?page={page}" if page > 1 else "")


def _load(pg, url: str) -> str | None:
    """Open a page; return its HTML once job links are there, None when there are none. Raises HumanCheckPending."""
    pg.goto(url, wait_until="domcontentloaded")
    _pause(config.PAUSE_AFTER_LOAD)
    try:
        pg.wait_for_selector(config.JOB_LINK, timeout=config.CARDS_TIMEOUT_MS)
    except Exception:
        body = pg.inner_text("body").lower() if pg.query_selector("body") else ""
        if any(m in body for m in config.CHECK_MARKERS):
            raise HumanCheckPending("Wellfound is asking for a human check")
        return None
    for _ in range(random.randint(*config.SCROLL_STEPS)):    # scroll a little, like a reader
        pg.mouse.wheel(0, random.randint(*config.SCROLL_PIXELS))
        time.sleep(random.uniform(0.6, 1.6))
    return pg.content()


def in_window(job: dict, hours: int, now: datetime | None = None) -> bool:
    """Estimated posted date inside the window; hours = 0 means no window. Labels are coarse, so the check is on whole days."""
    if not hours or job.get("posted_date") is None:
        return True
    cutoff = ((now or datetime.now()) - timedelta(hours=hours)).date()
    return job["posted_date"] >= cutoff


def _keep(jobs: list[dict], t: Target, hours: int, min_experience: float, keep_all_locations: bool, counts: dict) -> list[dict]:
    out = []
    for j in jobs:
        if not in_window(j, hours):
            counts["outside_window"] += 1
            continue
        eligibility = classify_location(j.get("location", ""), j.get("work_mode", ""), t.kind)
        if not keep_all_locations and eligibility not in KEEP_LOCATIONS:
            counts["dropped_location"] += 1
            continue
        if not experience_ok(j["experience"], min_experience):
            counts["dropped_experience"] += 1
            continue
        out.append(dict(j, role=t.role, term=t.keyword, slug=t.slug, source_list=t.kind, eligibility=eligibility,
                        bengaluru="Yes" if is_bengaluru(j.get("location", "")) else ""))
    return out


class _Pool:
    """The shared state of one run: the page queue, what each list has produced so far, and a stop flag."""

    def __init__(self, targets: list[Target], on_page) -> None:
        self.tasks: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.on_page = on_page
        self.jobs = {t: {} for t in targets}                                       # per list: url -> job
        self.reports = {t: {"slug": t.slug, "kind": t.kind, "total_pages": None, "pages": 0, "read": 0, "skipped": ""} for t in targets}
        self.errors: list[str] = []
        self.chrome_pages: dict[int, int] = {}                                     # pages read per Chrome slot
        for t in targets:
            self.tasks.put((t, 1))

    def add_page(self, t: Target, page: int, jobs: list[dict], slot: int) -> int:
        with self.lock:
            bucket, before = self.jobs[t], len(self.jobs[t])
            for j in jobs:
                bucket.setdefault(j["url"], j)
            rep = self.reports[t]
            rep["pages"] += 1
            rep["read"] = len(bucket)
            self.chrome_pages[slot] = self.chrome_pages.get(slot, 0) + 1
            return len(bucket) - before


def _worker(slot: int, start_delay: float, pool: _Pool) -> None:
    """One Chrome: take pages from the queue until it is empty."""
    if start_delay:
        _pause((start_delay, start_delay))
    session, failures = None, 0
    try:
        while True:
            item = pool.tasks.get()
            try:
                if item is None:
                    return
                t, page = item
                if pool.stop.is_set():
                    continue                                   # drain: a human check somewhere stopped the run
                if page > 1 or pool.chrome_pages.get(slot):    # polite pause before every page except a Chrome's very first
                    _pause(config.PAUSE_BETWEEN_PAGES)
                session = session or Session(profile_dir=config.worker_profile(slot))
                html = _load(session.page(), _url(t, page))
                failures = 0
                if html is None:
                    continue                                   # an empty page: the list has ended
                if page == 1:
                    if is_generic_page(page_title(html), t.slug):
                        pool.reports[t]["skipped"] = f"no real Wellfound page for {t.slug!r} (generic page shown)"
                        continue
                    total = total_pages(html)
                    pool.reports[t]["total_pages"] = total
                    if total:                                  # the rest of the list goes to whichever Chrome is free
                        for n in range(2, min(total, config.MAX_PAGES) + 1):
                            pool.tasks.put((t, n))
                new = pool.add_page(t, page, parse_page(html), slot)
                if pool.on_page:
                    pool.on_page(t, page, new)
                if page == 1 and not pool.reports[t]["total_pages"] and new and page < config.MAX_PAGES:
                    pool.tasks.put((t, 2))                     # the page did not say how many pages there are: read on one by one
                elif page > 1 and not pool.reports[t]["total_pages"] and new and page < config.MAX_PAGES:
                    pool.tasks.put((t, page + 1))
            except HumanCheckPending as exc:
                pool.stop.set()
                with pool.lock:
                    pool.errors.append(f"{exc} (Chrome {slot}): double-click check_wellfound.bat")
            except Exception as exc:
                failures += 1
                with pool.lock:
                    pool.errors.append(f"{type(exc).__name__}: {str(exc)[:100]} ({item[0].slug} {item[0].kind} page {item[1]})")
                if session:
                    session.close()
                    session = None                              # next page starts a fresh Chrome
                if failures >= 3:
                    return
            finally:
                pool.tasks.task_done()
    finally:
        if session:
            session.close()


def search(queries: list[Query], hours: int, on_page=None, slugs: dict[str, str] | None = None, workers: int | None = None,
           keep_all_locations: bool = False) -> tuple[list[dict], str | None, dict]:
    """Read every planned list with a pool of Chromes sharing one page queue. Returns (jobs, error, stats). Partial results are kept."""
    targets, notes = plan(queries, slugs)
    min_exp = {q.role: q.min_experience for q in queries}
    n = max(1, min(workers or config.WORKERS_MAX, config.WORKERS_MAX))
    pool = _Pool(targets, on_page)
    threads = [threading.Thread(target=_worker, args=(k, k * random.uniform(*config.START_STAGGER), pool), daemon=True) for k in range(n)]
    for th in threads:
        th.start()
    while pool.tasks.unfinished_tasks:                          # until every queued page was read, skipped or failed
        if not any(th.is_alive() for th in threads):            # every Chrome gave up: drain what is left so nothing waits forever
            pool.errors.append("all Chromes stopped before the queue was empty")
            while True:
                try:
                    pool.tasks.get_nowait()
                    pool.tasks.task_done()
                except queue.Empty:
                    break
            break
        time.sleep(0.2)
    for _ in threads:
        pool.tasks.put(None)
    for th in threads:
        th.join()

    found, counts = {}, {"outside_window": 0, "dropped_location": 0, "dropped_experience": 0}
    stats = {"targets": len(targets), "chromes": n, "pages": 0, "read": 0, "notes": notes, "reports": [], "per_role": {},
             "pages_per_chrome": dict(sorted(pool.chrome_pages.items()))}
    for t in targets:                                           # plan order: the first role to find a job keeps it
        rep = pool.reports[t]
        stats["pages"] += rep["pages"]
        stats["read"] += rep["read"]
        stats["reports"].append(rep)
        if rep["skipped"]:
            notes.append(rep["skipped"])
        kept = _keep(list(pool.jobs[t].values()), t, hours, min_exp.get(t.role, 0), keep_all_locations, counts)
        for j in kept:
            found.setdefault(j["url"], j)
        r = stats["per_role"].setdefault(t.role, {"pages": 0, "read": 0, "kept": 0})
        r["pages"] += rep["pages"]
        r["read"] += rep["read"]
        r["kept"] += len(kept)
    stats.update(counts)
    stats["in_window"] = len(found)
    return list(found.values()), ("; ".join(dict.fromkeys(pool.errors)) or None), stats
