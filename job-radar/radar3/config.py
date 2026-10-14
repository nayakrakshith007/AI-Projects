"""Settings of the V3 radar: where things live, the local server port, and the run limits.
V3 never reads or writes anything of V2 (job-radar-V2); everything below is inside this folder."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = HERE / "data"
SOURCES_CSV = DATA_DIR / "sources.csv"
ROLE_PATTERNS = DATA_DIR / "role_patterns.csv"
OUTPUT_DIR = HERE / "output"
SOURCES_OUT = OUTPUT_DIR / "sources"                  # one json file per source: the jobs it returned in its last good run
EXCEL_PATH = OUTPUT_DIR / "Job_Radar_V3.xlsx"
STATE_PATH = OUTPUT_DIR / "run_state.json"            # live state of a run, read by the progress page
SNAPSHOT_PATH = OUTPUT_DIR / "snapshot.json"          # data for the dashboard
RUNS_PATH = OUTPUT_DIR / "runs.jsonl"                  # one line per finished run (the progress page shows the last ones)
HISTORY_PATH = OUTPUT_DIR / "history.jsonl"           # one line per source per run
SOURCE_STATS_PATH = OUTPUT_DIR / "source_stats.json"  # per source: last count, consecutive zero runs (the canary)
LAST_RUN_PATH = OUTPUT_DIR / "last_run.json"

V2_WORKBOOK = Path(os.environ.get("RADAR_V2_WORKBOOK", OUTPUT_DIR / "previous" / "Job_Radar.xlsx"))   # an earlier combined workbook (optional): read once by `import-v2`, never written
V2_SEED_PATH = DATA_DIR / "v2_history.json"                                                       # Status, Notes and First seen of V2's jobs, by link; the next builds merge it

PORT = 8771                                           # V2's tracker uses 8770, so both can run together
TASK_NAME = "Job Radar V3 Daily"
RUN_TIME = "08:30"
SCHEDULE_WITH_BOARDS = True                           # the one daily task (08:30) reads everything, the job boards included (visible Chrome, about 40 min). V2's own 09:00 task is disabled (2026-10-14): V3 is the only scheduler

HTTP_WORKERS = 8                                      # sources read at the same time (plain requests, no browser)
MIN_SECONDS_PER_HOST = 1.0                            # politeness: at most one request per host per second
HTTP_TIMEOUT = 25
HTTP_RETRIES = 2
SOURCE_RETRIES = 1                                    # a source that raises an error is read once more after a short wait
RETRY_WAIT_SEC = 4
SHRINK_KEEP_BELOW = 0.3                               # fewer jobs than this share of the usual count: keep the previous list (the read was probably partial)
SHRINK_FLAG_BELOW = 0.5                               # fewer than this share: save, but flag the source
MIN_COUNT_FOR_SHRINK = 20                             # only sources that usually return at least this many are judged for shrinking
HEALTH_PATH = OUTPUT_DIR / "health.json"
SOURCE_TIMEOUT_SEC = 300                              # a source still running after this is marked timed out
USER_AGENT = "Mozilla/5.0 (compatible; JobRadarV3/0.1; personal job search)"
