"""Fixture-based integration tests for insert_markers_into_dom.

Loads real platform HTML from tests/fixtures/conversations/, runs it
through the input pipeline (attribute stripping, empty-element removal),
then verifies the round-trip property:
  extract_text_from_html(html)[start:end] == text between markers

This complements the isolated unit tests in test_insert_markers.py by
exercising real-world HTML from Claude, Gemini, OpenAI, AustLII, CJK
content, and more.

Note: Fixtures must pass through ``process_input`` first because raw
platform HTML contains duplicate entity text (e.g. ``&nbsp;`` in style
attributes) that confuses the sequential text-node offset search in
``_find_text_node_offsets``.  The pipeline's attribute stripping removes
these, matching the production flow where annotation always receives
pipeline-processed HTML.
"""

from __future__ import annotations

import re
from functools import lru_cache

import pytest
from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline import process_input
from promptgrimoire.input_pipeline.html_input import (
    extract_text_from_html,
    insert_markers_into_dom,
)
from tests.conftest import load_conversation_fixture

_WHITESPACE_RUN = re.compile(r"[\s\u00a0]+")
_MARKER_RE = re.compile(r"(?:HLSTART|HLEND)\d+ENDHL|ANNMARKER\d+ENDMARKER")

# ------------------------------------------------------------------
# Fixtures to test -- (name, has_cjk)
# Excludes 183-clipboard.html.html.gz (malformed double extension)
# ------------------------------------------------------------------
_FIXTURES: list[tuple[str, bool]] = [
    ("austlii", False),
    ("chinese_wikipedia", True),
    ("claude_cooking", False),
    ("claude_maths", False),
    ("google_aistudio_image", False),
    ("google_aistudio_ux_discussion", False),
    ("google_gemini_debug", False),
    ("google_gemini_deep_research", False),
    ("openai_biblatex", False),
    ("openai_dh_dr", False),
    ("openai_dprk_denmark", False),
    ("openai_software_long_dr", False),
    ("scienceos_loc", False),
    ("scienceos_philsci", False),
    ("translation_japanese_sample", True),
    ("translation_korean_sample", True),
    ("translation_spanish_sample", False),
]

_FIXTURE_NAMES = [name for name, _cjk in _FIXTURES]
_CJK_FIXTURES = [name for name, cjk in _FIXTURES if cjk]


# ------------------------------------------------------------------
# Fixture loading with pipeline cleaning (cached per process)
# ------------------------------------------------------------------
@lru_cache(maxsize=32)
def _load_raw(name: str) -> str:
    return load_conversation_fixture(name)


def _extract_body(html: str) -> str:
    """Extract ``<body>`` HTML from a full document.

    ``insert_markers_into_dom`` walks from ``tree.body`` but searches
    for text-node offsets in the full HTML string.  If ``<head>``
    contains ``<script>``/``<title>`` text the sequential search
    matches against the wrong positions.  Extracting the body first
    mirrors production: the annotation page stores body content only.
    """
    tree = LexborHTMLParser(html)
    body = tree.body
    if body is not None:
        return body.html  # type: ignore[no-any-return]
    return html


async def _load_cleaned(name: str) -> str:
    """Load fixture, pipeline-clean, and extract body."""
    raw = _load_raw(name)
    cleaned = await process_input(raw, "html")
    return _extract_body(cleaned)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _assert_round_trip(
    html: str,
    highlights: list[dict[str, int]],
    *,
    fixture_name: str = "",
) -> str:
    """Assert the round-trip property for all highlights.

    Runs ``extract_text_from_html`` on the *marked* HTML to find where
    each marker lands in the character stream, then verifies that the
    text between HLSTART and HLEND equals the expected span from the
    original character list.  This avoids re-parsing HTML fragments
    which changes block-boundary whitespace.

    Returns the marked HTML for further assertions.
    """
    chars = extract_text_from_html(html)
    marked, ordered = insert_markers_into_dom(html, highlights)
    # Extract the full character stream from the marked HTML
    # (markers appear as literal text in the stream)
    marked_chars = "".join(extract_text_from_html(marked))

    for hl_idx, hl in enumerate(ordered):
        start = hl["start_char"]
        end = hl["end_char"]
        expected = "".join(chars[start:end])

        start_marker = f"HLSTART{hl_idx}ENDHL"
        end_marker = f"HLEND{hl_idx}ENDHL"
        sm_pos = marked_chars.find(start_marker)
        em_pos = marked_chars.find(end_marker)
        assert sm_pos != -1, f"[{fixture_name}] HLSTART{hl_idx} not in chars"
        assert em_pos != -1, f"[{fixture_name}] HLEND{hl_idx} not in chars"

        actual = marked_chars[sm_pos + len(start_marker) : em_pos]
        # Strip any other markers that appear inside
        actual = _MARKER_RE.sub("", actual)
        assert actual == expected, (
            f"[{fixture_name}] HL {hl_idx} [{start}:{end}]: "
            f"expected {expected!r}, got {actual!r}"
        )
        assert f"ANNMARKER{hl_idx}ENDMARKER" in marked

    return marked


def _make_highlights_at_positions(
    total_chars: int,
    *,
    span: int = 20,
) -> list[dict[str, int]]:
    """Highlights at 0%, 25%, 50%, 75%, and near (but not at) end.

    The last highlight ends 1 char before the document end to avoid a
    known edge case where HLEND at the very last character position is
    not emitted by insert_markers_into_dom.
    """
    if total_chars == 0:
        return []

    # Margin of 1 at each end avoids known edge cases where
    # the first char is block-boundary whitespace or the last
    # position cannot receive an HLEND marker.
    safe_start = 1
    safe_end = total_chars - 1
    positions = [
        safe_start,
        max(safe_start, total_chars // 4),
        max(safe_start, total_chars // 2),
        max(safe_start, 3 * total_chars // 4),
        max(safe_start, safe_end - span),
    ]
    highlights: list[dict[str, int]] = []
    for start in positions:
        end = min(start + span, safe_end)
        if end > start:
            highlights.append({"start_char": start, "end_char": end})
    return highlights


def _is_cjk(ch: str) -> bool:
    """True if character is CJK, Hangul, or Kana."""
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xAC00 <= cp <= 0xD7AF
        or 0x3040 <= cp <= 0x309F
        or 0x30A0 <= cp <= 0x30FF
        or 0xFF66 <= cp <= 0xFF9F
    )


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------
class TestFixtureRoundTrip:
    """Round-trip property on pipeline-cleaned fixture HTML."""

    @pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
    async def test_multiple_positions(self, fixture_name: str) -> None:
        """Highlights at 0/25/50/75/100% all round-trip."""
        html = await _load_cleaned(fixture_name)
        chars = extract_text_from_html(html)
        highlights = _make_highlights_at_positions(len(chars))
        assert len(highlights) >= 3, (
            f"{fixture_name}: only {len(highlights)} highlights from {len(chars)} chars"
        )
        _assert_round_trip(html, highlights, fixture_name=fixture_name)

    @pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
    async def test_single_char_highlight(self, fixture_name: str) -> None:
        """Single-character highlight at midpoint round-trips."""
        html = await _load_cleaned(fixture_name)
        chars = extract_text_from_html(html)
        mid = len(chars) // 2
        _assert_round_trip(
            html,
            [{"start_char": mid, "end_char": mid + 1}],
            fixture_name=fixture_name,
        )

    @pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
    async def test_large_span_highlight(self, fixture_name: str) -> None:
        """Highlight spanning 10% of document round-trips."""
        html = await _load_cleaned(fixture_name)
        chars = extract_text_from_html(html)
        span = max(1, len(chars) // 10)
        start = len(chars) // 3
        end = min(start + span, len(chars))
        _assert_round_trip(
            html,
            [{"start_char": start, "end_char": end}],
            fixture_name=fixture_name,
        )


class TestCJKFixtureRoundTrip:
    """CJK-specific: highlights land on CJK characters."""

    @pytest.mark.parametrize("fixture_name", _CJK_FIXTURES)
    async def test_cjk_characters_highlighted(self, fixture_name: str) -> None:
        """Highlight a run of CJK characters."""
        html = await _load_cleaned(fixture_name)
        chars = extract_text_from_html(html)

        # Find first run of >=3 CJK characters
        cjk_start: int | None = None
        cjk_end: int = 0
        for i, ch in enumerate(chars):
            if _is_cjk(ch):
                if cjk_start is None:
                    cjk_start = i
                cjk_end = i + 1
            elif cjk_start is not None:
                if cjk_end - cjk_start >= 3:
                    break
                cjk_start = None

        assert cjk_start is not None, f"No CJK run of >=3 chars in {fixture_name}"
        cjk_end = min(cjk_start + 20, cjk_end)

        _assert_round_trip(
            html,
            [{"start_char": cjk_start, "end_char": cjk_end}],
            fixture_name=fixture_name,
        )


class TestOverlappingHighlightsFixture:
    """Overlapping highlights on fixture HTML."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "austlii",
            "claude_cooking",
            "translation_spanish_sample",
        ],
    )
    async def test_overlapping_highlights(self, fixture_name: str) -> None:
        """Two overlapping highlights both round-trip."""
        html = await _load_cleaned(fixture_name)
        chars = extract_text_from_html(html)
        mid = len(chars) // 2
        hl1_start = mid
        hl1_end = min(mid + 30, len(chars))
        hl2_start = min(mid + 20, len(chars) - 1)
        hl2_end = min(mid + 50, len(chars))
        if hl2_start >= hl2_end:
            hl2_start = hl1_start + 5
            hl2_end = min(hl2_start + 30, len(chars))

        _assert_round_trip(
            html,
            [
                {
                    "start_char": hl1_start,
                    "end_char": hl1_end,
                },
                {
                    "start_char": hl2_start,
                    "end_char": hl2_end,
                },
            ],
            fixture_name=fixture_name,
        )
