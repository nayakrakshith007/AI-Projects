"""All LinkedIn settings in one place. Public job data only: no login, ever."""
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROFILE_DIR = ROOT / "data" / "linkedin_profile"   # saved Chrome profile for the browser engine (never committed)
OUTPUT_DIR = HERE / "output"                       # everything the workflow produces
EXCEL_PATH = OUTPUT_DIR / "LinkedIn.xlsx"
STATE_PATH = OUTPUT_DIR / "state.json"            # latest posted date a complete run has read (sets the next window)
RUNS_DIR = OUTPUT_DIR / "runs"                     # one raw JSONL backup per run

# ---- Engine 1 (default): JobSpy, ten jobs per request, several searches in parallel ----
WORKERS = 3                  # searches running at the same time
START_STAGGER = (5, 15)      # seconds added between the starts of the first workers
BATCH = 10                   # LinkedIn's guest API returns ten jobs per request
MAX_BATCHES = 60             # safety ceiling per search (600 jobs); paging normally ends on an empty batch
# Each search draws its own pause profile: low = DELAY_LOW, high = low + DELAY_SPREAD, then every pause is random in [low, high].
DELAY_LOW = (8, 15)
DELAY_SPREAD = (10, 20)
BACKOFF = (60, 120)          # wait after LinkedIn pushes back (HTTP 429), then retry the same page once more
MAX_BLOCKS_PER_QUERY = 2     # give up on one search after this many pushbacks in a row
STOP_AFTER_BLOCKED_QUERIES = 3   # stop the whole run after this many searches gave up

# ---- Engine 2 (fallback): real Chrome on the public search pages ----
BASE = "https://www.linkedin.com/jobs/search/"
CARD_SELECTOR = "div.base-search-card"
MORE_BUTTON = "button.infinite-scroller__show-more-button"
PAUSE_AFTER_LOAD = (4, 8)
PAUSE_BETWEEN_SCROLLS = (2.5, 5.5)
PAUSE_BETWEEN_TERMS = (30, 60)
MAX_CARDS = 1000          # LinkedIn shows about 1000 results per search at most
STALE_ROUNDS = 3          # stop after this many scrolls that bring no new cards
CHECK_MARKERS = ("join linkedin to see", "security verification", "let's do a quick security check", "captcha", "unusual activity")
CHECK_URL_PARTS = ("/authwall", "/login", "/checkpoint")


def place(location: str) -> str:
    """Location text LinkedIn understands: a bare city gets ', India' added."""
    loc = (location or "India").strip()
    return loc if "india" in loc.lower() else f"{loc}, India"


def search_url(term: str, hours: int, location: str = "India") -> str:
    """Public search, newest first, posted within `hours` (LinkedIn takes seconds in f_TPR)."""
    return f"{BASE}?keywords={quote(term)}&location={quote(place(location))}&f_TPR=r{int(hours) * 3600}&sortBy=DD"
