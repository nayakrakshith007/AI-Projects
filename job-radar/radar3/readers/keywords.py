"""Search keywords for every reader that searches a career site by text. Recall check on 2026-10-13: with only data / machine learning /
artificial intelligence / analytics, Accenture returned 27% of the role-matching jobs, Citi 60%, Microsoft 70%; this list gets most of the rest.
Titles are matched against the ten role patterns afterwards, so a broad keyword only costs a few extra requests (a keyword stops as soon as a page adds nothing new)."""

ROLE_KEYWORDS = (
    "data", "machine learning", "artificial intelligence", "analytics", "scientist", "generative ai", "data engineer", "analyst", "architect", "mlops",
    "llm", "deep learning", "nlp", "ai engineer", "ai", "ml", "bi", "business intelligence", "research engineer", "forward deployed", "prompt",
    "python", "sql", "statistic", "insights", "modelling",
)
