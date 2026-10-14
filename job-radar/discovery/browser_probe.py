"""Open one page with the Playwright library (system Edge, headless), scroll, and print a compact report: XHR/fetch calls that returned job-like JSON,
iframes, and job-looking links. usage: python discovery/browser_probe.py <url> [scrolls]"""
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, __file__.rsplit("discovery", 1)[0])
from discovery.html_scan import job_lists  # noqa: E402

url = sys.argv[1]
scrolls = int(sys.argv[2]) if len(sys.argv) > 2 else 3
seen = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu", "--blink-settings=imagesEnabled=false"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    def on_response(r):
        try:
            if r.request.resource_type in ("xhr", "fetch") and r.status == 200:
                body = r.text()
                if body[:1] in "{[" and len(body) > 300:
                    lists = job_lists(json.loads(body))
                    seen.append((r.request.method, r.url[:110], len(body), max(lists) if lists else None))
        except Exception:
            pass
    page.on("response", on_response)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    for _ in range(scrolls):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(2500)
    html = page.content()
    frames = [f.url[:90] for f in page.frames[1:] if f.url.startswith("http")]
    links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText.trim().slice(0,60), e.href]).filter(x => /job|career|position|opening|vacanc|requisition/i.test(x[1]) && x[0])")
    print("title:", page.title()[:80], "| html chars:", len(html), "| iframes:", frames[:4])
    print("json calls with job-like lists:")
    for m, u, n, jl in seen:
        if jl:
            print(f"  {m} {n // 1024}KB list={jl[0]} keys={jl[1][:4]} {u}")
    print("other JSON calls:", len([s for s in seen if not s[3]]))
    print("job-looking links:", len(links), links[:3])
    browser.close()
