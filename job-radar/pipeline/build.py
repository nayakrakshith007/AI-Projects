"""Build the one combined workbook: Job_Radar.xlsx.

Tabs: 'New today' (first seen today), 'All' (every matched job), one tab per role, and 'Unmatched' (titles that fit no role).
Rows are ranked: Bengaluru first, then remote, then the rest of India; newest first inside each. Status, Notes and First seen are kept
between rebuilds (matched by any of the job's links), so edit them in any tab; the 'All' tab wins if two tabs disagree."""
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import config
from .dedupe import dedupe, rank_key
from .route import load_patterns, route

HEADERS = ["Roles", "Title", "Company", "Location", "Bengaluru", "Work mode", "Experience", "Salary", "Posted date", "Sites", "Skills",
           "First seen", "Link", "Other links", "Status", "Notes"]
WIDTHS = {"Roles": 20, "Title": 46, "Company": 28, "Location": 24, "Bengaluru": 10, "Work mode": 14, "Experience": 12, "Salary": 14,
          "Posted date": 12, "Sites": 20, "Skills": 40, "First seen": 12, "Link": 8, "Other links": 30, "Status": 14, "Notes": 30}
STATUSES = ["New", "Interested", "Applied", "Not relevant"]
FIXED_TABS = ("New today", "All", "Unmatched")
THIN = Side(style="thin", color="BFC7D1")
EXCEL_SHEET_LIMIT = 31


def _read_previous(path: Path) -> dict[str, dict]:
    """Status, Notes and First seen from an earlier workbook, by link."""
    if not path.exists():
        return {}
    wb = load_workbook(path)
    prev: dict[str, dict] = {}
    order = [n for n in wb.sheetnames if n not in ("All",)] + [n for n in wb.sheetnames if n == "All"]
    for name in order:
        ws = wb[name]
        names = [c.value for c in ws[1]]
        if "Link" not in names:
            continue
        idx = {n: i for i, n in enumerate(names)}
        for row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            cell = ws.cell(row=row_no, column=idx["Link"] + 1)
            urls = [cell.hyperlink.target] if cell.hyperlink and cell.hyperlink.target else []
            urls += [u.strip() for u in str(row[idx["Other links"]] or "").splitlines() if u.strip()] if "Other links" in idx else []
            status = row[idx["Status"]] if "Status" in idx else None
            notes = row[idx["Notes"]] if "Notes" in idx else None
            seen = row[idx["First seen"]] if "First seen" in idx else None
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


def _apply_previous(job: dict, prev: dict[str, dict]) -> None:
    hits = [prev[u] for _, u in job["links"] if u in prev]
    job["status"] = next((h["status"] for h in hits if h["status"]), "New")
    job["notes"] = " | ".join(dict.fromkeys(h["notes"] for h in hits if h["notes"]))
    seen = [h["first_seen"] for h in hits if h["first_seen"]] + ([job["first_seen"]] if job.get("first_seen") else [])
    job["first_seen"] = min(seen) if seen else None


def _sheet_name(name: str) -> str:
    return name[:EXCEL_SHEET_LIMIT]


def _write_sheet(wb: Workbook, name: str, jobs: list[dict]) -> None:
    ws = wb.create_sheet(_sheet_name(name))
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for j in jobs:
        ws.append([
            "; ".join(j["roles"]), j["title"], j["company"], j["location"], "Yes" if j["bengaluru"] else "", j["work_mode"], j["experience"],
            j["salary"], j["posted_date"], ", ".join(j["sites"]), j["skills"], j["first_seen"], "Open", "\n".join(j["other_links"]),
            j["status"], j["notes"],
        ])
        ws.cell(row=ws.max_row, column=HEADERS.index("Link") + 1).hyperlink = j["url"]
    link_col, date_cols = HEADERS.index("Link"), {HEADERS.index("Posted date"), HEADERS.index("First seen")}
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
            c.alignment = Alignment(vertical="top")
            c.font = Font(name="Calibri", size=10, color="0563C1", underline="single") if c.column - 1 == link_col else Font(name="Calibri", size=10)
            if c.column - 1 in date_cols:
                c.number_format = "yyyy-mm-dd"
    for i, h in enumerate(HEADERS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS[h]
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    letter = get_column_letter(HEADERS.index("Status") + 1)
    dv.add(f"{letter}2:{letter}{max(ws.max_row, 2)}")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def combine(site_jobs: dict[str, list[dict]]) -> tuple[list[dict], list[dict], dict]:
    """Route, de-duplicate and rank. Returns (matched, unmatched, stats)."""
    patterns = load_patterns()
    everything = [j for jobs in site_jobs.values() for j in jobs]
    route(everything, patterns)
    parked = 0
    if config.ROLE_SCOPE == "tech":      # jobs found by a parked (non-tech) role search and fitting no tech role are left out for now
        parked_roles = config.role_names(False)
        keep = []
        for j in everything:
            parts = [p.strip() for p in re.split(r"[;,]", j.get("role_hint") or "") if p.strip()]
            if not j["roles"] and parts and all(p in parked_roles for p in parts):
                parked += 1
            else:
                keep.append(j)
        everything = keep
    merged = dedupe(everything)
    matched = sorted((j for j in merged if j["roles"]), key=rank_key)
    unmatched = sorted((j for j in merged if not j["roles"]), key=rank_key)
    stats = {"read": {s: len(j) for s, j in site_jobs.items()}, "total_read": len(everything), "unique": len(merged),
             "duplicates_removed": len(everything) - len(merged), "matched": len(matched), "unmatched": len(unmatched),
             "on_several_sites": sum(1 for j in merged if len(j["sites"]) > 1), "parked_non_tech": parked}
    return matched, unmatched, stats


def build(site_jobs: dict[str, list[dict]], path: Path = config.EXCEL_PATH, today: date | None = None) -> tuple[Path, dict]:
    """Write Job_Radar.xlsx. If Excel has it open, a timestamped copy is written instead. Returns (file written, stats)."""
    today = today or date.today()
    matched, unmatched, stats = combine(site_jobs)
    prev = _read_previous(path)
    for j in matched + unmatched:
        _apply_previous(j, prev)
    new_today = [j for j in matched if j["first_seen"] == today]
    roles = [p.role for p in load_patterns()]

    def make() -> Workbook:
        wb = Workbook()
        wb.remove(wb.active)
        _write_sheet(wb, "New today", new_today)
        _write_sheet(wb, "All", matched)
        for r in roles:
            _write_sheet(wb, r, [j for j in matched if r in j["roles"]])
        _write_sheet(wb, "Unmatched", unmatched)
        return wb

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        make().save(path)
        written = path
    except PermissionError:
        written = path.with_name(f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        make().save(written)
    by_role = Counter(r for j in matched for r in j["roles"])
    stats.update({"new_today": len(new_today), "new_today_bengaluru": sum(1 for j in new_today if j["bengaluru"]),
                  "by_role": {r: by_role.get(r, 0) for r in roles}, "bengaluru": sum(1 for j in matched if j["bengaluru"]),
                  "written": written.name})
    return written, stats
