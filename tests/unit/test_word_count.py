"""Unit tests for word_count module.

Tests normalise_text(), segment_by_script(), and word_count() functions
for multilingual word counting with anti-gaming measures.
"""

from __future__ import annotations

import pytest

from promptgrimoire.word_count import normalise_text, segment_by_script, word_count


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
            pytest.param(
                "hello<br />world",
                "hello\nworld",
                id="html-br-self-closing-space-to-newline",
            ),
            pytest.param(
                "hello<br/>world",
                "hello\nworld",
                id="html-br-self-closing-to-newline",
            ),
            pytest.param(
                "hello<br>world",
                "hello\nworld",
                id="html-br-open-to-newline",
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


class TestWordCount:
    """Tests for word_count() main function.

    CJK word counts use +-1 tolerance because jieba and MeCab tokenisation
    depends on dictionary version. The exact counts in acceptance criteria
    (AC1.2: 7 words, AC1.3: 8 words) are illustrative of expected magnitude,
    not precise requirements.
    """

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            pytest.param(
                "well-known fact",
                3,
                id="AC1.1-hyphens-split-three-words",
            ),
            pytest.param(
                "write-like-this-to-game",
                5,
                id="AC1.7-anti-gaming-hyphens-split-five-words",
            ),
            pytest.param(
                "",
                0,
                id="AC1.10-empty-string-returns-zero",
            ),
            pytest.param(
                "42",
                0,
                id="AC1.11-numbers-only-returns-zero",
            ),
        ],
    )
    def test_word_count_exact(self, input_text: str, expected: int) -> None:
        """Verify word_count returns exact expected counts for non-CJK cases."""
        assert word_count(input_text) == expected

    @pytest.mark.parametrize(
        ("input_text", "low", "high"),
        [
            pytest.param(
                "\u8fd9\u662f\u4e2d\u6587\u7ef4\u57fa\u767e\u79d1\u9996\u9875\u7684\u793a\u4f8b\u5185\u5bb9",
                6,
                8,
                id="AC1.2-chinese-jieba-approx-7",
            ),
            pytest.param(
                "\u65e5\u672c\u56fd\u61b2\u6cd5\u306f\u6700\u9ad8\u6cd5\u898f\u3067\u3042\u308b",
                7,
                9,
                id="AC1.3-japanese-mecab-approx-8",
            ),
        ],
    )
    def test_word_count_cjk_tolerance(
        self, input_text: str, low: int, high: int
    ) -> None:
        """CJK word counts use +-1 tolerance for dictionary variation."""
        result = word_count(input_text)
        assert low <= result <= high, f"expected {low}-{high}, got {result}"

    def test_word_count_korean(self) -> None:
        """AC1.4: Korean space-delimited text returns 4 words."""
        korean = (
            "\ub300\ud55c\ubbfc\uad6d \ud5cc\ubc95\uc740"
            " \ucd5c\uace0\uc758 \ubc95\ub960\uc785\ub2c8\ub2e4"
        )
        assert word_count(korean) == 4

    def test_milkdown_br_not_counted(self) -> None:
        """#262: Milkdown <br /> not counted as word."""
        assert word_count("hello\n\n<br />\n\nworld") == 2

    def test_many_br_tags_not_inflating(self) -> None:
        """#262: Many <br /> must not inflate count."""
        md = "word\n\n" + "<br />\n\n" * 100 + "another"
        assert word_count(md) == 2


class TestWordCountAntiGaming:
    """Integration tests for the full word_count pipeline.

    Verifies normalise -> segment -> tokenise -> filter works end-to-end
    for anti-gaming measures and mixed-script inputs.
    """

    def test_mixed_script_english_japanese(self) -> None:
        """AC1.5: Mixed English+Japanese counts both segments."""
        text = "The contract states \u5951\u7d04\u306f\u6709\u52b9\u3067\u3042\u308b"
        result = word_count(text)
        # 3 English words + Japanese tokens (count varies by MeCab dict)
        assert result >= 5

    def test_markdown_link_counts_text_only(self) -> None:
        """AC1.6: Markdown link URL excluded, only link text counted."""
        result = word_count("[click here](https://example.com/long/path)")
        assert result == 2

    def test_zero_width_space_merges_words(self) -> None:
        """AC1.8: Zero-width space stripped, adjacent words merge."""
        assert word_count("hello\u200bworld") == 1

    def test_fullwidth_normalised(self) -> None:
        """AC1.9: Full-width text NFKC-normalised before counting."""
        assert (
            word_count("\uff28\uff45\uff4c\uff4c\uff4f \uff37\uff4f\uff52\uff4c\uff44")
            == 2
        )

    def test_combined_anti_gaming(self) -> None:
        """Multiple anti-gaming measures combined in one string."""
        text = "write-like-this \u200b and [link](http://x.com)"
        result = word_count(text)
        # "write", "like", "this", "and", "link" = 5 words
        # zero-width stripped, link URL stripped but link text kept
        assert result == 5

    def test_markdown_image(self) -> None:
        """Markdown image: only alt text counted, not URL."""
        assert word_count("![alt text](image.png)") == 2

    def test_pure_punctuation(self) -> None:
        """Pure punctuation returns 0 words."""
        assert word_count("... --- !!!") == 0

    def test_mixed_cjk_english(self) -> None:
        """Mixed CJK and English in one sentence."""
        text = "Hello \u4e16\u754c world"
        result = word_count(text)
        # "Hello" + Chinese segment + "world" = at least 3
        assert result >= 3
