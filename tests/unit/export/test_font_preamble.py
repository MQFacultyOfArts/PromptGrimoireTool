"""Tests for build_font_preamble() output.

Verifies:
- AC3.3: Latin-only preamble (no CJK, no non-base fonts)
- AC3.4: CJK preamble (luatexja-fontspec, CJK font setup, renewcommand cjktext)
- Mixed scripts: selective font inclusion
- Full chain: all fonts included when all scripts detected
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.unicode_latex import (
    _REQUIRED_SCRIPTS,
    FONT_REGISTRY,
    build_font_preamble,
)


class TestLatinOnlyPreambleAC33:
    """AC3.3: build_font_preamble(frozenset()) emits Latin-only output."""

    @pytest.fixture
    def latin_preamble(self) -> str:
        return build_font_preamble(frozenset())

    def test_contains_base_fonts(self, latin_preamble: str) -> None:
        """Latin base fonts are always in the fallback chain."""
        assert "Gentium Plus" in latin_preamble
        assert "Charis SIL" in latin_preamble
        assert "Noto Serif" in latin_preamble

    def test_contains_setmainfont(self, latin_preamble: str) -> None:
        assert r"\setmainfont{TeX Gyre Termes}" in latin_preamble

    def test_no_luatexja_fontspec(self, latin_preamble: str) -> None:
        assert "luatexja-fontspec" not in latin_preamble

    def test_no_setmainjfont(self, latin_preamble: str) -> None:
        assert r"\setmainjfont" not in latin_preamble

    def test_no_renewcommand_cjktext(self, latin_preamble: str) -> None:
        assert r"\renewcommand" not in latin_preamble or "cjktext" not in latin_preamble

    def test_no_non_base_fonts(self, latin_preamble: str) -> None:
        """No script-specific fonts in Latin-only output."""
        non_base_names = [
            "Ezra SIL",
            "Scheherazade",
            "Annapurna SIL",
            "Noto Serif Hebrew",
            "Noto Naskh Arabic",
            "Noto Serif Devanagari",
            "Noto Serif Bengali",
            "Noto Serif Tamil",
            "Noto Serif Thai",
            "Noto Serif Georgian",
            "Noto Serif Armenian",
            "Abyssinica SIL",
            "Noto Serif Ethiopic",
            "Khmer Mondulkiri",
            "Noto Serif Khmer",
            "Noto Serif Lao",
            "Padauk",
            "Noto Serif Myanmar",
            "Noto Serif Sinhala",
            "Tai Heritage Pro",
            "Sophia Nubian",
            "Nuosu SIL",
            "Galatia SIL",
            "Noto Sans Deseret",
            "Noto Sans Osage",
            "Noto Sans Shavian",
            "Noto Sans Symbols",
            "Noto Sans Symbols2",
            "Noto Sans Math",
        ]
        for name in non_base_names:
            assert name not in latin_preamble, (
                f"Non-base font {name!r} should not appear in Latin-only preamble"
            )


class TestCJKPreambleAC34:
    """AC3.4: build_font_preamble(frozenset({"cjk"})) emits CJK setup."""

    @pytest.fixture
    def cjk_preamble(self) -> str:
        return build_font_preamble(frozenset({"cjk"}))

    def test_contains_luatexja_fontspec(self, cjk_preamble: str) -> None:
        assert r"\usepackage{luatexja-fontspec}" in cjk_preamble

    def test_contains_ltjsetparameter(self, cjk_preamble: str) -> None:
        assert r"\ltjsetparameter{jacharrange={-2}}" in cjk_preamble

    def test_contains_setmainjfont(self, cjk_preamble: str) -> None:
        assert r"\setmainjfont{Noto Serif CJK SC}" in cjk_preamble

    def test_contains_setsansjfont(self, cjk_preamble: str) -> None:
        assert r"\setsansjfont{Noto Sans CJK SC}" in cjk_preamble

    def test_contains_newjfontfamily(self, cjk_preamble: str) -> None:
        assert r"\newjfontfamily\notocjk" in cjk_preamble

    def test_contains_renewcommand_cjktext(self, cjk_preamble: str) -> None:
        assert r"\renewcommand{\cjktext}" in cjk_preamble
        assert "notocjk" in cjk_preamble

    def test_contains_setmainfont(self, cjk_preamble: str) -> None:
        assert r"\setmainfont{TeX Gyre Termes}" in cjk_preamble

    def test_contains_base_fonts(self, cjk_preamble: str) -> None:
        """Base fonts still present alongside CJK."""
        assert "Gentium Plus" in cjk_preamble
        assert "Charis SIL" in cjk_preamble
        assert "Noto Serif" in cjk_preamble


class TestMixedScriptsPreamble:
    """Mixed scripts: selective font inclusion."""

    @pytest.fixture
    def mixed_preamble(self) -> str:
        return build_font_preamble(frozenset({"hebr", "arab"}))

    def test_contains_hebrew_fonts(self, mixed_preamble: str) -> None:
        assert "Ezra SIL" in mixed_preamble
        assert "Noto Serif Hebrew" in mixed_preamble

    def test_contains_arabic_fonts(self, mixed_preamble: str) -> None:
        assert "Scheherazade" in mixed_preamble
        assert "Noto Naskh Arabic" in mixed_preamble

    def test_no_cjk(self, mixed_preamble: str) -> None:
        assert "luatexja-fontspec" not in mixed_preamble
        assert r"\setmainjfont" not in mixed_preamble

    def test_contains_base_fonts(self, mixed_preamble: str) -> None:
        assert "Gentium Plus" in mixed_preamble
        assert "Charis SIL" in mixed_preamble
        assert "Noto Serif" in mixed_preamble


class TestFullChainGuard:
    """Full chain: all fonts activated when all scripts detected."""

    def test_all_fonts_present(self) -> None:
        """build_font_preamble(_REQUIRED_SCRIPTS) contains every font."""
        preamble = build_font_preamble(_REQUIRED_SCRIPTS)
        for font in FONT_REGISTRY:
            assert font.name in preamble, (
                f"Font {font.name!r} (tag={font.script_tag!r}) missing from "
                f"full-chain preamble"
            )
