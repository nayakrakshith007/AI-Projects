"""Phase 2 readers (Phenom, Eightfold, Oracle HCM, Workday India filter) on saved real responses; no network."""
import json
from datetime import date

from radar3.readers import ats, platforms
from radar3.tests.test_readers import FakeHttp, src


class RecordingHttp(FakeHttp):
    """FakeHttp that also keeps the payloads it was sent."""
    def __init__(self, routes):
        super().__init__(routes)
        self.payloads = []

    def post_json(self, url, payload, **kw):
        self.payloads.append(payload)
        return super().post_json(url, payload, **kw)


def test_phenom_filters_to_india_and_reads_jobs():
    http = RecordingHttp({"/widgets": "phenom.json"})
    jobs = platforms.phenom_widget(src(slug="careers.wbd.com|WAMEGLOBAL|en_global|global/en", company="WBD"), http)
    assert jobs and all(j["tier"] in (2, 3, 4) for j in jobs)                       # India, onsite
    assert http.payloads[0]["selected_fields"] == {"country": ["India"]} and http.payloads[0]["refNum"] == "WAMEGLOBAL"
    assert jobs[0]["url"].startswith("https://") and jobs[0]["posted_date"]
    assert len(jobs) == len({j["url"] for j in jobs})                                # the four keyword searches are merged


def test_eightfold_pcsx():
    jobs = platforms.eightfold(src(slug="citi.eightfold.ai|citi.com|pcsx", company="Citi"), FakeHttp({"/api/pcsx/search": "eightfold_pcsx.json"}))
    assert jobs and jobs[0]["url"].startswith("https://citi.eightfold.ai/careers/job/")
    assert jobs[0]["tier"] in (2, 3, 4) and jobs[0]["posted_date"]


def test_eightfold_apply_style():
    jobs = platforms.eightfold(src(slug="bcg.eightfold.ai|bcg.com|apply", company="BCG"), FakeHttp({"/api/apply/v2/jobs": "eightfold_apply.json"}))
    assert jobs and jobs[0]["url"].startswith("https://bcg.eightfold.ai/careers/job/") and jobs[0]["posted_date"]


def test_oracle_hcm_uses_india_facet_and_builds_links():
    http = FakeHttp({"recruitingCEJobRequisitions": "oracle.json"})
    jobs = platforms.oracle_hcm(src(slug="jpmc.fa.oraclecloud.com|CX_1001", company="JPMorgan Chase"), http)
    assert len(jobs) == 4 and jobs[0]["url"].startswith("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/")
    assert jobs[0]["tier"] == 2 and "Bengaluru" in jobs[0]["location"]
    assert any("selectedLocationsFacet=300000000289360" in u for u in http.calls[1:])      # the India id was read from the facets and used


def test_workday_applies_india_country_filter_and_reads_city_from_link():
    http = RecordingHttp({"wday/cxs": "workday_india.json"})
    jobs = ats.workday(src(slug="accenture.wd103.myworkdayjobs.com|accenture|AccentureCareers", company="Accenture"), http, today=date(2026, 10, 13))
    assert http.payloads[0]["appliedFacets"] == {}                                    # the first call only finds the facet
    assert http.payloads[1]["appliedFacets"] == {"locationCountry": ["c4f78be1a8f14da0ab49ce1162348a5e"]}
    assert [j["location"] for j in jobs] == ["Chennai, India", "Bengaluru, India"]      # tenant gives no locationsText
    assert jobs[1]["tier"] == 2 and jobs[0]["tier"] == 3


def test_smartrecruiters_builds_public_links_for_india():
    jobs = ats.smartrecruiters(src(slug="swiggy", company="Swiggy"), FakeHttp({"api.smartrecruiters.com": "smartrecruiters.json"}))
    assert len(jobs) == 4 and jobs[0]["url"].startswith("https://jobs.smartrecruiters.com/SWIGGY/")
    assert all("India" in j["location"].title() or j["location"].endswith("IN") for j in jobs) and all(j["tier"] in (2, 3, 4) for j in jobs)


def test_workday_india_filter_falls_back_to_india_locations():
    from radar3.readers.ats import _workday_india_filter
    facets = [{"facetParameter": "locationMainGroup", "values": [{"facetParameter": "locations", "descriptor": "Locations", "values": [
        {"descriptor": "India - Chennai", "id": "a1"}, {"descriptor": "IN - Indianapolis, 4225 East", "id": "b2"}, {"descriptor": "India, Bangalore", "id": "a3"}]}]}]
    assert set(_workday_india_filter(facets)["locations"]) == {"a1", "a3"}                 # Indianapolis is not India
    assert _workday_india_filter([{"facetParameter": "locationCountry", "values": [{"descriptor": "India", "id": "c1"}]}]) == {"locationCountry": ["c1"]}
    assert _workday_india_filter([]) == {}


# ---- HTML / page-builder readers
def test_sf_classic_parses_rows_and_total():
    from radar3.readers import pages
    html = (__import__("pathlib").Path(__file__).parent / "samples" / "sf_classic.html").read_text(encoding="utf-8")
    jobs, total = pages.parse_sf_classic(html, "careers.ey.com", src(company="EY"))
    assert total == 2082 and len(jobs) == 3
    assert jobs[0]["url"].startswith("https://careers.ey.com/ey/job/") and jobs[0]["job_id"].isdigit() and jobs[0]["tier"] in (2, 3, 4)


def test_sf_csb_wipro_and_hcl():
    wipro = pages_mod().sf_csb(src(slug="careers.wipro.com|India", company="Wipro"), FakeHttp({"services/recruiting": "sf_csb_wipro.json"}))
    assert wipro and wipro[0]["url"].startswith("https://careers.wipro.com/job/") and wipro[0]["url"].endswith("-en_US") and wipro[0]["tier"] in (2, 3, 4)
    assert "<br" not in wipro[0]["location"]
    hcl = pages_mod().sf_csb(src(slug="careers.hcltech.com|", company="HCLTech"), FakeHttp({"services/recruiting": "sf_csb_hcl.json"}))
    assert hcl and hcl[0]["location"] == "Bangalore, India" and hcl[0]["tier"] == 2          # city + country come from the custom fields


def pages_mod():
    from radar3.readers import pages
    return pages


def test_avature_metlife_reads_place_date_and_id():
    html = (__import__("pathlib").Path(__file__).parent / "samples" / "avature.html").read_text(encoding="utf-8")
    jobs, total = pages_mod().parse_avature(html, src(company="MetLife"))
    assert total == 44 and len(jobs) == 3 and all(j["location"] == "Pune, India" and j["posted_date"] == date(2026, 10, 12) for j in jobs)
    assert {j["job_id"] for j in jobs} == {"21040", "20922", "20923"}


def test_avature_deloitte_style_takes_place_from_subtitle():
    html = (__import__("pathlib").Path(__file__).parent / "samples" / "avature_deloitte.html").read_text(encoding="utf-8")
    jobs, _ = pages_mod().parse_avature(html, src(company="Deloitte"))
    assert len(jobs) == 2 and any("United States" in j["location"] for j in jobs)
    assert all(j["tier"] is None for j in jobs if "United States" in j["location"])             # a US job is correctly not open to India


# ---- custom career sites (their own JSON)
def custom_mod():
    from radar3.readers import custom
    return custom


def test_amazon_builds_links_and_dates():
    jobs = custom_mod().amazon(src(cls="C", company="Amazon"), FakeHttp({"amazon.jobs/en/search.json": "amazon.json"}))
    assert jobs and jobs[0]["url"].startswith("https://www.amazon.jobs/en/jobs/") and jobs[0]["location"].endswith("India") and jobs[0]["tier"] in (2, 3, 4)
    assert jobs[0]["posted_date"] and len({j["url"] for j in jobs}) == len(jobs)


def test_goldman_graphql_india_roles():
    jobs = custom_mod().goldman(src(cls="C", company="Goldman Sachs"), FakeHttp({"api-higher.gs.com": "goldman.json"}))
    assert jobs and jobs[0]["url"].startswith("https://higher.gs.com/roles/") and "Bengaluru" in jobs[0]["location"] and jobs[0]["tier"] == 2


def test_apple_reads_hydration_json():
    import json
    sample = json.loads((__import__("pathlib").Path(__file__).parent / "samples" / "apple.json").read_text(encoding="utf-8"))
    html = 'x<script>window.__staticRouterHydrationData = JSON.parse("' + json.dumps(json.dumps(sample))[1:-1] + '");</script>'
    rows, total = custom_mod().parse_apple(html)
    assert total == 85 and len(rows) == 4 and rows[0]["positionId"]


def test_deutsche_bank_india_query(monkeypatch):
    class Http:
        def __init__(self):
            self.bodies = []

        def post_json(self, url, payload, **kw):
            self.bodies.append(payload)
            return {"SearchResult": {"SearchResultCountAll": 1, "SearchResultItems": [{"MatchedObjectId": "69591", "MatchedObjectDescriptor": {
                "PositionTitle": "Coupa Config Developer, AS", "PublicationStartDate": "2026-10-12",
                "PositionLocation": [{"CityName": "Pune", "CountryCode": "IN", "CountryName": "Indien", "Country": "81"}]}}]}}
    h = Http()
    jobs = custom_mod().deutsche(src(cls="C", company="Deutsche Bank"), h)
    assert h.bodies[0]["SearchCriteria"][0]["CriterionValue"] == ["81"]
    assert jobs[0]["location"] == "Pune, India" and jobs[0]["url"].endswith("/job/69591") and jobs[0]["tier"] == 4


def test_google_reads_jobs_from_the_page_data_block():
    html = (__import__("pathlib").Path(__file__).parent / "samples" / "google.html").read_text(encoding="utf-8")
    rows, total = custom_mod().parse_google(html)
    assert len(rows) == 3 and total > 3
    jobs = custom_mod().google(src(cls="C", company="Google"), FakeHttp({"google.com/about/careers": "google.html"}))
    assert jobs and jobs[0]["url"].startswith("https://www.google.com/about/careers/applications/jobs/results/") and jobs[0]["tier"] in (2, 3, 4)
    assert jobs[0]["posted_date"]


def test_meta_replays_the_graphql_call_with_the_page_token():
    http = FakeHttp({"metacareers.com/jobsearch": "meta_page.html", "metacareers.com/graphql": "meta.json"})
    jobs = custom_mod().meta(src(cls="C", company="Meta", slug="27129360303422352"), http)
    assert http.forms[0]["doc_id"] == "27129360303422352" and http.forms[0]["lsd"] == "AdR_X1h0dvXy0KIwaWv6zgSEp1c"
    assert [j["title"] for j in jobs][:2] == ["Data Scientist, Product", "Director, Software Engineer - WhatsApp"] and jobs[0]["tier"] == 2
    assert jobs[2]["tier"] is None and len({j["url"] for j in jobs}) == 3                     # a US job is dropped later; the five office calls are merged


def test_ibm_reads_title_url_and_place():
    jobs = custom_mod().ibm(src(cls="C", company="IBM"), FakeHttp({"www-api.ibm.com/search": "ibm.json"}))
    assert jobs and jobs[0]["url"].startswith("https://careers.ibm.com/") and jobs[0]["tier"] in (2, 3, 4) and jobs[0]["skills"]


def test_capgemini_api():
    jobs = custom_mod().capgemini(src(cls="C", company="Capgemini"), FakeHttp({"cg-jobstream-api": "capgemini.json"}))
    assert jobs and jobs[0]["location"].endswith(", India") and jobs[0]["url"].startswith("https://careers.capgemini.com/") and jobs[0]["posted_date"]


def test_sf_csb_locale_in_slug_and_links():
    http = RecordingHttp({"services/recruiting": "sf_csb_wipro.json"})
    jobs = pages_mod().sf_csb(src(slug="jobs.standardchartered.com|India|en_GB", company="Standard Chartered"), http)
    assert http.payloads[0]["locale"] == "en_GB" and http.payloads[0]["location"] == "India" and jobs[0]["url"].endswith("-en_GB")


def test_infosys_single_list_call():
    jobs = custom_mod().infosys(src(cls="C", company="Infosys"), FakeHttp({"getCareerSearchJobs": "infosys.json"}))
    assert len(jobs) == 3 and jobs[0]["url"].startswith("https://career.infosys.com/jobdesc?jobReferenceCode=INFSYS-EXTERNAL-")
    assert jobs[0]["location"].endswith(", India") and jobs[0]["tier"] in (2, 3, 4) and jobs[0]["posted_date"]


def test_consider_boards_use_the_page_csrf_token_and_india_filter():
    class H(RecordingHttp):
        def post_json(self, url, payload, **kw):
            self.payloads.append((payload, kw.get("headers")))
            return FakeHttp.post_json(self, url, payload)
    http = H({"api-boards/search-jobs": "consider.json", "sequoiacap.com/jobs": "consider_page.html"})
    jobs = custom_mod().consider(src(cls="B", company="Sequoia", slug="jobs.sequoiacap.com|sequoia-capital"), http)
    payload, headers = http.payloads[0]
    assert payload["query"] == {"locations": ["India"]} and payload["board"]["id"] == "sequoia-capital" and headers["X-CSRF-Token"] == "tok123"
    assert len(jobs) == 3 and jobs[0]["company"] == "Ethos Life" and jobs[0]["tier"] in (0, 2, 3, 4) and jobs[0]["posted_date"]


def test_affine_json():
    jobs = custom_mod().affine(src(cls="C", company="Affine"), FakeHttp({"affine.ai/data/jobs.json": "affine.json"}))
    assert jobs[0]["title"] == "Consultant Data Scientist" and jobs[0]["location"] == "Bengaluru, India" and jobs[0]["tier"] == 2


def test_consider_pages_with_the_sequence_token_not_an_offset():
    def job(i):
        return {"jobId": f"j{i}", "title": "Data Scientist", "applyUrl": f"https://x.test/{i}", "companyName": "Acme", "locations": ["Bengaluru, India"], "timeStamp": "2026-10-13T00:00:00Z"}
    pages = [{"total": 150, "meta": {"sequence": "S1"}, "jobs": [job(i) for i in range(100)]}, {"total": 150, "meta": {"sequence": "S2"}, "jobs": [job(i) for i in range(100, 150)]}]

    class H:
        def __init__(self):
            self.metas = []

        def get_text(self, url, **kw):
            return 'window.x={"csrfToken":"t"}'

        def post_json(self, url, payload, **kw):
            self.metas.append(payload["meta"])
            return pages[len(self.metas) - 1]
    h = H()
    jobs = custom_mod().consider(src(cls="B", company="X", slug="jobs.example.com|board"), h)
    assert len(jobs) == 150 and h.metas == [{"size": 100}, {"size": 100, "sequence": "S1"}]


def test_getro_board_india_filter_and_company_name():
    class H:
        def __init__(self):
            self.bodies = []

        def post_json(self, url, payload, **kw):
            self.bodies.append((url, payload))
            return json.loads((__import__("pathlib").Path(__file__).parent / "samples" / "getro.json").read_text(encoding="utf-8"))
    h = H()
    jobs = custom_mod().getro(src(cls="B", company="General Catalyst portfolio", slug="222"), h)
    url, body = h.bodies[0]
    assert url.endswith("/collections/222/search/jobs") and body["filters"] == {"searchable_locations": ["India"]}
    assert len(jobs) == 20 and jobs[0]["company"] != "General Catalyst portfolio" and jobs[0]["posted_date"] and jobs[0]["tier"] in (0, 1, 2, 3, 4)       # company = the hiring company, not the board


def test_yc_reads_the_data_page_of_each_city_and_merges():
    import html as htmllib
    sample = json.loads((__import__("pathlib").Path(__file__).parent / "samples" / "yc.json").read_text(encoding="utf-8"))
    page = '<div id="app" data-page="' + htmllib.escape(json.dumps({"props": sample}), quote=True) + '"></div>'

    class H:
        def __init__(self):
            self.urls = []

        def get_text(self, url, **kw):
            self.urls.append(url)
            return page
    h = H()
    jobs = custom_mod().yc_jobs(src(cls="B", company="Y Combinator", slug="india,bengaluru"), h)
    assert h.urls == ["https://www.ycombinator.com/jobs/location/india", "https://www.ycombinator.com/jobs/location/bengaluru"]
    assert len(jobs) == 4 and len({j["url"] for j in jobs}) == 4                                 # the same jobs on two pages are merged
    assert jobs[0]["url"].startswith("https://www.ycombinator.com/companies/") and jobs[0]["company"] and jobs[0]["tier"] in (0, 2, 3, 4)
    assert ", IN" not in jobs[0]["location"]
