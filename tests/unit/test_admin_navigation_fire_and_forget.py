"""Test that admin/restart navigation uses fire-and-forget JS calls.

Verifies eliminate-js-await-454.AC5.1 through AC5.3:
- AC5.1: Pre-restart client navigation is fire-and-forget
- AC5.2: Memory-threshold restart navigation is fire-and-forget
- AC5.3: Ban redirect is fire-and-forget

Traceability: Issue #454
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from unittest.mock import MagicMock
from uuid import UUID

from promptgrimoire.auth.client_registry import disconnect_user


class TestPreRestartFireAndForget:
    """AC5.1: Pre-restart navigation is fire-and-forget."""

    def test_pre_restart_does_not_await_run_javascript(self) -> None:
        """The navigation call in pre_restart_handler is not awaited.

        Inspects the source AST to confirm ``client.run_javascript``
        is called outside an ``await`` expression.
        """
        from promptgrimoire.pages.restart import pre_restart_handler

        source = textwrap.dedent(inspect.getsource(pre_restart_handler))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Await):
                inner = node.value
                if isinstance(inner, ast.Call):
                    func = inner.func
                    # Check for run_javascript as an attribute call
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "run_javascript"
                    ):
                        msg = (
                            "pre_restart_handler still awaits "
                            "client.run_javascript — should be fire-and-forget"
                        )
                        raise AssertionError(msg)


class TestMemoryRestartFireAndForget:
    """AC5.2: Memory-threshold restart navigation is fire-and-forget."""

    def test_navigate_clients_does_not_await_run_javascript(self) -> None:
        """_navigate_clients_to_restarting does not await run_javascript."""
        from promptgrimoire.diagnostics import _navigate_clients_to_restarting

        source = textwrap.dedent(inspect.getsource(_navigate_clients_to_restarting))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Await):
                inner = node.value
                if isinstance(inner, ast.Call):
                    func = inner.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "run_javascript"
                    ):
                        msg = (
                            "_navigate_clients_to_restarting still awaits "
                            "run_javascript — should be fire-and-forget"
                        )
                        raise AssertionError(msg)


class TestBanRedirectFireAndForget:
    """AC5.3: Ban redirect is fire-and-forget."""

    def test_disconnect_user_is_not_coroutine(self) -> None:
        assert not inspect.iscoroutinefunction(disconnect_user)

    def test_disconnect_user_only_counts_successful_sends(self) -> None:
        """Counter only increments when run_javascript succeeds."""
        from promptgrimoire.auth import client_registry

        user_id = UUID("00000000-0000-0000-0000-000000000001")

        client_ok = MagicMock()
        client_fail = MagicMock()
        client_fail.run_javascript = MagicMock(side_effect=RuntimeError("disconnected"))

        client_registry._registry[user_id] = {client_ok, client_fail}

        count = disconnect_user(user_id)

        # Only the successful send is counted
        assert count == 1

    def test_disconnect_user_calls_run_javascript_sync(self) -> None:
        """run_javascript is called without await."""
        from promptgrimoire.auth import client_registry

        user_id = UUID("00000000-0000-0000-0000-000000000002")
        client = MagicMock()
        client_registry._registry[user_id] = {client}

        disconnect_user(user_id)

        client.run_javascript.assert_called_once()
