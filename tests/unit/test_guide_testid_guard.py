"""Structural guard: testids in tests/doc scripts must exist in pages.

Scans test files (``tests/``) and doc script files
(``src/promptgrimoire/docs/scripts/``) for testid references, then verifies
each referenced testid is defined somewhere in ``src/promptgrimoire/pages/``.

Uses AST parsing to extract string arguments from ``get_by_test_id()`` calls,
``data-testid=`` string literals, ``data-testid^=`` prefix selectors, and
``highlight=`` lists in the Guide DSL.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_PAGES_DIR = Path("src/promptgrimoire/pages")
_TESTS_DIR = Path("tests")
_SCRIPTS_DIR = Path("src/promptgrimoire/docs/scripts")

# Testids that cannot be found statically.  Each entry needs a comment.
ALLOWED_TESTIDS: set[str] = {
    # Indirect: string stored in tuple, interpolated via
    # f'data-testid="{testid}"' at annotation/css.py:455
    "tag-settings-btn",
    "tag-create-btn",
    # Indirect: prefix passed to _add_option_testids() which
    # constructs Vue :data-testid bindings at runtime
    "placement-course-opt-",
    "placement-week-opt-",
    "placement-activity-opt-",
    # Dynamic: built from section_key at runtime in navigator/_sections.py
    "section-header-unstarted",
    "section-header-my-work",
}

# Files whose testid references are test fixtures / infrastructure,
# not real page testid references.
_EXCLUDED_FILES: set[str] = {
    # Unit tests for the Guide/Screenshot DSL itself use fake testids
    "test_docs_guide.py",
    "test_docs_screenshot.py",
    # This guard file contains testid regexes that look like testids
    "test_guide_testid_guard.py",
    # NiceGUI test helpers use placeholder testids in docstrings
    "nicegui_helpers.py",
    # Session contamination reproducer (#438) uses testids from test-only
    # routes in conftest.py and cli/e2e/_server_script.py, not pages/
    "test_session_contamination.py",
    "conftest.py",
}


def _extract_string_value(node: ast.expr) -> str | None:
    """Extract a plain string value from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


_Ref = tuple[str, Path, int]


def _refs_from_string_literal(
    s: str,
    py_file: Path,
    lineno: int,
    exact_refs: list[_Ref],
    prefix_refs: list[_Ref],
) -> None:
    """Extract testid references from a string literal value."""
    # data-testid^="foo" -> prefix reference
    for m in re.finditer(r'data-testid\^="([^"]+)"', s):
        prefix_refs.append((m.group(1), py_file, lineno))
    # data-testid="foo" -> exact reference (skip dynamic {})
    for m in re.finditer(r'data-testid="([^"]+)"', s):
        tid = m.group(1)
        if "{" not in tid:
            exact_refs.append((tid, py_file, lineno))


def _collect_references(
    py_files: list[Path],
) -> tuple[list[_Ref], list[_Ref]]:
    """Collect testid references from Python files.

    Returns (exact_refs, prefix_refs) where each element is
    (testid, file_path, line_number).
    """
    exact_refs: list[_Ref] = []
    prefix_refs: list[_Ref] = []

    for py_file in py_files:
        if py_file.name in _EXCLUDED_FILES:
            continue
        source = py_file.read_text()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # get_by_test_id("foo") -> exact reference
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_by_test_id"
                and node.args
            ):
                val = _extract_string_value(node.args[0])
                if val:
                    exact_refs.append((val, py_file, node.lineno))

            # String literals containing data-testid patterns
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                _refs_from_string_literal(
                    node.value,
                    py_file,
                    node.lineno,
                    exact_refs,
                    prefix_refs,
                )

            # highlight=["foo", "bar"] -> prefix references
            if (
                isinstance(node, ast.keyword)
                and node.arg == "highlight"
                and isinstance(node.value, ast.List)
            ):
                for elt in node.value.elts:
                    val = _extract_string_value(elt)
                    if val:
                        prefix_refs.append((val, py_file, getattr(node, "lineno", 0)))

    return exact_refs, prefix_refs


# Matches both quoted and unquoted data-testid values.
# Group 1: quoted value, Group 2: unquoted value (up to space/quote).
_TESTID_RE = re.compile(
    r'data-testid="([^"]*)"'
    r"|"
    r"data-testid=([^\s\"'>]+)"
)

# Vue-style :data-testid binding with a prefix string.
# Matches patterns like :data-testid="'prefix-' + expr"
_VUE_TESTID_RE = re.compile(r""":data-testid="'([^']+)'""")


def _classify_testid(
    tid: str,
    exact_testids: set[str],
    prefix_testids: set[str],
    *,
    dynamic_marker: str = "{",
) -> None:
    """Add a testid to exact or prefix set based on dynamism."""
    if dynamic_marker in tid:
        static = tid.split(dynamic_marker, maxsplit=1)[0]
        if static:
            prefix_testids.add(static)
    else:
        exact_testids.add(tid)


def _defs_from_fstring(
    node: ast.JoinedStr,
    exact_testids: set[str],
    prefix_testids: set[str],
) -> None:
    """Extract testid definitions from an f-string AST node.

    F-strings like ``f'data-testid="foo-{x}"'`` split across
    Constant and FormattedValue nodes.  We reconstruct the
    static prefix before each ``{`` interpolation.
    """
    parts: list[str] = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        else:
            parts.append("{}")
    combined = "".join(parts)
    for m in _TESTID_RE.finditer(combined):
        tid = m.group(1) or m.group(2)
        _classify_testid(tid, exact_testids, prefix_testids, dynamic_marker="{}")


def _collect_definitions(
    pages_dir: Path,
) -> tuple[set[str], set[str]]:
    """Collect testid definitions from pages source files.

    Returns (exact_testids, prefix_testids) where prefix_testids
    are stems of dynamic testids (e.g. ``foo-`` from ``foo-{bar}``).
    """
    exact_testids: set[str] = set()
    prefix_testids: set[str] = set()

    for py_file in sorted(pages_dir.rglob("*.py")):
        source = py_file.read_text()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Plain string constants (quoted and unquoted)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for m in _TESTID_RE.finditer(node.value):
                    tid = m.group(1) or m.group(2)
                    _classify_testid(tid, exact_testids, prefix_testids)
                # Vue-style bound testid prefix patterns
                for m in _VUE_TESTID_RE.finditer(node.value):
                    prefix_testids.add(m.group(1))

            # F-strings: data-testid="prefix-{dynamic}"
            if isinstance(node, ast.JoinedStr):
                _defs_from_fstring(node, exact_testids, prefix_testids)

    return exact_testids, prefix_testids


def _testid_exists(
    tid: str,
    exact_defs: set[str],
    prefix_defs: set[str],
    *,
    is_prefix: bool,
) -> bool:
    """Check if a testid reference resolves to a definition.

    For exact references: must appear as an exact definition, OR
    the reference must be a prefix of a dynamic testid.

    For prefix references: must match exactly, OR must be a prefix
    of at least one exact or dynamic definition.
    """
    if tid in ALLOWED_TESTIDS:
        return True
    if tid in exact_defs:
        return True
    # Check if tid is a prefix of any dynamic testid prefix
    # e.g. "start-activity-btn" matches prefix "start-activity-btn-"
    for pfx in prefix_defs:
        if pfx.startswith(tid) or tid.startswith(pfx):
            return True
    if is_prefix:
        # For prefix refs, also check if any exact testid starts with this prefix
        return any(etid.startswith(tid) for etid in exact_defs)
    return False


def test_testid_references_resolve() -> None:
    """Every data-testid referenced in tests or doc scripts must exist in pages.

    If this test fails, either:
    1. Fix the testid reference to match the actual testid in pages, or
    2. Add the testid to ALLOWED_TESTIDS with a comment explaining why
       it cannot be found statically.
    """
    # Collect all Python files to scan
    test_files = sorted(_TESTS_DIR.rglob("*.py"))
    script_files = sorted(_SCRIPTS_DIR.rglob("*.py"))
    ref_files = test_files + script_files

    exact_refs, prefix_refs = _collect_references(ref_files)
    exact_defs, prefix_defs = _collect_definitions(_PAGES_DIR)

    violations: list[str] = []

    for tid, fpath, lineno in exact_refs:
        if not _testid_exists(tid, exact_defs, prefix_defs, is_prefix=False):
            violations.append(f"  {fpath}:{lineno}: exact testid {tid!r} not in pages")

    for tid, fpath, lineno in prefix_refs:
        if not _testid_exists(tid, exact_defs, prefix_defs, is_prefix=True):
            violations.append(f"  {fpath}:{lineno}: prefix testid {tid!r} not in pages")

    if violations:
        msg = (
            "Test/doc testid references that do not resolve to any "
            "data-testid in src/promptgrimoire/pages/:\n" + "\n".join(violations)
        )
        raise AssertionError(msg)
