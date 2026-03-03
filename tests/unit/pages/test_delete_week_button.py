"""Unit tests for delete week button and _confirm_and_delete helper.

Verifies the structural aspects that can be tested without running the UI:
- Required imports exist in the courses module
- _confirm_and_delete helper has correct signature
- _render_week_management_controls accepts on_delete parameter
- _render_week_header accepts on_delete parameter
"""

from __future__ import annotations

import inspect


def test_delete_week_imported() -> None:
    """courses module must import delete_week from db.weeks."""
    import promptgrimoire.pages.courses as mod

    assert hasattr(mod, "delete_week"), (
        "courses module does not import delete_week from promptgrimoire.db.weeks"
    )


def test_deletion_blocked_error_imported() -> None:
    """courses module must import DeletionBlockedError from db.exceptions."""
    import promptgrimoire.pages.courses as mod

    assert hasattr(mod, "DeletionBlockedError"), (
        "courses module does not import DeletionBlockedError"
        " from promptgrimoire.db.exceptions"
    )


def test_confirm_and_delete_exists_and_is_async() -> None:
    """_confirm_and_delete must be an async function."""
    from promptgrimoire.pages.courses import _confirm_and_delete

    assert inspect.iscoroutinefunction(_confirm_and_delete), (
        "_confirm_and_delete must be an async function"
    )


def test_confirm_and_delete_signature() -> None:
    """_confirm_and_delete must accept the expected keyword-only parameters."""
    from promptgrimoire.pages.courses import _confirm_and_delete

    sig = inspect.signature(_confirm_and_delete)
    param_names = list(sig.parameters.keys())
    # All parameters should be keyword-only
    for name, param in sig.parameters.items():
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"Parameter {name} should be keyword-only"
        )
    assert "entity_label" in param_names
    assert "delete_fn" in param_names
    assert "entity_id" in param_names
    assert "is_admin" in param_names
    assert "on_success" in param_names


def test_render_week_management_controls_accepts_on_delete() -> None:
    """_render_week_management_controls must accept on_delete parameter."""
    from promptgrimoire.pages.courses import _render_week_management_controls

    sig = inspect.signature(_render_week_management_controls)
    assert "on_delete" in sig.parameters, (
        "_render_week_management_controls must accept on_delete parameter"
    )
    # on_delete should default to None
    param = sig.parameters["on_delete"]
    assert param.default is None, "on_delete should default to None"


def test_render_week_header_accepts_on_delete() -> None:
    """_render_week_header must accept on_delete parameter."""
    from promptgrimoire.pages.courses import _render_week_header

    sig = inspect.signature(_render_week_header)
    assert "on_delete" in sig.parameters, (
        "_render_week_header must accept on_delete parameter"
    )
    # on_delete should default to None
    param = sig.parameters["on_delete"]
    assert param.default is None, "on_delete should default to None"
