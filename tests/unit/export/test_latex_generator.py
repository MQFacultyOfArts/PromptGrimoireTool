"""Unit tests for LaTeX generator.

Tests highlight/underline generation from regions.
Uses regions directly - does NOT call lexer or region builder.
"""

from promptgrimoire.export.latex import (
    Region,
    generate_highlight_wrapper,
    generate_highlighted_latex,
    generate_underline_wrapper,
)


class TestGenerateUnderlineWrapper:
    """Tests for generate_underline_wrapper helper."""

    def test_empty_active_returns_identity(self) -> None:
        """No active highlights means no underlines."""
        wrapper = generate_underline_wrapper(frozenset(), {})
        assert wrapper("text") == "text"

    def test_single_highlight_1pt_underline(self) -> None:
        """Single highlight produces 1pt underline with tag's dark colour."""
        highlights = {0: {"tag": "alpha"}}
        wrapper = generate_underline_wrapper(frozenset({0}), highlights)
        result = wrapper("text")

        assert (
            result == r"\underLine[color=tag-alpha-dark, height=1pt, bottom=-3pt]{text}"
        )

    def test_two_highlights_stacked_underlines(self) -> None:
        """Two highlights produce stacked 2pt + 1pt underlines."""
        highlights = {0: {"tag": "alpha"}, 1: {"tag": "beta"}}
        wrapper = generate_underline_wrapper(frozenset({0, 1}), highlights)
        result = wrapper("text")

        # Outer (lower index) is 2pt, inner (higher index) is 1pt
        expected = (
            r"\underLine[color=tag-alpha-dark, height=2pt, bottom=-3pt]{"
            r"\underLine[color=tag-beta-dark, height=1pt, bottom=-3pt]{text}}"
        )
        assert result == expected

    def test_three_highlights_many_underline(self) -> None:
        """Three or more highlights produce single many-dark 4pt underline."""
        highlights = {0: {"tag": "alpha"}, 1: {"tag": "beta"}, 2: {"tag": "gamma"}}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")

        assert result == r"\underLine[color=many-dark, height=4pt, bottom=-5pt]{text}"

    def test_four_highlights_also_many_underline(self) -> None:
        """Four highlights also uses many-dark (not 4 stacked)."""
        highlights = {i: {"tag": f"tag{i}"} for i in range(4)}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2, 3}), highlights)
        result = wrapper("text")

        assert "many-dark" in result
        # Should NOT have multiple nested underlines
        assert result.count(r"\underLine") == 1

    def test_underline_colours_from_tag_names(self) -> None:
        """Underline colours use tag-{name}-dark format."""
        highlights = {5: {"tag": "jurisdiction"}}
        wrapper = generate_underline_wrapper(frozenset({5}), highlights)
        result = wrapper("text")

        assert "tag-jurisdiction-dark" in result

    def test_tag_with_underscore_converted(self) -> None:
        """Underscores in tag names are converted to hyphens."""
        highlights = {0: {"tag": "my_custom_tag"}}
        wrapper = generate_underline_wrapper(frozenset({0}), highlights)
        result = wrapper("text")

        assert "tag-my-custom-tag-dark" in result

    def test_sorted_indices_for_deterministic_nesting(self) -> None:
        """Highlights are sorted by index for deterministic output."""
        highlights = {2: {"tag": "c"}, 0: {"tag": "a"}, 1: {"tag": "b"}}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")

        # With 3 highlights, uses many-dark, so ordering doesn't show
        # But we can test with a mock that captures the order
        # For now, just verify it doesn't crash
        assert "many-dark" in result


class TestGenerateHighlightWrapper:
    """Tests for generate_highlight_wrapper helper."""

    def test_empty_active_returns_identity(self) -> None:
        """No active highlights means no wrapping."""
        wrapper = generate_highlight_wrapper(frozenset(), {})
        assert wrapper("text") == "text"

    def test_single_highlight_wraps_with_light_colour(self) -> None:
        """Single highlight wraps in highLight with light colour."""
        highlights = {0: {"tag": "alpha"}}
        wrapper = generate_highlight_wrapper(frozenset({0}), highlights)
        result = wrapper("text")

        assert result == r"\highLight[tag-alpha-light]{text}"

    def test_two_highlights_nested_wrapping(self) -> None:
        """Two highlights produce nested highLight commands."""
        highlights = {0: {"tag": "alpha"}, 1: {"tag": "beta"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 1}), highlights)
        result = wrapper("text")

        # Lower index is outer
        assert (
            result == r"\highLight[tag-alpha-light]{\highLight[tag-beta-light]{text}}"
        )

    def test_three_highlights_triple_nested(self) -> None:
        """Three highlights produce triple-nested commands."""
        highlights = {0: {"tag": "a"}, 1: {"tag": "b"}, 2: {"tag": "c"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")

        # Should have 3 \highLight commands
        assert result.count(r"\highLight") == 3

    def test_sorted_indices_for_deterministic_nesting(self) -> None:
        """Highlights are sorted by index regardless of set iteration order."""
        highlights = {2: {"tag": "c"}, 0: {"tag": "a"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 2}), highlights)
        result = wrapper("text")

        # tag-a (index 0) should be outer
        assert result.startswith(r"\highLight[tag-a-light]")


class TestGenerateHighlightedLatex:
    """Tests for generate_highlighted_latex main function."""

    def test_empty_regions_returns_empty(self) -> None:
        """Empty region list returns empty string."""
        result = generate_highlighted_latex([], {}, [])
        assert result == ""

    def test_no_active_highlights_passthrough(self) -> None:
        """Regions with no active highlights pass through unchanged."""
        regions = [Region("plain text", frozenset(), [])]
        result = generate_highlighted_latex(regions, {}, [])
        assert result == "plain text"

    def test_single_highlight_full_wrapping(self) -> None:
        """Single active highlight produces highLight + underLine."""
        regions = [Region("text", frozenset({0}), [])]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])

        # Should have both highLight and underLine
        assert r"\highLight[tag-alpha-light]" in result
        assert r"\underLine[color=tag-alpha-dark" in result

    def test_multiple_regions_concatenated(self) -> None:
        """Multiple regions are concatenated in order."""
        regions = [
            Region("before ", frozenset(), []),
            Region("highlighted", frozenset({0}), []),
            Region(" after", frozenset(), []),
        ]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])

        assert result.startswith("before ")
        assert result.endswith(" after")
        assert r"\highLight" in result

    def test_annmarker_emits_annot_command(self) -> None:
        """Regions with annots emit \\annot commands."""
        regions = [Region("text", frozenset({0}), [0])]
        highlights = {
            0: {
                "tag": "alpha",
                "author": "Test User",
                "comments": [],
                "created_at": "2026-01-28T10:00:00Z",
            }
        }
        result = generate_highlighted_latex(regions, highlights, [])

        assert r"\annot{" in result

    def test_env_boundary_splits_highlight(self) -> None:
        """Environment boundaries within region split the highlight."""
        # Text with a \\par in the middle
        regions = [Region(r"before\par after", frozenset({0}), [])]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])

        # Should have two separate \\highLight blocks around \\par
        assert result.count(r"\highLight") == 2
        assert r"\par" in result

    def test_interleaved_example_b(self) -> None:
        """Example B from design: interleaved highlights."""
        # Regions from build_regions for interleaved case
        regions = [
            Region("The ", frozenset(), []),
            Region(" quick ", frozenset({1}), []),
            Region(" fox ", frozenset({1, 2}), []),
            Region(" over ", frozenset({2}), []),
            Region(" dog", frozenset(), []),
        ]
        highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}}
        result = generate_highlighted_latex(regions, highlights, [])

        # Plain text regions
        assert "The " in result
        assert " dog" in result

        # Highlighted regions have commands
        # " quick " has only highlight 1
        # " fox " has both highlights (overlapping)
        # " over " has only highlight 2
        assert r"\highLight[tag-alpha-light]" in result
        assert r"\highLight[tag-beta-light]" in result
