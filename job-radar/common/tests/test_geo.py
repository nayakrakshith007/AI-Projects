from common.geo import is_bengaluru, is_indian_place


def test_indian_places():
    for text in ("India", "Bengaluru", "Bangalore Urban", "Gurgaon", "Onsite or remote • Bengaluru", "Hyderabad", "KA, India", "Pune, MH", "Remote - India"):
        assert is_indian_place(text), text


def test_non_indian_places():
    for text in ("United States", "New York", "Toronto", "North America", "Tel Aviv", "Munich", "San Francisco Bay Area", "Hong Kong", "", None):
        assert not is_indian_place(text), text
    assert not is_indian_place("Remote - UP, United States")   # a state code next to another country is not Uttar Pradesh


def test_bengaluru():
    assert is_bengaluru("Bangalore Urban") and is_bengaluru("Onsite or remote • Bengaluru") and not is_bengaluru("Pune")
