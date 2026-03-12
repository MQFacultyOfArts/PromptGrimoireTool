"""Structural guard: cross-link anchors in guide scripts must resolve.

Every markdown cross-link like ``[text](target.md#anchor)`` in a guide
script must point to a heading that actually exists in the target guide
script.  Headings are extracted from ``guide.step()``,
``guide.section()``, and ``g.subheading()`` calls, then slugified using
the standard Pandoc/MkDocs algorithm.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SCRIPTS_DIR = Path("src/promptgrimoire/docs/scripts")

# Regex for markdown cross-links: [text](filename.md#anchor)
_CROSSLINK_RE = re.compile(r"\[.*?\]\(([\w-]+\.md)#([\w-]+)\)")

# Map generated .md filenames to their source script files.
# Guide("Title", ...) produces {slugify(title)}.md
_MD_TO_SCRIPT: dict[str, str] = {
    "instructor-setup.md": "instructor_setup.py",
    "student-workflow.md": "student_workflow.py",
    "your-personal-grimoire.md": "personal_grimoire.py",
    "using-promptgrimoire.md": "using_promptgrimoire.py",
}


def _slugify(heading: str) -> str:
    """Slugify a heading using the Pandoc/MkDocs algorithm.

    Lowercase, spaces to hyphens, strip non-alphanumeric (except
    hyphens).  Consecutive hyphens are preserved (Pandoc and
    python-markdown do not collapse them).
    """
    slug = heading.lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug.strip("-")


def _extract_headings(script_path: Path) -> set[str]:
    """Extract step/section/subheading strings from a guide script.

    Parses the AST looking for:
    - ``guide.step("heading", ...)``
    - ``guide.section("heading")``
    - ``g.subheading("heading")``

    Returns the set of slugified headings.
    """
    source = script_path.read_text()
    tree = ast.parse(source, filename=str(script_path))

    headings: set[str] = set()
    # Method names that produce headings
    heading_methods = {"step", "section", "subheading"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in heading_methods:
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            headings.add(_slugify(arg.value))

    return headings


def _extract_crosslinks(
    script_path: Path,
) -> list[tuple[str, str, int]]:
    """Extract cross-link references from string literals.

    Returns list of (target_md, anchor, lineno) tuples.
    """
    source = script_path.read_text()
    tree = ast.parse(source, filename=str(script_path))

    links: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, str):
            continue
        for m in _CROSSLINK_RE.finditer(node.value):
            links.append((m.group(1), m.group(2), node.lineno))

    return links


def test_crosslink_anchors_resolve() -> None:
    """Every cross-link anchor in guide scripts must resolve to a heading.

    If this test fails, either:
    1. Fix the anchor to match the actual heading slug, or
    2. Add the missing heading to the target guide script.
    """
    violations: list[str] = []

    # Pre-compute headings for each target script
    heading_cache: dict[str, set[str]] = {}

    for script_file in sorted(_SCRIPTS_DIR.glob("*.py")):
        if script_file.name == "__init__.py":
            continue

        links = _extract_crosslinks(script_file)
        for target_md, anchor, lineno in links:
            if target_md not in _MD_TO_SCRIPT:
                violations.append(
                    f"  {script_file}:{lineno}: unknown target {target_md!r}"
                )
                continue

            target_script = _MD_TO_SCRIPT[target_md]
            target_path = _SCRIPTS_DIR / target_script

            if target_script not in heading_cache:
                heading_cache[target_script] = _extract_headings(target_path)

            headings = heading_cache[target_script]
            if anchor not in headings:
                violations.append(
                    f"  {script_file}:{lineno}: "
                    f"anchor {anchor!r} not in "
                    f"{target_md} (available: "
                    f"{sorted(headings)!r})"
                )

    if violations:
        msg = (
            "Guide cross-link anchors that do not resolve "
            "to a heading:\n" + "\n".join(violations)
        )
        raise AssertionError(msg)
