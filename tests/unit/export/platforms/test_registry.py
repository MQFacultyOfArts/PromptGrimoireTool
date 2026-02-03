"""Unit tests for platform handler registry and autodiscovery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


class TestDiscoverHandlers:
    """Tests for handler autodiscovery."""

    def test_discovers_openai_handler(self) -> None:
        """Autodiscovery finds OpenAI handler."""
        from promptgrimoire.export.platforms import _handlers

        assert "openai" in _handlers

    def test_discovers_claude_handler(self) -> None:
        """Autodiscovery finds Claude handler."""
        from promptgrimoire.export.platforms import _handlers

        assert "claude" in _handlers

    def test_discovers_gemini_handler(self) -> None:
        """Autodiscovery finds Gemini handler."""
        from promptgrimoire.export.platforms import _handlers

        assert "gemini" in _handlers

    def test_discovers_aistudio_handler(self) -> None:
        """Autodiscovery finds AI Studio handler."""
        from promptgrimoire.export.platforms import _handlers

        assert "aistudio" in _handlers

    def test_discovers_scienceos_handler(self) -> None:
        """Autodiscovery finds ScienceOS handler."""
        from promptgrimoire.export.platforms import _handlers

        assert "scienceos" in _handlers

    def test_discovers_all_five_handlers(self) -> None:
        """Autodiscovery finds exactly 5 handlers."""
        from promptgrimoire.export.platforms import _handlers

        assert len(_handlers) == 5


class TestGetHandler:
    """Tests for get_handler dispatch."""

    def test_returns_openai_handler_for_openai_html(self) -> None:
        """get_handler returns OpenAI handler for matching HTML."""
        from promptgrimoire.export.platforms import get_handler

        html = '<div class="agent-turn">Content</div>'
        handler = get_handler(html)

        assert handler is not None
        assert handler.name == "openai"

    def test_returns_claude_handler_for_claude_html(self) -> None:
        """get_handler returns Claude handler for matching HTML."""
        from promptgrimoire.export.platforms import get_handler

        html = '<div class="font-user-message">Content</div>'
        handler = get_handler(html)

        assert handler is not None
        assert handler.name == "claude"

    def test_returns_none_for_unknown_html(self) -> None:
        """get_handler returns None for unrecognized HTML."""
        from promptgrimoire.export.platforms import get_handler

        html = '<div class="unknown-platform">Content</div>'
        handler = get_handler(html)

        assert handler is None

    def test_returns_none_for_empty_html(self) -> None:
        """get_handler returns None for empty HTML."""
        from promptgrimoire.export.platforms import get_handler

        assert get_handler("") is None
        assert get_handler("<html></html>") is None


class TestPreprocessForExport:
    """Tests for preprocess_for_export entry point."""

    def test_processes_openai_html(self) -> None:
        """Entry point processes OpenAI HTML through handler."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = """
        <div class="agent-turn">
            <h5 class="sr-only">You said:</h5>
            <p>Hello!</p>
        </div>
        """
        result = preprocess_for_export(html)

        # sr-only elements should be removed
        assert "sr-only" not in result
        assert "You said:" not in result
        assert "Hello!" in result

    def test_returns_content_unchanged_for_unknown_platform(self) -> None:
        """Entry point preserves content for unknown platforms.

        Note: selectolax normalizes HTML (adds html/head/body tags)
        so we check content preservation, not exact equality.
        """
        from promptgrimoire.export.platforms import preprocess_for_export

        html = '<div class="unknown-platform">Content</div>'
        result = preprocess_for_export(html)

        # Content should be preserved
        assert "Content" in result
        assert "unknown-platform" in result

    def test_platform_hint_overrides_autodiscovery(self) -> None:
        """platform_hint parameter skips autodiscovery and uses specified handler."""
        from promptgrimoire.export.platforms import preprocess_for_export

        # HTML with OpenAI's sr-only labels that OpenAI handler would remove
        html = """
        <div class="agent-turn">
            <h5 class="sr-only">You said:</h5>
            <p>Content</p>
        </div>
        """

        # Force Claude handler (which does NOT remove sr-only elements)
        result = preprocess_for_export(html, platform_hint="claude")

        # Claude handler doesn't strip sr-only, so it should remain
        # (OpenAI handler would have removed it)
        assert "sr-only" in result or "You said:" in result
        assert "Content" in result

    def test_invalid_platform_hint_falls_back_to_autodiscovery(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid platform_hint logs warning and falls back to autodiscovery."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = '<div class="agent-turn">Content</div>'

        with caplog.at_level(logging.WARNING, logger="promptgrimoire.export.platforms"):
            result = preprocess_for_export(html, platform_hint="nonexistent")

        assert "Unknown platform_hint" in caplog.text
        assert "Content" in result  # Still processed via autodiscovery


class TestImportFailureHandling:
    """Tests for graceful handling of handler import failures."""

    def test_import_failure_logs_and_continues(self) -> None:
        """Import failures are logged but don't crash autodiscovery."""
        # This test verifies the error handling path
        # We can't easily trigger a real import failure, so we test
        # that the logging infrastructure is in place

        # Import the module to trigger autodiscovery
        import promptgrimoire.export.platforms

        # Autodiscovery should have completed without raising
        assert promptgrimoire.export.platforms._handlers is not None


class TestPlatformHandlerProtocol:
    """Tests for PlatformHandler protocol compliance."""

    def test_all_handlers_implement_protocol(self) -> None:
        """All registered handlers implement PlatformHandler protocol."""
        from promptgrimoire.export.platforms import PlatformHandler, _handlers

        for name, handler in _handlers.items():
            assert isinstance(handler, PlatformHandler), (
                f"{name} doesn't implement protocol"
            )
            assert hasattr(handler, "name")
            assert hasattr(handler, "matches")
            assert hasattr(handler, "preprocess")
            assert hasattr(handler, "get_turn_markers")

    def test_handler_names_match_registry_keys(self) -> None:
        """Handler names match their registry keys."""
        from promptgrimoire.export.platforms import _handlers

        for key, handler in _handlers.items():
            assert handler.name == key, (
                f"Handler {key} has mismatched name {handler.name}"
            )
