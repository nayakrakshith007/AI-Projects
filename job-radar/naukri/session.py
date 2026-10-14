"""One visible Chrome with a saved profile. The owner passes Naukri's human check by hand; we never solve it."""
import atexit
import time

from . import config


class HumanCheckPending(Exception):
    """Naukri is showing its human check. Run check.bat (python -m naukri check) and pass it by hand."""


class Session:
    def __init__(self, minimized: bool = True) -> None:
        self.minimized = minimized
        self.pw = self.ctx = None

    def page(self):
        if self.ctx is None:
            from playwright.sync_api import sync_playwright
            config.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self.pw = sync_playwright().start()
            args = ["--start-minimized"] if self.minimized else []
            self.ctx = self.pw.chromium.launch_persistent_context(
                str(config.PROFILE_DIR), channel="chrome", headless=False, args=args
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
    """Open Naukri in the saved profile and wait while the owner passes the check. True once results show."""
    s = Session(minimized=False)
    pg = s.page()
    pg.goto(config.page_url("data scientist", 1, 1), wait_until="domcontentloaded")
    print("Chrome is open. If Naukri asks you to prove you are human, do it in that window.")
    end, ok = time.time() + timeout_s, False
    while time.time() < end:
        try:
            if pg.query_selector(config.CARD_SELECTOR):
                ok = True
                break
        except Exception:
            break  # the owner closed the window
        time.sleep(2)
    s.close()
    return ok
