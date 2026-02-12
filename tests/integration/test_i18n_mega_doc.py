"""i18n mega-document: all CJK and multilingual LaTeX compile tests in one compilation.

Combines 4 CJK/multilingual fixtures (chinese_wikipedia, translation_japanese_sample,
translation_korean_sample, translation_spanish_sample) into a single mega-document.
This reduces 8 individual compile_latex() invocations to 1.

Each fixture becomes a MegaDocSegment compiled via the subfiles package.
Tests use pytest-subtests for independent assertion execution (AC1.6).

AC1.1: Contributes 1 compile (down from 8).
AC1.2: All original assertions from TestChatbotFixturesToPdf (CJK) and
        TestI18nPdfExport are preserved as subtests.
AC1.5: Each segment is independently compilable via subfiles.
AC1.6: Subtest failures do not prevent remaining subtests from executing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import pytest_asyncio

from tests.conftest import requires_latexmk
from tests.integration.conftest import (
    MegaDocResult,
    MegaDocSegment,
    compile_mega_document,
)

# ---------------------------------------------------------------------------
# Fixture / segment data
# ---------------------------------------------------------------------------

# Clean fixture directory (article content only, no chatbot chrome)
_CLEAN_FIXTURES_DIR = (
    Path(__file__).parent.parent / "fixtures" / "conversations" / "clean"
)

# i18n fixture names
_I18N_FIXTURES = [
    "chinese_wikipedia",
    "translation_japanese_sample",
    "translation_korean_sample",
    "translation_spanish_sample",
]

# Expected characters per fixture (for content verification).
# Migrated verbatim from test_pdf_export.py::TestI18nPdfExport._EXPECTED_CHARS.
_EXPECTED_CHARS: dict[str, list[str]] = {
    "chinese_wikipedia": ["维基百科", "示例内容"],
    "translation_japanese_sample": ["家庭法令", "離婚判決謄本", "オーストラリア"],
    "translation_korean_sample": [
        "법은",
        "차이를",
        "조정하는",
    ],
    "translation_spanish_sample": ["vehículo", "búsqueda"],
}


def _build_i18n_segments() -> list[MegaDocSegment]:
    """Build all i18n mega-document segments.

    Returns a list of MegaDocSegment instances for 4 CJK/multilingual fixtures.
    Uses clean fixtures (article content only) with preprocess=True to match
    the production pipeline's behaviour.
    """
    segments: list[MegaDocSegment] = []

    for name in _I18N_FIXTURES:
        fixture_path = _CLEAN_FIXTURES_DIR / f"{name}.html"
        html = fixture_path.read_text(encoding="utf-8")
        segments.append(
            MegaDocSegment(
                name=name,
                html=html,
                preprocess=True,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# Module-scoped fixture: compile once, share across all tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def i18n_mega_result(tmp_path_factory) -> MegaDocResult:
    """Compile the i18n mega-document once for all tests in this module.

    Combines 4 CJK/multilingual fixtures into a single LaTeX compilation
    via the subfiles package. Uses the full Unicode preamble (all fonts loaded)
    because content includes CJK, Latin, and other scripts.
    """
    output_dir = tmp_path_factory.mktemp("i18n_mega")
    segments = _build_i18n_segments()
    return await compile_mega_document(segments, output_dir)


# ---------------------------------------------------------------------------
# Test classes: assertions migrated VERBATIM from original test files
# ---------------------------------------------------------------------------

# Patterns indicating font problems in LaTeX log
# (migrated from test_pdf_export.py::TestI18nPdfExport._check_log_for_font_errors)
_FONT_ERROR_PATTERNS = [
    "Font .* not found",
    "Missing character:",
    "! Font \\\\",
    "kpathsea: Running mktextfm",
]


@requires_latexmk
class TestI18nCompilation:
    """Verify all 4 i18n fixtures compile in the mega-document.

    Migrated from:
    - test_chatbot_fixtures.py::TestChatbotFixturesToPdf (CJK fixtures)
    - test_pdf_export.py::TestI18nPdfExport
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_pdf_exists_and_valid(self, i18n_mega_result: MegaDocResult) -> None:
        """PDF was generated and is valid.

        Migrated from: test_chatbot_fixtures.py::TestChatbotFixturesToPdf
        (asserts PDF exists and is non-empty for each CJK fixture).
        Also from: test_pdf_export.py::TestI18nPdfExport
        (asserts PDF exists, non-empty, and has %PDF header).
        """
        assert i18n_mega_result.pdf_path.exists(), "PDF not generated"
        assert i18n_mega_result.pdf_path.stat().st_size > 0, "PDF is empty"
        with i18n_mega_result.pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF", "Invalid PDF header"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_all_segments_present(
        self, i18n_mega_result: MegaDocResult, subtests
    ) -> None:
        """Each i18n fixture has a segment in the mega-document.

        Migrated from: test_chatbot_fixtures.py::TestChatbotFixturesToPdf
        (asserted each fixture compiled individually).
        """
        for name in _I18N_FIXTURES:
            with subtests.test(msg=name):
                assert name in i18n_mega_result.segment_tex

    @pytest.mark.asyncio(loop_scope="module")
    async def test_tex_contains_i18n_characters(
        self, i18n_mega_result: MegaDocResult, subtests
    ) -> None:
        """TEX file contains expected i18n characters for each fixture.

        Migrated VERBATIM from: test_pdf_export.py::TestI18nPdfExport::
        test_export_i18n_fixture (assertion 2: "Verify TEX file contains
        expected i18n characters").
        """
        for fixture_name in _I18N_FIXTURES:
            expected_chars = _EXPECTED_CHARS.get(fixture_name, [])
            tex_content = i18n_mega_result.segment_tex[fixture_name]
            for expected in expected_chars:
                with subtests.test(msg=f"{fixture_name}-char-{expected}"):
                    assert expected in tex_content, (
                        f"Expected '{expected}' not found in TEX for {fixture_name}"
                    )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_no_font_errors_in_log(
        self, i18n_mega_result: MegaDocResult, subtests
    ) -> None:
        """LaTeX log has no font substitution errors.

        Migrated VERBATIM from: test_pdf_export.py::TestI18nPdfExport::
        test_export_i18n_fixture (assertion 3: "Verify LaTeX log has no
        font errors").

        Checks the mega-document log file for font-related error patterns.
        """
        log_path = i18n_mega_result.output_dir / "mega_test.log"
        if not log_path.exists():
            pytest.fail("Mega-document log file not found")

        log_content = log_path.read_text(encoding="utf-8", errors="replace")

        errors: list[str] = []
        for line in log_content.split("\n"):
            for pattern in _FONT_ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip())
                    break

        with subtests.test(msg="no-font-errors"):
            assert not errors, "Font errors in mega-document log:\n" + "\n".join(
                errors[:5]
            )
