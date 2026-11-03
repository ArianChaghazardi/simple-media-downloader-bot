"""
Enforces pure functional design across the entire codebase.
No user-defined classes are allowed anywhere in the src/ tree.
"""

import ast
from pathlib import Path


def test_no_classes_in_source():
    src_dir = Path(__file__).parent.parent / "src"
    violations = []

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                violations.append(f"{py_file.name}:{node.lineno} class {node.name}")

    assert not violations, f"Found forbidden custom classes in functional architecture: {violations}"
