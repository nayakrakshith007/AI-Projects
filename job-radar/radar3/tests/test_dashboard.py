"""The dashboard builder: the data is embedded safely, the page's script is valid JavaScript, and the shipped snapshot fields are the ones the page reads."""
import json
import shutil
import subprocess

import pytest

from radar3 import dashboard

SNAP = {"generated": "2026-10-13T08:30:00", "stats": {"remote_open_to_india": 1}, "jobs": [
    {"roles": ["ML Engineer"], "title": "ML </script><b>Engineer", "company": "Acme", "location": "Bengaluru, India", "more_locations": "", "tier": 2, "bengaluru": True, "remote": False,
     "eligibility": "india", "work_mode": "", "salary": "", "skills": "python, sql", "posted": "2026-10-12", "first_seen": "2026-10-13", "sites": ["Src (S1)"], "source_types": ["Platform"],
     "url": "https://x.test/1", "other_links": [], "status": "New"}]}


def test_render_embeds_the_snapshot_and_escapes_script_tags():
    html = dashboard.render(SNAP)
    assert "__DATA__" not in html and '"company": "Acme"' in html
    assert "</script><b>" not in html and "<" + chr(92) + "/script><b>" in html          # a job title cannot close the data block
    assert html.count("</script>") == 2                                      # the data block and the page script


def test_build_dashboard_writes_a_single_file(tmp_path):
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps(SNAP), encoding="utf-8")
    out = dashboard.build_dashboard(snap, tmp_path / "Dashboard.html")
    assert out.exists() and out.read_text(encoding="utf-8").startswith("<!doctype html>")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_script_is_valid_javascript(tmp_path):
    import re
    html = dashboard.render(SNAP)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    js = tmp_path / "page.js"
    js.write_text(scripts[-1], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
