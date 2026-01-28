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


def test_replace_markers_worked_example_from_design():
    """Test the exact worked example from the design document.

    Input: "The HLSTART0ENDHLquick HLSTART1ENDHLbrown HLEND0ENDHLfox HLEND1ENDHLjumps"

    Expected regions:
    - "The " (no highlights)
    - "quick " (hl0 only)
    - "brown " (hl0, hl1)
    - "fox " (hl1 only)
    - "jumps" (no highlights)
    """
    text = "The HLSTART0ENDHLquick HLSTART1ENDHLbrown HLEND0ENDHLfox HLEND1ENDHLjumps"
    marker_highlights = [
        {"tag": "alpha", "author": "Test", "text": "quick brown", "comments": []},
        {"tag": "beta", "author": "Test", "text": "brown fox", "comments": []},
    ]

    result = _replace_markers_with_annots(text, marker_highlights)

    # "The " and "jumps" should be plain text
    assert result.startswith("The ")
    assert result.endswith("jumps")

    # "quick " should have only tag-alpha highlight
    assert "\\highLight[tag-alpha-light]{" in result
    # "brown " should have both highlights (nested)
    # "fox " should have only tag-beta highlight
    assert "\\highLight[tag-beta-light]{" in result

    # No markers should remain
    assert "HLSTART" not in result
    assert "HLEND" not in result


def test_replace_markers_with_annotations():
    """Annotations should appear in the output."""
    text = "HLSTART0ENDHLtextANNMARKER0ENDMARKERHLEND0ENDHL"
    marker_highlights = [
        {"tag": "alpha", "author": "Alice", "text": "test", "comments": []}
    ]

    result = _replace_markers_with_annots(text, marker_highlights)

    # Annotation should be formatted (existing _format_annot behaviour)
    # Check for the \annot command which includes the tag
    assert "\\annot{tag-alpha}" in result
    # No markers should remain
    assert "ANNMARKER" not in result
    assert "HLSTART" not in result
    assert "HLEND" not in result


def test_replace_markers_three_overlapping():
    """Three overlapping highlights should use many-dark underline."""
    text = (
        "HLSTART0ENDHLHLSTART1ENDHLHLSTART2ENDHLtextHLEND2ENDHLHLEND1ENDHLHLEND0ENDHL"
    )
    marker_highlights = [
        {"tag": "alpha", "author": "Test", "text": "t1", "comments": []},
        {"tag": "beta", "author": "Test", "text": "t2", "comments": []},
        {"tag": "gamma", "author": "Test", "text": "t3", "comments": []},
    ]

    result = _replace_markers_with_annots(text, marker_highlights)

    # Should have three nested highLight commands
    assert result.count("\\highLight[") == 3
    # Should have many-dark underline (4pt)
    assert "many-dark" in result
    assert "height=4pt" in result


def test_replace_markers_preserves_latex_commands():
    """LaTeX commands within highlighted text should be preserved."""
    text = "HLSTART0ENDHLsome \\textbf{bold} textHLEND0ENDHL"
    marker_highlights = [
        {"tag": "alpha", "author": "Test", "text": "t", "comments": []}
    ]

    result = _replace_markers_with_annots(text, marker_highlights)

    assert "\\textbf{bold}" in result
