"""All Cutshort settings in one place. Public pages only: no login, ever."""
import csv
import re
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT_DIR = HERE / "output"                       # everything the workflow produces
EXCEL_PATH = OUTPUT_DIR / "Cutshort.xlsx"
STATE_PATH = OUTPUT_DIR / "state.json"             # latest posted date a complete run has read (sets the next window)
RUNS_DIR = OUTPUT_DIR / "runs"                     # one raw JSONL backup per run
LISTS_FILE = HERE / "lists.csv"                    # the public Cutshort job lists that are read

BASE = "https://cutshort.io"
MAX_WINDOW_HOURS = 168                             # only jobs posted within the last week are wanted
DESCRIPTION_LIMIT = 32000                          # an Excel cell holds at most 32,767 characters

# Politeness: one Chrome, a handful of pages, slow on purpose. Seconds, picked at random in the range.
PAUSE_AFTER_LOAD = (3, 6)
PAUSE_BETWEEN_PAGES = (6, 12)
LOAD_TIMEOUT_MS = 20000
CHECK_MARKERS = ("verify you are human", "captcha", "access denied", "checking your browser", "press & hold", "unusual traffic")


class JobList(NamedTuple):
    slug: str        # cutshort.io/jobs/<slug>
    label: str       # shown in the workbook, e.g. "Data Science, Bengaluru"


def list_url(slug: str) -> str:
    return f"{BASE}/jobs/{slug}"


def load_lists(path: Path = LISTS_FILE) -> list[JobList]:
    with open(path, newline="", encoding="utf-8") as f:
        return [JobList(r["slug"].strip(), r["label"].strip()) for r in csv.DictReader(f) if r.get("slug", "").strip()]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
