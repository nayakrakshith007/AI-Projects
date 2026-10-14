"""The same search as search.py, but 2-3 searches at a time: one Chrome (one saved profile), one tab per worker.

Playwright's sync API cannot be shared between threads and one profile cannot be opened by two Chromes, so this uses the async API
with several tabs of the same Chrome. Each worker keeps the same slow pauses as the single-tab reader; only the number of searches
in flight changes. A human check stops every worker; what was read stays."""
import asyncio
import random

from common.inputs import Query, experience_ok

from . import config
from .parse import parse_page
from .session import HumanCheckPending

START_STAGGER = (6, 14)       # seconds between the starts of the workers


async def _pause(rng: tuple[float, float]) -> None:
    await asyncio.sleep(random.uniform(*rng))


async def _scroll_like_a_reader(pg) -> None:
    for _ in range(random.randint(*config.SCROLL_STEPS)):
        await pg.mouse.wheel(0, random.randint(*config.SCROLL_PIXELS))
        await asyncio.sleep(random.uniform(0.8, 2.2))


async def _page_html(pg) -> str | None:
    try:
        await pg.wait_for_selector(config.CARD_SELECTOR, timeout=config.CARDS_TIMEOUT_MS)
    except Exception:
        body = (await pg.inner_text("body")).lower() if await pg.query_selector("body") else ""
        if any(m in body for m in config.CHECK_MARKERS):
            raise HumanCheckPending("Naukri is asking for a human check")
        return None
    await _scroll_like_a_reader(pg)
    return await pg.content()


async def search_query(pg, q: Query, hours: int, on_page=None) -> list[dict]:
    jobs = {}
    age = config.job_age_days(hours)
    for n in range(1, config.MAX_PAGES + 1):
        await pg.goto(config.page_url(q.keyword, n, age, q.location), wait_until="domcontentloaded")
        await _pause(config.PAUSE_AFTER_LOAD)
        html = await _page_html(pg)
        if html is None:
            break
        before = len(jobs)
        for j in parse_page(html):
            j["role"], j["term"], j["searched_location"] = q.role, q.keyword, q.location
            jobs.setdefault(j["url"], j if experience_ok(j["experience"], q.min_experience) else None)
        if on_page:
            on_page(q, n, len(jobs) - before)
        if len(jobs) == before:
            break
        await _pause(config.PAUSE_BETWEEN_PAGES)
    return [j for j in jobs.values() if j]


async def _run(queries: list[Query], hours: int, workers: int, on_page, on_query_done) -> tuple[list[dict], str | None]:
    from playwright.async_api import async_playwright
    todo: asyncio.Queue = asyncio.Queue()
    for q in queries:
        todo.put_nowait(q)
    all_jobs: dict[str, dict] = {}
    state = {"error": None}
    stop = asyncio.Event()

    config.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(str(config.PROFILE_DIR), channel="chrome", headless=False, args=["--start-minimized"])

    async def worker(k: int) -> None:
        await asyncio.sleep(k * random.uniform(*START_STAGGER))
        pg = ctx.pages[0] if (k == 0 and ctx.pages) else await ctx.new_page()
        first = True
        while not stop.is_set():
            try:
                q = todo.get_nowait()
            except asyncio.QueueEmpty:
                return
            if not first:
                await _pause(config.PAUSE_BETWEEN_TERMS)
            first = False
            try:
                found = await search_query(pg, q, hours, on_page)
            except HumanCheckPending as exc:
                state["error"] = f"{exc}: double-click check.bat"
                stop.set()
                return
            except Exception as exc:
                state["error"] = state["error"] or f"{type(exc).__name__}: {str(exc)[:120]}"
                stop.set()
                return
            batch = []
            for j in found:
                if j["url"] not in all_jobs:
                    all_jobs[j["url"]] = j
                    batch.append(j)
            if on_query_done and batch:
                on_query_done(batch)

    try:
        await asyncio.gather(*(worker(k) for k in range(max(1, workers))))
    finally:
        try:
            await ctx.close()
            await pw.stop()
        except Exception:
            pass
    return list(all_jobs.values()), state["error"]


def search(queries: list[Query], hours: int, on_page=None, on_query_done=None, workers: int = 2) -> tuple[list[dict], str | None]:
    """Run every query, `workers` at a time. Returns (jobs, error)."""
    return asyncio.run(_run(queries, hours, workers, on_page, on_query_done))
