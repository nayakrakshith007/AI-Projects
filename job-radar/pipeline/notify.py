"""Windows message box shown when the daily run ends. It blocks until clicked, so the window cannot vanish with the process."""


def popup(title: str, message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1000)  # info icon, topmost
    except Exception:
        pass  # not on Windows: the console message is enough
