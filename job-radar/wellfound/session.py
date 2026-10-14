"""One visible Chrome with a saved profile, used for public Wellfound pages. We never log in or solve checks."""
import atexit
import time

from . import config


class HumanCheckPending(Exception):
    """Wellfound is showing a human check. Run check_wellfound.bat and pass it by hand."""


class Session:
    def __init__(self, minimized: bool = True, profile_dir=None) -> None:
        self.minimized = minimized
        self.profile_dir = profile_dir or config.PROFILE_DIR
        self.pw = self.ctx = None

    def page(self):
        if self.ctx is None:
            from playwright.sync_api import sync_playwright
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.pw = sync_playwright().start()
            args = ["--start-minimized"] if self.minimized else []
            self.ctx = self.pw.chromium.launch_persistent_context(
                str(self.profile_dir), channel="chrome", headless=False, args=args
            )
            atexit.register(self.close)
        return self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()

    def close(self) -> None:
        try:
            if self.ctx:
                self.ctx.close()
            if self.pw:
                self.pw.stop()
        except Exception:
            pass
        self.ctx = self.pw = None


def wait_for_human(timeout_s: int = 600) -> bool:
    """Open a Wellfound role page in the saved profile and wait while the owner passes any check. True once jobs show."""
    s = Session(minimized=False)
    pg = s.page()
    pg.goto(config.INDIA_PAGE.format(slug="data-scientist"), wait_until="domcontentloaded")
    print("Chrome is open. If Wellfound asks you to prove you are human, do it in that window (do not sign in).")
    end, ok = time.time() + timeout_s, False
    while time.time() < end:
        try:
            if pg.query_selector(config.JOB_LINK):
                ok = True
                break
        except Exception:
            break  # the owner closed the window
        time.sleep(2)
    s.close()
    return ok
