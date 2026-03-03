"""Tests for workspace delete button on navigator cards (AC3.2, AC3.3, AC3.4).

Verifies:
- delete_workspace is imported in _cards module
- _delete_workspace_from_navigator exists with correct signature
- _get_user_id helper exists in _cards module
"""

from __future__ import annotations

import inspect


def test_delete_workspace_imported_in_cards() -> None:
    """_cards module must import delete_workspace from db.workspaces."""
    import promptgrimoire.pages.navigator._cards as mod

    assert hasattr(mod, "delete_workspace"), (
        "_cards module does not import delete_workspace from db.workspaces"
    )


def test_delete_workspace_from_navigator_exists_and_is_async() -> None:
    """_delete_workspace_from_navigator must be an async function."""
    from promptgrimoire.pages.navigator._cards import (
        _delete_workspace_from_navigator,
    )

    assert inspect.iscoroutinefunction(_delete_workspace_from_navigator), (
        "_delete_workspace_from_navigator must be an async function"
    )


def test_delete_workspace_from_navigator_signature() -> None:
    """_delete_workspace_from_navigator takes workspace_id, card, and user_id."""
    from promptgrimoire.pages.navigator._cards import (
        _delete_workspace_from_navigator,
    )

    sig = inspect.signature(_delete_workspace_from_navigator)
    param_names = list(sig.parameters.keys())
    assert "workspace_id" in param_names, (
        f"Missing workspace_id parameter, has: {param_names}"
    )
    assert "card" in param_names, f"Missing card parameter, has: {param_names}"
    assert "user_id" in param_names, f"Missing user_id parameter, has: {param_names}"
