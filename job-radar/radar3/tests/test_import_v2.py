"""import-v2: V2's Status, Notes and First seen are carried into V3 (V2's workbook is only read), and V3's own values win."""
import json
from datetime import date

from openpyxl import Workbook

from radar3 import build

HEAD = ["Roles", "Title", "Company", "Location", "Bengaluru", "Work mode", "Experience", "Salary", "Posted date", "Sites", "Skills", "First seen", "Link", "Other links", "Status", "Notes"]


def v2_workbook(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "All"
    ws.append(HEAD)
    rows = [("AI Engineer", "AI Engineer", "Acme", "Bengaluru", "Yes", "", "", "", None, "naukri", "", date(2026, 9, 1), "https://x/1", "https://y/1\nhttps://z/1", "Applied", "called HR"),
            ("AI Engineer", "ML Engineer", "Beta", "Pune", "", "", "", "", None, "linkedin", "", date(2026, 10, 5), "https://x/2", "", "New", "")]
    for i, r in enumerate(rows, start=2):
        ws.append(list(r))
        ws.cell(row=i, column=13).hyperlink = r[12]
    wb.save(path)


def test_import_saves_status_notes_first_seen_by_every_link_and_leaves_new_status_out(tmp_path):
    src, dest = tmp_path / "Job_Radar.xlsx", tmp_path / "seed.json"
    v2_workbook(src)
    assert build.import_v2(src, dest) == 4                                    # two jobs, the first with three links
    seed = json.loads(dest.read_text(encoding="utf-8"))
    assert seed["https://x/1"] == {"status": "Applied", "notes": "called HR", "first_seen": "2026-09-01"} and seed["https://z/1"]["status"] == "Applied"
    assert seed["https://x/2"]["status"] == "" and seed["https://x/2"]["first_seen"] == "2026-10-05"       # "New" is not a decision, so it is not carried


def test_merge_keeps_v3_values_and_the_earlier_first_seen(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"https://x/1": {"status": "Applied", "notes": "from V2", "first_seen": "2026-09-01"}, "https://x/9": {"status": "Interested", "notes": "", "first_seen": ""}}))
    prev = {"https://x/1": {"status": "Interested", "notes": "", "first_seen": date(2026, 10, 10)}}
    out = build._merge_seed(prev, seed)
    assert out["https://x/1"] == {"status": "Interested", "notes": "from V2", "first_seen": date(2026, 9, 1)}       # V3's status wins, V2's note fills a gap, the earlier date wins
    assert out["https://x/9"]["status"] == "Interested"


def test_merge_without_a_seed_file_changes_nothing(tmp_path):
    prev = {"https://x/1": {"status": "", "notes": "", "first_seen": None}}
    assert build._merge_seed(prev, tmp_path / "missing.json") is prev
