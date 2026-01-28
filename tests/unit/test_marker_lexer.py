"""Unit tests for marker lexer.

Tests tokenization stage ONLY - no region building or LaTeX generation.
"""

import pytest

from promptgrimoire.export.latex import (
    MarkerToken,
    MarkerTokenType,
    tokenize_markers,
)


class TestMarkerTokenDataclass:
    """Tests for the MarkerToken dataclass itself."""

    def test_text_token_has_none_index(self) -> None:
        """TEXT tokens have index=None."""
        token = MarkerToken(
            type=MarkerTokenType.TEXT,
            value="hello world",
            index=None,
            start_pos=0,
            end_pos=11,
        )
        assert token.type == MarkerTokenType.TEXT
        assert token.index is None

    def test_hlstart_token_has_int_index(self) -> None:
        """HLSTART tokens have integer index."""
        token = MarkerToken(
            type=MarkerTokenType.HLSTART,
            value="HLSTART{42}ENDHL",
            index=42,
            start_pos=0,
            end_pos=16,
        )
        assert token.type == MarkerTokenType.HLSTART
        assert token.index == 42

    def test_token_is_frozen(self) -> None:
        """MarkerToken is immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        token = MarkerToken(
            type=MarkerTokenType.TEXT,
            value="x",
            index=None,
            start_pos=0,
            end_pos=1,
        )
        # Should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            token.value = "changed"  # type: ignore[invalid-assignment]


class TestTokenizeMarkers:
    """Tests for tokenize_markers function."""

    def test_empty_input(self) -> None:
        """Empty string returns empty list."""
        assert tokenize_markers("") == []

    def test_text_only_no_markers(self) -> None:
        """Plain text without markers returns single TEXT token."""
        tokens = tokenize_markers("Hello world")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.TEXT
        assert tokens[0].value == "Hello world"
        assert tokens[0].index is None

    def test_single_hlstart(self) -> None:
        """Single HLSTART marker is tokenized correctly."""
        tokens = tokenize_markers("HLSTART{1}ENDHL")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].value == "HLSTART{1}ENDHL"
        assert tokens[0].index == 1

    def test_single_hlend(self) -> None:
        """Single HLEND marker is tokenized correctly."""
        tokens = tokenize_markers("HLEND{42}ENDHL")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.HLEND
        assert tokens[0].value == "HLEND{42}ENDHL"
        assert tokens[0].index == 42

    def test_single_annmarker(self) -> None:
        """Single ANNMARKER is tokenized correctly."""
        tokens = tokenize_markers("ANNMARKER{7}ENDMARKER")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.ANNMARKER
        assert tokens[0].value == "ANNMARKER{7}ENDMARKER"
        assert tokens[0].index == 7

    def test_complete_highlight_pair(self) -> None:
        """HLSTART...text...HLEND produces correct token sequence."""
        tokens = tokenize_markers("HLSTART{1}ENDHL hello HLEND{1}ENDHL")
        assert len(tokens) == 3
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].index == 1
        assert tokens[1].type == MarkerTokenType.TEXT
        assert tokens[1].value == " hello "
        assert tokens[2].type == MarkerTokenType.HLEND
        assert tokens[2].index == 1

    def test_preserves_spaces_in_text(self) -> None:
        """Whitespace in TEXT tokens is preserved exactly."""
        tokens = tokenize_markers("  spaces  HLSTART{1}ENDHL  more  ")
        text_tokens = [t for t in tokens if t.type == MarkerTokenType.TEXT]
        assert text_tokens[0].value == "  spaces  "
        assert text_tokens[1].value == "  more  "

    def test_preserves_newlines_in_text(self) -> None:
        """Newlines in TEXT tokens are preserved."""
        tokens = tokenize_markers("line1\nline2\nHLSTART{1}ENDHL")
        assert tokens[0].type == MarkerTokenType.TEXT
        assert tokens[0].value == "line1\nline2\n"

    def test_adjacent_markers_no_text_between(self) -> None:
        """Adjacent markers with no text between produce no TEXT token."""
        tokens = tokenize_markers("HLSTART{1}ENDHLHLSTART{2}ENDHL")
        assert len(tokens) == 2
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].index == 1
        assert tokens[1].type == MarkerTokenType.HLSTART
        assert tokens[1].index == 2

    def test_multiple_highlights_sequential(self) -> None:
        """Multiple non-overlapping highlights tokenize correctly."""
        tokens = tokenize_markers(
            "a HLSTART{1}ENDHL b HLEND{1}ENDHL c HLSTART{2}ENDHL d HLEND{2}ENDHL e"
        )
        types = [t.type for t in tokens]
        assert types == [
            MarkerTokenType.TEXT,  # "a "
            MarkerTokenType.HLSTART,  # {1}
            MarkerTokenType.TEXT,  # " b "
            MarkerTokenType.HLEND,  # {1}
            MarkerTokenType.TEXT,  # " c "
            MarkerTokenType.HLSTART,  # {2}
            MarkerTokenType.TEXT,  # " d "
            MarkerTokenType.HLEND,  # {2}
            MarkerTokenType.TEXT,  # " e"
        ]

    def test_nested_markers(self) -> None:
        """Properly nested markers tokenize correctly."""
        # Example A from design: nested
        input_text = (
            "The HLSTART{1}ENDHL quick HLSTART{2}ENDHL fox "
            "HLEND{2}ENDHL brown HLEND{1}ENDHL dog"
        )
        tokens = tokenize_markers(input_text)
        types = [(t.type, t.index) for t in tokens]
        assert types == [
            (MarkerTokenType.TEXT, None),  # "The "
            (MarkerTokenType.HLSTART, 1),
            (MarkerTokenType.TEXT, None),  # " quick "
            (MarkerTokenType.HLSTART, 2),
            (MarkerTokenType.TEXT, None),  # " fox "
            (MarkerTokenType.HLEND, 2),
            (MarkerTokenType.TEXT, None),  # " brown "
            (MarkerTokenType.HLEND, 1),
            (MarkerTokenType.TEXT, None),  # " dog"
        ]

    def test_interleaved_markers(self) -> None:
        """Interleaved (not properly nested) markers tokenize correctly."""
        # Example B from design: interleaved
        input_text = (
            "The HLSTART{1}ENDHL quick HLSTART{2}ENDHL fox "
            "HLEND{1}ENDHL over HLEND{2}ENDHL dog"
        )
        tokens = tokenize_markers(input_text)
        types = [(t.type, t.index) for t in tokens]
        assert types == [
            (MarkerTokenType.TEXT, None),  # "The "
            (MarkerTokenType.HLSTART, 1),
            (MarkerTokenType.TEXT, None),  # " quick "
            (MarkerTokenType.HLSTART, 2),
            (MarkerTokenType.TEXT, None),  # " fox "
            (MarkerTokenType.HLEND, 1),
            (MarkerTokenType.TEXT, None),  # " over "
            (MarkerTokenType.HLEND, 2),
            (MarkerTokenType.TEXT, None),  # " dog"
        ]

    def test_extracts_correct_indices(self) -> None:
        """Indices are correctly extracted as integers."""
        tokens = tokenize_markers("HLSTART{0}ENDHL HLSTART{999}ENDHL HLEND{123}ENDHL")
        indices = [t.index for t in tokens if t.type != MarkerTokenType.TEXT]
        assert indices == [0, 999, 123]

    def test_latex_commands_in_text_preserved(self) -> None:
        """LaTeX commands in TEXT are preserved verbatim."""
        tokens = tokenize_markers(r"\textbf{bold} HLSTART{1}ENDHL \emph{italic}")
        text_values = [t.value for t in tokens if t.type == MarkerTokenType.TEXT]
        assert text_values[0] == r"\textbf{bold} "
        assert text_values[1] == r" \emph{italic}"

    def test_start_positions_are_correct(self) -> None:
        """Token start_pos values are accurate byte offsets."""
        # "abc " = 4 chars, "HLSTART{1}ENDHL" = 15 chars, " xyz" = 4 chars
        tokens = tokenize_markers("abc HLSTART{1}ENDHL xyz")
        assert tokens[0].start_pos == 0  # "abc " starts at 0
        assert tokens[1].start_pos == 4  # HLSTART{1}ENDHL starts at 4
        assert tokens[2].start_pos == 19  # " xyz" starts at 19 (4 + 15)

    def test_end_positions_are_correct(self) -> None:
        """Token end_pos values are accurate byte offsets."""
        # "abc " = 4 chars, "HLSTART{1}ENDHL" = 15 chars, " xyz" = 4 chars
        tokens = tokenize_markers("abc HLSTART{1}ENDHL xyz")
        assert tokens[0].end_pos == 4  # "abc " ends at 4
        assert tokens[1].end_pos == 19  # HLSTART{1}ENDHL ends at 19 (4 + 15)
        assert tokens[2].end_pos == 23  # " xyz" ends at 23 (total length)
