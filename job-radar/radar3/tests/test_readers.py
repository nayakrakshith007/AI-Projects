"""Each reader parses a saved real response (radar3/tests/samples); no network."""
import json
from datetime import date
from pathlib import Path

from radar3.readers import ats, feeds

S = Path(__file__).parent / "samples"


class FakeHttp:
    """Returns saved samples by URL substring."""
    def __init__(self, routes: dict[str, str]) -> None:
        self.routes, self.calls = routes, []

    def _find(self, url: str) -> str:
        self.calls.append(url)
        for key, name in self.routes.items():
            if key in url:
                return (S / name).read_text(encoding="utf-8")
        raise AssertionError(f"no sample for {url}")

    def get_json(self, url, **kw):
        return json.loads(self._find(url))

    def get_text(self, url, **kw):
        return self._find(url)

    def post_json(self, url, payload, **kw):
        return json.loads(self._find(url))

    def post_form(self, url, data, **kw):
        self.forms = getattr(self, 'forms', []) + [data]
        return json.loads(self._find(url))


def src(**kw):
    return {"id": "T01", "name": "Test source", "company": "", "cls": "B", "slug": "x", **kw}


def test_remoteok_skips_legal_notice_and_keeps_link():
    jobs = feeds.remoteok(src(cls="A"), FakeHttp({"remoteok.com/api": "remoteok.json"}))
    assert jobs and all(j["url"].lower().startswith("https://remoteok.com/") for j in jobs)
    assert all(j["remote"] and j["source_type"] == "Feed" for j in jobs)
    assert all(isinstance(j["posted_date"], date) for j in jobs)


def test_remotive_reads_jobs():
    jobs = feeds.remotive(src(cls="A", slug="data"), FakeHttp({"remotive.com/api": "remotive.json"}))
    assert len(jobs) == 5 and jobs[0]["company"] and jobs[0]["location"] == "Worldwide" and jobs[0]["tier"] == 0


def test_workingnomads_location_drives_eligibility():
    jobs = feeds.workingnomads(src(cls="A"), FakeHttp({"workingnomads": "workingnomads.json"}))
    assert jobs and jobs[0]["tier"] is None and jobs[0]["eligibility"] == "no"        # 'United States' only


def test_weworkremotely_splits_company_and_title():
    jobs = feeds.weworkremotely(src(cls="A", slug="remote-jobs.rss"), FakeHttp({"weworkremotely.com": "wwr.xml"}))
    assert jobs[0]["company"] == "Prove" and jobs[0]["title"].startswith("Senior Software Engineer")
    assert jobs[0]["tier"] == 0                                                          # 'Anywhere in the World'


def test_weworkremotely_dedupes_across_feeds():
    jobs = feeds.weworkremotely(src(cls="A", slug="a.rss,b.rss"), FakeHttp({"weworkremotely.com": "wwr.xml"}))
    assert len(jobs) == len({j["url"] for j in jobs})


def test_jobspresso_company_and_place_from_creator():
    jobs = feeds.jobspresso(src(cls="A"), FakeHttp({"jobspresso.co": "jobspresso.xml"}))
    assert jobs[0]["company"] == "ShyftOff" and jobs[0]["location"] == "United States" and jobs[0]["tier"] is None


def test_greenhouse():
    jobs = ats.greenhouse(src(slug="xai", company="xAI"), FakeHttp({"greenhouse.io": "greenhouse.json"}))
    assert len(jobs) == 5 and all(j["url"].startswith("https://") for j in jobs) and all(j["job_id"].isdigit() for j in jobs)


def test_ashby_marks_remote_and_reads_secondary_locations():
    jobs = ats.ashby(src(slug="cohere", company="Cohere"), FakeHttp({"ashbyhq.com": "ashby.json"}))
    assert jobs and jobs[0]["work_mode"] == "Remote" and jobs[0]["more_locations"]


def test_lever():
    jobs = ats.lever(src(slug="palantir", company="Palantir"), FakeHttp({"api.lever.co": "lever.json"}))
    assert jobs and jobs[0]["url"].startswith("https://jobs.lever.co/")


def test_workable():
    jobs = ats.workable(src(slug="huggingface", company="Hugging Face"), FakeHttp({"workable.com": "workable.json"}))
    assert jobs and jobs[0]["remote"] and jobs[0]["url"].startswith("https://apply.workable.com/")


def test_workday_builds_job_links_and_dates():
    http = FakeHttp({"wday/cxs": "workday.json"})
    jobs = ats.workday(src(slug="cat.wd5.myworkdayjobs.com|cat|CaterpillarCareers", company="Caterpillar"), http, today=date(2026, 10, 13))
    assert jobs[0]["url"].startswith("https://cat.wd5.myworkdayjobs.com/en-US/CaterpillarCareers/job/")
    assert jobs[0]["posted_date"] == date(2026, 10, 8) and jobs[0]["tier"] == 3         # Chennai, onsite
    assert len(jobs) == len({j["url"] for j in jobs})                                    # the four keyword searches are merged
