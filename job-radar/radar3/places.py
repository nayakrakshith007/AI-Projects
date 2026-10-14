"""Where is a job, and can someone in India take it? Produces the ranking tier.

Owner's order (2026-10-13): remote roles open to India first, then Bengaluru, then Hyderabad or Chennai, then the rest of India.
  tier 0  remote and clearly open to India (worldwide / anywhere / Asia / India)
  tier 1  remote, India not mentioned either way: kept and flagged 'check eligibility'
  tier 2  Bengaluru
  tier 3  Hyderabad or Chennai
  tier 4  anywhere else in India
  None    not open to India (onsite abroad, or remote limited to another region): left out and counted"""
import re

from common.geo import is_bengaluru, is_indian_place

WORLDWIDE = re.compile(r"worldwide|world[\s-]*wide|anywhere|global|any\s+location|all\s+locations|international|apac|\basia\b|\bgmt\b\s*\+?\s*5|south asia|earth", re.I)
OTHER = re.compile(
    r"\b(us|usa|u\.s\.a?\.?|united states|north america|americas|canada|uk|united kingdom|england|europe|european|eu|emea|germany|france|spain|portugal|"
    r"poland|netherlands|ireland|italy|sweden|norway|denmark|finland|switzerland|austria|belgium|romania|ukraine|czech|brazil|latam|latin america|"
    r"mexico|argentina|colombia|chile|australia|new zealand|israel|uae|dubai|saudi|turkey|south africa|nigeria|kenya|egypt|singapore|japan|china|"
    r"korea|hong kong|taiwan|philippines|indonesia|malaysia|vietnam|thailand|london|new york|nyc|san francisco|sf|seattle|austin|boston|chicago|"
    r"los angeles|toronto|vancouver|berlin|paris|dublin|amsterdam|tel aviv|sydney|melbourne)\b",
    re.I,
)
US_STATES = re.compile(
    r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|"
    r"louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|"
    r"new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|"
    r"virginia|washington|west virginia|wisconsin|wyoming)\b", re.I)
US_ABBR = re.compile(r"(?<![A-Za-z])(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IA|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY|DC)(?![A-Za-z])")   # IN and OR left out: India, 'or'
HYD_CHENNAI = re.compile(r"hyderabad|secunderabad|chennai|madras", re.I)


def classify(location: str, more: str = "", remote: bool = False) -> dict:
    """{'remote', 'bengaluru', 'tier', 'eligibility'}; tier None means the job is not open to India."""
    text = f"{location or ''} {more or ''}".strip()
    is_remote = bool(remote or re.search(r"remote|work from home|wfh|telecommut|anywhere", text, re.I))
    bengaluru = bool(is_bengaluru(text))
    if is_indian_place(text):
        if is_remote:
            tier, elig = 0, "yes"
        elif bengaluru:
            tier, elig = 2, "india"
        elif HYD_CHENNAI.search(text):
            tier, elig = 3, "india"
        else:
            tier, elig = 4, "india"
    elif is_remote:
        if WORLDWIDE.search(text):
            tier, elig = 0, "yes"
        elif OTHER.search(text) or US_STATES.search(text) or US_ABBR.search(text):
            tier, elig = None, "no"
        else:
            tier, elig = 1, "unclear"
    else:
        tier, elig = None, "no"
    return {"remote": is_remote, "bengaluru": bengaluru, "tier": tier, "eligibility": elig}
