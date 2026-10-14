"""All Hirist settings in one place. Public pages only: no login, ever."""
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT_DIR = HERE / "output"                       # everything the workflow produces
EXCEL_PATH = OUTPUT_DIR / "Hirist.xlsx"
STATE_PATH = OUTPUT_DIR / "state.json"             # latest posted date a complete run has read (sets the next window)
RUNS_DIR = OUTPUT_DIR / "runs"                     # one raw JSONL backup per run
COMPARE_PATH = OUTPUT_DIR / "compare_methods.csv"  # per role: what the tag method and the search method each found
TAGS_FILE = HERE / "tags.csv"                      # keyword -> Hirist tag pages (for the tag method)

BASE = "https://www.hirist.tech"
PAGE_SIZE = 20
CARD_SELECTOR = "div.joblist-card-v2"

# Hirist filters by date on its own server: posting=1|3|7|15|30 days. It also remembers filters between visits in the
# same browser, so every Chrome here starts with an empty state (a fresh browser context) and every URL names its filters.
POSTING_STEPS = (1, 3, 7, 15, 30)
MAX_WINDOW_HOURS = 168                             # only jobs posted within the last week are wanted
METHODS = ("search", "tag")

# Politeness: small and slow on purpose. Seconds, picked at random in the range.
WORKERS = 4                                        # Chromes sharing the page queue
WORKERS_MAX = 6
START_STAGGER = (3, 8)
PAUSE_AFTER_LOAD = (2, 4)
PAUSE_BETWEEN_PAGES = (5, 11)
RESPONSE_TIMEOUT_MS = 15000
MAX_PAGES = 100
CHECK_MARKERS = ("verify you are human", "captcha", "access denied", "checking your browser", "press & hold", "unusual traffic")


def posting_days(hours: int) -> int:
    """Smallest Hirist 'posted within' filter that covers the wanted window (never more than the 7 day cap)."""
    days = math.ceil(min(hours or MAX_WINDOW_HOURS, MAX_WINDOW_HOURS) / 24)
    return next(d for d in POSTING_STEPS if days <= d)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def tag_url(tag_slug: str, days: int, page: int) -> str:
    """Hirist's own tag page for a skill or role tag, e.g. /k/data-scientist-jobs?posting=7&page=2."""
    return f"{BASE}/k/{tag_slug}-jobs?posting={days}" + (f"&page={page}" if page > 1 else "")


def search_url(keyword_slug: str, days: int, page: int) -> str:
    """Hirist's free-text search for any keyword. The first page is page=0, the second page=2, and so on."""
    n = 0 if page <= 1 else page
    return (f"{BASE}/search/{keyword_slug}-jobs?loc=&minexp=0&maxexp=0&posting={days}&ref=homepage"
            f"&query={keyword_slug}&sort=&page={n}&industry=")
