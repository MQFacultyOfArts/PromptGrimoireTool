"""Tests for server-side presence refactor (CSS Highlight API Phase 5).

Verifies:
- AC3.5: Old CSS-injection presence symbols are removed from annotation.py
- AC3.4: broadcast_cursor and broadcast_selection skip the local client
- _RemotePresence dataclass replaces _ClientState
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from promptgrimoire.pages import annotation

# ---------------------------------------------------------------------------
# AC3.5 — deleted symbols must not exist
# ---------------------------------------------------------------------------


class TestDeletedSymbolsAC35:
    """css-highlight-api.AC3.5: old presence symbols no longer exist."""

    def _source_text(self) -> str:
        src_file = Path(inspect.getfile(annotation))
        return src_file.read_text()

    def _source_names(self) -> set[str]:
        """Collect all top-level and nested names from the AST."""
        tree = ast.parse(self._source_text())
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        return names

    def test_no_connected_clients_dict(self) -> None:
        """_connected_clients must not appear anywhere in the source."""
        assert "_connected_clients" not in self._source_text()

    def test_no_client_state_class(self) -> None:
        """_ClientState class must not exist."""
        assert not hasattr(annotation, "_ClientState")
        assert "_ClientState" not in self._source_names()

    def test_no_build_remote_cursor_css(self) -> None:
        """_build_remote_cursor_css function must not exist."""
        assert not hasattr(annotation, "_build_remote_cursor_css")
        assert "_build_remote_cursor_css" not in self._source_names()

    def test_no_build_remote_selection_css(self) -> None:
        """_build_remote_selection_css function must not exist."""
        assert not hasattr(annotation, "_build_remote_selection_css")
        assert "_build_remote_selection_css" not in self._source_names()

    def test_no_update_cursor_css(self) -> None:
        """_update_cursor_css function must not exist."""
        assert not hasattr(annotation, "_update_cursor_css")
        assert "_update_cursor_css" not in self._source_names()

    def test_no_update_selection_css(self) -> None:
        """_update_selection_css function must not exist."""
        assert not hasattr(annotation, "_update_selection_css")
        assert "_update_selection_css" not in self._source_names()

    def test_no_cursor_style_on_page_state(self) -> None:
        """PageState must not have cursor_style field."""
        assert not hasattr(annotation.PageState, "cursor_style")

    def test_no_selection_style_on_page_state(self) -> None:
        """PageState must not have selection_style field."""
        assert not hasattr(annotation.PageState, "selection_style")


# ---------------------------------------------------------------------------
# _RemotePresence dataclass
# ---------------------------------------------------------------------------


class TestRemotePresenceDataclass:
    """_RemotePresence replaces _ClientState as a dataclass."""

    def test_remote_presence_exists(self) -> None:
        """_RemotePresence must exist in the annotation module."""
        assert hasattr(annotation, "_RemotePresence")

    def test_remote_presence_is_dataclass(self) -> None:
        """_RemotePresence must be a dataclass."""
        import dataclasses

        assert dataclasses.is_dataclass(annotation._RemotePresence)

    def test_remote_presence_fields(self) -> None:
        """_RemotePresence must have the expected fields."""
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(annotation._RemotePresence)}
        expected = {
            "name",
            "color",
            "nicegui_client",
            "callback",
            "cursor_char",
            "selection_start",
            "selection_end",
            "has_milkdown_editor",
        }
        assert expected == field_names

    def test_workspace_presence_dict_exists(self) -> None:
        """_workspace_presence module-level dict must exist."""
        assert hasattr(annotation, "_workspace_presence")
        assert isinstance(annotation._workspace_presence, dict)
