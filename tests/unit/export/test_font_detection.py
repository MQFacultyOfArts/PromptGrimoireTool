"""Tests for font registry and script detection.

Verifies:
- AC3.1: detect_scripts() returns correct tags for representative text
- AC3.2 (Guard 2): every script in _REQUIRED_SCRIPTS is detectable
- AC3.7 (Guard 4): font registry and detection ranges are consistent
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.unicode_latex import (
    _REQUIRED_SCRIPTS,
    FONT_REGISTRY,
    SCRIPT_TAG_RANGES,
    detect_scripts,
)


class TestDetectScriptsAC31:
    """AC3.1: detect_scripts returns correct tags for representative text."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            pytest.param("Hello world", frozenset(), id="ascii"),
            pytest.param("\u05e9\u05dc\u05d5\u05dd", frozenset({"hebr"}), id="hebrew"),
            pytest.param(
                "\u0645\u0631\u062d\u0628\u0627", frozenset({"arab"}), id="arabic"
            ),
            pytest.param("\u4f60\u597d", frozenset({"cjk"}), id="cjk"),
            pytest.param(
                "\u0928\u092e\u0938\u094d\u0924\u0947",
                frozenset({"deva"}),
                id="devanagari",
            ),
            pytest.param("\u03b1\u03b2\u03b3", frozenset({"grek"}), id="greek"),
            pytest.param(
                "Hello \u4f60\u597d \u05e9\u05dc\u05d5\u05dd",
                frozenset({"cjk", "hebr"}),
                id="mixed",
            ),
            pytest.param("", frozenset(), id="empty"),
        ],
    )
    def test_detect_scripts(self, text: str, expected: frozenset[str]) -> None:
        assert detect_scripts(text) == expected


class TestGuard2ScriptDetectability:
    """AC3.2 (Guard 2): every script in _REQUIRED_SCRIPTS is detectable.

    For each tag, take the first code point from its first range,
    construct a single-character string, and verify detect_scripts
    includes that tag.
    """

    @pytest.mark.parametrize("tag", sorted(_REQUIRED_SCRIPTS))
    def test_every_required_script_is_detectable(self, tag: str) -> None:
        first_cp = SCRIPT_TAG_RANGES[tag][0][0]
        char = chr(first_cp)
        result = detect_scripts(char)
        assert tag in result, (
            f"detect_scripts(chr({first_cp:#x})) = {result}, "
            f"expected {tag!r} to be present"
        )


class TestGuard4DataConsistency:
    """AC3.7 (Guard 4): font registry and detection ranges are consistent."""

    def test_required_scripts_subset_of_detection_ranges(self) -> None:
        """Every font tag has detection ranges."""
        missing = _REQUIRED_SCRIPTS - SCRIPT_TAG_RANGES.keys()
        assert not missing, (
            f"Scripts in _REQUIRED_SCRIPTS without detection ranges: {missing}"
        )

    def test_every_font_tag_has_detection_path(self) -> None:
        """Every non-latn script_tag in FONT_REGISTRY appears in SCRIPT_TAG_RANGES."""
        font_tags = {f.script_tag for f in FONT_REGISTRY if f.script_tag != "latn"}
        missing = font_tags - SCRIPT_TAG_RANGES.keys()
        assert not missing, f"Font tags without detection ranges: {missing}"

    def test_all_scripts_detected_from_combined_text(self) -> None:
        """A string with one char per required script detects all of them."""
        chars = [chr(SCRIPT_TAG_RANGES[tag][0][0]) for tag in _REQUIRED_SCRIPTS]
        combined = "".join(chars)
        result = detect_scripts(combined)
        assert result == _REQUIRED_SCRIPTS, (
            f"Expected {_REQUIRED_SCRIPTS}, got {result}. "
            f"Missing: {_REQUIRED_SCRIPTS - result}"
        )
