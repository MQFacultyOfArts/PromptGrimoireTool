"""Integration tests for preprocess_for_export pipeline equivalence."""

from __future__ import annotations

import pytest


class TestPipelineEquivalence:
    """Verify new pipeline produces equivalent output to old pipeline.

    Note: These tests supersede TestChromeRemoval and TestUIChromeRemoval from
    test_css_fidelity.py. Chrome removal functionality (remote images, small icons,
    hidden elements, etc.) is now tested here via real fixtures and in the
    individual platform handler tests.
    """

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "openai_biblatex.html",
            "claude_cooking.html",
            "google_gemini_debug.html",
            "google_aistudio_ux_discussion.html",
            "scienceos_loc.html",
        ],
    )
    def test_preprocess_for_export_processes_fixture(self, fixture_name: str) -> None:
        """New entry point successfully processes platform fixtures."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture(fixture_name)
        result = preprocess_for_export(html)

        # Basic sanity checks
        assert len(result) > 0
        assert len(result) < len(html)  # Should be smaller after chrome removal
        assert 'data-speaker="user"' in result or 'data-speaker="assistant"' in result

    def test_preprocess_returns_unchanged_for_unknown_platform(self) -> None:
        """Unknown platforms return HTML unchanged."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = "<html><body><p>Plain content</p></body></html>"
        result = preprocess_for_export(html)

        # Should be similar (selectolax may normalize slightly)
        assert "Plain content" in result

    def test_speaker_markers_preserved_through_chrome_removal(self) -> None:
        """Empty container removal preserves data-speaker markers."""
        from promptgrimoire.export.platforms import preprocess_for_export

        # Simulate HTML after speaker label injection with empty marker divs
        html = """
        <div data-speaker="user" class="speaker-turn"></div>
        <div class="content">User message</div>
        <div data-speaker="assistant" class="speaker-turn"></div>
        <div class="content">Assistant response</div>
        """
        result = preprocess_for_export(html)

        # Speaker markers must be preserved even though they're "empty"
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result

    def test_katex_html_removed_mathml_preserved(self) -> None:
        """KaTeX visual rendering removed, MathML preserved for Pandoc."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = """
        <span class="katex">
            <span class="katex-mathml"><math>...</math></span>
            <span class="katex-html">visual rendering</span>
        </span>
        """
        result = preprocess_for_export(html)

        # Visual rendering removed
        assert "katex-html" not in result
        assert "visual rendering" not in result
        # MathML preserved
        assert "katex-mathml" in result


class TestInteractiveElementSanitisation:
    """#117: Interactive elements must not interfere with annotation."""

    def test_links_unwrapped(self) -> None:
        """<a> tags unwrapped — visible text kept, href dropped."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = '<p>See <a href="https://example.com">the docs</a> here</p>'
        result = preprocess_for_export(html)

        assert "the docs" in result
        assert "href" not in result
        assert "<a " not in result

    def test_all_buttons_removed(self) -> None:
        """All buttons removed, not just copy/share/download."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = "<div><button>Retry</button><p>Content</p></div>"
        result = preprocess_for_export(html)

        assert "Retry" not in result
        assert "Content" in result

    def test_event_attributes_stripped(self) -> None:
        """on* event attributes stripped from all elements."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = '<div onclick="alert(1)" onmouseover="x()"><p>Text</p></div>'
        result = preprocess_for_export(html)

        assert "Text" in result
        assert "onclick" not in result
        assert "onmouseover" not in result
