import threading

from common.inputs import Query
from linkedin import config, engine_jobspy


def job(n):
    return {"title": f"Job {n}", "company": "Acme", "location": "India", "posted_text": "", "posted_date": None,
            "url": f"https://www.linkedin.com/jobs/view/{n}"}


def make_fetch(total, blocked_calls=0, calls=None):
    """Fake LinkedIn: `total` jobs served ten at a time; the first `blocked_calls` calls are rate limited."""
    state = {"blocked": blocked_calls}
    lock = threading.Lock()

    def fetch(q, hours, offset):
        with lock:
            if calls is not None:
                calls.append((q.keyword, offset))
            if state["blocked"] > 0:
                state["blocked"] -= 1
                return [], True
        return [job(i) for i in range(offset, min(offset + 10, total))], False
    return fetch


Q = Query("AI Engineer", "ai engineer", "India", 5)
NO_SLEEP = lambda s: None


def test_pages_until_results_run_out():
    calls = []
    jobs, err = engine_jobspy.search([Q], 24, fetch=make_fetch(35, calls=calls), sleep=NO_SLEEP, workers=1)
    assert len(jobs) == 35 and err is None
    assert [c[1] for c in calls] == [0, 10, 20, 30, 40]          # the fifth request comes back empty and ends it
    assert jobs[0]["role"] == "AI Engineer" and jobs[0]["term"] == "ai engineer" and jobs[0]["searched_location"] == "India"


def test_backs_off_and_retries_the_same_page():
    calls, sleeps = [], []
    jobs, err = engine_jobspy.search([Q], 24, fetch=make_fetch(20, blocked_calls=1, calls=calls), sleep=sleeps.append, workers=1)
    assert len(jobs) == 20 and err is None
    assert calls[0] == calls[1] == ("ai engineer", 0)             # offset 0 asked twice
    assert any(config.BACKOFF[0] <= s <= config.BACKOFF[1] for s in sleeps)


def test_gives_up_on_a_search_after_repeated_rate_limits():
    jobs, err = engine_jobspy.search([Q], 24, fetch=make_fetch(50, blocked_calls=99), sleep=NO_SLEEP, workers=1)
    assert jobs == [] and "rate limit" in err


def test_whole_run_stops_after_several_searches_give_up():
    queries = [Query("R", f"kw{i}", "India", 0) for i in range(8)]
    calls = []
    jobs, err = engine_jobspy.search(queries, 24, fetch=make_fetch(50, blocked_calls=10_000, calls=calls), sleep=NO_SLEEP, workers=1)
    assert "stopped early" in err
    assert len({c[0] for c in calls}) < 8                           # later searches were never started


def test_parallel_workers_dedupe_across_searches():
    queries = [Query("A", "one", "India", 0), Query("B", "two", "India", 0), Query("C", "three", "India", 0)]
    jobs, err = engine_jobspy.search(queries, 24, fetch=make_fetch(25), sleep=NO_SLEEP, workers=3)
    assert err is None and len(jobs) == 25                          # the same 25 jobs from three searches count once
    assert next(j for j in jobs if j["url"].endswith("/0"))["role"] == "A"


def test_place_and_url():
    assert config.place("India") == "India" and config.place("Bengaluru") == "Bengaluru, India"
    assert "location=Bengaluru%2C%20India" in config.search_url("data scientist", 24, "Bengaluru")


def test_each_search_is_handed_over_when_it_ends_one_at_a_time():
    queries = [Query("A", "one", "India", 0), Query("B", "two", "India", 0), Query("C", "three", "India", 0)]
    batches, inside = [], []

    def on_done(batch):
        inside.append(1)
        assert len(inside) == 1                                      # never two calls at once
        batches.append([j["url"] for j in batch])
        inside.pop()
    jobs, err = engine_jobspy.search(queries, 24, fetch=make_fetch(25), sleep=NO_SLEEP, workers=3, on_query_done=on_done)
    assert err is None and len(jobs) == 25
    assert sum(len(b) for b in batches) == 25 and len({u for b in batches for u in b}) == 25      # each job is handed over exactly once


def test_a_search_that_gives_up_still_hands_over_what_it_read():
    got = []
    jobs, err = engine_jobspy.search([Q], 24, fetch=make_fetch(30, blocked_calls=0), sleep=NO_SLEEP, workers=1,
                                     on_query_done=lambda b: got.extend(j["url"] for j in b))
    assert len(got) == len(jobs) == 30
