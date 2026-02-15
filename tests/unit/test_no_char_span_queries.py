"""Guard tests for AC3.5, AC8.4, and AC8.5 — no legacy identifiers in annotation page.

AC3.5: Old presence symbols deleted (_connected_clients, _ClientState, etc.).
AC8.4: No querySelector('[data-char-index]') calls exist in the annotation page JS.
AC8.5: Throb animation uses only ::highlight()-compatible CSS properties.
"""

import re
from pathlib import Path


def _read_annotation_package_source() -> str:
    """Read all .py files in the annotation package and concatenate their source."""
    parts: list[str] = []
    for py_file in sorted(_ANNOTATION_PKG.glob("*.py")):
        parts.append(py_file.read_text())
    return "\n".join(parts)


def test_no_char_index_queries_in_annotation_py() -> None:
    """AC8.4: no querySelector('[data-char-index]') in annotation package."""
    source = _read_annotation_package_source()

    # Check for both quoted forms: single and double quotes
    assert "data-char-index" not in source, (
        "annotation package contains 'data-char-index' reference — "
        "char-span DOM queries must be removed"
    )


def test_no_char_index_queries_in_annotation_highlight_js() -> None:
    """AC8.4: annotation-highlight.js contains no data-char-index references."""
    js_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "promptgrimoire"
        / "static"
        / "annotation-highlight.js"
    )
    source = js_path.read_text()

    assert "data-char-index" not in source, (
        "annotation-highlight.js contains 'data-char-index' reference — "
        "char-span DOM queries must be removed"
    )


_ANNOTATION_PKG = (
    Path(__file__).parent.parent.parent
    / "src"
    / "promptgrimoire"
    / "pages"
    / "annotation"
)


def test_no_old_presence_symbols_in_annotation_py() -> None:
    """AC3.5: Old presence identifiers are deleted from annotation package."""
    source = _read_annotation_package_source()

    forbidden = [
        "_connected_clients",
        "_ClientState",
        "_build_remote_cursor_css",
        "_build_remote_selection_css",
    ]
    for symbol in forbidden:
        assert symbol not in source, (
            f"annotation package still contains '{symbol}' — "
            "old presence symbols must be removed (AC3.5)"
        )


def test_hl_throb_css_rule_uses_only_background_color() -> None:
    """AC8.5: The ::highlight(hl-throb) CSS rule uses only background-color.

    The CSS Highlight API only supports a limited set of properties.
    Since we're using ::highlight(), we must restrict to supported properties.
    """
    source = _read_annotation_package_source()

    # Find the hl-throb CSS rule
    pattern = r"::highlight\(hl-throb\)\s*\{([^}]+)\}"
    match = re.search(pattern, source)
    assert match is not None, (
        "Could not find ::highlight(hl-throb) CSS rule in annotation package"
    )

    css_content = match.group(1)

    # Extract all CSS properties (format: property: value;)
    property_pattern = r"(\w+-?\w+)\s*:"
    properties = re.findall(property_pattern, css_content)

    # The only allowed property is background-color
    unsupported = [p for p in properties if p != "background-color"]
    assert not unsupported, (
        f"::highlight(hl-throb) contains unsupported CSS properties: {unsupported}. "
        "Only background-color is supported in ::highlight() pseudo-elements."
    )
