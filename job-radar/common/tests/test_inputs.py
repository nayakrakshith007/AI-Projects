import pytest

from common.inputs import experience_ok, load_input, parse_experience


def write(tmp_path, text):
    p = tmp_path / "input.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_input(tmp_path):
    p = write(tmp_path, 'Role,Keywords,Experience,Location\nAI Engineer,"AI Engineer;LLM Engineer",5,India;Bengaluru\nClinical,CRA,0,\n')
    roles = load_input(p)
    assert roles[0].role == "AI Engineer" and roles[0].keywords == ["AI Engineer", "LLM Engineer"]
    assert roles[0].min_experience == 5 and roles[0].locations == ["India", "Bengaluru"]
    assert roles[1].min_experience == 0 and roles[1].locations == ["India"]   # blank location defaults to India


def test_load_input_errors(tmp_path):
    with pytest.raises(ValueError, match="missing column"):
        load_input(write(tmp_path, "Role,Keywords\nA,b\n"))
    with pytest.raises(ValueError, match="Experience must be a number"):
        load_input(write(tmp_path, "Role,Keywords,Experience,Location\nA,b,lots,India\n"))
    with pytest.raises(ValueError, match="no keywords"):
        load_input(write(tmp_path, "Role,Keywords,Experience,Location\nA,,5,India\n"))


def test_parse_experience():
    assert parse_experience("3-6 Yrs") == (3, 6)
    assert parse_experience("5+ Yrs") == (5, 99)
    assert parse_experience("4 Yrs") == (4, 4)
    assert parse_experience("") is None and parse_experience("Fresher") is None


def test_experience_ok():
    assert experience_ok("3-6 Yrs", 5)          # range reaches 5
    assert not experience_ok("0-2 Yrs", 5)
    assert experience_ok("", 5)                 # unstated: kept
    assert experience_ok("0-2 Yrs", 0)          # no filter
