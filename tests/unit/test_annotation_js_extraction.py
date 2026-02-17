"""Guard test: JS extraction structural invariants.

Verifies that scroll-sync card positioning and copy protection JavaScript
has been extracted from Python string constants to static JS files, and
that no Python file in the source tree retains the old constant.

Traceability:
- Design: docs/implementation-plans/2026-02-14-annotation-split-120/phase_01.md
- AC: 120-annotation-split.AC2.1, AC2.2, AC2.5
"""

from pathlib import Path

_STATIC_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "promptgrimoire" / "static"
)

_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "promptgrimoire"


class TestCardSyncJsExists:
    """AC2.1: static/annotation-card-sync.js exists and exposes setupCardPositioning."""

    def test_file_exists(self) -> None:
        """annotation-card-sync.js must exist in the static directory."""
        path = _STATIC_DIR / "annotation-card-sync.js"
        assert path.exists(), f"Expected file not found: {path}"

    def test_exposes_setup_function(self) -> None:
        """annotation-card-sync.js must declare setupCardPositioning function."""
        path = _STATIC_DIR / "annotation-card-sync.js"
        content = path.read_text()
        assert "function setupCardPositioning" in content, (
            "annotation-card-sync.js does not contain "
            "'function setupCardPositioning' declaration"
        )


class TestCopyProtectionJsExists:
    """AC2.2: copy-protection.js exists and exposes setupCopyProtection."""

    def test_file_exists(self) -> None:
        """annotation-copy-protection.js must exist in the static directory."""
        path = _STATIC_DIR / "annotation-copy-protection.js"
        assert path.exists(), f"Expected file not found: {path}"

    def test_exposes_setup_function(self) -> None:
        """annotation-copy-protection.js must declare setupCopyProtection function."""
        path = _STATIC_DIR / "annotation-copy-protection.js"
        content = path.read_text()
        assert "function setupCopyProtection" in content, (
            "annotation-copy-protection.js does not contain "
            "'function setupCopyProtection' declaration"
        )


class TestNoCopyProtectionJsConstant:
    """AC2.5: no Python file defines _COPY_PROTECTION_JS constant."""

    def test_no_python_file_defines_constant(self) -> None:
        """No .py file in src/promptgrimoire/ should assign _COPY_PROTECTION_JS.

        The constant has been replaced by the static JS file. This guard
        prevents re-introduction of the Python string constant.
        """
        violations: list[str] = []

        for py_file in _SRC_DIR.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            content = py_file.read_text()
            for lineno, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "_COPY_PROTECTION_JS" in line and "=" in line:
                    # Check it looks like an assignment (not just a comment
                    # or string containing the name)
                    rel = py_file.relative_to(_SRC_DIR)
                    violations.append(f"{rel}:{lineno}: {stripped}")

        assert not violations, (
            "_COPY_PROTECTION_JS constant found in Python source files.\n"
            "This constant was extracted to static/annotation-copy-protection.js.\n"
            "Remove the Python constant and use setupCopyProtection() instead.\n\n"
            "Violations:\n" + "\n".join(f"  {v}" for v in violations)
        )
