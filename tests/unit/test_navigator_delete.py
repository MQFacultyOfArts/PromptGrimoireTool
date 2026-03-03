"""Unit tests for navigator workspace-delete helpers.

Acceptance Criteria:
- crud-management-229.AC3.2: _delete_workspace_from_navigator exists with correct
  signature (full navigator card flow covered by manual UAT; the navigator query
  stack requires the full UNION ALL CTE fixture which is out of scope for unit
  tests).
"""

from __future__ import annotations

import inspect

from promptgrimoire.pages.navigator._cards import _delete_workspace_from_navigator


class TestDeleteWorkspaceFromNavigatorSignature:
    """Verify _delete_workspace_from_navigator has the expected signature."""

    def test_is_coroutine(self) -> None:
        """Function must be an async coroutine."""
        assert inspect.iscoroutinefunction(_delete_workspace_from_navigator)

    def test_parameters(self) -> None:
        """Function must accept workspace_id, card, and user_id."""
        sig = inspect.signature(_delete_workspace_from_navigator)
        params = list(sig.parameters)
        assert params == ["workspace_id", "card", "user_id"], (
            f"Unexpected parameters: {params}"
        )
