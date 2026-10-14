"""The one input file every site workflow reads: job-radar-V3/input.csv

Columns: Role, Keywords, Experience, Location
- Role:       a name for the group; becomes the "Role" column in each site's Excel file.
- Keywords:   search terms for that role, separated by semicolons (each is searched on its own).
- Experience: minimum years wanted, a plain number such as 5 or 0. Blank or 0 means no filter.
              A job is kept when its stated range reaches that number (3-6 years passes for 5)
              or when it states no experience at all (recall over precision).
- Location:   one or more places separated by semicolons, for example India or India;Bengaluru.
"""
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

INPUT_FILE = Path(__file__).resolve().parents[1] / "input.csv"
COLUMNS = ["Role", "Keywords", "Experience", "Location"]

_RANGE = re.compile(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})")
_PLUS = re.compile(r"(\d{1,2})\s*\+")
_ONE = re.compile(r"(\d{1,2})")


@dataclass(frozen=True)
class RoleInput:
    role: str
    keywords: list[str]
    min_experience: float
    locations: list[str]


class Query(NamedTuple):
    """One search: a keyword in a place, for a role, with that role's minimum experience."""
    role: str
    keyword: str
    location: str
    min_experience: float


def queries_from(roles: list[RoleInput]) -> list[Query]:
    """One query per role, keyword and location."""
    return [Query(r.role, k, loc, r.min_experience) for r in roles for k in r.keywords for loc in r.locations]


def _split(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split(";") if p.strip()]


def load_input(path: Path = INPUT_FILE) -> list[RoleInput]:
    """Read input.csv. Raises a clear error for a missing column, an empty role or a bad experience number."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {missing}; expected {COLUMNS}")
        out = []
        for n, row in enumerate(reader, start=2):
            if None in row or None in row.values():
                raise ValueError(f"{path.name} line {n}: wrong number of columns (put quotes around fields with commas)")
            role = (row["Role"] or "").strip()
            if not role:
                continue
            keywords = _split(row["Keywords"])
            if not keywords:
                raise ValueError(f"{path.name} line {n}: role {role!r} has no keywords")
            exp_text = (row["Experience"] or "").strip().rstrip("+")
            try:
                min_exp = float(exp_text) if exp_text else 0.0
            except ValueError:
                raise ValueError(f"{path.name} line {n}: Experience must be a number, got {row['Experience']!r}") from None
            out.append(RoleInput(role, keywords, min_exp, _split(row["Location"]) or ["India"]))
    return out


def parse_experience(text: str | None) -> tuple[int, int] | None:
    """'3-6 Yrs' -> (3, 6); '5+ Yrs' -> (5, 99); '4 Yrs' -> (4, 4); no digits -> None."""
    if not text:
        return None
    m = _RANGE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo, hi) if lo <= hi else (hi, lo)
    m = _PLUS.search(text)
    if m:
        return int(m.group(1)), 99
    m = _ONE.search(text)
    return (int(m.group(1)), int(m.group(1))) if m else None


def experience_ok(text: str | None, min_experience: float) -> bool:
    """Keep the job when no minimum is set, when it states no experience, or when its range reaches the minimum."""
    if not min_experience:
        return True
    rng = parse_experience(text)
    return rng is None or rng[1] >= min_experience
