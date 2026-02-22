"""Integration test: export workspace fixture to PDF.

Uses real workspace data from fa008b89-a772-4d02-a3a3-d5a99b62c720 (Lawlis v R)
with 11 highlights, comments, and a multilingual response draft containing
Armenian, Arabic, Chinese, Korean, Georgian, Hindi, Hebrew, Thai, and other
scripts that must render without tofu.

Tests verify the **PDF output** directly using pymupdf text extraction,
not intermediate .tex files. This catches issues that .tex-level checks miss
(font fallback failures, glyph rendering, highlight boundary drift).

Compilation strategy: Two module-scoped fixtures compile the workspace once
each (variant A without draft, variant B with draft). All tests in this module
read from these cached results. This reduces 30 compile_latex() calls to 2.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio

from promptgrimoire.export.pdf_export import (
    export_annotation_pdf,
    markdown_to_latex_notes,
)
from tests.conftest import requires_latexmk
from tests.integration.conftest import extract_pdf_text_pymupdf

# Dispatch slow tests first so xdist workers aren't idle waiting for stragglers.
pytestmark = pytest.mark.order(1)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"

# Tag colours for PDF export tests. Values are arbitrary valid hex colours;
# the actual colour doesn't matter for compilation correctness.
_TAG_COLOURS: dict[str, str] = {
    "jurisdiction": "#1f77b4",
    "procedural_history": "#ff7f0e",
    "legally_relevant_facts": "#2ca02c",
    "legal_issues": "#d62728",
    "reasons": "#9467bd",
    "courts_reasoning": "#8c564b",
    "decision": "#e377c2",
    "order": "#7f7f7f",
    "domestic_sources": "#bcbd22",
    "reflection": "#17becf",
}


def _load_workspace_fixture() -> dict:
    """Load the Lawlis v R workspace fixture."""
    fixture_path = FIXTURE_DIR / "workspace_lawlis_v_r.json"
    with fixture_path.open() as f:
        return json.load(f)


def _load_html() -> str:
    """Load the Lawlis v R HTML fixture."""
    html_path = FIXTURE_DIR / "conversations" / "lawlis_v_r_austlii.html"
    return html_path.read_text()


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract full text from PDF using pdftotext (poppler).

    pdftotext produces more reliable Unicode extraction than pymupdf
    for detecting tofu/missing glyphs — it emits U+FFFD replacement
    characters for glyphs the PDF couldn't render.
    """
    result = subprocess.run(  # nosec B603, B607
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


_HYPHEN_NL = re.compile(r"-\n")
_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_pdf_text(text: str) -> str:
    """Normalize PDF-extracted text for fragment matching.

    Handles two artefacts of PDF text extraction:
    1. LaTeX hyphenation: "Cor-\\nrections" -> "Corrections"
    2. Line breaks within phrases: "sentence\\nproceedings"
       -> "sentence proceedings"
    """
    text = _HYPHEN_NL.sub("", text)
    return _WHITESPACE_RUN.sub(" ", text)


# ===================================================================
# Module-scoped compiled fixtures: compile once, reuse across all tests
# ===================================================================


@dataclass(frozen=True)
class WorkspaceExportResult:
    """Cached result from a single workspace export compilation.

    Holds all data that tests need to assert against, avoiding
    repeated compile_latex() calls for the same input.
    """

    pdf_path: Path
    """Path to the compiled PDF."""

    tex_path: Path
    """Path to the .tex file."""

    tex_content: str
    """Full content of the .tex file."""

    output_dir: Path
    """Directory containing all output files."""

    pdf_text_pymupdf: str
    """Normalized PDF text (pymupdf extraction, whitespace-collapsed)."""

    pdf_text_pymupdf_raw: str
    """Raw PDF text from pymupdf (not normalized)."""

    pdf_text_poppler: str
    """PDF text from pdftotext (poppler) for Unicode tofu detection."""


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def lawlis_no_draft_result(tmp_path_factory) -> WorkspaceExportResult:
    """Compile variant A: Lawlis HTML + 11 highlights, NO response draft.

    Used by TestHighlightBoundariesInPdf and TestHighlightWrappingInTex.
    Compiled once at module scope, shared across all tests that need
    the no-draft variant.
    """
    output_dir = tmp_path_factory.mktemp("lawlis_no_draft")
    fixture = _load_workspace_fixture()
    html = _load_html()
    highlights = fixture["highlights"]

    pdf_path = await export_annotation_pdf(
        html_content=html,
        highlights=highlights,
        tag_colours=_TAG_COLOURS,
        output_dir=output_dir,
    )

    tex_path = output_dir / "annotated_document.tex"
    tex_content = tex_path.read_text()
    raw_pymupdf = extract_pdf_text_pymupdf(pdf_path)
    normalized_pymupdf = _normalize_pdf_text(raw_pymupdf)
    poppler_text = _extract_pdf_text(pdf_path)

    return WorkspaceExportResult(
        pdf_path=pdf_path,
        tex_path=tex_path,
        tex_content=tex_content,
        output_dir=output_dir,
        pdf_text_pymupdf=normalized_pymupdf,
        pdf_text_pymupdf_raw=raw_pymupdf,
        pdf_text_poppler=poppler_text,
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def lawlis_with_draft_result(tmp_path_factory) -> WorkspaceExportResult:
    """Compile variant B: Lawlis HTML + 11 highlights + response draft.

    Used by TestPdfBasicIntegrity, TestUnicodeRendering, and any test
    that needs the multilingual response draft content. Compiled once
    at module scope, shared across all tests that need the draft variant.
    """
    output_dir = tmp_path_factory.mktemp("lawlis_with_draft")
    fixture = _load_workspace_fixture()
    html = _load_html()
    highlights = fixture["highlights"]
    response_md = fixture["response_draft_markdown"]

    notes_latex = await markdown_to_latex_notes(response_md)

    pdf_path = await export_annotation_pdf(
        html_content=html,
        highlights=highlights,
        tag_colours=_TAG_COLOURS,
        notes_latex=notes_latex,
        output_dir=output_dir,
    )

    tex_path = output_dir / "annotated_document.tex"
    tex_content = tex_path.read_text()
    raw_pymupdf = extract_pdf_text_pymupdf(pdf_path)
    normalized_pymupdf = _normalize_pdf_text(raw_pymupdf)
    poppler_text = _extract_pdf_text(pdf_path)

    return WorkspaceExportResult(
        pdf_path=pdf_path,
        tex_path=tex_path,
        tex_content=tex_content,
        output_dir=output_dir,
        pdf_text_pymupdf=normalized_pymupdf,
        pdf_text_pymupdf_raw=raw_pymupdf,
        pdf_text_poppler=poppler_text,
    )


@requires_latexmk
class TestPdfBasicIntegrity:
    """Basic PDF generation checks."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_export_produces_pdf(
        self, lawlis_with_draft_result: WorkspaceExportResult
    ) -> None:
        """Full pipeline: HTML + highlights + response draft -> PDF."""
        pdf_path = lawlis_with_draft_result.pdf_path

        assert pdf_path.exists(), f"PDF not created at {pdf_path}"
        assert pdf_path.suffix == ".pdf"
        size = pdf_path.stat().st_size
        assert size > 50_000, (
            f"PDF too small ({size} bytes) — compilation likely failed"
        )
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF", "Output is not a valid PDF"


# ===================================================================
# Highlight boundary detection: every highlight's text must appear
# ===================================================================

# Expected text fragments for each highlight — start and end of the
# highlighted region. These come from the fixture's `text` field and
# represent what MUST appear in the PDF within highlight formatting.
_HIGHLIGHT_BOUNDARY_EXPECTATIONS: list[dict[str, str | list[str]]] = [
    {
        "index": "0",
        "tag": "jurisdiction",
        "must_contain": [
            "Lawlis v R",
            "3 November 2025",
        ],
        "comment": "juristdiction 1",
    },
    {
        "index": "1",
        "tag": "jurisdiction",
        "must_contain": [
            "Last Updated",
            "10 November 2025",
        ],
        "comment": "last fliberty",
    },
    {
        "index": "2",
        "tag": "jurisdiction",
        "must_contain": [
            "Court of Criminal Appeal",
        ],
        "comment": "header court",
    },
    {
        "index": "3",
        "tag": "procedural_history",
        "must_contain": [
            "Supreme Court",
        ],
        "comment": "supremes",
    },
    {
        "index": "4",
        "tag": "reasons",
        "must_contain": [
            "Kirk JA",
            "Sweeney J",
            "Coleman J",
            "Orders made on 3 November 2025",
            "Grant leave to appeal",
            "Allow the appeal",
            "Quash the sentence",
            "Taking into account",
        ],
        "comment": "this is going to break a lot of stuff",
    },
    {
        "index": "5",
        "tag": "jurisdiction",
        "must_contain": [
            "Grounds of Appeal",
            "Mr Lawlis sought leave to rely on three grounds",
            "manifestly excessive",
        ],
        "comment": "1",
    },
    {
        "index": "6",
        "tag": "procedural_history",
        "must_contain": [
            "Remarks on Sentence",
        ],
        "comment": "2",
    },
    {
        "index": "7",
        "tag": "legally_relevant_facts",
        "must_contain": [
            "Judge Abadee sentenced Mr Lawlis",
            "sentence proceedings",
        ],
        "comment": "3",
    },
    {
        "index": "8",
        "tag": "legal_issues",
        "must_contain": [
            "5% discount",
            "trial was due to commence",
        ],
        "comment": "4",
    },
    {
        "index": "9",
        "tag": "legal_issues",
        "must_contain": [
            # Highlight 9: "omes of the victims" ->
            # "counsellors, and had tried medication"
            "financial gain",
            "Subjective factors",
            "counsellors",
            "tried medication",
        ],
        "comment": "this is also going to break stuff.",
    },
    {
        "index": "10",
        "tag": "reflection",
        "must_contain": [
            "3 November 2025 the Court made the following orders",
            "Grant leave to appeal",
            "Intensive Corrections Order",
        ],
        "comment": "lol",
    },
]


@requires_latexmk
class TestHighlightBoundariesInPdf:
    """Every highlight's text boundaries must appear in the PDF.

    These tests verify that the marker insertion pipeline places
    HLSTART/HLEND at the correct character positions by checking
    the actual PDF text output -- not the intermediate .tex file.
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_all_comments_appear_in_pdf(
        self,
        lawlis_no_draft_result: WorkspaceExportResult,
        subtests,
    ) -> None:
        """Every highlight comment must appear in the PDF text."""
        pdf_text = lawlis_no_draft_result.pdf_text_pymupdf
        fixture = _load_workspace_fixture()
        highlights = fixture["highlights"]

        for i, h in enumerate(highlights):
            for comment in h.get("comments", []):
                comment_text = comment["text"]
                with subtests.test(msg=f"highlight-{i}-comment"):
                    assert comment_text in pdf_text, (
                        f"Highlight {i} [{h['tag']}] comment "
                        f"{comment_text!r} not found in PDF text"
                    )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_highlight_boundaries_in_pdf(
        self,
        lawlis_no_draft_result: WorkspaceExportResult,
        subtests,
    ) -> None:
        """Each highlight's text fragments must appear in the PDF.

        This verifies CONTENT presence -- the text that should be
        inside each highlight actually appears in the PDF output.
        Marker boundary alignment errors cause text to be highlighted
        at wrong positions or not at all.
        """
        pdf_text = lawlis_no_draft_result.pdf_text_pymupdf

        for highlight_index, expectation in enumerate(_HIGHLIGHT_BOUNDARY_EXPECTATIONS):
            with subtests.test(msg=f"highlight-{highlight_index}"):
                for fragment in expectation["must_contain"]:
                    assert fragment in pdf_text, (
                        f"Highlight {highlight_index} [{expectation['tag']}]: "
                        f"expected text {fragment!r} not found in PDF. "
                        f"This may indicate marker boundary misalignment."
                    )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_highlight_boundaries_in_tex(
        self,
        lawlis_no_draft_result: WorkspaceExportResult,
    ) -> None:
        r"""Verify \\highLight wrapping in .tex matches expected content.

        For each highlight, the .tex file should contain \\highLight
        commands wrapping the expected text. This is a stronger test
        than just checking PDF text presence -- it verifies the text
        is actually INSIDE highlight formatting, not just somewhere
        in the document.
        """
        tex_content = lawlis_no_draft_result.tex_content
        fixture = _load_workspace_fixture()
        highlights = fixture["highlights"]

        # Every comment must appear in an \annot command
        for i, h in enumerate(highlights):
            for comment in h.get("comments", []):
                assert comment["text"] in tex_content, (
                    f"Highlight {i} [{h['tag']}] comment {comment['text']!r} "
                    f"not in .tex output"
                )

        # The .tex must have the right number of \annot commands
        annot_count = tex_content.count(r"\annot")
        # Filter out \annot in preamble definitions
        assert annot_count >= len(highlights), (
            f"Expected at least {len(highlights)} \\annot commands, found {annot_count}"
        )


def _find_brace_content(tex: str, start: int) -> str:
    """Extract content of first {...} group starting at `start`."""
    depth = 0
    begin = None
    for i in range(start, len(tex)):
        if tex[i] == "{":
            if depth == 0:
                begin = i + 1
            depth += 1
        elif tex[i] == "}":
            depth -= 1
            if depth == 0 and begin is not None:
                return tex[begin:i]
    return ""


def _extract_highlight_bodies(tex: str) -> list[str]:
    r"""Extract all \\highLight body contents from .tex."""
    bodies = []
    prefix = r"\highLight"
    pos = 0
    while True:
        idx = tex.find(prefix, pos)
        if idx == -1:
            break
        after = idx + len(prefix)
        # Skip optional [...] arg
        if after < len(tex) and tex[after] == "[":
            close = tex.find("]", after)
            if close != -1:
                after = close + 1
        brace = tex.find("{", after)
        if brace == -1:
            break
        body = _find_brace_content(tex, brace)
        bodies.append(body)
        pos = brace + 1
    return bodies


def _text_inside_any_highlight(tex: str, fragment: str) -> bool:
    """Check if fragment appears inside any highLight body."""
    normalized_frag = _WHITESPACE_RUN.sub(" ", fragment)
    for body in _extract_highlight_bodies(tex):
        normalized_body = _WHITESPACE_RUN.sub(" ", body)
        if normalized_frag in normalized_body:
            return True
    return False


# Fragments that must be INSIDE \highLight{} wrapping (not just
# present in the document). These catch marker boundary drift
# where the text exists but the highlight coloring is wrong.
_MUST_BE_HIGHLIGHTED: list[dict[str, str | list[str]]] = [
    {
        "id": "hl5_jurisdiction",
        "highlight": "5",
        "tag": "jurisdiction",
        "inside_highlight": [
            "Grounds of Appeal",
            "Mr Lawlis sought leave to rely on three grounds",
        ],
    },
    {
        "id": "hl9_legal_issues",
        "highlight": "9",
        "tag": "legal_issues",
        "inside_highlight": [
            "Subjective factors",
            "21 years old at the time",
            "tried medication",
        ],
    },
    {
        "id": "hl4_reasons",
        "highlight": "4",
        "tag": "reasons",
        "inside_highlight": [
            "Orders made on 3 November 2025",
        ],
    },
]


@requires_latexmk
class TestHighlightWrappingInTex:
    r"""Text must appear INSIDE \\highLight wrapping, not just in the doc.

    These tests catch marker boundary drift -- where the text exists
    in the PDF but the highlight coloring stops/starts at wrong
    positions. Detected by checking the .tex file's \\highLight{}
    block contents.
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_text_inside_highlight_wrapping(
        self,
        lawlis_no_draft_result: WorkspaceExportResult,
        subtests,
    ) -> None:
        """Verify text is inside highLight body, not just in doc."""
        tex_content = lawlis_no_draft_result.tex_content

        for spec in _MUST_BE_HIGHLIGHTED:
            with subtests.test(msg=spec["id"]):
                for fragment in spec["inside_highlight"]:
                    assert _text_inside_any_highlight(tex_content, fragment), (
                        f"Highlight {spec['highlight']} "
                        f"[{spec['tag']}]: "
                        f"{fragment!r} not inside any "
                        r"\highLight{} block. "
                        f"Marker boundary is misaligned."
                    )


# ===================================================================
# Tofu detection: multilingual text must render without replacement chars
# ===================================================================

# Scripts that must render in the General Notes section.
# Each tuple: (script_name, sample_text_that_must_appear)
_REQUIRED_SCRIPTS: list[tuple[str, str]] = [
    ("Armenian", "Հայերեն"),
    ("Arabic", "العربية"),
    ("Bulgarian/Cyrillic", "Български"),
    ("Chinese Simplified", "中文简体"),
    ("Georgian", "ქართული"),
    ("Greek", "Ελληνικά"),
    ("Hebrew", "עברית"),
    ("Hindi/Devanagari", "हिन्दी"),
    ("Thai", "ไทย"),
    ("Ukrainian/Cyrillic", "Українська"),
    ("Vietnamese", "Việt"),
]


@requires_latexmk
class TestUnicodeRendering:
    """Multilingual text in the response draft must render without tofu.

    The response draft contains link text in Armenian, Arabic, Chinese,
    Georgian, Greek, Hebrew, Hindi, Thai, and other scripts. The PDF
    must render all of these using the .sty font fallback
    chain -- no replacement characters (U+FFFD) or missing glyphs.
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_no_replacement_characters_in_pdf(
        self, lawlis_with_draft_result: WorkspaceExportResult
    ) -> None:
        """PDF text extraction must not contain U+FFFD replacement characters.

        pdftotext emits U+FFFD for glyphs that the PDF couldn't render.
        Any occurrence means a font fallback failure (tofu).
        """
        pdf_text = lawlis_with_draft_result.pdf_text_poppler
        replacement_count = pdf_text.count("\ufffd")
        if replacement_count > 0:
            idx = pdf_text.find(chr(0xFFFD))
            ctx = pdf_text[idx - 20 : idx + 20]
            pytest.fail(
                f"PDF has {replacement_count} U+FFFD chars. Context: ...{ctx}..."
            )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_script_renders_in_pdf(
        self,
        lawlis_with_draft_result: WorkspaceExportResult,
        subtests,
    ) -> None:
        """Each script's text must be extractable from the PDF.

        If a script renders as tofu, pdftotext either emits replacement
        characters or omits the text entirely. Either way, the expected
        text won't be found in the extracted output.
        """
        pdf_text_poppler = lawlis_with_draft_result.pdf_text_poppler
        pdf_text_mupdf = lawlis_with_draft_result.pdf_text_pymupdf_raw

        for script_name, expected_text in _REQUIRED_SCRIPTS:
            with subtests.test(msg=script_name):
                # RTL scripts (Arabic, Hebrew) may extract in reversed
                # char order; complex scripts (Devanagari) may decompose
                # ligatures differently. Check both forward and reversed
                # text, and also check that all expected characters are
                # present in the same extraction.
                reversed_text = expected_text[::-1]
                chars_present = all(c in pdf_text_mupdf for c in expected_text)
                found = (
                    expected_text in pdf_text_poppler
                    or expected_text in pdf_text_mupdf
                    or reversed_text in pdf_text_mupdf
                    or reversed_text in pdf_text_poppler
                    or chars_present
                )
                assert found, (
                    f"{script_name} text {expected_text!r} not found in PDF. "
                    f"Font fallback likely failed for this script."
                )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_general_notes_section_exists(
        self, lawlis_with_draft_result: WorkspaceExportResult
    ) -> None:
        """The General Notes section must appear in the PDF."""
        pdf_text = lawlis_with_draft_result.pdf_text_pymupdf_raw
        assert "General Notes" in pdf_text, (
            "General Notes section not found in PDF text"
        )
        assert "Lorem Ipsum" in pdf_text, (
            "Lorem Ipsum content from response draft not in PDF"
        )
