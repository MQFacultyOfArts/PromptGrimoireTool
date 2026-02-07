"""Unit tests for LaTeX generator.

Tests highlight/underline generation from regions.
Uses regions directly - does NOT call lexer or region builder.
Assertions use LaTeX AST parsing (pylatexenc) for structural validation.
"""

from promptgrimoire.export.latex import (
    Region,
    generate_highlight_wrapper,
    generate_highlighted_latex,
    generate_underline_wrapper,
)
from tests.helpers.latex_parse import (
    find_macros,
    get_body_text,
    get_opt_arg,
    parse_latex,
    require_opt_arg,
)


class TestGenerateUnderlineWrapper:
    """Tests for generate_underline_wrapper helper."""

    def test_empty_active_returns_identity(self) -> None:
        """No active highlights means no underlines."""
        wrapper = generate_underline_wrapper(frozenset(), {})
        assert wrapper("text") == "text"

    def test_single_highlight_1pt_underline(self) -> None:
        """Single highlight produces 1pt underline with dark colour."""
        highlights = {0: {"tag": "alpha"}}
        wrapper = generate_underline_wrapper(frozenset({0}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        assert len(uls) == 1
        opt = require_opt_arg(uls[0])
        assert "tag-alpha-dark" in opt
        assert "height=1pt" in opt
        assert get_body_text(uls[0]) == "text"

    def test_two_highlights_stacked_underlines(self) -> None:
        """Two highlights produce stacked 2pt + 1pt underlines."""
        highlights = {
            0: {"tag": "alpha"},
            1: {"tag": "beta"},
        }
        wrapper = generate_underline_wrapper(frozenset({0, 1}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        # Two nested underlines
        assert len(uls) == 2
        # Outer (alpha) is 2pt, inner (beta) is 1pt
        opt_outer = require_opt_arg(uls[0])
        assert "tag-alpha-dark" in opt_outer
        assert "height=2pt" in opt_outer
        opt_inner = require_opt_arg(uls[1])
        assert "tag-beta-dark" in opt_inner
        assert "height=1pt" in opt_inner
        assert get_body_text(uls[1]) == "text"

    def test_three_highlights_many_underline(self) -> None:
        """3+ highlights produce single many-dark 4pt underline."""
        highlights = {
            0: {"tag": "alpha"},
            1: {"tag": "beta"},
            2: {"tag": "gamma"},
        }
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        assert len(uls) == 1
        opt = require_opt_arg(uls[0])
        assert "many-dark" in opt
        assert "height=4pt" in opt
        assert get_body_text(uls[0]) == "text"

    def test_four_highlights_also_many_underline(self) -> None:
        """Four highlights also uses many-dark (not 4 stacked)."""
        highlights = {i: {"tag": f"tag{i}"} for i in range(4)}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2, 3}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        assert len(uls) == 1
        assert "many-dark" in require_opt_arg(uls[0])

    def test_underline_colours_from_tag_names(self) -> None:
        """Underline colours use tag-{name}-dark format."""
        highlights = {5: {"tag": "jurisdiction"}}
        wrapper = generate_underline_wrapper(frozenset({5}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        assert len(uls) == 1
        opt = require_opt_arg(uls[0])
        assert "tag-jurisdiction-dark" in opt

    def test_tag_with_underscore_converted(self) -> None:
        """Underscores in tag names are converted to hyphens."""
        highlights = {0: {"tag": "my_custom_tag"}}
        wrapper = generate_underline_wrapper(frozenset({0}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        assert len(uls) == 1
        opt = require_opt_arg(uls[0])
        assert "tag-my-custom-tag-dark" in opt

    def test_sorted_indices_for_deterministic_nesting(self) -> None:
        """Highlights sorted by index for deterministic output."""
        highlights = {
            2: {"tag": "c"},
            0: {"tag": "a"},
            1: {"tag": "b"},
        }
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        uls = find_macros(nodes, "underLine")

        # With 3 highlights, uses many-dark
        assert len(uls) == 1
        assert "many-dark" in require_opt_arg(uls[0])


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
        nodes = parse_latex(result)
        hls = find_macros(nodes, "highLight")

        assert len(hls) == 1
        assert get_opt_arg(hls[0]) == "tag-alpha-light"
        assert get_body_text(hls[0]) == "text"

    def test_two_highlights_nested_wrapping(self) -> None:
        """Two highlights produce nested highLight commands."""
        highlights = {
            0: {"tag": "alpha"},
            1: {"tag": "beta"},
        }
        wrapper = generate_highlight_wrapper(frozenset({0, 1}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        hls = find_macros(nodes, "highLight")

        assert len(hls) == 2
        # Lower index (alpha) is outer
        assert get_opt_arg(hls[0]) == "tag-alpha-light"
        assert get_opt_arg(hls[1]) == "tag-beta-light"
        assert get_body_text(hls[1]) == "text"

    def test_three_highlights_triple_nested(self) -> None:
        """Three highlights produce triple-nested commands."""
        highlights = {
            0: {"tag": "a"},
            1: {"tag": "b"},
            2: {"tag": "c"},
        }
        wrapper = generate_highlight_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        hls = find_macros(nodes, "highLight")

        assert len(hls) == 3

    def test_sorted_indices_for_deterministic_nesting(self) -> None:
        """Highlights sorted by index regardless of iteration."""
        highlights = {2: {"tag": "c"}, 0: {"tag": "a"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 2}), highlights)
        result = wrapper("text")
        nodes = parse_latex(result)
        hls = find_macros(nodes, "highLight")

        # tag-a (index 0) should be outer (first found)
        assert get_opt_arg(hls[0]) == "tag-a-light"


class TestGenerateHighlightedLatex:
    """Tests for generate_highlighted_latex main function."""

    def test_empty_regions_returns_empty(self) -> None:
        """Empty region list returns empty string."""
        result = generate_highlighted_latex([], {}, [])
        assert result == ""

    def test_no_active_highlights_passthrough(self) -> None:
        """Regions with no active highlights pass through."""
        regions = [Region("plain text", frozenset(), [])]
        result = generate_highlighted_latex(regions, {}, [])
        assert result == "plain text"

    def test_single_highlight_full_wrapping(self) -> None:
        """Single active highlight produces highLight + underLine."""
        regions = [Region("text", frozenset({0}), [])]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])
        nodes = parse_latex(result)

        hls = find_macros(nodes, "highLight")
        assert len(hls) >= 1
        assert get_opt_arg(hls[0]) == "tag-alpha-light"

        uls = find_macros(nodes, "underLine")
        assert len(uls) >= 1
        ul_opt = require_opt_arg(uls[0])
        assert "tag-alpha-dark" in ul_opt

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
        nodes = parse_latex(result)
        assert len(find_macros(nodes, "highLight")) >= 1

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
        nodes = parse_latex(result)
        annots = find_macros(nodes, "annot")

        assert len(annots) >= 1

    def test_env_boundary_splits_highlight(self) -> None:
        """Environment boundaries split the highlight."""
        regions = [Region(r"before\par after", frozenset({0}), [])]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])
        nodes = parse_latex(result)
        hls = find_macros(nodes, "highLight")

        # Two separate highLight blocks around \par
        assert len(hls) == 2

    def test_interleaved_example_b(self) -> None:
        """Example B from design: interleaved highlights."""
        regions = [
            Region("The ", frozenset(), []),
            Region(" quick ", frozenset({1}), []),
            Region(" fox ", frozenset({1, 2}), []),
            Region(" over ", frozenset({2}), []),
            Region(" dog", frozenset(), []),
        ]
        highlights = {
            1: {"tag": "alpha"},
            2: {"tag": "beta"},
        }
        result = generate_highlighted_latex(regions, highlights, [])
        nodes = parse_latex(result)

        # Both highlight colours present
        hls = find_macros(nodes, "highLight")
        opt_args = {get_opt_arg(h) for h in hls}
        assert "tag-alpha-light" in opt_args
        assert "tag-beta-light" in opt_args

        # Plain text regions present
        assert "The " in result
        assert " dog" in result
