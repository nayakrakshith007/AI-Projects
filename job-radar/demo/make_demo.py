"""Build a demo dashboard from invented data, so the project can be seen without running a single scraper.
Every company, title and link below is made up. Run from the project folder:  python demo/make_demo.py
It writes demo/output/snapshot.json and demo/output/Dashboard.html (open the second one in a browser)."""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from radar3 import dashboard                                                # noqa: E402

random.seed(7)
TODAY = date.today()
ROLES = {"AI Engineer": 0.26, "Data Engineer": 0.17, "Data Scientist": 0.14, "ML Engineer": 0.11, "Data Analyst / BI Analyst": 0.1, "AI Architect / Solutions Architect": 0.08,
         "GenAI / LLM Engineer": 0.07, "MLOps / ML Platform Engineer": 0.04, "Applied Scientist / Research Engineer": 0.02, "Prompt Engineer / AI Product": 0.01}
TITLES = {r: [r.split(" / ")[0], "Senior " + r.split(" / ")[0], "Lead " + r.split(" / ")[0], r.split(" / ")[0] + " II"] for r in ROLES}
COMPANIES = ["Northwind Labs", "Acme Analytics", "Contoso AI", "Globex Data", "Initech Cloud", "Umbrella Insights", "Hooli Research", "Stark Systems", "Wayne Digital", "Vandelay Tech",
             "Soylent Data", "Pied Piper AI", "Massive Dynamic", "Cyberdyne Labs", "Tyrell Analytics", "Wonka Intelligence"]
PLACES = [("Bengaluru, Karnataka", 2, True), ("Hyderabad, Telangana", 3, False), ("Chennai, Tamil Nadu", 3, False), ("Pune, Maharashtra", 4, False), ("Gurugram, Haryana", 4, False),
          ("Mumbai, Maharashtra", 4, False), ("Remote, India", 0, False)]
SOURCES = [("Demo Job Board A", "Job board"), ("Demo Job Board B", "Job board"), ("Demo Platform (Greenhouse)", "Platform"), ("Demo Platform (Workday)", "Platform"),
           ("Demo Custom Page", "Custom page"), ("Demo Remote Feed", "Feed")]
SKILLS = ["python, sql, machine learning", "llm, rag, langchain, aws", "spark, airflow, dbt, sql", "pytorch, mlops, docker, kubernetes", "tableau, power bi, sql", "azure, mlflow, python"]

jobs = []
for n in range(420):
    role = random.choices(list(ROLES), weights=ROLES.values())[0]
    place, tier, bengaluru = random.choices(PLACES, weights=[30, 14, 10, 12, 10, 12, 12])[0]
    site, kind = random.choice(SOURCES)
    posted = TODAY - timedelta(days=random.randint(0, 14))
    first = posted if random.random() < 0.7 else TODAY - timedelta(days=random.randint(0, 6))
    remote = tier == 0
    jobs.append({"roles": [role], "title": random.choice(TITLES[role]), "company": random.choice(COMPANIES), "location": place, "more_locations": "", "tier": tier,
                 "bengaluru": bengaluru, "remote": remote, "eligibility": "yes" if remote else "india", "work_mode": "Remote" if remote else random.choice(["", "Hybrid", "Onsite"]),
                 "salary": random.choice(["", "", "1,800,000 - 2,600,000 INR yearly", "3,000,000 - 4,200,000 INR yearly"]), "skills": random.choice(SKILLS),
                 "posted": posted.isoformat(), "first_seen": first.isoformat(), "sites": [site], "source_types": [kind], "url": f"https://example.com/jobs/{n}", "other_links": [],
                 "status": "New" if first == TODAY else "Seen"})

tiers = {str(t): sum(1 for j in jobs if j["tier"] == t) for t in range(5)}
by_site = {}
for j in jobs:
    by_site[j["sites"][0]] = by_site.get(j["sites"][0], 0) + 1
stats = {"read": {f"{name} (D{i:02d})": c * 6 for i, (name, c) in enumerate(by_site.items(), 1)}, "total_read": sum(by_site.values()) * 6, "not_open_to_india": 310,
         "unique": sum(by_site.values()) * 4, "duplicates_removed": sum(by_site.values()) * 2, "matched": len(jobs), "unmatched": sum(by_site.values()) * 3, "tiers": tiers,
         "by_source": {f"D{i:02d}": c for i, c in enumerate(by_site.values(), 1)}, "remote_open_to_india": tiers["0"], "remote_check_eligibility": tiers["1"],
         "bengaluru": tiers["2"], "hyderabad_chennai": tiers["3"], "rest_of_india": tiers["4"], "new_today": sum(1 for j in jobs if j["first_seen"] == TODAY.isoformat()),
         "by_role": {r: sum(1 for j in jobs if r in j["roles"]) for r in ROLES}, "written": "Job_Radar_V3.xlsx"}

out = ROOT / "demo" / "output"
out.mkdir(parents=True, exist_ok=True)
snap = out / "snapshot.json"
snap.write_text(json.dumps({"generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"), "stats": stats, "jobs": jobs}), encoding="utf-8")
print("wrote", dashboard.build_dashboard(snap, out / "Dashboard.html"))
