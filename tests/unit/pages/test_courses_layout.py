"""Tests for course detail page layout migration (AC7.4).

Verifies that the course detail page uses the shared page_layout()
context manager and correctly references the courses.css file.
"""

from __future__ import annotations


def test_css_file_path_points_to_existing_file() -> None:
    """_CSS_FILE must resolve to an existing courses.css file."""
    from promptgrimoire.pages.courses import _CSS_FILE

    assert _CSS_FILE.exists(), f"CSS file not found: {_CSS_FILE}"
    assert _CSS_FILE.name == "courses.css"


def test_css_file_contains_content_column_class() -> None:
    """courses.css must define the .courses-content-column class."""
    from promptgrimoire.pages.courses import _CSS_FILE

    contents = _CSS_FILE.read_text()
    assert ".courses-content-column" in contents


def test_course_detail_page_imports_page_layout() -> None:
    """course_detail_page module must import page_layout from layout."""
    import promptgrimoire.pages.courses as mod

    # page_layout should be accessible in the module namespace
    assert hasattr(mod, "page_layout"), (
        "courses module does not import page_layout from promptgrimoire.pages.layout"
    )


def test_css_file_path_is_under_static_dir() -> None:
    """_CSS_FILE must be under the static/ directory."""
    from promptgrimoire.pages.courses import _CSS_FILE

    assert "static" in _CSS_FILE.parts, f"CSS file not under static/: {_CSS_FILE}"
    # Also check it's a .css file
    assert _CSS_FILE.suffix == ".css"
