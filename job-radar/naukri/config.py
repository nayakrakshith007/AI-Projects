"""All Naukri settings in one place. Change behaviour here, not in the code."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "naukri_profile"   # saved Chrome session (never committed)
HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"                     # everything the workflow produces
EXCEL_PATH = OUTPUT_DIR / "Naukri.xlsx"
STATE_PATH = OUTPUT_DIR / "state.json"            # latest posted date a complete run has read (sets the next window)
RUNS_DIR = OUTPUT_DIR / "runs"                   # one raw JSONL backup per run

BASE = "https://www.naukri.com"
CARD_SELECTOR = "div.srp-jobtuple-wrapper"

# Politeness: small and slow on purpose. Seconds, picked at random in the range.
PAUSE_AFTER_LOAD = (3, 6)
PAUSE_BETWEEN_PAGES = (9, 20)
PAUSE_BETWEEN_TERMS = (25, 55)
SCROLL_STEPS = (3, 5)
SCROLL_PIXELS = (500, 900)
WORKERS = 1               # default for `naukri search`; the pipeline passes --workers 3 (tabs of one Chrome)
WORKERS_MAX = 3
MAX_PAGES = 15            # at most 15 pages (about 300 jobs) per search; paging also ends when a page adds no new jobs
CARDS_TIMEOUT_MS = 15000

# If one of these appears on a page with no job cards, Naukri is asking for a human check.
CHECK_MARKERS = ("check the box", "verify you are human", "captcha", "access denied", "unusual traffic")

# Naukri only filters by these day counts.
JOB_AGE_STEPS = (1, 3, 7, 15, 30)


def job_age_days(hours: int) -> int:
    """Smallest Naukri 'posted within' filter that covers the wanted window."""
    return next((d for d in JOB_AGE_STEPS if hours <= d * 24), JOB_AGE_STEPS[-1])


def slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def page_url(term: str, page: int, age_days: int, location: str = "India") -> str:
    """Public results page for a keyword in a place, e.g. /data-scientist-jobs-in-bengaluru?jobAge=1 (page n adds -n)."""
    return f"{BASE}/{slug(term)}-jobs-in-{slug(location) or 'india'}" + (f"-{page}" if page > 1 else "") + f"?jobAge={age_days}"
