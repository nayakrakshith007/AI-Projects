"""Save a workbook so that a run stopped part-way (a stall restart, Stop, a crash) can never leave a half-written Excel file:
write to a side file first, then swap it in. If Excel has the target open the swap raises PermissionError, exactly like a direct save."""
import os
from pathlib import Path


def save_workbook(wb, path: Path) -> None:
    path = Path(path)
    part = path.with_name(path.name + ".part")
    try:
        wb.save(part)
        os.replace(part, path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
