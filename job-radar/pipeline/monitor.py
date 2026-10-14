"""Samples the machine while a run is going: free memory and the number of Chrome processes. The numbers go into run_state.json (the
tracker shows them live) and into the run's history line, so a run's memory use can be compared with the time it took."""
import subprocess
import threading

from . import runner


def chrome_count() -> int:
    """Chrome processes now (the user's own windows included; the sampler remembers the count at the start)."""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=20).stdout
        return sum(1 for line in out.splitlines() if line.lower().startswith('"chrome.exe"'))
    except Exception:
        return 0


class Sampler:
    """Background thread: every `every` seconds read free memory and Chrome count, and hand a summary to `update`."""

    def __init__(self, update, every: float = 10.0) -> None:
        self.update, self.every = update, every
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.n, self.sum_free = 0, 0
        self.min_free = None
        self.base = chrome_count()
        self.peak = self.base

    def _sample(self) -> None:
        free, chrome = runner.free_mb(), chrome_count()
        self.n += 1
        self.sum_free += free
        self.min_free = free if self.min_free is None else min(self.min_free, free)
        self.peak = max(self.peak, chrome)
        self.update({"free_mb": free, "min_free_mb": self.min_free, "avg_free_mb": round(self.sum_free / self.n),
                     "chrome_now": chrome, "chrome_baseline": self.base, "chrome_peak": self.peak, "samples": self.n})

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self._sample()
            except Exception:
                pass
            self.stop.wait(self.every)

    def start(self) -> "Sampler":
        self.thread.start()
        return self

    def finish(self) -> None:
        self.stop.set()
        self.thread.join(timeout=15)
