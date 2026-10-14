"""Write Job_Radar_V3.xlsx and snapshot.json from the jobs of every source.

Columns: the 16 of V2 (so the Workspace/dashboard code works on it) plus 'Source type' and 'Check' ('check eligibility' for remote roles
whose location does not say whether India is allowed). Tabs: 'New today', 'All', one per role, 'Unmatched'.
Status, Notes and First seen survive rebuilds, matched by any of the job's links."""
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from common.safe_save import save_workbook

from . import config, roles
from .combine import combine

HEADERS = ["Roles", "Title", "Company", "Location", "Bengaluru", "Work mode", "Experience", "Salary", "Posted date", "Sites", "Skills",
           "First seen", "Link", "Other links", "Status", "Notes", "Source type", "Check"]
WIDTHS = {"Roles": 22, "Title": 46, "Company": 26, "Location": 26, "Bengaluru": 10, "Work mode": 12, "Experience": 12, "Salary": 16, "Posted date": 12,
          "Sites": 22, "Skills": 36, "First seen": 12, "Link": 8, "Other links": 30, "Status": 14, "Notes": 30, "Source type": 12, "Check": 18}
STATUSES = ["New", "Interested", "Applied", "Not relevant"]
THIN = Side(style="thin", color="BFC7D1")


def sheet_name(name: str) -> str:
    """Excel sheet names: no / \\ ? * [ ] : and at most 31 characters."""
    return re.sub(r"[/\\?*\[\]:]", "-", name)[:31]


def _read_previous(path: Path) -> dict[str, dict]:
    """Status, Notes and First seen from an earlier workbook, by link."""
    if not path.exists():
        return {}
    wb = load_workbook(path)
    prev: dict[str, dict] = {}
    # 'Unmatched' (thousands of rows nobody edits) is not read: it was the slowest part of every build. 'All' last: it wins
    for name in [n for n in wb.sheetnames if n not in ("All", "Unmatched")] + [n for n in wb.sheetnames if n == "All"]:
        ws = wb[name]
        names = [c.value for c in ws[1]]
        if "Link" not in names:
            continue
        idx = {n: i for i, n in enumerate(names)}
        for row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            cell = ws.cell(row=row_no, column=idx["Link"] + 1)
            urls = [cell.hyperlink.target] if cell.hyperlink and cell.hyperlink.target else []
            urls += [u.strip() for u in str(row[idx["Other links"]] or "").splitlines() if u.strip()] if "Other links" in idx else []
            status, notes, seen = (row[idx[k]] if k in idx else None for k in ("Status", "Notes", "First seen"))
            seen = seen.date() if isinstance(seen, datetime) else seen if isinstance(seen, date) else None
            for u in urls:
                p = prev.setdefault(u, {"status": "", "notes": "", "first_seen": None})
                if status and status != "New":
                    p["status"] = status
                if notes:
                    p["notes"] = str(notes)
                if seen and (p["first_seen"] is None or seen < p["first_seen"]):
                    p["first_seen"] = seen
    wb.close()
    return prev


def import_v2(src: Path | None = None, dest: Path | None = None) -> int:
    """Read V2's workbook (read only) and save the Status, Notes and First seen of its jobs, by link, to the seed file that every build merges.
    V2's workbook has the same 16 columns as V3's, so the same reader is used. Returns the number of links saved."""
    prev = _read_previous(src or config.V2_WORKBOOK)
    data = {u: {"status": p["status"], "notes": p["notes"], "first_seen": p["first_seen"].isoformat() if p["first_seen"] else ""}
            for u, p in prev.items() if p["status"] or p["notes"] or p["first_seen"]}
    dest = dest or config.V2_SEED_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return len(data)


def _merge_seed(prev: dict[str, dict], seed_path: Path | None = None) -> dict[str, dict]:
    """Add what V2 knew. V3's own values win; for First seen the earlier date wins."""
    seed_path = seed_path or config.V2_SEED_PATH
    if not seed_path.exists():
        return prev
    for url, s in json.loads(seed_path.read_text(encoding="utf-8")).items():
        p = prev.setdefault(url, {"status": "", "notes": "", "first_seen": None})
        if s.get("status") and not p["status"]:
            p["status"] = s["status"]
        if s.get("notes") and not p["notes"]:
            p["notes"] = s["notes"]
        seen = date.fromisoformat(s["first_seen"]) if s.get("first_seen") else None
        if seen and (p["first_seen"] is None or seen < p["first_seen"]):
            p["first_seen"] = seen
    return prev


def _apply_previous(job: dict, prev: dict[str, dict], today: date) -> None:
    hits = [prev[u] for _, u in job["links"] if u in prev]
    job["status"] = next((h["status"] for h in hits if h["status"]), "New")
    job["notes"] = " | ".join(dict.fromkeys(h["notes"] for h in hits if h["notes"]))
    seen = [h["first_seen"] for h in hits if h["first_seen"]]
    job["first_seen"] = min(seen) if seen else today


def _row(j: dict) -> list:
    return ["; ".join(j["roles"]), j["title"], j["company"], j["location"] + (f"; {j['more_locations']}" if j.get("more_locations") else ""),
            "Yes" if j["bengaluru"] else "", j["work_mode"], j["experience"], j["salary"], j["posted_date"], ", ".join(j["sites"]), j["skills"],
            j["first_seen"], "Open", "\n".join(j["other_links"]), j["status"], j["notes"], ", ".join(j["source_types"]),
            "check eligibility" if j["eligibility"] == "unclear" else ""]


def _write_sheet(wb: Workbook, name: str, jobs: list[dict], plain: bool = False) -> None:
    """plain: header, links, widths and filter only, no per-cell fonts and borders (used for the very long Unmatched tab; about 5 times faster)."""
    ws = wb.create_sheet(sheet_name(name))
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    li = HEADERS.index("Link")
    for j in jobs:
        row = _row(j)
        if plain:
            row[li] = j["url"]                                      # plain URL text: a clickable hyperlink object per row is what made this tab slow
            ws.append(row)
        else:
            ws.append(row)
            ws.cell(row=ws.max_row, column=li + 1).hyperlink = j["url"]
    link_col, date_cols = HEADERS.index("Link"), {HEADERS.index("Posted date"), HEADERS.index("First seen")}
    for row in (() if plain else ws.iter_rows(min_row=2)):
        for c in row:
            c.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
            c.alignment = Alignment(vertical="top")
            c.font = Font(name="Calibri", size=10, color="0563C1", underline="single") if c.column - 1 == link_col else Font(name="Calibri", size=10)
            if c.column - 1 in date_cols:
                c.number_format = "yyyy-mm-dd"
    for i, h in enumerate(HEADERS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS[h]
    if not plain:
        dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        letter = get_column_letter(HEADERS.index("Status") + 1)
        dv.add(f"{letter}2:{letter}{max(ws.max_row, 2)}")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def _snapshot_job(j: dict) -> dict:
    return {"roles": j["roles"], "title": j["title"], "company": j["company"], "location": j["location"], "more_locations": j.get("more_locations", ""),
            "tier": j["tier"], "bengaluru": j["bengaluru"], "remote": j["remote"], "eligibility": j["eligibility"], "work_mode": j["work_mode"],
            "salary": j["salary"], "skills": j["skills"], "posted": j["posted_date"].isoformat() if j["posted_date"] else "",
            "first_seen": j["first_seen"].isoformat() if j["first_seen"] else "", "sites": j["sites"], "source_types": j["source_types"], "url": j["url"],
            "other_links": j["other_links"], "status": j["status"]}


def build(jobs_by_source: dict[str, list[dict]], path: Path = config.EXCEL_PATH, snapshot_path: Path | None = config.SNAPSHOT_PATH,
          today: date | None = None) -> tuple[Path, dict]:
    """Write the workbook (and the dashboard snapshot). If Excel has the workbook open, a timestamped copy is written. Returns (file, stats)."""
    today = today or date.today()
    matched, unmatched, stats = combine(jobs_by_source)
    prev = _merge_seed(_read_previous(path))
    for j in matched + unmatched:
        _apply_previous(j, prev, today)
    new_today = [j for j in matched if j["first_seen"] == today]
    role_names = [p.role for p in roles.load_patterns()]

    def make() -> Workbook:
        wb = Workbook()
        wb.remove(wb.active)
        _write_sheet(wb, "New today", new_today)
        _write_sheet(wb, "All", matched)
        for r in role_names:
            _write_sheet(wb, r, [j for j in matched if r in j["roles"]])
        _write_sheet(wb, "Unmatched", unmatched, plain=True)
        return wb

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        save_workbook(make(), path)
        written = path
    except PermissionError:
        written = path.with_name(f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        save_workbook(make(), written)
    by_role = Counter(r for j in matched for r in j["roles"])
    stats.update({"new_today": len(new_today), "by_role": {r: by_role.get(r, 0) for r in role_names}, "written": written.name})
    if snapshot_path:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps({"generated": datetime.now().isoformat(timespec="seconds"), "stats": stats,
                                             "jobs": [_snapshot_job(j) for j in matched]}, default=str), encoding="utf-8")
    return written, stats
