"""Build the dashboard: radar3/output/Dashboard.html, the template radar3/web/Dashboard.html with the last snapshot embedded in it.
The result is one file: double-click it, no server needed (the progress page also serves it at /dashboard). Rebuilt at the end of every run, or by hand:
  python -m radar3 dashboard"""
import json
from pathlib import Path

from . import config
from .fsutil import safe_replace

TEMPLATE = Path(__file__).resolve().parent / "web" / "Dashboard.html"
DASHBOARD_PATH = config.OUTPUT_DIR / "Dashboard.html"


def render(snapshot: dict) -> str:
    """The template with the snapshot inside. '</' is escaped so a job title can never close the script tag early."""
    data = json.dumps(snapshot, ensure_ascii=False, default=str).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", data, 1)


def build_dashboard(snapshot_path: Path | None = None, out: Path | None = None) -> Path:
    snapshot_path = snapshot_path or config.SNAPSHOT_PATH
    out = out or config.OUTPUT_DIR / "Dashboard.html"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(render(snapshot), encoding="utf-8")
    safe_replace(tmp, out)
    return out
