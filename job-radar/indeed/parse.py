"""Turn Indeed rows (from JobSpy) into plain job dicts and read everything useful out of the text. Pure functions."""
import re

import pandas as pd

from common.inputs import parse_experience

from . import config

DESCRIPTION_LIMIT = 32000   # Excel cells hold at most 32,767 characters

# ---------- experience ----------
_RANGE = re.compile(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr)\b", re.I)
_PLUS = re.compile(r"(\d{1,2})\s*\+\s*(?:years|year|yrs|yr)\b", re.I)
_MIN = re.compile(r"(?:minimum|at least|min\.?|over|more than|atleast)\s*(?:of\s*)?(\d{1,2})\s*(?:years|year|yrs|yr)\b", re.I)
_SINGLE = re.compile(r"(\d{1,2})\s*(?:years|year|yrs|yr)\b", re.I)
_NOUNIT = re.compile(r"(?:experience|exp\.?)\s*(?:required|needed)?\s*[:\-–]?\s*(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})(?!\d)", re.I)
_FRESHER = re.compile(r"\bfreshers?\b", re.I)
_CONTEXT = re.compile(r"exp", re.I)


def experience_from_text(*texts: str | None) -> str:
    """Experience stated in a title or description as text such as '6-8 years' or '5+ years'; '' when none is found.

    Titles are trusted ('Data Scientist (Exp 6-8 yrs)'). In descriptions a match only counts when the word
    'experience' (or 'exp') is close by, so '10 years in business' is not mistaken for a requirement.
    'Fresher' alone gives '0 years (fresher)'.
    """
    for i, text in enumerate(texts):
        text = (text or "")[:8000]
        for rx, fmt in ((_RANGE, lambda m: f"{m.group(1)}-{m.group(2)} years"),
                        (_PLUS, lambda m: f"{m.group(1)}+ years"),
                        (_MIN, lambda m: f"{m.group(1)}+ years"),
                        (_SINGLE, lambda m: f"{m.group(1)} years")):
            for m in rx.finditer(text):
                near = text[max(0, m.start() - 60): m.end() + 60]
                if i == 0 or _CONTEXT.search(near):
                    return fmt(m)
        m = _NOUNIT.search(text)
        if m:
            return f"{m.group(1)}-{m.group(2)} years"
    if any(_FRESHER.search(t or "") for t in texts):
        return "0 years (fresher)"
    return ""


# ---------- qualification ----------
_DEGREES = [
    ("BAMS", r"\bB\.?\s?A\.?\s?M\.?\s?S\b|bachelor of ayurved"),
    ("MD/MS Ayurveda", r"\bM\.?\s?D\.?\s*\(?\s*ayurved|\bM\.?\s?S\.?\s*\(?\s*ayurved|\bM\.?\s?D\.?\s*/\s*M\.?\s?S\.?\s*\(?\s*ayurved|post\s?graduate in ayurved|\bMD\b.{0,20}\bRasa"),
    ("BUMS", r"\bB\.?\s?U\.?\s?M\.?\s?S\b"),
    ("BHMS", r"\bB\.?\s?H\.?\s?M\.?\s?S\b"),
    ("BSMS", r"\bB\.?\s?S\.?\s?M\.?\s?S\b"),
    ("MBBS", r"\bM\.?\s?B\.?\s?B\.?\s?S\b"),
    ("MD", r"\bM\.?\s?D\.?\b(?!\s*\(?\s*ayurved)(?=\s*[\(\-,/ ]\s*(?:medicine|pharmacology|pathology|community|pediatric|radiology|anaesth)|\s*degree)"),
    ("B.Pharm", r"\bB\.?\s?Pharm(?:a|acy)?\b|bachelor of pharmacy"),
    ("M.Pharm", r"\bM\.?\s?Pharm(?:a|acy)?\b|master of pharmacy"),
    ("Pharm.D", r"\bPharm\.?\s?D\b|doctor of pharmacy"),
    ("B.Sc", r"\bB\.?\s?Sc\b|bachelor of science"),
    ("M.Sc", r"\bM\.?\s?Sc\b|master of science"),
    ("B.Tech/BE", r"\bB\.?\s?Tech\b|\bB\.?\s?E\.?\b(?=\s*[/(,]|\s+in\b)|bachelor of (?:engineering|technology)"),
    ("M.Tech/ME", r"\bM\.?\s?Tech\b|master of (?:engineering|technology)"),
    ("MBA/PGDM", r"\bMBA\b|\bPGDM\b"),
    ("MCA/BCA", r"\bMCA\b|\bBCA\b"),
    ("MPH", r"\bMPH\b|master of public health"),
    ("PhD", r"\bPh\.?\s?D\b|doctorate"),
    ("Post graduate", r"post[\s-]?graduat|\bPG\b"),
    ("Graduate", r"\bgraduat(?:e|ion)\b|bachelor'?s?\b|\bdegree\b"),
    ("Diploma", r"\bdiploma\b"),
    ("12th/10th", r"\b12th\b|\b10th\b|\bHSC\b|\bSSLC\b"),
]
_DEGREE_RX = [(label, re.compile(rx, re.I)) for label, rx in _DEGREES]


def qualifications(text: str | None) -> str:
    """Degrees and qualifications named in the text, in order of first appearance, e.g. 'BAMS, MD/MS Ayurveda'."""
    text = (text or "")[:8000]
    hits = []
    for label, rx in _DEGREE_RX:
        m = rx.search(text)
        if m:
            hits.append((m.start(), label))
    return ", ".join(label for _, label in sorted(hits))


# ---------- skills ----------
SKILLS = [
    # data / AI
    "python", "sql", "r programming", "pyspark", "spark", "hadoop", "tableau", "power bi", "excel", "tensorflow", "pytorch",
    "scikit-learn", "machine learning", "deep learning", "nlp", "computer vision", "llm", "generative ai", "langchain", "rag",
    "mlops", "aws", "azure", "gcp", "docker", "kubernetes", "airflow", "snowflake", "databricks", "statistics", "a/b testing",
    "forecasting", "time series", "data modeling", "etl", "java", "scala", "c++", "javascript", "fastapi", "flask", "git",
    # clinical / pharma / regulatory
    "gcp", "ich-gcp", "ich", "gmp", "glp", "gdp", "sop", "pharmacovigilance", "drug safety", "argus", "meddra", "clinical trial",
    "clinical data management", "edc", "medidata", "oracle clinical", "sas", "cdisc", "sdtm", "adam", "regulatory affairs", "cdsco",
    "usfda", "ectd", "dossier", "medical writing", "protocol", "icf", "site management", "monitoring", "capa", "qms", "audit",
    "validation", "quality assurance", "quality control", "hplc", "gc", "stability studies", "formulation", "r&d",
    # ayurveda
    "panchakarma", "kayachikitsa", "rasashastra", "bhaishajya kalpana", "dravyaguna", "shalya", "shalakya", "prasuti", "kaumarbhritya",
    "swasthavritta", "agad tantra", "ayurvedic formulation", "herbal", "patient counselling", "opd", "ipd", "teaching", "research",
]
_SKILL_RX = [(s, re.compile(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", re.I)) for s in dict.fromkeys(SKILLS)]


def detect_skills(text: str | None) -> str:
    """Skills and tools from a fixed vocabulary that appear in the text, in vocabulary order."""
    text = (text or "")[:8000]
    return ", ".join(s for s, rx in _SKILL_RX if rx.search(text))


# ---------- contacts and small facts ----------
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")
_WALKIN = re.compile(r"walk[\s-]?in", re.I)
_OPENINGS = re.compile(r"(\d{1,3})\s*(?:vacanc(?:y|ies)|openings?|positions?|posts?)\b", re.I)


def emails_in(text: str | None, extra: str | None = None) -> str:
    found = dict.fromkeys(e.lower().rstrip(".") for e in _EMAIL.findall(f"{extra or ''} {text or ''}"))
    return ", ".join(found)


def phones_in(text: str | None) -> str:
    found = dict.fromkeys(re.sub(r"[\s-]", "", m) for m in _PHONE.findall(text or ""))
    return ", ".join(found)


def openings_in(text: str | None) -> str:
    m = _OPENINGS.search((text or "")[:6000])
    return m.group(1) if m else ""


# ---------- salary ----------
_MONTHLY_FACTOR = {"yearly": 1 / 12, "monthly": 1, "weekly": 52 / 12, "daily": 26, "hourly": 8 * 26}


def _num(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)


def salary_fields(r: dict) -> dict:
    """Salary as shown text plus numbers per month in INR (yearly/12; weekly, daily and hourly are rough conversions)."""
    lo, hi, cur, per = _num(r.get("min_amount")), _num(r.get("max_amount")), r.get("currency") or "", str(r.get("interval") or "")
    if lo is None and hi is None:
        return {"salary": "", "salary_min_month": None, "salary_max_month": None}
    amounts = f"{int(lo):,} - {int(hi):,}" if lo is not None and hi is not None else f"{int(lo if lo is not None else hi):,}"
    factor = _MONTHLY_FACTOR.get(per.lower())
    monthly = (lambda v: round(v * factor)) if factor and str(cur).upper() == "INR" else (lambda v: None)
    return {"salary": f"{amounts} {cur} {per}".strip(),
            "salary_min_month": monthly(lo) if lo is not None else None,
            "salary_max_month": monthly(hi) if hi is not None else None}


# ---------- rows to jobs ----------
def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def to_jobs(df: pd.DataFrame) -> list[dict]:
    """JobSpy table to job dicts. The Indeed link (viewjob?jk=...) is kept whole: the jk value is the job's identity."""
    jobs = []
    for r in df.to_dict("records"):
        url = _s(r.get("job_url"))
        if not url:
            continue
        posted = pd.to_datetime(r.get("date_posted"), errors="coerce")
        desc = _s(r.get("description"))
        title = _s(r.get("title"))
        exp = experience_from_text(title, desc)
        rng = parse_experience(exp)
        about = _s(r.get("company_description"))
        extras = [x for x in (_s(r.get("company_revenue")), _s(r.get("company_addresses")), about[:200]) if x]
        job = {
            "title": title, "company": _s(r.get("company")), "location": _s(r.get("location")),
            "experience": exp, "experience_min": rng[0] if rng else None, "experience_max": (rng[1] if rng and rng[1] < 99 else None),
            "qualification": qualifications(f"{title} {desc}"), "skills": detect_skills(f"{title} {desc}"),
            "work_mode": "Remote" if r.get("is_remote") is True else "", "job_type": _s(r.get("job_type")),
            "walk_in": "Yes" if _WALKIN.search(f"{title} {desc}") else "",
            "openings": openings_in(desc), "emails": emails_in(desc, _s(r.get("emails"))), "phones": phones_in(desc),
            "company_rating": _num(r.get("company_rating")), "company_reviews": _num(r.get("company_reviews_count")),
            "company_industry": _s(r.get("company_industry")), "company_size": _s(r.get("company_num_employees")),
            "company_info": "; ".join(extras), "company_website": _s(r.get("company_url_direct")), "company_page": _s(r.get("company_url")),
            "apply_link": _s(r.get("job_url_direct")),
            "snippet": re.sub(r"\s+", " ", desc)[: config.SNIPPET_CHARS], "description": desc[:DESCRIPTION_LIMIT],
            "posted_text": "", "posted_date": posted.date() if pd.notna(posted) else None, "url": url,
        }
        job.update(salary_fields(r))
        jobs.append(job)
    return jobs
