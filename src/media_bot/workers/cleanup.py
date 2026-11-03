"""
Functional temporary file cleanup module.
Zero custom classes.
"""

import time
from pathlib import Path
from typing import Any, Dict, Optional


def safe_delete_file(file_path: Optional[str]) -> bool:
    if not file_path:
        return False
    try:
        p = Path(file_path)
        if p.is_file():
            p.unlink(missing_ok=True)
            return True
    except Exception:
        pass
    return False


def clean_expired_files(temp_dir: str, max_age_hours: int = 2) -> Dict[str, Any]:
    dir_path = Path(temp_dir)
    if not dir_path.is_dir():
        return {"scanned": 0, "deleted": 0, "freed_bytes": 0}

    now = time.time()
    cutoff = now - (max_age_hours * 3600)

    scanned = 0
    deleted = 0
    freed_bytes = 0

    for file_path in dir_path.glob("*"):
        if file_path.is_file():
            scanned += 1
            try:
                stat = file_path.stat()
                if stat.st_mtime < cutoff:
                    size = stat.st_size
                    file_path.unlink()
                    deleted += 1
                    freed_bytes += size
            except Exception:
                continue

    return {
        "scanned": scanned,
        "deleted": deleted,
        "freed_bytes": freed_bytes,
    }
