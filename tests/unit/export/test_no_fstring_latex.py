"""Guard test: migrated export modules must not regress to f-string LaTeX.

After the Phase 4 t-string migration (AC4.1, AC4.2), the following functions
use ``latex_cmd()`` / ``render_latex()`` / ``NoEscape`` instead of f-string
LaTeX command construction:

- ``preamble.generate_tag_colour_definitions()``
- ``latex_format.format_annot_latex()``
- ``unicode_latex.escape_unicode_latex()`` (via ``_format_emoji_for_latex``)

This test scans those files for f-string patterns containing LaTeX command
backslashes (``\\``) to catch accidental regression.  Known exceptions
(``build_annotation_preamble``, ``build_font_preamble``, ``format_annot_latex``
scriptsize wrappers) are explicitly allowlisted.
"""

import ast
from pathlib import Path

_EXPORT_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "promptgrimoire"
    / "export"
)

# Files that were migrated in Phase 4
_MIGRATED_FILES = (
    "preamble.py",
    "latex_format.py",
    "unicode_latex.py",
)

# Functions whose f-string LaTeX usage is explicitly allowed.
# Key: filename, Value: set of function names.
_ALLOWED_FUNCTIONS: dict[str, set[str]] = {
    # build_annotation_preamble() uses f-string for preamble assembly
    # (\\usepackage interpolation), not LaTeX command construction.
    "preamble.py": {"build_annotation_preamble"},
    # format_annot_latex() retains f-string \\par{\\scriptsize ...} wrappers
    # because the interpolated values are already NoEscape-wrapped.
    # build_font_preamble() uses f-strings for \\directlua blocks.
    "latex_format.py": {"format_annot_latex"},
    "unicode_latex.py": {"build_font_preamble"},
}


def _fstring_nodes_with_backslash(
    tree: ast.Module,
) -> list[tuple[int, str]]:
    """Find JoinedStr (f-string) nodes whose static parts contain backslashes.

    Returns list of (line_number, enclosing_function_name) tuples.
    """
    results: list[tuple[int, str]] = []

    # Walk tree tracking enclosing function name
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        func_name = node.name
        for child in ast.walk(node):
            if isinstance(child, ast.JoinedStr):
                # Check if any Constant part of the f-string contains backslash
                for part in child.values:
                    if (
                        isinstance(part, ast.Constant)
                        and isinstance(part.value, str)
                        and "\\" in part.value
                    ):
                        results.append((child.lineno, func_name))
                        break  # One hit per f-string is enough

    return results


def test_no_fstring_latex_in_migrated_files() -> None:
    """Migrated export files must not contain f-string LaTeX command construction.

    After Phase 4 migration to latex_cmd()/render_latex()/NoEscape, the three
    migrated files should use the latex_render module for LaTeX command building.
    This test catches regressions where someone adds a new f-string containing
    LaTeX backslash commands instead of using the structured API.

    Allowed exceptions are documented in _ALLOWED_FUNCTIONS.
    """
    violations: list[str] = []

    for filename in _MIGRATED_FILES:
        filepath = _EXPORT_DIR / filename
        assert filepath.exists(), f"Migrated file not found: {filepath}"

        content = filepath.read_text()
        tree = ast.parse(content, filename=filename)

        allowed = _ALLOWED_FUNCTIONS.get(filename, set())
        hits = _fstring_nodes_with_backslash(tree)

        for lineno, func_name in hits:
            if func_name in allowed:
                continue
            violations.append(
                f"{filename}:{lineno} in {func_name}() - "
                f"f-string with LaTeX backslash (use latex_cmd/render_latex instead)"
            )

    assert not violations, (
        "F-string LaTeX patterns found in migrated files.\n"
        "After Phase 4 migration, use latex_cmd() / render_latex() / NoEscape\n"
        "instead of f-string LaTeX command construction.\n\n"
        "If this is intentional, add the function to _ALLOWED_FUNCTIONS in\n"
        f"{Path(__file__).name}.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


def test_migrated_files_import_latex_render() -> None:
    """Migrated files must import from latex_render module.

    Ensures the migration is not circumvented by removing the import.
    """
    for filename in _MIGRATED_FILES:
        filepath = _EXPORT_DIR / filename
        content = filepath.read_text()

        assert "from promptgrimoire.export.latex_render import" in content, (
            f"{filename} does not import from latex_render module. "
            f"Migrated files must use latex_cmd/NoEscape/render_latex."
        )
