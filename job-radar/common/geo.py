"""Is a place in India? Shared by every site workflow. Matches 'India', Indian states and the cities job posts mention."""
import re

INDIA = re.compile(
    r"india|bengaluru|bangalore|mumbai|delhi|gurugram|gurgaon|noida|hyderabad|pune|chennai|kolkata|ahmedabad|kerala|kochi|cochin|"
    r"ernakulam|thiruvananthapuram|trivandrum|kozhikode|karnataka|mysuru|mysore|mangalore|mangaluru|hubli|belagavi|belgaum|tamil nadu|"
    r"coimbatore|madurai|andhra|telangana|vijayawada|visakhapatnam|vizag|maharashtra|nagpur|nashik|thane|navi mumbai|gujarat|jamnagar|"
    r"vadodara|surat|rajkot|rajasthan|jaipur|jodhpur|udaipur|uttar pradesh|lucknow|varanasi|banaras|kanpur|ghaziabad|faridabad|"
    r"madhya pradesh|bhopal|indore|odisha|bhubaneswar|bihar|patna|punjab|chandigarh|mohali|ludhiana|haryana|uttarakhand|dehradun|"
    r"haridwar|himachal|jammu|assam|guwahati|jharkhand|ranchi|jamshedpur|chhattisgarh|raipur|goa|panaji|puducherry|pondicherry|"
    r"\bmh\b|\bka\b|\btn\b|\bup\b|\bhr\b|\bdl\b|\btg\b|\bgj\b",
    re.I,
)
BENGALURU = re.compile(r"bengaluru|bangalore", re.I)
_STATE_CODES = re.compile(r"\b(?:mh|ka|tn|up|hr|dl|tg|gj)\b", re.I)


def is_indian_place(text: str | None) -> bool:
    """True when the text names India or an Indian state or city. State abbreviations (KA, MH ...) only count when no
    other country is named, so 'Remote - UP, United States' is not mistaken for Uttar Pradesh."""
    t = (text or "").strip()
    if not t:
        return False
    if INDIA.search(re.sub(_STATE_CODES, "", t)):
        return True
    return bool(_STATE_CODES.search(t)) and not re.search(r"united states|usa|canada|uk|europe|germany|israel|australia", t, re.I)


def is_bengaluru(text: str | None) -> bool:
    return bool(BENGALURU.search(text or ""))
