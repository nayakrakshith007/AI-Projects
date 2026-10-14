"""Per-site reports and the error log of one run.

For every site that finishes, `<run folder>/<site>_report.md` says what happened (status, time, jobs added, problems, the log files);
`run_report.md` is the table of all sites so far; `errors.log` has one timestamped line per problem or restart."""
import re
from datetime import datetime
from pathlib import Path

KEY_LINES = re.compile(r"fetched|kept|window|lists|roles,|unique|dropped|saved|wrote", re.I)


class RunReport:
    def __init__(self, run_dir: Path) -> None:
        self.dir = run_dir
        self.rows: list[dict] = []
        run_dir.mkdir(parents=True, exist_ok=True)

    def _error(self, site: str, text: str) -> None:
        with open(self.dir / "errors.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {site}: {text}\n")

    def event(self, res: dict) -> str | None:
        """Call for every on_done result. Returns the text of the site report when the site is finished (None for a restart notice)."""
        if res["status"].startswith("stuck"):
            self._error(res["site"], f"log silent too long; stopped and {res['status'].split(', ', 1)[1]}")
            return None
        return self.finish(res)

    def finish(self, res: dict) -> str:
        site = res["site"]
        logs = sorted(self.dir.glob(f"{site}*.log")) + sorted((self.dir / "retry").glob(f"{site}*.log")) if (self.dir / "retry").exists() else sorted(self.dir.glob(f"{site}*.log"))
        logs = [p for p in logs if p.name != "errors.log"]
        problems, key = [], []
        for p in logs:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("!!") and line.strip() not in problems:
                    problems.append(line.strip())
                elif KEY_LINES.search(line) and not line.startswith("  ["):
                    key.append(line.strip()[:200])
        for pr in problems:
            self._error(site, pr[:300])
        if res["status"] not in ("ok",) and not problems:
            self._error(site, f"ended as '{res['status']}' (exit code {res['exit_code']}) without a '!!' line; see {Path(res['log']).name if res['log'] else 'no log'}")
        added = f"{res['new']} new, {res['known']} already known, {res['total']} jobs now in the site workbook" if res["new"] is not None else "not reported (the site did not reach its summary line)"
        lines = [f"# {site}: {res['status']}", "",
                 f"- Finished: {datetime.now():%Y-%m-%d %H:%M:%S}, took {res['minutes']} min (last attempt)",
                 f"- Attempts: {1 + res.get('reruns', 0) + (1 if res.get('retried') else 0)}"
                 + (f" (restarted {res['reruns']}x after 2 silent minutes)" if res.get("reruns") else "")
                 + (f" (second try at the end after '{res.get('first_status')}')" if res.get("retried") else ""),
                 f"- Jobs: {added}", f"- Exit code: {res['exit_code']}", ""]
        lines += ["## Problems"] + ([f"- {p}" for p in problems] if problems else ["- none"]) + [""]
        lines += ["## Key lines from the log"] + ([f"- {k}" for k in key[-8:]] if key else ["- none"]) + [""]
        lines += ["## Log files"] + [f"- {p}" for p in logs]
        text = "\n".join(lines) + "\n"
        (self.dir / f"{site}_report.md").write_text(text, encoding="utf-8")
        self.rows.append(res)
        self._table()
        return text

    def _table(self) -> None:
        rows = ["# Run report", "", "| Site | Status | Minutes | New | Already known | In workbook | Restarts | Problems |", "|---|---|---|---|---|---|---|---|"]
        for r in self.rows:
            rows.append(f"| {r['site']} | {r['status']} | {r['minutes']} | {r['new'] if r['new'] is not None else '-'} | "
                        f"{r['known'] if r['known'] is not None else '-'} | {r['total'] if r['total'] is not None else '-'} | "
                        f"{r.get('reruns', 0)} | {len(r['problems'])} |")
        (self.dir / "run_report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
