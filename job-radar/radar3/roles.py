"""Role routing: which of the ten AI/ML/Data roles does a job title belong to? A title can fit several; one that fits none goes to 'Unmatched'."""
import csv
import re

from . import config


class RolePattern:
    def __init__(self, role: str, pattern: str) -> None:
        self.role, self.rx = role, re.compile(pattern, re.I)


def load_patterns(path=config.ROLE_PATTERNS) -> list[RolePattern]:
    with open(path, newline="", encoding="utf-8") as f:
        return [RolePattern(r["role"], r["title_pattern"]) for r in csv.DictReader(f) if r.get("title_pattern")]


def roles_for(title: str, patterns: list[RolePattern]) -> list[str]:
    return [p.role for p in patterns if p.rx.search(title or "")]
