"""All Indeed settings in one place. Public job data only: no login."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT_DIR = HERE / "output"                     # everything the workflow produces
EXCEL_PATH = OUTPUT_DIR / "Indeed.xlsx"
STATE_PATH = OUTPUT_DIR / "state.json"            # latest posted date a complete run has read (sets the next window)
RUNS_DIR = OUTPUT_DIR / "runs"                   # one raw JSONL backup per run

COUNTRY = "India"            # Indeed site to use (in.indeed.com)
RESULTS = 100                # jobs asked for per search; Indeed returns what it has for the window
RESULTS_NO_WINDOW = 1000     # jobs asked for per search when there is no time filter (--hours 0)
WORKERS = 3                  # searches running at the same time
START_STAGGER = (3, 8)       # seconds added between the starts of the first workers
# Each search draws its own pause profile: low = DELAY_LOW, high = low + DELAY_SPREAD; the pause after a search is random in [low, high].
DELAY_LOW = (3, 7)
DELAY_SPREAD = (4, 9)
BACKOFF = (60, 120)          # wait after Indeed pushes back (HTTP 403/429), then try the same search once more
MAX_BLOCKS_PER_QUERY = 2     # give up on one search after this many pushbacks in a row
STOP_AFTER_BLOCKED_QUERIES = 3   # stop the whole run after this many searches gave up
SNIPPET_CHARS = 300          # characters of the description kept in Excel
PUSHBACK_MARKERS = ("429", "403", "rate limit", "forbidden", "blocked")


def place(location: str) -> str:
    """Location text Indeed understands: a bare city gets ', India' added."""
    loc = (location or "India").strip()
    return loc if "india" in loc.lower() else f"{loc}, India"
