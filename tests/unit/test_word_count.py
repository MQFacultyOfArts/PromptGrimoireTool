"""Unit tests for word_count module.

Tests normalise_text(), segment_by_script(), and word_count() functions
for multilingual word counting with anti-gaming measures.
"""

from __future__ import annotations

import pytest

from promptgrimoire.word_count import normalise_text, segment_by_script


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


class TestSegmentByScript:
    """Tests for segment_by_script() script-based text segmentation."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            pytest.param(
                "hello world",
                [("latin", "hello world")],
                id="AC1.5-pure-english-single-latin-segment",
            ),
            pytest.param(
                "这是中文",
                [("zh", "这是中文")],
                id="AC1.5-pure-chinese-single-zh-segment",
            ),
            pytest.param(
                "日本語のテスト",
                [("ja", "日本語のテスト")],
                id="AC1.5-pure-japanese-hiragana-kanji-merged-ja",
            ),
            pytest.param(
                "한국어",
                [("ko", "한국어")],
                id="AC1.5-pure-korean-single-ko-segment",
            ),
            pytest.param(
                "Hello 你好",
                [("latin", "Hello "), ("zh", "你好")],
                id="AC1.5-mixed-english-chinese-two-segments",
            ),
            pytest.param(
                "English 中文 日本語の テスト 한국어",
                [
                    ("latin", "English "),
                    ("zh", "中文"),
                    ("latin", " "),
                    ("ja", "日本語の"),
                    ("latin", " "),
                    ("ja", "テスト"),
                    ("latin", " "),
                    ("ko", "한국어"),
                ],
                id="AC1.5-mixed-all-four-scripts",
            ),
            pytest.param(
                "漢字のある文",
                [("ja", "漢字のある文")],
                id="kanji-adjacent-to-hiragana-classified-ja",
            ),
            pytest.param(
                "漢字",
                [("zh", "漢字")],
                id="standalone-kanji-no-hiragana-classified-zh",
            ),
        ],
    )
    def test_segment_by_script(
        self, input_text: str, expected: list[tuple[str, str]]
    ) -> None:
        """Verify segment_by_script groups characters by script correctly."""
        assert segment_by_script(input_text) == expected

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            pytest.param(
                "",
                [],
                id="empty-string-returns-empty-list",
            ),
            pytest.param(
                "   ",
                [("latin", "   ")],
                id="whitespace-only-returns-single-latin",
            ),
            pytest.param(
                "42 + 3.14",
                [("latin", "42 + 3.14")],
                id="numbers-and-punctuation-are-latin",
            ),
            pytest.param(
                "\u3001\u3002\u300c\u300d",
                [("latin", "\u3001\u3002\u300c\u300d")],
                id="cjk-punctuation-classified-as-latin",
            ),
            pytest.param(
                "\U0001f600\U0001f680",
                [("latin", "\U0001f600\U0001f680")],
                id="emoji-fallback-to-latin",
            ),
            pytest.param(
                "\u5b57",
                [("zh", "\u5b57")],
                id="single-kanji-no-neighbours-classified-zh",
            ),
        ],
    )
    def test_segment_by_script_edge_cases(
        self, input_text: str, expected: list[tuple[str, str]]
    ) -> None:
        """Edge cases: empty input, whitespace, punctuation, emoji, lone kanji."""
        assert segment_by_script(input_text) == expected
