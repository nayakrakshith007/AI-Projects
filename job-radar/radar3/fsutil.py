"""File helpers. On Windows, replacing a file that another process has open (the progress page reads run_state.json every 2 seconds) can fail with
PermissionError for a moment. safe_replace retries briefly before giving up."""
import os
import time


def safe_replace(src, dst, tries: int = 12, wait: float = 0.05) -> None:
    for attempt in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(wait * (attempt + 1))
