"""Title filtering and role routing: which of the roles in input.csv does a job title belong to?

The patterns are the old project's validated role title patterns (pipeline/role_patterns.csv). A job can fit more than one role
(an 'AI Architect' is an Architect and an AI job). A job that fits none goes to the 'Unmatched' tab, so nothing is lost silently."""
import csv
import re
from pathlib import Path

from . import config


class RolePattern:
    def __init__(self, role: str, pattern: str, tech: bool) -> None:
        self.role, self.tech = role, tech
        self.rx = re.compile(pattern, re.I)


def load_patterns(path: Path = config.ROLE_PATTERNS) -> list[RolePattern]:
    """All role patterns, or only the tech ones while config.ROLE_SCOPE is 'tech'."""
    with open(path, newline="", encoding="utf-8") as f:
        patterns = [RolePattern(r["role"], r["title_pattern"], r["tech"].strip().lower() == "yes") for r in csv.DictReader(f) if r.get("title_pattern")]
    return [p for p in patterns if p.tech] if config.ROLE_SCOPE == "tech" else patterns


def roles_for(title: str, patterns: list[RolePattern]) -> list[str]:
    return [p.role for p in patterns if p.rx.search(title or "")]


def route(jobs: list[dict], patterns: list[RolePattern] | None = None) -> tuple[list[dict], list[dict]]:
    """Adds job['roles'] (a list). Returns (matched, unmatched), both in the input order."""
    patterns = patterns or load_patterns()
    matched, unmatched = [], []
    for j in jobs:
        j["roles"] = roles_for(j["title"], patterns)
        (matched if j["roles"] else unmatched).append(j)
    return matched, unmatched
