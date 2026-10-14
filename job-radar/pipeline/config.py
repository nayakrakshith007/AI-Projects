"""Settings of the combined pipeline: which site workflows run, where their workbooks are, and where the result goes."""
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT_DIR = HERE / "output"
EXCEL_PATH = OUTPUT_DIR / "Job_Radar.xlsx"
LOGS_DIR = OUTPUT_DIR / "logs"
SUMMARY_PATH = OUTPUT_DIR / "last_run.json"
CONTROL_DIR = OUTPUT_DIR / "control"                    # commands from the tracker to a running pipeline (stop / restart one site)
ROLE_PATTERNS = HERE / "role_patterns.csv"          # role, title_pattern (the old project's validated patterns), tech yes/no
INPUT_FILE = ROOT / "input.csv"

TASK_NAME = "Job Radar V2 Daily"
RUN_TIME = "09:00"
SITE_TIMEOUT_MIN = 90                               # a site workflow still running this long (from its own start) is stopped; its saved results stay
SITE_TIMEOUTS = {"naukri": 240}                    # Naukri is paced slowly on purpose and saves after every search, so it gets longer
STALL_SEC = 120                                      # a site whose log has not changed for this long is stuck: it is stopped and started again
SAVE_STALL_FACTOR = 5                               # while a site is writing its Excel file (its log says so) it may be silent this many times longer
MAX_RERUNS = 2                                      # how many times a stuck site is started again at once before it is marked stalled
MIN_FREE_MB = 1000                                  # a site starts only when this much memory is free
MEMORY_WAIT_MIN = 20                                # waiting longer than this for memory: the site is skipped for now and retried at the end
RETRY_FAILED = True                                 # a stalled, timed-out, failed or skipped site gets one more try, alone, at the end
POPUP_AT_END = True
ROLE_SCOPE = "tech"                                 # "tech": only the tech roles for now (Ayurveda, clinical and drug roles are parked); "all": every role in input.csv
ACTIVE_INPUT: Path | None = None                    # the input file passed to the sites (set by `pipeline run` when the scope is not "all")


class Site(NamedTuple):
    name: str                  # also the folder name
    sheet: str                 # worksheet name in the site's workbook
    workbook: Path
    args: tuple[str, ...]      # command line after `python -m <name> search`
    priority: int              # lower = richer data: wins when two sites report the same job


def _site(name: str, sheet: str, priority: int, *args: str) -> Site:
    return Site(name, sheet, ROOT / name / "output" / f"{sheet}.xlsx", args, priority)


# Chrome counts are lowered from each workflow's own default because several sites run at the same time.
SITES = [
    _site("hirist", "Hirist", 1, "--workers", "3"),
    _site("iimjobs", "IIMJobs", 2, "--workers", "2"),
    _site("cutshort", "Cutshort", 3),
    _site("wellfound", "Wellfound", 4, "--workers", "4"),
    _site("indeed", "Indeed", 5),
    _site("naukri", "Naukri", 6, "--workers", "3"),
    _site("linkedin", "LinkedIn", 7),
]
SITE_BY_NAME = {s.name: s for s in SITES}

# Lanes run side by side; the sites inside a lane run one after another. LinkedIn, Indeed and Naukri are long and use one Chrome each,
# so they start at once; the short, wider sites share one lane so only a few Chromes are open at any time (about 8 at the peak).
SERIES_ORDER = ["cutshort", "hirist", "iimjobs", "wellfound", "indeed", "linkedin", "naukri"]      # --series: one site at a time, shortest first
LANES = [["linkedin"], ["indeed"], ["naukri"], ["hirist", "iimjobs", "cutshort", "wellfound"]]


def lanes_for(sites: list["Site"], series: bool = False) -> list[list["Site"]]:
    """The lanes restricted to the selected sites (sites outside LANES get a lane of their own). With `series` every site is in one lane."""
    if series:
        order = {n: i for i, n in enumerate(SERIES_ORDER)}
        return [sorted(sites, key=lambda s: order.get(s.name, 99))]
    chosen = {s.name: s for s in sites}
    lanes = [[chosen.pop(n) for n in lane if n in chosen] for lane in LANES]
    lanes += [[s] for s in chosen.values()]
    return [lane for lane in lanes if lane]


def role_names(tech: bool) -> set[str]:
    """Role names from role_patterns.csv that are tech (tech=True) or not."""
    import csv
    with open(ROLE_PATTERNS, newline="", encoding="utf-8") as f:
        return {r["role"] for r in csv.DictReader(f) if r.get("role") and (r["tech"].strip().lower() == "yes") == tech}


def scoped_input() -> Path | None:
    """For the tech scope: write pipeline/output/input_tech.csv (input.csv without the parked roles) and return it. None for scope 'all'."""
    import csv
    if ROLE_SCOPE != "tech":
        return None
    keep = role_names(True)
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, [r for r in reader if r["Role"] in keep]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "input_tech.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def activate_scope() -> str:
    """Prepare the roles for a run: sets ACTIVE_INPUT (tech scope) and returns a line that says what will be read."""
    global ACTIVE_INPUT
    ACTIVE_INPUT = scoped_input()
    return ("roles: tech roles only (Ayurveda, clinical and drug roles are parked)" if ROLE_SCOPE == "tech" else "roles: all roles")         + (f", input file {ACTIVE_INPUT.name}" if ACTIVE_INPUT else "")
