"""Tests for workspace delete button on course detail page (AC3.1, AC3.3, AC3.4).

Verifies:
- delete_workspace is imported from db.workspaces
- _handle_delete_workspace exists with correct signature
- _render_activity_row accepts on_delete_workspace parameter
- _render_week_activities accepts on_delete_workspace parameter
"""

from __future__ import annotations

import inspect


def test_delete_workspace_imported() -> None:
    """courses module must import delete_workspace from db.workspaces."""
    import promptgrimoire.pages.courses as mod

    assert hasattr(mod, "delete_workspace"), (
        "courses module does not import delete_workspace from db.workspaces"
    )


def test_handle_delete_workspace_exists_and_is_async() -> None:
    """_handle_delete_workspace must be an async function."""
    from promptgrimoire.pages.courses import _handle_delete_workspace

    assert inspect.iscoroutinefunction(_handle_delete_workspace), (
        "_handle_delete_workspace must be an async function"
    )


def test_handle_delete_workspace_signature() -> None:
    """_handle_delete_workspace takes workspace_id and on_success callback."""
    from promptgrimoire.pages.courses import _handle_delete_workspace

    sig = inspect.signature(_handle_delete_workspace)
    param_names = list(sig.parameters.keys())
    assert "workspace_id" in param_names, (
        f"Missing workspace_id parameter, has: {param_names}"
    )
    assert "on_success" in param_names, (
        f"Missing on_success parameter, has: {param_names}"
    )


def test_render_activity_row_accepts_on_delete_workspace() -> None:
    """_render_activity_row must accept on_delete_workspace parameter."""
    from promptgrimoire.pages.courses import _render_activity_row

    sig = inspect.signature(_render_activity_row)
    assert "on_delete_workspace" in sig.parameters, (
        f"_render_activity_row missing on_delete_workspace parameter,"
        f" has: {list(sig.parameters)}"
    )
    param = sig.parameters["on_delete_workspace"]
    assert param.default is None, "on_delete_workspace default should be None"


def test_render_week_activities_accepts_on_delete_workspace() -> None:
    """_render_week_activities must accept on_delete_workspace parameter."""
    from promptgrimoire.pages.courses import _render_week_activities

    sig = inspect.signature(_render_week_activities)
    assert "on_delete_workspace" in sig.parameters, (
        f"_render_week_activities missing on_delete_workspace parameter,"
        f" has: {list(sig.parameters)}"
    )
    param = sig.parameters["on_delete_workspace"]
    assert param.default is None, "on_delete_workspace default should be None"
