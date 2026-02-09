"""Tests for empty-content ValueError guard and fixture regression.

Verifies:
- pdf-export-char-alignment.AC1.5: export_annotation_pdf raises ValueError
  when highlights are provided with empty content
- pdf-export-char-alignment.AC1.6: ValueError message contains "empty content"
- pdf-export-char-alignment.AC5.1: All HTML conversation fixtures pass through
  insert_markers_into_dom without error when given highlights at valid char
  positions from extract_text_from_html

Note: Fixture tests process raw HTML through the input pipeline first
(``process_input`` + body extraction), matching the production flow where
annotation always receives pipeline-processed HTML. Round-trip character
verification is covered thoroughly in
``tests/unit/input_pipeline/test_insert_markers_fixtures.py``.
"""

from __future__ import annotations

import pytest
from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.input_pipeline import process_input
from promptgrimoire.input_pipeline.html_input import (
    extract_text_from_html,
    insert_markers_into_dom,
)
from tests.conftest import load_conversation_fixture

# ------------------------------------------------------------------
# Fixture list for parametrised AC5.1 regression test
# Excludes 183-clipboard.html.html.gz (malformed double extension)
# ------------------------------------------------------------------
_FIXTURE_NAMES: list[str] = [
    "austlii",
    "chinese_wikipedia",
    "claude_cooking",
    "claude_maths",
    "google_aistudio_image",
    "google_aistudio_ux_discussion",
    "google_gemini_debug",
    "google_gemini_deep_research",
    "openai_biblatex",
    "openai_dh_dr",
    "openai_dprk_denmark",
    "openai_software_long_dr",
    "scienceos_loc",
    "scienceos_philsci",
    "translation_japanese_sample",
    "translation_korean_sample",
    "translation_spanish_sample",
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _extract_body(html: str) -> str:
    """Extract ``<body>`` inner HTML from a full document.

    Mirrors production: the annotation page stores body content only.
    Without this, ``<head>`` text nodes (titles, scripts) confuse
    the sequential text-node offset search.
    """
    tree = LexborHTMLParser(html)
    body = tree.body
    if body is not None:
        # selectolax .html stub returns str|None but body check above
        return body.html  # type: ignore[no-any-return]  # selectolax stub
    return html


async def _load_cleaned(name: str) -> str:
    """Load fixture, pipeline-clean, and extract body."""
    raw = load_conversation_fixture(name)
    cleaned = await process_input(raw, "html")
    return _extract_body(cleaned)


def _make_synthetic_highlights(
    total_chars: int,
    *,
    span: int = 10,
) -> list[dict[str, object]]:
    """Create synthetic highlights at ~25%, 50%, 75%.

    Uses safe margins (matching test_insert_markers_fixtures.py)
    to avoid boundary edge cases tested separately in
    test_insert_markers.py. Starts after first 10% and ends
    before the last character.
    """
    if total_chars < 4:
        return []

    safe_start = max(1, total_chars // 10)
    safe_end = max(safe_start + 1, total_chars - 1)

    positions = [
        safe_start + (safe_end - safe_start) // 4,
        safe_start + (safe_end - safe_start) // 2,
        safe_start + 3 * (safe_end - safe_start) // 4,
    ]
    highlights: list[dict[str, object]] = []
    for i, start in enumerate(positions):
        end = min(start + span, safe_end)
        if end > start:
            highlights.append(
                {
                    "start_char": start,
                    "end_char": end,
                    "tag": f"test_tag_{i}",
                    "text": f"synthetic_{i}",
                    "author": "test",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "comments": [],
                }
            )
    return highlights


# ------------------------------------------------------------------
# AC1.5, AC1.6: ValueError guard tests
# ------------------------------------------------------------------
class TestEmptyContentValueError:
    """ValueError when highlights provided with empty content."""

    async def test_empty_string_with_highlights_raises(self) -> None:
        """AC1.5: Empty string + highlights raises ValueError."""
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 5,
                "tag": "test",
                "text": "hello",
                "author": "tester",
                "created_at": "2026-01-01T00:00:00+00:00",
                "comments": [],
            }
        ]
        with pytest.raises(ValueError, match="empty content"):
            await export_annotation_pdf(
                html_content="",
                highlights=highlights,
                tag_colours={"test": "#ff0000"},
            )

    async def test_whitespace_only_with_highlights_raises(
        self,
    ) -> None:
        """AC1.5: Whitespace-only + highlights raises ValueError."""
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 3,
                "tag": "test",
                "text": "abc",
                "author": "tester",
                "created_at": "2026-01-01T00:00:00+00:00",
                "comments": [],
            }
        ]
        with pytest.raises(ValueError, match="empty content"):
            await export_annotation_pdf(
                html_content="   \n\t  ",
                highlights=highlights,
                tag_colours={"test": "#ff0000"},
            )

    async def test_error_message_is_descriptive(self) -> None:
        """AC1.6: ValueError message describes the problem."""
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 1,
                "tag": "test",
                "text": "x",
                "author": "tester",
                "created_at": "2026-01-01T00:00:00+00:00",
                "comments": [],
            }
        ]
        with pytest.raises(ValueError) as exc_info:
            await export_annotation_pdf(
                html_content="",
                highlights=highlights,
                tag_colours={"test": "#ff0000"},
            )

        message = str(exc_info.value)
        assert "empty content" in message.lower()
        assert "marker" in message.lower() or "annotation" in message.lower()

    async def test_empty_highlights_no_error(self) -> None:
        """No ValueError when highlights list is empty."""
        # Guard should NOT trigger; later stages may fail
        try:
            await export_annotation_pdf(
                html_content="",
                highlights=[],
                tag_colours={},
            )
        except ValueError:
            pytest.fail("ValueError raised when highlights is empty")
        except Exception:
            # Pandoc/LaTeX errors are acceptable here
            pass

    async def test_falsy_content_with_highlights_raises(
        self,
    ) -> None:
        """AC1.5: Falsy content with highlights raises ValueError."""
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 2,
                "tag": "test",
                "text": "ab",
                "author": "tester",
                "created_at": "2026-01-01T00:00:00+00:00",
                "comments": [],
            }
        ]
        with pytest.raises(ValueError, match="empty content"):
            await export_annotation_pdf(
                html_content="",
                highlights=highlights,
                tag_colours={"test": "#ff0000"},
            )


# ------------------------------------------------------------------
# AC5.1: Fixture regression tests
# ------------------------------------------------------------------
class TestFixtureMarkerInsertion:
    """All HTML fixtures pass through insert_markers_into_dom.

    Loads each fixture through the input pipeline (matching
    production flow), then verifies marker insertion succeeds
    with synthetic highlights at valid character positions.

    Round-trip character verification (that text between markers
    matches expected chars) is covered thoroughly in
    ``tests/unit/input_pipeline/test_insert_markers_fixtures.py``.
    """

    @pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
    async def test_fixture_markers_no_error(self, fixture_name: str) -> None:
        """Fixture HTML with synthetic highlights inserts markers."""
        html = await _load_cleaned(fixture_name)
        chars = extract_text_from_html(html)

        highlights = _make_synthetic_highlights(len(chars))
        if not highlights:
            pytest.skip(f"{fixture_name}: fewer than 4 characters")

        # This should not raise
        marked_html, ordered = insert_markers_into_dom(html, highlights)

        # Basic sanity: markers were inserted
        assert len(ordered) == len(highlights)
        for i in range(len(ordered)):
            assert f"HLSTART{i}ENDHL" in marked_html
            assert f"HLEND{i}ENDHL" in marked_html
            assert f"ANNMARKER{i}ENDMARKER" in marked_html
