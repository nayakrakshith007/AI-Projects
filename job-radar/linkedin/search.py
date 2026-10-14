"""Engine 2 (fallback): real Chrome on LinkedIn's public search pages. Scroll and press 'See more jobs', slowly.

Used with `--engine browser` when the JobSpy engine is rate limited. One search at a time, no login.
"""
import random
import time

from common.inputs import Query

from . import config
from .parse import parse_page
from .session import HumanCheckPending, Session


def _pause(rng: tuple[float, float]) -> None:
    time.sleep(random.uniform(*rng))


def _wall_shown(pg) -> bool:
    if any(p in pg.url for p in config.CHECK_URL_PARTS):
        return True
    body = pg.inner_text("body").lower() if pg.query_selector("body") else ""
    return any(m in body for m in config.CHECK_MARKERS) and not pg.query_selector(config.CARD_SELECTOR)


def _load_all(pg, on_round=None) -> None:
    """Scroll down and press 'See more jobs' until the number of cards stops growing."""
    last, stale = 0, 0
    while stale < config.STALE_ROUNDS:
        count = len(pg.query_selector_all(config.CARD_SELECTOR))
        if on_round:
            on_round(count)
        if count >= config.MAX_CARDS:
            break
        stale = stale + 1 if count == last else 0
        last = count
        pg.mouse.wheel(0, random.randint(1800, 3200))
        btn = pg.query_selector(config.MORE_BUTTON)
        if btn and btn.is_visible():
            try:
                btn.click(timeout=3000)
            except Exception:
                pass
        _pause(config.PAUSE_BETWEEN_SCROLLS)


def search_query(session: Session, q: Query, hours: int, on_round=None) -> list[dict]:
    pg = session.page()
    pg.goto(config.search_url(q.keyword, hours, q.location), wait_until="domcontentloaded")
    _pause(config.PAUSE_AFTER_LOAD)
    if _wall_shown(pg):
        raise HumanCheckPending("LinkedIn is showing a sign-in wall or security check")
    _load_all(pg, on_round)
    jobs = {}
    for j in parse_page(pg.content()):
        j.update(role=q.role, term=q.keyword, searched_location=q.location)
        jobs.setdefault(j["url"], j)
    return list(jobs.values())


def search(queries: list[Query], hours: int, on_round=None) -> tuple[list[dict], str | None]:
    """Run every query. Returns (jobs, error). Stops at the first wall; partial results are kept."""
    session, all_jobs, error = Session(), {}, None
    try:
        for i, q in enumerate(queries):
            if i:
                _pause(config.PAUSE_BETWEEN_TERMS)
            found = search_query(session, q, hours, (lambda c, q=q: on_round(q, c)) if on_round else None)
            for j in found:
                all_jobs.setdefault(j["url"], j)
    except HumanCheckPending as exc:
        error = f"{exc}: double-click check_linkedin.bat"
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        session.close()
    return list(all_jobs.values()), error
