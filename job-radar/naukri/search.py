"""Read Naukri result pages for search terms: page after page until the results run out, slowly and politely."""
import random
import time

from common.inputs import Query, experience_ok, queries_from  # noqa: F401  (queries_from is used by the command line)

from . import config
from .parse import parse_page
from .session import HumanCheckPending, Session


def _pause(rng: tuple[float, float]) -> None:
    time.sleep(random.uniform(*rng))


def _scroll_like_a_reader(pg) -> None:
    for _ in range(random.randint(*config.SCROLL_STEPS)):
        pg.mouse.wheel(0, random.randint(*config.SCROLL_PIXELS))
        time.sleep(random.uniform(0.8, 2.2))


def _page_html(pg) -> str | None:
    """HTML of a loaded results page, or None when it has no cards. Raises HumanCheckPending on the check page."""
    try:
        pg.wait_for_selector(config.CARD_SELECTOR, timeout=config.CARDS_TIMEOUT_MS)
    except Exception:
        body = pg.inner_text("body").lower() if pg.query_selector("body") else ""
        if any(m in body for m in config.CHECK_MARKERS):
            raise HumanCheckPending("Naukri is asking for a human check")
        return None
    _scroll_like_a_reader(pg)
    return pg.content()


def search_query(session: Session, q: Query, hours: int, on_page=None) -> list[dict]:
    """All jobs for one keyword in one location within the window, minus jobs below the role's minimum experience.
    `on_page(query, page_no, new_count)` is an optional progress hook."""
    pg, jobs = session.page(), {}
    age = config.job_age_days(hours)
    for n in range(1, config.MAX_PAGES + 1):
        pg.goto(config.page_url(q.keyword, n, age, q.location), wait_until="domcontentloaded")
        _pause(config.PAUSE_AFTER_LOAD)
        html = _page_html(pg)
        if html is None:
            break
        before = len(jobs)
        for j in parse_page(html):
            j["role"], j["term"], j["searched_location"] = q.role, q.keyword, q.location
            if experience_ok(j["experience"], q.min_experience):
                jobs.setdefault(j["url"], j)
            else:
                jobs.setdefault(j["url"], None)   # seen but filtered: still counts as "not new" for paging
        if on_page:
            on_page(q, n, len(jobs) - before)
        if len(jobs) == before:  # nothing new: the results have run out
            break
        _pause(config.PAUSE_BETWEEN_PAGES)
    return [j for j in jobs.values() if j]


def search(queries: list[Query], hours: int, on_page=None, on_query_done=None, workers: int = 1) -> tuple[list[dict], str | None]:
    """Run every query. Returns (jobs, error). Stops at the first human check; partial results are kept.
    `on_query_done(jobs)` is called after each query with the jobs that were new in this run, so they can be saved at once.
    `workers` > 1 reads that many searches at a time in tabs of one Chrome (search_parallel.py)."""
    if workers > 1:
        from . import search_parallel
        return search_parallel.search(queries, hours, on_page, on_query_done, min(workers, config.WORKERS_MAX))
    session, all_jobs, error = Session(), {}, None
    try:
        for i, q in enumerate(queries):
            if i:
                _pause(config.PAUSE_BETWEEN_TERMS)
            batch = []
            for j in search_query(session, q, hours, on_page):
                if j["url"] not in all_jobs:
                    all_jobs[j["url"]] = j
                    batch.append(j)
            if on_query_done and batch:
                on_query_done(batch)
    except HumanCheckPending as exc:
        error = f"{exc}: double-click check.bat"
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        session.close()
    return list(all_jobs.values()), error
