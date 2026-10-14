from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from naukri import config, excel
from naukri.parse import parse_card, posted_to_date

CARD = (Path(__file__).parent / "fixtures" / "card.html").read_text(encoding="utf-8")
TODAY = date(2026, 10, 11)


def test_parse_card_fields():
    job = parse_card(CARD, TODAY)
    assert job["title"] == "AI / ML Forward Deployed Engineer"
    assert job["company"] == "Kiya.ai"
    assert job["experience"] == "3-6 Yrs"
    assert job["location"] == "Hyderabad"
    assert "LLM" in job["skills"] and "Python" in job["skills"]
    assert job["url"].startswith("https://www.naukri.com/job-listings-")
    assert job["posted_date"] == date(2026, 10, 10)


def test_posted_to_date():
    assert posted_to_date("Few hours ago", TODAY) == TODAY
    assert posted_to_date("1 day ago", TODAY) == date(2026, 10, 10)
    assert posted_to_date("2 weeks ago", TODAY) == date(2026, 9, 27)
    assert posted_to_date("", TODAY) is None


def test_urls_and_age():
    assert config.page_url("Forward Deployed Engineer", 1, 1) == "https://www.naukri.com/forward-deployed-engineer-jobs-in-india?jobAge=1"
    assert config.page_url("AI Engineer", 3, 3).endswith("ai-engineer-jobs-in-india-3?jobAge=3")
    assert [config.job_age_days(h) for h in (12, 24, 48, 72, 100, 400, 1000)] == [1, 1, 3, 3, 7, 30, 30]


def test_excel_adds_dedupes_and_keeps_user_fields(tmp_path):
    path = tmp_path / "Naukri.xlsx"
    job = parse_card(CARD, TODAY)
    job["term"] = "forward deployed engineer"
    written, n_new, n_upd, total = excel.save([job], path, TODAY)
    assert (written, n_new, n_upd, total) == (path, 1, 0, 1)

    wb = load_workbook(path)
    ws = wb["Naukri"]
    status_col = excel.HEADERS.index("Status") + 1
    ws.cell(row=2, column=status_col).value = "Applied"   # the owner's own edit
    wb.save(path)

    written, n_new, n_upd, total = excel.save([job], path, TODAY)   # same job again
    assert (n_new, n_upd, total) == (0, 1, 1)
    assert load_workbook(path)["Naukri"].cell(row=2, column=status_col).value == "Applied"
    assert load_workbook(path)["Naukri"].cell(row=2, column=excel.HEADERS.index("Link") + 1).hyperlink.target == job["url"]


def test_second_save_with_date_cells_does_not_crash(tmp_path):
    path = tmp_path / "Naukri.xlsx"
    a = parse_card(CARD, TODAY)
    a["term"] = "x"
    excel.save([a], path, TODAY)
    b = dict(a, url=a["url"] + "-2")
    written, n_new, n_upd, total = excel.save([b], path, date(2026, 10, 12))  # existing rows come back as datetimes
    assert (n_new, total) == (1, 2)


def test_location_in_url():
    assert config.page_url("Data Scientist", 1, 1, "Bengaluru") == "https://www.naukri.com/data-scientist-jobs-in-bengaluru?jobAge=1"
    assert config.page_url("Data Scientist", 2, 3, "Navi Mumbai").endswith("data-scientist-jobs-in-navi-mumbai-2?jobAge=3")


def test_older_workbook_without_role_column_still_loads(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / "Naukri.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Naukri"
    old = ["Title", "Company", "Experience", "Location", "Skills", "Snippet", "Posted", "Posted date", "Search term", "First seen", "Link", "Status", "Notes"]
    ws.append(old)
    ws.append(["Old job", "Acme", "3-6 Yrs", "Pune", "", "", "1 day ago", date(2026, 10, 10), "ai engineer", date(2026, 10, 10), "Open", "Applied", "call Monday"])
    ws.cell(row=2, column=11).hyperlink = "https://www.naukri.com/job-listings-old"
    wb.save(path)

    job = parse_card(CARD, TODAY)
    job.update(term="x", role="AI Engineer")
    written, n_new, n_upd, total = excel.save([job], path, TODAY)
    assert (n_new, total) == (1, 2)
    ws = load_workbook(path)["Naukri"]
    by_title = {ws.cell(row=r, column=1).value: r for r in (2, 3)}
    old_row = by_title["Old job"]
    assert ws.cell(row=old_row, column=excel.col("Status")).value == "Applied"
    assert ws.cell(row=old_row, column=excel.col("Notes")).value == "call Monday"


def test_each_search_is_handed_over_as_soon_as_it_is_read(monkeypatch):
    from common.inputs import Query
    from naukri import search as s

    class FakeSession:
        def close(self):
            pass

    batches = []
    data = {"a": [{"url": "u1"}, {"url": "u2"}], "b": [{"url": "u2"}, {"url": "u3"}], "c": []}
    monkeypatch.setattr(s, "Session", FakeSession)
    monkeypatch.setattr(s, "_pause", lambda rng: None)
    monkeypatch.setattr(s, "search_query", lambda session, q, hours, on_page=None: [dict(j) for j in data[q.keyword]])
    qs = [Query(role="R", keyword=k, min_experience=0, location="India") for k in ("a", "b", "c")]
    jobs, error = s.search(qs, 24, on_query_done=lambda batch: batches.append([j["url"] for j in batch]))
    assert error is None and [j["url"] for j in jobs] == ["u1", "u2", "u3"]
    assert batches == [["u1", "u2"], ["u3"]]                       # only jobs new to the run, and nothing for an empty search


def test_page_ceiling_is_fifteen():
    assert config.MAX_PAGES == 15


def test_parallel_reader_runs_searches_in_tabs_and_hands_over_each_one(monkeypatch):
    import asyncio
    import sys
    import types

    from common.inputs import Query
    from naukri import search_parallel as sp

    opened = []

    class FakePage:
        pass

    class FakeCtx:
        pages = []

        async def new_page(self):
            opened.append(1)
            return FakePage()

        async def close(self):
            pass

    class FakePw:
        class chromium:
            @staticmethod
            async def launch_persistent_context(*a, **k):
                return FakeCtx()

        async def stop(self):
            pass

    class FakeStarter:
        async def start(self):
            return FakePw()

    fake_mod = types.ModuleType("playwright.async_api")
    fake_mod.async_playwright = lambda: FakeStarter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_mod)
    monkeypatch.setattr(sp, "START_STAGGER", (0, 0))
    monkeypatch.setattr(sp, "_pause", lambda rng: asyncio.sleep(0))
    seen = []

    async def fake_query(pg, q, hours, on_page=None):
        seen.append(q.keyword)
        await asyncio.sleep(0.01)
        return [{"url": f"u-{q.keyword}"}, {"url": "shared"}]

    monkeypatch.setattr(sp, "search_query", fake_query)
    qs = [Query(role="R", keyword=k, min_experience=0, location="India") for k in "abcd"]
    batches = []
    jobs, error = sp.search(qs, 24, on_query_done=lambda b: batches.append(sorted(j["url"] for j in b)), workers=3)
    assert error is None and sorted(seen) == ["a", "b", "c", "d"] and len(opened) == 3          # 3 workers: 1 first tab + 2 new tabs... 
    assert sorted(j["url"] for j in jobs) == ["shared", "u-a", "u-b", "u-c", "u-d"] and len(batches) == 4
