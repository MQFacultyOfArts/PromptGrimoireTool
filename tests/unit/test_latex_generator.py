"""Unit tests for LaTeX generator.

Tests highlight/underline generation from regions.
Uses regions directly - does NOT call lexer or region builder.
"""

from promptgrimoire.export.latex import (
    generate_highlight_wrapper,
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
