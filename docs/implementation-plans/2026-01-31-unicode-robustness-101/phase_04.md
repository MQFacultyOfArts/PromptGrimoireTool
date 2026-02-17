# Unicode Robustness Implementation Plan - Phase 4

**Goal:** Add required LaTeX packages for CJK and emoji to TinyTeX

**Architecture:** Extend existing `scripts/setup_latex.py` REQUIRED_PACKAGES list with `emoji`, `luatexja`, and `notocjksc` packages. Add memory warning for first-time CJK compilation.

**Tech Stack:** TinyTeX, tlmgr, Python

**Scope:** Phase 4 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add CJK and emoji packages to setup_latex.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/scripts/setup_latex.py`

**Step 1: Add packages to REQUIRED_PACKAGES list**

Update the REQUIRED_PACKAGES list (lines 20-30) to include the new packages:

```python
REQUIRED_PACKAGES = [
    "lua-ul",
    "fontspec",
    "luacolor",
    "todonotes",
    "geometry",
    "marginalia",
    "latexmk",
    "xcolor",
    "soul",
    # Unicode support (Issue #101)
    "emoji",         # Emoji rendering in LuaLaTeX
    "luatexja",      # CJK support for LuaLaTeX
    "notocjksc",     # Noto CJK Simplified Chinese fonts
]
```

**Step 2: Run setup script to verify installation works**

Run: `uv run python scripts/setup_latex.py`

Expected: All packages install successfully (or already installed)

**Step 3: Verify packages installed**

Run: `~/.TinyTeX/bin/x86_64-linux/tlmgr list --only-installed | grep -E "(emoji|luatexja|notocjksc)"`

Expected:
```
i emoji
i luatexja
i notocjksc
```

**Step 4: Commit**

```bash
git add scripts/setup_latex.py
git commit -m "feat(latex): add CJK and emoji packages to TinyTeX setup (#101)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add memory warning to setup script

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/scripts/setup_latex.py`

**Step 1: Add warning message after installation**

Add to the end of `main()` function (around line 105, before final return):

```python
    print()
    print("Note: First compilation with CJK fonts may use ~6GB RAM")
    print("for font cache generation. Subsequent compilations are faster.")
```

**Step 2: Verify script runs with warning**

Run: `uv run python scripts/setup_latex.py`

Expected: Warning message appears at end of output

**Step 3: Commit**

```bash
git add scripts/setup_latex.py
git commit -m "docs(latex): add memory warning for CJK font cache generation (#101)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create test for TinyTeX package verification

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_latex_packages.py`

**Step 1: Write test to verify packages are installed**

```python
"""Tests for LaTeX package availability."""

import subprocess
from pathlib import Path

import pytest


# Required packages for unicode support
UNICODE_PACKAGES = ["emoji", "luatexja", "notocjksc"]


def get_tlmgr_path() -> Path | None:
    """Get path to tlmgr if TinyTeX is installed."""
    tinytex_bin = Path.home() / ".TinyTeX" / "bin"
    if not tinytex_bin.exists():
        return None
    # Find architecture-specific bin dir
    for arch_dir in tinytex_bin.iterdir():
        tlmgr = arch_dir / "tlmgr"
        if tlmgr.exists():
            return tlmgr
    return None


@pytest.mark.slow
class TestLaTeXPackages:
    """Test LaTeX package availability."""

    def test_unicode_packages_installed(self) -> None:
        """Verify CJK and emoji packages are installed in TinyTeX."""
        tlmgr = get_tlmgr_path()
        if tlmgr is None:
            pytest.skip("TinyTeX not installed")

        result = subprocess.run(
            [str(tlmgr), "list", "--only-installed"],
            capture_output=True,
            text=True,
            check=True,
        )
        installed = result.stdout

        for package in UNICODE_PACKAGES:
            assert f"i {package}" in installed or package in installed, (
                f"Package {package} not installed. Run: uv run python scripts/setup_latex.py"
            )
```

**Step 2: Run test (will skip if TinyTeX not installed)**

Run: `uv run pytest tests/unit/test_latex_packages.py -v -m slow`

Expected: Test passes (or skips if TinyTeX not present)

**Step 3: Commit**

```bash
git add tests/unit/test_latex_packages.py
git commit -m "test(latex): add package verification test for unicode support (#101)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 4 Verification

**Done when:**
- [ ] `scripts/setup_latex.py` installs emoji, luatexja, notocjksc packages
- [ ] Memory warning displayed after installation
- [ ] Test verifies packages are installed
- [ ] LuaLaTeX can compile documents with `\usepackage{emoji}` and `\usepackage{luatexja-fontspec}`

**Verification commands:**

```bash
# Run setup script
uv run python scripts/setup_latex.py

# Verify packages installed
~/.TinyTeX/bin/x86_64-linux/tlmgr list --only-installed | grep -E "(emoji|luatexja|notocjksc)"

# Test compilation (create temp file)
echo '\documentclass{article}
\usepackage{emoji}
\usepackage{luatexja-fontspec}
\begin{document}
Test
\end{document}' > /tmp/test-unicode.tex
~/.TinyTeX/bin/x86_64-linux/latexmk -lualatex -interaction=nonstopmode /tmp/test-unicode.tex
```
