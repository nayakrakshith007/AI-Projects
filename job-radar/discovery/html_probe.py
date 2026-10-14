"""Look at the HTML job-search pages of SuccessFactors, Avature and iCIMS sites to find where title, link, location and date sit."""
import re
import sys

import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (compatible; JobRadarV3-probe/0.3; personal job search)", "Accept-Language": "en"}
SAVE = sys.argv[1] if len(sys.argv) > 1 else ""


def get(url):
    r = requests.get(url, headers=H, timeout=30)
    print("\n###", r.status_code, r.url[:110], len(r.text))
    return r.text


def show(label, html, selectors):
    soup = BeautifulSoup(html, "html.parser")
    print(label)
    for sel in selectors:
        found = soup.select(sel)
        print("  ", sel, len(found), (found[0].get_text(" ", strip=True)[:80] if found else ""))
    return soup


# SuccessFactors
for name, url in [("EY", "https://careers.ey.com/ey/search/?q=data&locationsearch=India&startrow=0"),
                  ("StanChart", "https://jobs.standardchartered.com/search/?q=data&locationsearch=India&startrow=0"),
                  ("SAP", "https://jobs.sap.com/search/?q=data&locationsearch=India&startrow=0"),
                  ("Wipro", "https://careers.wipro.com/search/?q=data&locationsearch=India&startrow=0"),
                  ("HCLTech", "https://careers.hcltech.com/search/?q=data&locationsearch=India&startrow=0")]:
    try:
        t = get(url)
    except Exception as e:
        print(name, "ERR", str(e)[:80])
        continue
    soup = show(name, t, ["tr.data-row", "a.jobTitle-link", "span.jobLocation", "span.jobDate", ".paginationLabel", "li.job-tile", "a[href*='/job/']"])
    a = soup.select_one("a.jobTitle-link") or soup.select_one("a[href*='/job/']")
    print("   first link:", a.get("href") if a else None, "| total text:", (soup.select_one(".paginationLabel") or soup.select_one("[class*=pagination]") or soup).get_text(" ", strip=True)[:100] if soup.select_one(".paginationLabel") else "")
    if SAVE and name == "EY":
        open(SAVE + "_sf.html", "w", encoding="utf-8").write(t)

# Avature
for name, url in [("Deloitte", "https://apply.deloitte.com/en_US/careers/SearchJobs/data?3_1_3=India&jobOffset=0"),
                  ("Siemens", "https://jobs.siemens.com/en_US/externaljobs/SearchJobs/data?jobOffset=0"),
                  ("MetLife", "https://www.metlifecareers.com/en_US/ml/SearchJobs/data?jobOffset=0")]:
    try:
        t = get(url)
    except Exception as e:
        print(name, "ERR", str(e)[:80])
        continue
    soup = show(name, t, ["article.article--result", "a.link", "h3.article__header__text__title", "a[href*='JobDetail']", ".list-controls__text__legend", "span.list-item-location"])
    a = soup.select_one("a[href*='JobDetail']")
    print("   first link:", a.get("href") if a else None, "| page text:", (soup.select_one(".list-controls__text__legend") or soup).get_text(" ", strip=True)[:80] if soup.select_one(".list-controls__text__legend") else "")
    if SAVE and name == "Deloitte":
        open(SAVE + "_av.html", "w", encoding="utf-8").write(t)

# iCIMS
for name, url in [("Principal", "https://careers-principal.icims.com/jobs/search?ss=1&searchKeyword=data&in_iframe=1"),
                  ("Liberty", "https://careers-libertymutual.icims.com/jobs/search?ss=1&searchKeyword=data&in_iframe=1"),
                  ("Liberty2", "https://internal-libertymutual.icims.com/jobs/search?ss=1&searchKeyword=data&in_iframe=1")]:
    try:
        t = get(url)
    except Exception as e:
        print(name, "ERR", str(e)[:80])
        continue
    soup = show(name, t, ["div.iCIMS_JobsTable", "div.row", "a.iCIMS_Anchor", "h3", "a[href*='/jobs/']", ".iCIMS_JobHeaderTag", "span.sr-only"])
    a = soup.select_one("a.iCIMS_Anchor") or soup.select_one("a[href*='/jobs/']")
    print("   first link:", a.get("href") if a else None)
    if SAVE and name == "Principal":
        open(SAVE + "_ic.html", "w", encoding="utf-8").write(t)
