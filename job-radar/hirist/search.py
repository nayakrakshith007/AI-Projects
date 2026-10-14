"""Read Hirist with two methods and compare them.

search method: Hirist's free-text search (works for any keyword). The page loads its jobs as JSON; that response is read,
               which gives exact posting times, numeric experience and every location.
tag method:    Hirist's own tag pages (/k/<tag>-jobs), curated lists for skills and roles such as data-scientist or
               machine-learning. They arrive as HTML cards with relative dates ("Posted 3 days ago").
Both use Hirist's own date filter (posting=1|3|7|15|30), so only a few pages per keyword are read. A pool of Chromes shares
one queue of pages: page 1 of each list tells how many pages there are, pages 2..N go into the queue.
"""
import csv
import queue
import random
import re
import threading
import time
from datetime import datetime, timedelta
from typing import NamedTuple

from common.inputs import Query, experience_ok

from . import config
from .parse import pages_for, parse_search_json, parse_tag_page, title_matches, total_from_title
from .session import HumanCheckPending, Session


class Target(NamedTuple):
    role: str
    keyword: str
    slug: str
    method: str          # "search" or "tag"


def _pause(rng: tuple[float, float]) -> None:
    time.sleep(random.uniform(*rng))


def load_tags(path=config.TAGS_FILE) -> dict[str, list[str]]:
    """keyword (lower case) -> Hirist tag slugs; '-' means the keyword has no tag page."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["keyword"].strip().lower(): [t.strip() for t in r["tags"].split(";") if t.strip()] for r in csv.DictReader(f) if r.get("keyword")}


def plan(queries: list[Query], tags: dict[str, list[str]] | None = None, methods: tuple[str, ...] = config.METHODS) -> tuple[list[Target], list[str]]:
    """Lists to read: a search list per keyword and a tag list per mapped tag. Returns (targets, notes)."""
    tags = load_tags() if tags is None else tags
    targets, seen, notes = [], set(), []
    for q in queries:
        if "search" in methods and ("search", config.slug(q.keyword)) not in seen:
            seen.add(("search", config.slug(q.keyword)))
            targets.append(Target(q.role, q.keyword, config.slug(q.keyword), "search"))
        if "tag" in methods:
            mapped = tags.get(q.keyword.lower(), [config.slug(q.keyword)])
            if mapped == ["-"]:
                notes.append(f"{q.keyword!r}: no Hirist tag page, only the search method covers it")
            for tag in mapped:
                if tag != "-" and ("tag", tag) not in seen:
                    seen.add(("tag", tag))
                    targets.append(Target(q.role, q.keyword, tag, "tag"))
    return targets, notes


def _url(t: Target, days: int, page: int) -> str:
    return config.search_url(t.slug, days, page) if t.method == "search" else config.tag_url(t.slug, days, page)


def _check_or_empty(pg) -> None:
    body = pg.inner_text("body").lower() if pg.query_selector("body") else ""
    if any(m in body for m in config.CHECK_MARKERS):
        raise HumanCheckPending("Hirist is asking for a human check")


def read_page(pg, t: Target, days: int, page: int) -> tuple[list[dict], int | None]:
    """Open one page. Returns (jobs, total pages if the page says). Raises HumanCheckPending."""
    url = _url(t, days, page)
    if t.method == "search":
        def wanted(r):
            return "gladiator.hirist.tech/job/search?" in r.url and f"posting={days}" in r.url and r.status == 200
        try:
            with pg.expect_response(wanted, timeout=config.RESPONSE_TIMEOUT_MS) as info:
                pg.goto(url, wait_until="domcontentloaded")
            data = info.value.json()
            _pause(config.PAUSE_AFTER_LOAD)
            return parse_search_json(data), data.get("totalPages")
        except HumanCheckPending:
            raise
        except Exception:
            pass                                                   # no JSON arrived: read the cards on the page instead
    else:
        pg.goto(url, wait_until="domcontentloaded")
    _pause(config.PAUSE_AFTER_LOAD)
    try:
        pg.wait_for_selector(config.CARD_SELECTOR, timeout=config.RESPONSE_TIMEOUT_MS)
    except Exception:
        _check_or_empty(pg)
        return [], None                                            # "No result found": no such list
    html = pg.content()
    jobs = parse_tag_page(html)
    for j in jobs:
        j["source"] = "search-cards" if t.method == "search" else "tag"
    return jobs, pages_for(total_from_title(html))


def in_window(job: dict, hours: int, now: datetime | None = None) -> bool:
    """Posted inside the window. Exact when Hirist gave the posting time, whole days when only a label is known."""
    now = now or datetime.now()
    if not hours:
        return True
    if job.get("posted_at"):
        return datetime.fromisoformat(job["posted_at"]).replace(tzinfo=None) >= now - timedelta(hours=hours)
    if job.get("posted_date") is None:
        return True
    return job["posted_date"] >= (now - timedelta(hours=hours)).date()


class _Pool:
    """Shared state of one run: the page queue, what each list has produced so far, and a stop flag."""

    def __init__(self, targets: list[Target], days: int, on_page) -> None:
        self.tasks: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.days, self.on_page = days, on_page
        self.jobs = {t: {} for t in targets}
        self.reports = {t: {"slug": t.slug, "method": t.method, "total_pages": None, "pages": 0, "read": 0, "empty": False} for t in targets}
        self.errors: list[str] = []
        self.chrome_pages: dict[int, int] = {}
        for t in targets:
            self.tasks.put((t, 1))

    def add_page(self, t: Target, jobs: list[dict], slot: int) -> int:
        with self.lock:
            bucket, before = self.jobs[t], len(self.jobs[t])
            for j in jobs:
                bucket.setdefault(j["id"] or j["url"], j)
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
                    continue
                if pool.chrome_pages.get(slot):
                    _pause(config.PAUSE_BETWEEN_PAGES)
                session = session or Session()
                jobs, total = read_page(session.page(), t, pool.days, page)
                failures = 0
                if page == 1:
                    pool.reports[t]["total_pages"] = total
                    pool.reports[t]["empty"] = not jobs
                    for n in range(2, min(total or 1, config.MAX_PAGES) + 1):
                        pool.tasks.put((t, n))
                if not jobs:
                    continue
                new = pool.add_page(t, jobs, slot)
                if pool.on_page:
                    pool.on_page(t, page, new)
                if page == 1 and not total and len(jobs) >= config.PAGE_SIZE:      # page count unknown: read on one by one
                    pool.tasks.put((t, 2))
                elif page > 1 and not pool.reports[t]["total_pages"] and new and len(jobs) >= config.PAGE_SIZE and page < config.MAX_PAGES:
                    pool.tasks.put((t, page + 1))
            except HumanCheckPending as exc:
                pool.stop.set()
                with pool.lock:
                    pool.errors.append(f"{exc} (Chrome {slot}): double-click check_hirist.bat")
            except Exception as exc:
                failures += 1
                with pool.lock:
                    pool.errors.append(f"{type(exc).__name__}: {str(exc)[:100]} ({item[0].slug} {item[0].method} page {item[1]})")
                if session:
                    session.close()
                    session = None
                if failures >= 3:
                    return
            finally:
                pool.tasks.task_done()
    finally:
        if session:
            session.close()


def _stamp(j: dict, t: Target) -> dict:
    return dict(j, role=t.role, term=t.keyword, slug=t.slug, methods=[t.method], title_match="Yes" if title_matches(j, t.keyword) else "")


def _merge(old: dict, new: dict) -> dict:
    """The same job found twice: keep the richer record (the search JSON), remember every method that found it."""
    methods = sorted(set(old["methods"]) | set(new["methods"]))
    keep = new if new.get("posted_at") and not old.get("posted_at") else old
    other = old if keep is new else new
    merged = dict(keep, methods=methods)
    for k, v in other.items():                                   # fill gaps from the other record
        if merged.get(k) in (None, "", [], ()) and v not in (None, "", [], ()):
            merged[k] = v
    return merged


def search(queries: list[Query], hours: int, on_page=None, tags: dict[str, list[str]] | None = None, workers: int | None = None,
           methods: tuple[str, ...] = config.METHODS) -> tuple[list[dict], str | None, dict]:
    """Read every planned list. Returns (jobs, error, stats). stats['compare'] has what each method found per role."""
    targets, notes = plan(queries, tags, methods)
    min_exp = {q.role: q.min_experience for q in queries}
    days = config.posting_days(hours)
    n = max(1, min(workers or config.WORKERS, config.WORKERS_MAX))
    pool = _Pool(targets, days, on_page)
    threads = [threading.Thread(target=_worker, args=(k, k * random.uniform(*config.START_STAGGER), pool), daemon=True) for k in range(n)]
    for th in threads:
        th.start()
    while pool.tasks.unfinished_tasks:
        if not any(th.is_alive() for th in threads):
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

    final: dict[str, dict] = {}
    seen_by: dict[tuple[str, str], dict[str, bool]] = {}          # (role, method) -> {job id: title matches}
    counts = {"outside_window": 0, "dropped_experience": 0}
    stats = {"targets": len(targets), "chromes": n, "posting_days": days, "pages": 0, "read": 0, "notes": notes,
             "reports": [], "pages_per_chrome": dict(sorted(pool.chrome_pages.items()))}
    for t in targets:
        rep = pool.reports[t]
        stats["pages"] += rep["pages"]
        stats["read"] += rep["read"]
        stats["reports"].append(rep)
        if rep["empty"]:
            notes.append(f"{t.method} {t.slug!r}: no jobs in the window (or no such list)")
        for j in pool.jobs[t].values():
            if not in_window(j, hours):
                counts["outside_window"] += 1
                continue
            if not experience_ok(j["experience"], min_exp.get(t.role, 0)):
                counts["dropped_experience"] += 1
                continue
            s = _stamp(j, t)
            seen_by.setdefault((t.role, t.method), {})[s["id"] or s["url"]] = bool(s["title_match"])
            key = s["id"] or s["url"]
            final[key] = _merge(final[key], s) if key in final else s
    stats.update(counts)
    stats["compare"] = compare(seen_by, [q.role for q in queries])
    return list(final.values()), ("; ".join(dict.fromkeys(pool.errors)) or None), stats


def compare(seen_by: dict, roles_in_order: list[str]) -> list[dict]:
    """Per role: how many jobs each method found, how many of them look like the role, and how they overlap."""
    rows = []
    for role in dict.fromkeys(roles_in_order):
        s, t = seen_by.get((role, "search"), {}), seen_by.get((role, "tag"), {})
        both = set(s) & set(t)
        rows.append({
            "role": role, "search": len(s), "search_match_title": sum(s.values()), "tag": len(t), "tag_match_title": sum(t.values()),
            "both": len(both), "only_search": len(set(s) - set(t)), "only_tag": len(set(t) - set(s)),
            "union": len(set(s) | set(t)), "union_match_title": sum({**s, **t}.values()),
        })
    return rows
