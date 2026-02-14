"""Guard tests: annotation package structure invariants.

After the annotation.py monolith was split into pages/annotation/ package
(Issue #120, Phase 2), these tests prevent structural regression:

- The package directory must exist with __init__.py (AC1.1)
- The monolith annotation.py must NOT exist as a file (AC1.2, AC1.6)
- All 9 authored modules must be present (AC1.3)
- No PLC0415 per-file-ignores for the annotation package (AC3.3)
- The package must be importable (smoke test)

See: docs/implementation-plans/2026-02-14-120-annotation-split/phase_02.md
"""

from pathlib import Path

_PAGES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "promptgrimoire" / "pages"
)

_ANNOTATION_PKG = _PAGES_DIR / "annotation"

_AUTHORED_MODULES = (
    "__init__.py",
    "broadcast.py",
    "cards.py",
    "content_form.py",
    "css.py",
    "document.py",
    "highlights.py",
    "pdf_export.py",
    "workspace.py",
)


def test_annotation_is_package_directory() -> None:
    """AC1.1: pages/annotation/ must be a directory (package), not a file."""
    assert _ANNOTATION_PKG.is_dir(), (
        f"Expected {_ANNOTATION_PKG} to be a directory (Python package), "
        f"but it {'does not exist' if not _ANNOTATION_PKG.exists() else 'is a file'}."
    )


def test_annotation_init_exists() -> None:
    """AC1.1: Package must have __init__.py."""
    init_file = _ANNOTATION_PKG / "__init__.py"
    assert init_file.is_file(), (
        f"Expected {init_file} to exist. A Python package requires __init__.py."
    )


def test_monolith_annotation_py_does_not_exist() -> None:
    """AC1.2, AC1.6: annotation.py must not exist as a file alongside the package.

    If someone recreates pages/annotation.py as a file, it would shadow
    the package directory and break all imports. This test catches that.
    """
    monolith = _PAGES_DIR / "annotation.py"
    assert not monolith.exists(), (
        f"Found {monolith} — the monolith annotation.py must not exist. "
        f"The annotation module is now a package at {_ANNOTATION_PKG}/. "
        f"A file here would shadow the package and break all imports."
    )


def test_all_authored_modules_exist() -> None:
    """AC1.3: All 9 authored modules must be present in the package."""
    missing = [
        name for name in _AUTHORED_MODULES if not (_ANNOTATION_PKG / name).is_file()
    ]
    assert not missing, (
        f"Missing modules in {_ANNOTATION_PKG}:\n"
        + "\n".join(f"  {m}" for m in missing)
        + "\n\nExpected modules: "
        + ", ".join(_AUTHORED_MODULES)
    )


def test_no_plc0415_ignores_for_annotation_package() -> None:
    """AC3.3: No PLC0415 per-file-ignores for the annotation package in pyproject.toml.

    The annotation package uses definition-before-import ordering in __init__.py
    to resolve circular dependencies. There must be no PLC0415 (import-outside-
    toplevel) lint suppression for any annotation package module.
    """
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    assert pyproject.is_file(), f"pyproject.toml not found at {pyproject}"

    content = pyproject.read_text()

    # Check for any per-file-ignores targeting the annotation package
    # Patterns to catch:
    #   "src/promptgrimoire/pages/annotation/__init__.py" = ["PLC0415", ...]
    #   "src/promptgrimoire/pages/annotation/*.py" = ["PLC0415", ...]
    #   "src/promptgrimoire/pages/annotation/**/*.py" = ["PLC0415", ...]
    violations: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if "pages/annotation" in stripped and "PLC0415" in stripped:
            violations.append(stripped)

    assert not violations, (
        "Found PLC0415 per-file-ignores for annotation package in pyproject.toml.\n"
        "The annotation package must not suppress import-outside-toplevel warnings.\n"
        "It uses definition-before-import ordering instead of late imports.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_annotation_package_imports_succeed() -> None:
    """Smoke test: the package must be importable with key public names."""
    from promptgrimoire.pages.annotation import PageState, annotation_page

    # Verify they are callable/usable (not None or missing)
    assert PageState is not None, "PageState not found in annotation package"
    assert annotation_page is not None, (
        "annotation_page not found in annotation package"
    )
