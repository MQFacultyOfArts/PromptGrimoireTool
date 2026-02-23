"""Tests for the public resolve_tristate helper."""

from __future__ import annotations


def test_resolve_tristate_importable() -> None:
    """resolve_tristate is importable from db.workspaces (no underscore prefix)."""
    from promptgrimoire.db.workspaces import resolve_tristate

    assert callable(resolve_tristate)


def test_resolve_tristate_override_none_uses_default_true() -> None:
    """When override is None, the course default (True) is returned."""
    from promptgrimoire.db.workspaces import resolve_tristate

    assert resolve_tristate(None, True) is True


def test_resolve_tristate_override_none_uses_default_false() -> None:
    """When override is None, the course default (False) is returned."""
    from promptgrimoire.db.workspaces import resolve_tristate

    assert resolve_tristate(None, False) is False


def test_resolve_tristate_override_true() -> None:
    """Activity-level True overrides a False course default."""
    from promptgrimoire.db.workspaces import resolve_tristate

    assert resolve_tristate(True, False) is True


def test_resolve_tristate_override_false() -> None:
    """Activity-level False overrides a True course default."""
    from promptgrimoire.db.workspaces import resolve_tristate

    assert resolve_tristate(False, True) is False
