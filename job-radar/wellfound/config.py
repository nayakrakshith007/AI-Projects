"""All Wellfound settings in one place. Public pages only: no login, ever."""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROFILE_DIR = ROOT / "data" / "wellfound_profile"     # saved Chrome profile (never committed)
OUTPUT_DIR = HERE / "output"                           # everything the workflow produces
EXCEL_PATH = OUTPUT_DIR / "Wellfound.xlsx"
STATE_PATH = OUTPUT_DIR / "state.json"                 # latest posted date a complete run has read (sets the next window)
RUNS_DIR = OUTPUT_DIR / "runs"                         # one raw JSONL backup per run
SLUGS_FILE = HERE / "slugs.csv"                        # keyword -> Wellfound role page

BASE = "https://wellfound.com"
INDIA_PAGE = BASE + "/role/l/{slug}/india"             # jobs in India
REMOTE_PAGE = BASE + "/role/r/{slug}"                  # remote jobs, mostly US-based: flagged, eligibility unclear
JOB_LINK = "a[href*='/jobs/']"
CARD_CLASSES = ("mb-6", "w-full", "rounded", "border")  # one company block, holding one or more job rows

# Politeness: small and slow on purpose. Seconds, picked at random in the range.
PAUSE_AFTER_LOAD = (3, 6)
PAUSE_BETWEEN_PAGES = (7, 15)
PAUSE_BETWEEN_TARGETS = (20, 40)
WORKERS_MAX = 8                                        # one Chrome per role, at most this many at the same time
START_STAGGER = (4, 10)                                # seconds added between the starts of the first Chromes
SCROLL_STEPS = (2, 4)
SCROLL_PIXELS = (600, 1000)
MAX_PAGES = 100            # Wellfound itself shows at most 100 pages per list, so this is the only ceiling
CARDS_TIMEOUT_MS = 15000
MAX_WINDOW_HOURS = 168         # only jobs posted within the last week are wanted, however long a run was missed
TECH_ONLY_MIN_EXPERIENCE = 1   # only roles whose minimum experience in input.csv is at least this are searched

# If one of these appears on a page with no job cards, Wellfound is asking for a human check.
CHECK_MARKERS = ("verify you are human", "captcha", "access denied", "checking your browser", "press & hold", "unusual traffic")


def worker_profile(slot: int) -> Path:
    """Chrome allows one process per profile folder, so every parallel Chrome has its own."""
    return ROOT / "data" / "wellfound_profiles" / f"w{slot}"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
