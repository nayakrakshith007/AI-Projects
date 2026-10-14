"""Batch discovery with the Playwright CLI: for every source still waiting, open its career page (Edge, headless), list the network requests, and keep the
JSON responses that look like job lists. Everything goes to files; only a compact summary is printed. One site takes about 25 seconds.
Output: discovery/auto/<id>.json (candidates with request and response heads) and discovery/auto_summary.csv.   usage: python discovery/auto_discover.py [ids...]"""
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
OUT = ROOT / "discovery" / "auto"
OUT.mkdir(exist_ok=True)
JOBISH = re.compile(r'"(?:title|jobTitle|job_title|positionTitle|postingTitle|name|requisition\w*|jobId|job_id|location|city)"', re.I)
STATIC = re.compile(r"\.(png|svg|woff2?|css|jpg|jpeg|gif|ico|js|map|mp4|webp)(\?|$)|analytics|googletag|doubleclick|facebook|linkedin\.com/li|hotjar|onetrust|cookie|fonts\.|pixel|clarity|newrelic|datadog|adobedtm|demdex|tiktok|bing\.com|criteo|gstatic|recaptcha|sentry|segment|mixpanel|optimizely|cloudfront.*(js|css)", re.I)


def kill_tree(pid: int) -> None:
    subprocess.run(f"taskkill /PID {pid} /T /F", shell=True, capture_output=True)


def cli(*args, timeout=60) -> str:
    """Run one playwright-cli command. On a timeout the whole process tree is killed (killing only the shell leaves node holding the pipes and hangs the batch)."""
    proc = subprocess.Popen("npx playwright-cli " + " ".join(args), cwd=TOOLS, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out or ""
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return "TIMEOUT"


SITE_LIMIT_SEC = 150          # one site never takes longer than this; then its browser is killed and the batch moves on
MAX_BODIES = 12               # response bodies read per site


def discover(sid: str, name: str, url: str) -> dict:
    t_start = time.time()
    res = {"id": sid, "name": name, "url": url, "requests": 0, "challenge": False, "candidates": [], "error": ""}
    out = cli("open", f'"{url}"', "--browser=msedge", timeout=120)
    if "TIMEOUT" in out:
        res["error"] = "open timed out"
        cli("close", timeout=30)
        return res
    time.sleep(7)
    req = cli("requests")
    lines = re.findall(r"^(\d+)\. \[(GET|POST|PUT)\] (\S+) => \[(\d+|FAILED)\]", req, re.M)
    res["requests"] = len(lines)
    res["challenge"] = bool(re.search(r"challenge-platform|cdn-cgi/challenge|captcha", req, re.I)) or any(s == "403" for n, m, u, s in lines[:3])
    cands, bodies = [], 0
    for n, method, u, status in lines:
        if time.time() - t_start > SITE_LIMIT_SEC or bodies >= MAX_BODIES:
            res["error"] = "stopped early (time or body limit)"
            break
        if status != "200" or STATIC.search(u) or u.startswith("blob:") or u.startswith("data:"):
            continue
        bodies += 1
        body = cli("response-body", n, timeout=25)
        if not body or len(body) < 400 or body.lstrip()[:1] not in "{[" and "###" not in body[:5]:
            continue
        text = body.split("### Result", 1)[-1].strip() if "### Result" in body else body
        if text[:1] not in "{[":
            continue
        hits = len(JOBISH.findall(text))
        if hits < 6:
            continue
        reqbody = cli("request-body", n, timeout=25).split("### Result", 1)[-1].strip() if method == "POST" else ""
        cands.append({"n": n, "method": method, "url": u[:300], "bytes": len(text), "hits": hits, "head": re.sub(r"\s+", " ", text[:220]), "req_body": reqbody[:1500]})
    cands.sort(key=lambda c: -c["hits"])
    res["candidates"] = cands[:4]
    cli("close", timeout=30)
    return res


if __name__ == "__main__":
    want = set(sys.argv[1:])
    rows = [r for r in csv.DictReader(open(ROOT / "radar3" / "data" / "sources.csv", encoding="utf-8"))
            if r["enabled"] == "no" and r["cls"] in ("B", "C") and (not want or r["id"] in want) and r["url"].startswith("http")]
    print(len(rows), "sites to look at", flush=True)
    summary = []
    for i, r in enumerate(rows, 1):
        path = OUT / f"{r['id']}.json"
        if path.exists() and not want:
            continue
        t = time.time()
        try:
            res = discover(r["id"], r["name"], r["url"])
        except Exception as e:                                       # one bad site must not stop the batch
            res = {"id": r["id"], "name": r["name"], "url": r["url"], "requests": 0, "challenge": False, "candidates": [], "error": f"{type(e).__name__}: {str(e)[:80]}"}
            cli("close", timeout=30)
        path.write_text(json.dumps(res, indent=1), encoding="utf-8")
        top = res["candidates"][0] if res["candidates"] else None
        print(f"[{i}/{len(rows)}] {r['id']} {r['name'][:22]:22} {time.time() - t:4.0f}s req={res['requests']:3} chal={int(res['challenge'])} cands={len(res['candidates'])} "
              f"{(top['method'] + ' ' + top['url'][:80]) if top else res['error']}", flush=True)
