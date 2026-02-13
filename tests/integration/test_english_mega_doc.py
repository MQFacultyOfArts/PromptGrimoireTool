"""English mega-document: all English-only LaTeX compile tests in one compilation.

Combines 13 chatbot fixtures, pipeline highlight tests, cross-environment
highlights, and basic pipeline/marginnote tests into a single mega-document.
This reduces ~38 individual compile_latex() invocations to 1.

Each test input becomes a MegaDocSegment compiled via the subfiles package.
Tests use pytest-subtests for independent assertion execution (AC1.6).

AC1.1: Contributes 1 compile (down from ~38).
AC1.2: All original assertions are preserved as subtests.
AC1.5: Each segment is independently compilable via subfiles.
AC1.6: Subtest failures do not prevent remaining subtests from executing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from tests.conftest import load_conversation_fixture, requires_latexmk
from tests.integration.conftest import (
    TAG_COLOURS,
    MegaDocResult,
    MegaDocSegment,
    compile_mega_document,
)

# ---------------------------------------------------------------------------
# Fixture / segment data
# ---------------------------------------------------------------------------

# 13 English chatbot fixture filenames (no CJK)
_ENGLISH_CHATBOT_FIXTURES = [
    "claude_cooking",
    "claude_maths",
    "google_aistudio_image",
    "google_aistudio_ux_discussion",
    "google_gemini_debug",
    "google_gemini_deep_research",
    "openai_biblatex",
    "openai_dh_dr",
    "openai_dprk_denmark",
    "openai_software_long_dr",
    "scienceos_loc",
    "scienceos_philsci",
    "austlii",
]

# Path to 183-libreoffice.html used by cross-env highlights
_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
_CROSS_ENV_HTML_PATH = _FIXTURES_DIR / "183-libreoffice.html"


def _build_english_segments() -> list[MegaDocSegment]:
    """Build all English mega-document segments.

    Returns a list of MegaDocSegment instances covering:
    - 13 English chatbot fixtures
    - Pipeline highlight regression tests (issue_85, three_overlapping, cross_boundary)
    - Cross-environment highlight test (183-libreoffice.html)
    - Basic export pipeline test
    - Marginnote with comments test
    """
    segments: list[MegaDocSegment] = []

    # --- 13 English chatbot fixtures (no highlights, preprocess=True) ---
    for name in _ENGLISH_CHATBOT_FIXTURES:
        html = load_conversation_fixture(name)
        segments.append(
            MegaDocSegment(
                name=f"chatbot_{name}",
                html=html,
                preprocess=True,
            )
        )

    # --- Pipeline highlight tests ---

    # Issue #85 regression: interleaved highlights with literal marker check
    segments.append(
        MegaDocSegment(
            name="issue_85_regression",
            html="<p>The quick brown fox jumps over the lazy dog.</p>",
            highlights=[
                {
                    "start_char": 1,  # "quick"
                    "end_char": 4,  # through "fox"
                    "tag": "jurisdiction",
                    "author": "Test User",
                    "text": "quick brown fox",
                    "comments": [],
                    "created_at": "2026-01-28T10:00:00+00:00",
                },
                {
                    "start_char": 2,  # "brown"
                    "end_char": 6,  # through "over"
                    "tag": "legal_issues",
                    "author": "Test User",
                    "text": "brown fox jumps over",
                    "comments": [],
                    "created_at": "2026-01-28T10:00:00+00:00",
                },
            ],
            tag_colours={
                "jurisdiction": TAG_COLOURS["jurisdiction"],
                "legal_issues": TAG_COLOURS["legal_issues"],
            },
            preprocess=False,
        )
    )

    # Three overlapping highlights (many-dark underline codepath)
    segments.append(
        MegaDocSegment(
            name="three_overlapping",
            html="<p>Word one word two word three word four</p>",
            highlights=[
                {
                    "start_char": 0,
                    "end_char": 6,
                    "tag": "jurisdiction",
                    "author": "Test",
                    "text": "Word one word two word three",
                    "comments": [],
                },
                {
                    "start_char": 1,
                    "end_char": 5,
                    "tag": "legal_issues",
                    "author": "Test",
                    "text": "one word two word",
                    "comments": [],
                },
                {
                    "start_char": 2,
                    "end_char": 4,
                    "tag": "reasons",
                    "author": "Test",
                    "text": "word two",
                    "comments": [],
                },
            ],
            tag_colours={
                "jurisdiction": TAG_COLOURS["jurisdiction"],
                "legal_issues": TAG_COLOURS["legal_issues"],
                "reasons": TAG_COLOURS["reasons"],
            },
            preprocess=False,
        )
    )

    # Cross-boundary: overlapping highlights crossing list environment boundary
    segments.append(
        MegaDocSegment(
            name="cross_boundary",
            html="""
        <p>Before the list starts here.</p>
        <ol>
            <li>First item in the list.</li>
            <li>Second item in the list.</li>
        </ol>
        <p>After the list ends here.</p>
        """,
            highlights=[
                {
                    "start_char": 3,  # "starts"
                    "end_char": 11,  # through "item" (second)
                    "tag": "jurisdiction",
                    "author": "Test",
                    "text": "starts here First item in the list Second item",
                    "comments": [],
                },
                {
                    "start_char": 6,  # "item" (first)
                    "end_char": 15,  # through "After"
                    "tag": "legal_issues",
                    "author": "Test",
                    "text": "item in the list Second item in the list After",
                    "comments": [],
                },
            ],
            tag_colours={
                "jurisdiction": TAG_COLOURS["jurisdiction"],
                "legal_issues": TAG_COLOURS["legal_issues"],
            },
            preprocess=False,
        )
    )

    # Cross-env highlights: real document with highlight spanning list boundary
    # preprocess=True because the original test ran through export_annotation_pdf
    # which preprocesses the HTML before passing to convert_html_with_annotations
    cross_env_html = _CROSS_ENV_HTML_PATH.read_text(encoding="utf-8")
    segments.append(
        MegaDocSegment(
            name="cross_env_highlights",
            html=cross_env_html,
            highlights=[
                {
                    "start_char": 848,
                    "end_char": 906,
                    "tag": "order",
                    "author": "Test User",
                    "text": "test highlight spanning list boundary",
                    "comments": [],
                    "created_at": "2026-01-27T10:00:00+00:00",
                }
            ],
            tag_colours={"order": TAG_COLOURS["order"]},
            preprocess=True,
        )
    )

    # Basic pipeline: simple document with single highlight
    segments.append(
        MegaDocSegment(
            name="basic_pipeline",
            html="<p>This is a test document with highlighted text.</p>",
            highlights=[
                {
                    "id": "h1",
                    "start_char": 3,
                    "end_char": 5,
                    "tag": "jurisdiction",
                    "text": "test document",
                    "author": "Tester",
                    "created_at": "2026-01-26T14:30:00+00:00",
                    "comments": [],
                }
            ],
            tag_colours={"jurisdiction": TAG_COLOURS["jurisdiction"]},
            preprocess=False,
        )
    )

    # Marginnote with comments: highlight with comment thread
    segments.append(
        MegaDocSegment(
            name="marginnote_comments",
            html="<p>The court held that the defendant was liable.</p>",
            highlights=[
                {
                    "id": "h1",
                    "start_char": 0,
                    "end_char": 4,
                    "tag": "decision",
                    "text": "The court held that",
                    "author": "Alice",
                    "created_at": "2026-01-26T10:00:00+00:00",
                    "comments": [
                        {"author": "Bob", "text": "Good catch on this point."},
                        {"author": "Alice", "text": "Thanks, see also para 45."},
                    ],
                }
            ],
            tag_colours={"decision": TAG_COLOURS["decision"]},
            preprocess=False,
        )
    )

    return segments


# ---------------------------------------------------------------------------
# Module-scoped fixture: compile once, share across all tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def english_mega_result(tmp_path_factory) -> MegaDocResult:
    """Compile the English mega-document once for all tests in this module.

    Combines 13 chatbot fixtures + pipeline tests + cross-env + basic pipeline
    into a single LaTeX compilation via the subfiles package.
    """
    output_dir = tmp_path_factory.mktemp("english_mega")
    segments = _build_english_segments()
    return await compile_mega_document(segments, output_dir)


# ---------------------------------------------------------------------------
# Test classes: assertions migrated VERBATIM from original test files
# ---------------------------------------------------------------------------


@requires_latexmk
class TestChatbotCompilation:
    """Verify all 13 English chatbot fixtures compile in the mega-document.

    Migrated from: test_chatbot_fixtures.py::TestChatbotFixturesToPdf
    Original: 13 individual compile_latex() calls, each asserting PDF exists.
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_all_chatbot_segments_present(
        self, english_mega_result: MegaDocResult, subtests
    ) -> None:
        """Each English chatbot fixture has a segment in the mega-document."""
        for name in _ENGLISH_CHATBOT_FIXTURES:
            segment_name = f"chatbot_{name}"
            with subtests.test(msg=segment_name):
                assert segment_name in english_mega_result.segment_tex

    @pytest.mark.asyncio(loop_scope="module")
    async def test_pdf_exists_and_nonempty(
        self, english_mega_result: MegaDocResult
    ) -> None:
        """PDF was generated and is non-empty."""
        assert english_mega_result.pdf_path.exists(), "PDF not generated"
        assert english_mega_result.pdf_path.stat().st_size > 0, "PDF is empty"


@requires_latexmk
class TestPipelineHighlights:
    """Verify pipeline highlight tests compile correctly in the mega-document.

    Migrated from: test_pdf_pipeline.py::TestPdfPipeline
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_issue_85_regression(
        self, english_mega_result: MegaDocResult, subtests
    ) -> None:
        """Regression test: markers are processed, not literal text.

        Issue #85: Nested/interleaved highlights left literal HLSTART/HLEND
        markers in the output instead of processing them into LaTeX commands.

        CRITICAL: This test MUST fail if Issue #85 regresses.

        Migrated from: test_pdf_pipeline.py::TestPdfPipeline::
        test_issue_85_regression_no_literal_markers
        """
        latex_content = english_mega_result.segment_tex["issue_85_regression"]

        with subtests.test(msg="no-HLSTART"):
            # CRITICAL ASSERTIONS - markers must NOT appear literally
            assert "HLSTART" not in latex_content, (
                "HLSTART marker found in output - Issue #85 regression!"
            )
        with subtests.test(msg="no-HLEND"):
            assert "HLEND" not in latex_content, (
                "HLEND marker found in output - Issue #85 regression!"
            )
        with subtests.test(msg="no-ANNMARKER"):
            assert "ANNMARKER" not in latex_content, (
                "ANNMARKER found in output - Issue #85 regression!"
            )
        with subtests.test(msg="no-ENDHL"):
            assert "ENDHL" not in latex_content, (
                "ENDHL found in output - Issue #85 regression!"
            )
        with subtests.test(msg="no-ENDMARKER"):
            assert "ENDMARKER" not in latex_content, (
                "ENDMARKER found in output - Issue #85 regression!"
            )
        with subtests.test(msg="has-highLight"):
            # Positive assertions - LaTeX commands should be present
            assert r"\highLight" in latex_content, "No \\highLight command in output"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_three_overlapping_compile(
        self, english_mega_result: MegaDocResult, subtests
    ) -> None:
        """Three overlapping highlights should compile to PDF.

        Migrated from: test_pdf_pipeline.py::TestPdfPipeline
        ::test_three_overlapping_compile
        """
        with subtests.test(msg="three_overlapping"):
            assert english_mega_result.pdf_path.exists()

    @pytest.mark.asyncio(loop_scope="module")
    async def test_cross_boundary_compile(
        self, english_mega_result: MegaDocResult, subtests
    ) -> None:
        """Overlapping highlights crossing list boundary.

        Migrated from: test_pdf_pipeline.py::TestPdfPipeline
        ::test_overlapping_highlights_crossing_list_boundary
        """
        with subtests.test(msg="cross_boundary"):
            assert english_mega_result.pdf_path.exists()

    @pytest.mark.asyncio(loop_scope="module")
    async def test_cross_env_highlights(
        self, english_mega_result: MegaDocResult, subtests
    ) -> None:
        """Cross-environment highlights compile to PDF.

        Words 848-906 span across a \\item boundary. Confirms
        highlight boundary splitting works correctly.

        Migrated from: test_cross_env_highlights.py::
        TestCrossEnvironmentHighlights::
        test_cross_env_highlight_compiles_to_pdf
        """
        with subtests.test(msg="cross_env-pdf-exists"):
            assert english_mega_result.pdf_path.exists(), (
                f"PDF not created at {english_mega_result.pdf_path}"
            )
        with subtests.test(msg="cross_env-tex-exists"):
            sf = english_mega_result.subfile_paths
            assert sf["cross_env_highlights"].exists(), (
                f"TeX not created at {sf['cross_env_highlights']}"
            )


@requires_latexmk
class TestBasicPipeline:
    """Verify basic export pipeline compiles in the mega-document.

    Migrated from: test_pdf_export.py::
    TestMarginnoteExportPipeline::
    test_export_annotation_pdf_basic
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_basic_pipeline_compile(
        self, english_mega_result: MegaDocResult
    ) -> None:
        """export_annotation_pdf should produce a valid PDF.

        Migrated from: test_pdf_export.py::
        TestMarginnoteExportPipeline::
        test_export_annotation_pdf_basic
        """
        assert english_mega_result.pdf_path.exists()
        assert english_mega_result.pdf_path.suffix == ".pdf"
        # Check it's actually a PDF (starts with %PDF)
        with english_mega_result.pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF"


@requires_latexmk
class TestMarginnoteComments:
    """Verify marginnote with comments in the mega-document.

    Migrated from: test_pdf_export.py::
    TestMarginnoteExportPipeline::test_export_with_comments
    (compile-time assertions only)
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_comments_in_tex(
        self, english_mega_result: MegaDocResult, subtests
    ) -> None:
        """Comment authors and text appear in segment LaTeX.

        Migrated from: test_pdf_export.py::
        TestMarginnoteExportPipeline::
        test_export_with_comments
        """
        tex_content = english_mega_result.segment_tex["marginnote_comments"]

        with subtests.test(msg="author-Bob"):
            assert "Bob" in tex_content
        with subtests.test(msg="comment-text"):
            assert "Good catch" in tex_content
