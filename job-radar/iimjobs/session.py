"""One visible Chrome with an empty browser state. Nothing is kept between runs (its sister site Hirist remembers filters between visits)."""
import atexit

from . import config


class HumanCheckPending(Exception):
    """IIMJobs is showing a human check. Pass it by hand (run check_iimjobs.bat), then rerun."""


class Session:
    def __init__(self, minimized: bool = True) -> None:
        self.minimized = minimized
        self.pw = self.browser = self.ctx = self._page = None

    def page(self):
        if self._page is None:
            from playwright.sync_api import sync_playwright
            self.pw = sync_playwright().start()
            args = ["--start-minimized"] if self.minimized else []
            self.browser = self.pw.chromium.launch(channel="chrome", headless=False, args=args)
            self.ctx = self.browser.new_context()          # fresh state: no remembered experience, location or date filters
            self._page = self.ctx.new_page()
            atexit.register(self.close)
        return self._page

    def close(self) -> None:
        try:
            if self.browser:
                self.browser.close()
            if self.pw:
                self.pw.stop()
        except Exception:
            pass
        self.pw = self.browser = self.ctx = self._page = None


def wait_for_human(timeout_s: int = 600) -> bool:
    """Open a IIMJobs page and wait while the owner passes any check. True once job links show."""
    import time
    s = Session(minimized=False)
    pg = s.page()
    pg.goto(config.tag_url("data-scientist", 7, 1), wait_until="domcontentloaded")
    print("Chrome is open. If IIMJobs asks you to prove you are human, do it in that window (do not sign in).")
    end, ok = time.time() + timeout_s, False
    while time.time() < end:
        try:
            if pg.query_selector('a[href*="/j/"]'):
                ok = True
                break
        except Exception:
            break  # the owner closed the window
        time.sleep(2)
    s.close()
    return ok
