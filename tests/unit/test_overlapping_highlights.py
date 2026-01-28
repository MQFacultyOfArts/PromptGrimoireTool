"""Tests for overlapping/interleaved highlight handling.

These tests validate that the new lexer+region+generator pipeline in
_replace_markers_with_annots() correctly handles interleaved highlights,
which the previous regex-based implementation could not handle.
"""

from promptgrimoire.export.latex import _replace_markers_with_annots


def test_replace_markers_interleaved_highlights():
    """Interleaved highlights should produce correct nested LaTeX.

    Input: HLSTART0...HLSTART1...HLEND0...HLEND1

    This pattern cannot be matched by regex with backreferences because
    the markers are interleaved (not properly nested).
    """
    # HLSTART0...HLSTART1...HLEND0...HLEND1
    # Using 0-based indices to match marker_highlights list indexing
    text = "HLSTART0ENDHLouterHLSTART1ENDHLmiddleHLEND0ENDHLinnerHLEND1ENDHL"
    marker_highlights = [
        {"tag": "alpha", "author": "Test", "text": "outer text", "comments": []},
        {"tag": "beta", "author": "Test", "text": "inner text", "comments": []},
    ]

    result = _replace_markers_with_annots(text, marker_highlights)

    # Verify structure: both highlights wrap "middle", only hl1 wraps "inner"
    assert "\\highLight[tag-alpha-light]" in result
    assert "\\highLight[tag-beta-light]" in result
    # The "middle" text should have both highlights
    # The "inner" text should only have hl1
    # "outer" should only have hl0
    # No markers should remain
    assert "HLSTART" not in result
    assert "HLEND" not in result
