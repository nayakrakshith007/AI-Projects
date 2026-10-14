"""Tell the owner something needs them, with a Windows pop-up that does not block the run."""
import threading


def popup(title: str, message: str) -> None:
    def show() -> None:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1000)  # info icon, topmost
        except Exception:
            pass  # not on Windows: the console message is enough

    threading.Thread(target=show, daemon=True).start()
