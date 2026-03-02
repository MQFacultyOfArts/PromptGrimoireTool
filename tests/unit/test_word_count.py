"""Unit tests for word_count module.

Tests normalise_text(), segment_by_script(), and word_count() functions
for multilingual word counting with anti-gaming measures.
"""

from __future__ import annotations

import pytest

from promptgrimoire.word_count import normalise_text


class TestNormaliseText:
    """Tests for normalise_text() preprocessing function."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            pytest.param(
                "\uff21\uff22\uff23",
                "ABC",
                id="AC1.9-nfkc-fullwidth-to-ascii",
            ),
            pytest.param(
                "hello\u200bworld",
                "helloworld",
                id="AC1.8-zero-width-space-stripped",
            ),
            pytest.param(
                "[text](https://example.com)",
                "[text]",
                id="AC1.6-markdown-link-url-stripped",
            ),
            pytest.param(
                "![alt](http://img.png)",
                "[alt]",
                id="image-marker-stripped",
            ),
            pytest.param(
                "[a](http://x.com) and [b](http://y.com)",
                "[a] and [b]",
                id="nested-complex-multiple-links",
            ),
        ],
    )
    def test_normalise_text(self, input_text: str, expected: str) -> None:
        """Verify normalise_text handles NFKC, zero-width, and markdown URLs."""
        assert normalise_text(input_text) == expected

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            pytest.param(
                "[text][ref]",
                "[text][ref]",
                id="reference-style-link-preserved",
            ),
            pytest.param(
                "[a](http://x.com) then [b](http://y.com) then [c](http://z.com)",
                "[a] then [b] then [c]",
                id="multiple-links-all-stripped",
            ),
            pytest.param(
                "[**bold text**](http://example.com)",
                "[**bold text**]",
                id="nested-markdown-bold-inside-link",
            ),
            pytest.param(
                "\u200b\u200c\u200d\u2060\ufeff",
                "",
                id="only-zero-width-chars-becomes-empty",
            ),
            pytest.param(
                "already normalised text",
                "already normalised text",
                id="already-normalised-unchanged",
            ),
        ],
    )
    def test_normalise_text_edge_cases(self, input_text: str, expected: str) -> None:
        """Edge cases: reference links, multiple links, nested markdown."""
        assert normalise_text(input_text) == expected
