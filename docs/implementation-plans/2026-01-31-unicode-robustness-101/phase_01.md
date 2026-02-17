# Unicode Robustness Implementation Plan - Phase 1

**Goal:** Set up test infrastructure with BLNS corpus parsing and pytest markers

**Architecture:** Parse BLNS categories from blns.txt at test collection time, configure pytest markers for opt-in full corpus runs, add test-all-fixtures script

**Tech Stack:** pytest, Python pathlib

**Scope:** Phase 1 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add pytest markers to pyproject.toml

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/pyproject.toml`

**Step 1: Add blns marker**

Add to the `markers` list in `[tool.pytest.ini_options]` section (around line 85):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-ra -q"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "e2e: marks end-to-end tests requiring Playwright browsers",
    "blns: marks Big List of Naughty Strings tests (opt-in with '-m blns')",
]
```

**Step 2: Configure default marker exclusion**

Update `addopts` to exclude blns and slow by default:

```toml
addopts = "-ra -q -m 'not blns and not slow'"
```

**Step 3: Verify markers registered**

Run: `uv run pytest --markers | grep -E "(blns|slow)"`

Expected:
```
@pytest.mark.slow: marks tests as slow (deselect with '-m "not slow"')
@pytest.mark.blns: marks Big List of Naughty Strings tests (opt-in with '-m blns')
```

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(test): add blns and slow pytest markers with default exclusion"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create BLNS category parser in conftest.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/conftest.py`

**Step 1: Add BLNS parsing code**

Add after the existing imports (around line 25):

```python
from pathlib import Path
from typing import TypeAlias

# BLNS corpus parsing
BLNSCorpus: TypeAlias = dict[str, list[str]]

def _parse_blns_by_category(blns_path: Path) -> BLNSCorpus:
    """Parse blns.txt into {category: [strings]}.

    Category headers are lines starting with '#\t' followed by title-case text
    after a blank line. Explanatory comments (containing 'which') are skipped.
    """
    categories: BLNSCorpus = {}
    current_category = "Uncategorized"
    prev_blank = True

    for line in blns_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        # Track blank lines
        if not stripped:
            prev_blank = True
            continue

        # Check for category header: #\t followed by title-case, after blank
        if line.startswith("#\t") and prev_blank:
            header_text = line[2:].strip()
            # Category names are Title Case, not explanations
            if header_text and header_text[0].isupper() and "which" not in header_text.lower():
                current_category = header_text
                categories.setdefault(current_category, [])
        elif not line.startswith("#"):
            # Non-comment line is a test string
            categories.setdefault(current_category, []).append(line)

        prev_blank = False

    return categories


# Load BLNS corpus at module level (once per test session)
_FIXTURES_DIR = Path(__file__).parent / "fixtures"
BLNS_BY_CATEGORY: BLNSCorpus = _parse_blns_by_category(_FIXTURES_DIR / "blns.txt")

# Injection-related categories for always-run subset
INJECTION_CATEGORIES = [
    "Script Injection",
    "SQL Injection",
    "Server Code Injection",
    "Command Injection (Unix)",
    "Command Injection (Windows)",
    "Command Injection (Ruby)",
    "XXE Injection (XML)",
    "Unwanted Interpolation",
    "File Inclusion",
    "jinja2 injection",
]

BLNS_INJECTION_SUBSET: list[str] = [
    s for cat in INJECTION_CATEGORIES
    for s in BLNS_BY_CATEGORY.get(cat, [])
]
```

**Step 2: Add a simple test to verify parsing works**

Create file: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_blns_parsing.py`

```python
"""Tests for BLNS corpus parsing."""

from tests.conftest import BLNS_BY_CATEGORY, BLNS_INJECTION_SUBSET


class TestBLNSParsing:
    """Verify BLNS corpus is parsed correctly."""

    def test_blns_has_categories(self) -> None:
        """BLNS should parse into multiple categories."""
        assert len(BLNS_BY_CATEGORY) > 10, "Expected at least 10 categories"

    def test_blns_has_two_byte_characters(self) -> None:
        """Two-Byte Characters category should exist with CJK strings."""
        assert "Two-Byte Characters" in BLNS_BY_CATEGORY
        strings = BLNS_BY_CATEGORY["Two-Byte Characters"]
        assert len(strings) > 0
        # Should contain Japanese
        assert any("田中" in s for s in strings)

    def test_injection_subset_populated(self) -> None:
        """Injection subset should contain strings from injection categories."""
        assert len(BLNS_INJECTION_SUBSET) > 20, "Expected at least 20 injection strings"

    def test_injection_subset_has_sql(self) -> None:
        """Injection subset should include SQL injection strings."""
        assert any("SELECT" in s or "DROP" in s for s in BLNS_INJECTION_SUBSET)
```

**Step 3: Run tests to verify**

Run: `uv run pytest tests/unit/test_blns_parsing.py -v`

Expected: All 4 tests pass

**Step 4: Commit**

```bash
git add tests/conftest.py tests/unit/test_blns_parsing.py
git commit -m "feat(test): add BLNS corpus parser with category extraction"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create test-all-fixtures script

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/scripts/test_all_fixtures.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/pyproject.toml`

**Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Run full test corpus including BLNS and slow tests.

This script runs pytest without marker filtering, enabling all tests
including those marked with @pytest.mark.blns and @pytest.mark.slow.

Usage: uv run test-all-fixtures
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Run pytest without marker exclusions."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "",  # Empty marker filter = run all
        "-v",
        "--tb=short",
    ]

    # Pass through any additional arguments
    cmd.extend(sys.argv[1:])

    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Register as entry point in pyproject.toml**

Add to `[project.scripts]` section (around line 55):

```toml
[project.scripts]
test-debug = "promptgrimoire.cli:test_debug"
test-all-fixtures = "scripts.test_all_fixtures:main"
```

**Step 3: Verify script runs**

Run: `uv run test-all-fixtures --collect-only | head -20`

Expected: Shows test collection without marker filtering (includes blns tests when they exist)

**Step 4: Commit**

```bash
git add scripts/test_all_fixtures.py pyproject.toml
git commit -m "feat(test): add test-all-fixtures script for full corpus runs"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Document fontspec investigation decision

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/docs/implementation-plans/2026-01-31-unicode-robustness-101/fontspec-investigation.md`

**Step 1: Create investigation document**

This documents the Phase 1 decision: detect-and-wrap approach chosen over fontspec fallback.

```markdown
# Fontspec Investigation Results

**Date:** 2026-01-31
**Decision:** Use detect-and-wrap approach

## Background

The design plan considered two approaches for unicode handling in LaTeX:
1. **Fontspec fallback chain** - Configure LuaLaTeX with font fallback sequence
2. **Detect-and-wrap** - Scan text for unicode ranges, wrap in explicit font commands

## Investigation

Prior experience with fontspec fallback chains showed:
- Configuration is environment-dependent
- Font resolution varies across systems
- Silent failures produce tofu (□) instead of useful errors
- Debugging font issues is time-consuming

## Decision

**Detect-and-wrap is the primary approach.**

Benefits:
- Explicit control over which fonts render which characters
- Clear error messages when fonts missing
- Consistent behavior across environments
- Easier to test and verify

## Implementation

- `src/promptgrimoire/export/unicode_latex.py` will detect CJK/emoji ranges
- Text will be wrapped in explicit `\setCJKfamily` or similar commands
- Phases 2-3 implement this approach
```

**Step 2: Commit**

```bash
git add docs/implementation-plans/2026-01-31-unicode-robustness-101/fontspec-investigation.md
git commit -m "docs: document fontspec investigation - chose detect-and-wrap"
```
<!-- END_TASK_4 -->

## Phase 1 Verification

**Done when:**
- [x] `pytest --markers` shows `blns` and `slow` markers
- [x] `uv run pytest` excludes `blns` by default
- [x] `uv run test-all-fixtures` runs without marker filtering
- [x] `uv run test-debug` continues to work
- [x] Decision documented: detect-and-wrap approach

**Verification commands:**

```bash
# Verify markers registered
uv run pytest --markers | grep -E "(blns|slow)"

# Verify default exclusion (should not see blns tests)
uv run pytest --collect-only 2>&1 | grep -c "blns" || echo "0 blns tests collected (correct)"

# Verify test-all-fixtures works
uv run test-all-fixtures --collect-only | head -5

# Verify test-debug still works
uv run test-debug --help || uv run test-debug --collect-only | head -5
```
