"""Prune orphaned .pyc files whose source .py has been deleted.

Stale bytecode causes pytest to collect tests from deleted files,
leading to spurious failures (especially in e2e slow / e2e all).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def prune_orphan_pyc(root: Path = Path("tests")) -> list[Path]:
    """Delete .pyc files under *root* whose source .py no longer exists."""
    removed: list[Path] = []
    for pyc in root.rglob("*.pyc"):
        module = re.sub(r"\.cpython-\d+.*", "", pyc.stem)
        source = pyc.parent.parent / (module + ".py")
        if not source.exists():
            pyc.unlink()
            removed.append(pyc)
    return removed


if __name__ == "__main__":
    removed = prune_orphan_pyc()
    if removed:
        print(f"Pruned {len(removed)} orphaned .pyc file(s):")
        for p in removed:
            print(f"  {p}")
        sys.exit(0)  # Don't block the commit — just clean up
