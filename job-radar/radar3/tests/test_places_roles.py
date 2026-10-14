import pytest

from radar3 import places, roles

PATTERNS = roles.load_patterns()


@pytest.mark.parametrize("loc,remote,tier,elig", [
    ("Worldwide", True, 0, "yes"),
    ("Anywhere in the World", True, 0, "yes"),
    ("Remote - India", True, 0, "yes"),
    ("APAC", True, 0, "yes"),
    ("Remote", True, 1, "unclear"),
    ("", True, 1, "unclear"),
    ("USA Only", True, None, "no"),
    ("Remote - Europe", True, None, "no"),
    ("United States, Canada", True, None, "no"),
    ("Bengaluru, Karnataka", False, 2, "india"),
    ("Hyderabad, Telangana", False, 3, "india"),
    ("Chennai", False, 3, "india"),
    ("Pune, Maharashtra", False, 4, "india"),
    ("San Francisco, CA", False, None, "no"),
    ("London", False, None, "no"),
    ("Remote - Europe; Bangalore", True, 0, "yes"),             # an Indian place in the list wins
])
def test_classify(loc, remote, tier, elig):
    c = places.classify(loc, "", remote)
    assert (c["tier"], c["eligibility"]) == (tier, elig)


def test_bengaluru_flag():
    assert places.classify("Bangalore", "", False)["bengaluru"]
    assert not places.classify("Pune", "", False)["bengaluru"]


@pytest.mark.parametrize("title,expected", [
    ("Senior Machine Learning Engineer", {"ML Engineer"}),
    ("Data Scientist, Growth", {"Data Scientist"}),
    ("Senior Data Engineer", {"Data Engineer"}),
    ("Generative AI Engineer", {"AI Engineer", "GenAI / LLM Engineer"}),
    ("LLM Engineer", {"GenAI / LLM Engineer"}),
    ("Applied Scientist II", {"Applied Scientist / Research Engineer"}),
    ("Research Engineer, Pretraining", {"Applied Scientist / Research Engineer"}),
    ("MLOps Engineer", {"MLOps / ML Platform Engineer"}),
    ("Senior BI Analyst", {"Data Analyst / BI Analyst"}),
    ("AI Solutions Architect", {"AI Architect / Solutions Architect"}),
    ("Prompt Engineer", {"Prompt Engineer / AI Product"}),
    ("Product Manager, AI Platform", {"Prompt Engineer / AI Product"}),
])
def test_roles_match(title, expected):
    assert expected <= set(roles.roles_for(title, PATTERNS))


@pytest.mark.parametrize("title", ["Senior Sales Executive", "Account Executive", "Office Manager", "Recruiter", "Customer Support Agent"])
def test_roles_ignore_unrelated(title):
    assert roles.roles_for(title, PATTERNS) == []


@pytest.mark.parametrize("loc", ["Remote - California", "Remote - Illinois", "Remote, TX", "Remote (Washington, DC)", "Remote - New York"])
def test_remote_limited_to_a_us_state_is_not_open_to_india(loc):
    assert places.classify(loc, "", True)["tier"] is None


def test_remote_india_with_indiana_style_code_is_not_confused():
    assert places.classify("Remote - India", "", True)["tier"] == 0


@pytest.mark.parametrize("title,role", [
    ("Staff Software Engineer - Machine Learning (Search)", "ML Engineer"),
    ("Principal Software Engineer, AI", "AI Engineer"),
    ("Engineering Manager, Machine Learning (Safety)", "ML Engineer"),
    ("Director of Engineering (Data Infrastructure)", "Data Engineer"),
])
def test_roles_reverse_word_order(title, role):
    assert role in roles.roles_for(title, PATTERNS)


@pytest.mark.parametrize("title", ["Data Center Operations Technician", "Site Reliability Engineer, Data Center", "AI Tutor - French", "Senior Account Executive, Federal Defense and Intelligence"])
def test_roles_ignore_data_center_and_tutors(title):
    assert roles.roles_for(title, PATTERNS) == []
