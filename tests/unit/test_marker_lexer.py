"""Unit tests for marker lexer.

Tests tokenization stage ONLY - no region building or LaTeX generation.
"""

import pytest

from promptgrimoire.export.latex import MarkerToken, MarkerTokenType


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
