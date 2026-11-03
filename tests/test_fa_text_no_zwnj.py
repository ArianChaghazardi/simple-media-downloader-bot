"""
Enforces STRICT ZERO ZWNJ (Zero-Width Non-Joiner, \u200c) policy
across all project files, comments, and strings.
"""

from pathlib import Path


def test_zero_zwnj_in_all_files():
    base_dir = Path(__file__).parent.parent
    violations = []
    checked = 0

    scan_extensions = {".py", ".json", ".sql", ".md", ".txt", ".env"}

    for path in base_dir.rglob("*"):
        if any(ignored in path.parts for ignored in (".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "data")):
            continue
        if path.is_file() and path.suffix in scan_extensions:
            checked += 1
            try:
                content = path.read_text(encoding="utf-8")
                if "\u200c" in content:
                    violations.append(str(path.relative_to(base_dir)))
            except Exception:
                pass

    assert checked > 0
    assert not violations, f"Forbidden ZWNJ (\\u200c) found in files: {violations}"
