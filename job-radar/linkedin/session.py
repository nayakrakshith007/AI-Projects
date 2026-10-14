"""One visible Chrome with a saved profile, used for public LinkedIn pages. We never log in or solve checks."""
import atexit
import time

from . import config


class HumanCheckPending(Exception):
    """LinkedIn is showing a sign-in wall or a security check. Run check.bat and handle it by hand."""


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
    """Open a LinkedIn public search in the saved profile and wait while the owner handles any wall. True once cards show."""
    s = Session(minimized=False)
    pg = s.page()
    pg.goto(config.search_url("data scientist", 24), wait_until="domcontentloaded")
    print("Chrome is open. If LinkedIn asks for a check, handle it in that window (do not sign in).")
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
