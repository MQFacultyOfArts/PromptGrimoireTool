"""Guard tests: annotation package structure invariants.

After the annotation.py monolith was split into pages/annotation/ package
(Issue #120, Phase 2), these tests prevent structural regression:

- The package directory must exist with __init__.py (AC1.1)
- The monolith annotation.py must NOT exist as a file (AC1.2, AC1.6)
- All 13 authored modules must be present (AC1.3, AC1.4)
- Satellite modules (organise, respond, tags) are inside the package (AC1.4)
- No satellite files at pages/ level (AC1.5)
- No imports from old annotation_organise/respond/tags paths (AC3.1)
- No PLC0415 per-file-ignores for the annotation package (AC3.3)
- The package must be importable (smoke test)

See: docs/implementation-plans/2026-02-14-annotation-split-120/phase_02.md
See: docs/implementation-plans/2026-02-14-annotation-split-120/phase_03.md
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
    "organise.py",
    "pdf_export.py",
    "respond.py",
    "tag_management.py",
    "tags.py",
    "workspace.py",
)

# Satellite files that must NOT exist at the pages/ level (AC1.5).
# These were moved into the annotation package in Phase 3.
_LEGACY_SATELLITE_FILES = (
    "annotation_organise.py",
    "annotation_respond.py",
    "annotation_tags.py",
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
    """AC1.3, AC1.4: All 13 authored modules must be present in the package."""
    missing = [
        name for name in _AUTHORED_MODULES if not (_ANNOTATION_PKG / name).is_file()
    ]
    assert not missing, (
        f"Missing modules in {_ANNOTATION_PKG}:\n"
        + "\n".join(f"  {m}" for m in missing)
        + "\n\nExpected modules: "
        + ", ".join(_AUTHORED_MODULES)
    )


def test_no_satellite_files_at_pages_level() -> None:
    """AC1.5: No annotation_organise/respond/tags.py at pages/ level.

    These files were moved into the annotation package in Phase 3.
    If they reappear at the pages/ level, imports would be ambiguous.
    """
    found = [name for name in _LEGACY_SATELLITE_FILES if (_PAGES_DIR / name).exists()]
    assert not found, (
        "Found legacy satellite files at pages/ level:\n"
        + "\n".join(f"  {f}" for f in found)
        + "\n\nThese were moved into pages/annotation/ in Phase 3. "
        + "Remove the pages/-level copies."
    )


def test_no_imports_from_old_satellite_paths() -> None:
    """AC3.1: No source or test file imports from old satellite module paths.

    After Phase 3, all imports must use the new paths:
      promptgrimoire.pages.annotation.organise (not annotation_organise)
      promptgrimoire.pages.annotation.respond  (not annotation_respond)
      promptgrimoire.pages.annotation.tags     (not annotation_tags)
    """
    import re

    src_root = _PAGES_DIR.parent.parent  # src/
    test_root = _PAGES_DIR.parent.parent.parent / "tests"

    old_pattern = re.compile(
        r"^\s*(from|import)\s+promptgrimoire\.pages\.annotation_(organise|respond|tags)\b"
    )

    violations: list[str] = []
    for root in (src_root, test_root):
        for py_file in sorted(root.rglob("*.py")):
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                if old_pattern.match(line):
                    violations.append(
                        f"  {py_file.relative_to(root.parent)}:{i}: {line.strip()}"
                    )

    assert not violations, (
        "Found imports using old satellite module paths:\n"
        + "\n".join(violations)
        + "\n\nUse promptgrimoire.pages.annotation.{organise,respond,tags} instead."
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
