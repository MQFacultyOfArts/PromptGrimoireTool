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
    from promptgrimoire.pages import courses as mod

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


def test_handle_edit_template_exists_and_is_async() -> None:
    """_handle_edit_template must be an async function with correct signature."""
    import inspect

    from promptgrimoire.pages.courses import _handle_edit_template

    assert inspect.iscoroutinefunction(_handle_edit_template), (
        "_handle_edit_template must be an async function"
    )
    sig = inspect.signature(_handle_edit_template)
    param_names = list(sig.parameters.keys())
    assert param_names == ["activity_id", "template_workspace_id"], (
        f"Expected (activity_id, template_workspace_id), got {param_names}"
    )


def test_has_student_workspaces_imported() -> None:
    """courses module must import has_student_workspaces from db.workspaces."""
    from promptgrimoire.pages import courses as mod

    assert hasattr(mod, "has_student_workspaces"), (
        "courses module does not import has_student_workspaces"
    )


def test_delete_activity_imported() -> None:
    """courses module must import delete_activity from db.activities."""
    from promptgrimoire.pages import courses as mod

    assert hasattr(mod, "delete_activity"), (
        "courses module does not import delete_activity"
    )


def test_render_activity_row_accepts_on_delete() -> None:
    """_render_activity_row must accept an on_delete keyword parameter."""
    import inspect

    from promptgrimoire.pages.courses import _render_activity_row

    sig = inspect.signature(_render_activity_row)
    assert "on_delete" in sig.parameters, (
        f"_render_activity_row missing on_delete parameter, has: {list(sig.parameters)}"
    )
    param = sig.parameters["on_delete"]
    assert param.default is None, "on_delete default should be None"


def test_render_week_activities_accepts_on_delete_activity() -> None:
    """_render_week_activities must accept an on_delete_activity keyword parameter."""
    import inspect

    from promptgrimoire.pages.courses import _render_week_activities

    sig = inspect.signature(_render_week_activities)
    assert "on_delete_activity" in sig.parameters, (
        "_render_week_activities missing on_delete_activity param,"
        f" has: {list(sig.parameters)}"
    )
    param = sig.parameters["on_delete_activity"]
    assert param.default is None, "on_delete_activity default should be None"
