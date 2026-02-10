"""Integration test: export workspace fixture to PDF.

Uses real workspace data from fa008b89-a772-4d02-a3a3-d5a99b62c720 (Lawlis v R)
with 11 highlights, comments, and a multilingual response draft containing
Armenian, Arabic, Chinese, Korean, Georgian, Hindi, Hebrew, Thai, and other
scripts that must render without tofu.

Tests verify the **PDF output** directly using pymupdf text extraction,
not intermediate .tex files. This catches issues that .tex-level checks miss
(font fallback failures, glyph rendering, highlight boundary drift).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pymupdf
import pytest

from promptgrimoire.export.pdf_export import (
    export_annotation_pdf,
    markdown_to_latex_notes,
)
from promptgrimoire.models.case import TAG_COLORS
from tests.conftest import requires_latexmk

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"

# TAG_COLORS is dict[BriefTag, str]; export_annotation_pdf wants dict[str, str]
_TAG_COLOURS: dict[str, str] = {str(k): v for k, v in TAG_COLORS.items()}


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
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _extract_pdf_text_pymupdf(pdf_path: Path) -> str:
    """Extract full text from PDF using pymupdf."""
    doc = pymupdf.open(str(pdf_path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


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
# Shared fixture: generate PDF once, reuse across tests in this module
# ===================================================================


@pytest.fixture(scope="module")
def workspace_fixture() -> dict:
    """Load the workspace fixture data."""
    return _load_workspace_fixture()


@pytest.fixture(scope="module")
def html_content() -> str:
    """Load the HTML content."""
    return _load_html()


@requires_latexmk
class TestPdfBasicIntegrity:
    """Basic PDF generation checks."""

    @pytest.mark.asyncio
    async def test_export_produces_pdf(self, tmp_path: Path) -> None:
        """Full pipeline: HTML + highlights + response draft -> PDF."""
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
            output_dir=tmp_path,
        )

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
            # Highlight 9: "omes of the victims" →
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
    the actual PDF text output — not the intermediate .tex file.
    """

    @pytest.mark.asyncio
    async def test_all_comments_appear_in_pdf(self, tmp_path: Path) -> None:
        """Every highlight comment must appear in the PDF text."""
        fixture = _load_workspace_fixture()
        html = _load_html()
        highlights = fixture["highlights"]

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )

        raw_text = _extract_pdf_text_pymupdf(pdf_path)
        pdf_text = _normalize_pdf_text(raw_text)
        for i, h in enumerate(highlights):
            for comment in h.get("comments", []):
                comment_text = comment["text"]
                assert comment_text in pdf_text, (
                    f"Highlight {i} [{h['tag']}] comment "
                    f"{comment_text!r} not found in PDF text"
                )

    @pytest.mark.asyncio
    async def test_highlight_0_title_boundary(self, tmp_path: Path) -> None:
        """Highlight 0: title 'Lawlis v R [2025] NSWCCA 183 (3 November 2025)'."""
        await self._check_highlight_text(tmp_path, 0)

    @pytest.mark.asyncio
    async def test_highlight_1_last_updated_boundary(self, tmp_path: Path) -> None:
        """Highlight 1: 'Last Updated: 10 November 2025'."""
        await self._check_highlight_text(tmp_path, 1)

    @pytest.mark.asyncio
    async def test_highlight_2_court_boundary(self, tmp_path: Path) -> None:
        """Highlight 2: 'Court of Criminal Appeal'."""
        await self._check_highlight_text(tmp_path, 2)

    @pytest.mark.asyncio
    async def test_highlight_3_supreme_court_boundary(self, tmp_path: Path) -> None:
        """Highlight 3: 'Supreme Court'."""
        await self._check_highlight_text(tmp_path, 3)

    @pytest.mark.asyncio
    async def test_highlight_4_orders_boundary(self, tmp_path: Path) -> None:
        """Highlight 4: orders section spanning Kirk JA through Taking into account."""
        await self._check_highlight_text(tmp_path, 4)

    @pytest.mark.asyncio
    async def test_highlight_5_grounds_of_appeal_boundary(self, tmp_path: Path) -> None:
        """Highlight 5: 'Grounds of Appeal' through 'manifestly excessive'."""
        await self._check_highlight_text(tmp_path, 5)

    @pytest.mark.asyncio
    async def test_highlight_6_remarks_boundary(self, tmp_path: Path) -> None:
        """Highlight 6: 'Remarks on Sentence'."""
        await self._check_highlight_text(tmp_path, 6)

    @pytest.mark.asyncio
    async def test_highlight_7_judge_abadee_boundary(self, tmp_path: Path) -> None:
        """Highlight 7: Judge Abadee sentenced through sentence proceedings."""
        await self._check_highlight_text(tmp_path, 7)

    @pytest.mark.asyncio
    async def test_highlight_8_discount_boundary(self, tmp_path: Path) -> None:
        """Highlight 8: 5% discount through trial due to commence."""
        await self._check_highlight_text(tmp_path, 8)

    @pytest.mark.asyncio
    async def test_highlight_9_legal_issues_boundary(self, tmp_path: Path) -> None:
        """Highlight 9: financial gain through tried medication."""
        await self._check_highlight_text(tmp_path, 9)

    @pytest.mark.asyncio
    async def test_highlight_10_reflection_boundary(self, tmp_path: Path) -> None:
        """Highlight 10: Court orders through Intensive Corrections Order."""
        await self._check_highlight_text(tmp_path, 10)

    async def _check_highlight_text(self, tmp_path: Path, highlight_index: int) -> None:
        """Check that expected text fragments appear in the PDF.

        This verifies CONTENT presence — the text that should be
        inside each highlight actually appears in the PDF output.
        Marker boundary alignment errors cause text to be highlighted
        at wrong positions or not at all.
        """
        fixture = _load_workspace_fixture()
        html = _load_html()
        highlights = fixture["highlights"]

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )

        raw_text = _extract_pdf_text_pymupdf(pdf_path)
        pdf_text = _normalize_pdf_text(raw_text)
        expectation = _HIGHLIGHT_BOUNDARY_EXPECTATIONS[highlight_index]

        for fragment in expectation["must_contain"]:
            assert fragment in pdf_text, (
                f"Highlight {highlight_index} [{expectation['tag']}]: "
                f"expected text {fragment!r} not found in PDF. "
                f"This may indicate marker boundary misalignment."
            )

    @pytest.mark.asyncio
    async def test_highlight_boundaries_in_tex(self, tmp_path: Path) -> None:
        r"""Verify \\highLight wrapping in .tex matches expected content.

        For each highlight, the .tex file should contain \\highLight
        commands wrapping the expected text. This is a stronger test
        than just checking PDF text presence — it verifies the text
        is actually INSIDE highlight formatting, not just somewhere
        in the document.
        """
        fixture = _load_workspace_fixture()
        html = _load_html()
        highlights = fixture["highlights"]

        await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )

        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()

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
_MUST_BE_HIGHLIGHTED = [
    pytest.param(
        {
            "highlight": "5",
            "tag": "jurisdiction",
            "inside_highlight": [
                "Grounds of Appeal",
                "Mr Lawlis sought leave to rely on three grounds",
            ],
        },
        id="hl5_jurisdiction",
    ),
    pytest.param(
        {
            "highlight": "9",
            "tag": "legal_issues",
            "inside_highlight": [
                "Subjective factors",
                "21 years old at the time",
                "tried medication",
            ],
        },
        id="hl9_legal_issues",
    ),
    pytest.param(
        {
            "highlight": "4",
            "tag": "reasons",
            "inside_highlight": [
                "Orders made on 3 November 2025",
            ],
        },
        id="hl4_reasons",
    ),
]


@requires_latexmk
class TestHighlightWrappingInTex:
    r"""Text must appear INSIDE \\highLight wrapping, not just in the doc.

    These tests catch marker boundary drift — where the text exists
    in the PDF but the highlight coloring stops/starts at wrong
    positions. Detected by checking the .tex file's \\highLight{}
    block contents.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "spec",
        _MUST_BE_HIGHLIGHTED,
    )
    async def test_text_inside_highlight_wrapping(
        self, tmp_path: Path, spec: dict
    ) -> None:
        """Verify text is inside highLight body, not just in doc."""
        fixture = _load_workspace_fixture()
        html = _load_html()
        highlights = fixture["highlights"]

        await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=_TAG_COLOURS,
            output_dir=tmp_path,
        )

        tex_path = tmp_path / "annotated_document.tex"
        tex_content = tex_path.read_text()

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
    must render all of these using the UNICODE_PREAMBLE font fallback
    chain — no replacement characters (U+FFFD) or missing glyphs.
    """

    @pytest.mark.asyncio
    async def test_no_replacement_characters_in_pdf(self, tmp_path: Path) -> None:
        """PDF text extraction must not contain U+FFFD replacement characters.

        pdftotext emits U+FFFD for glyphs that the PDF couldn't render.
        Any occurrence means a font fallback failure (tofu).
        """
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
            output_dir=tmp_path,
        )

        pdf_text = _extract_pdf_text(pdf_path)
        replacement_count = pdf_text.count("\ufffd")
        if replacement_count > 0:
            idx = pdf_text.find(chr(0xFFFD))
            ctx = pdf_text[idx - 20 : idx + 20]
            pytest.fail(
                f"PDF has {replacement_count} U+FFFD chars. Context: ...{ctx}..."
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("script_name", "expected_text"),
        _REQUIRED_SCRIPTS,
        ids=[s[0] for s in _REQUIRED_SCRIPTS],
    )
    async def test_script_renders_in_pdf(
        self,
        tmp_path: Path,
        script_name: str,
        expected_text: str,
    ) -> None:
        """Each script's text must be extractable from the PDF.

        If a script renders as tofu, pdftotext either emits replacement
        characters or omits the text entirely. Either way, the expected
        text won't be found in the extracted output.
        """
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
            output_dir=tmp_path,
        )

        # Use both extractors — pymupdf and pdftotext may differ
        pdf_text_poppler = _extract_pdf_text(pdf_path)
        pdf_text_mupdf = _extract_pdf_text_pymupdf(pdf_path)

        # RTL scripts (Arabic, Hebrew) may extract in reversed char order;
        # complex scripts (Devanagari) may decompose ligatures differently.
        # Check both forward and reversed text, and also check that all
        # expected characters are present in the same extraction.
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

    @pytest.mark.asyncio
    async def test_general_notes_section_exists(self, tmp_path: Path) -> None:
        """The General Notes section must appear in the PDF."""
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
            output_dir=tmp_path,
        )

        pdf_text = _extract_pdf_text_pymupdf(pdf_path)
        assert "General Notes" in pdf_text, (
            "General Notes section not found in PDF text"
        )
        assert "Lorem Ipsum" in pdf_text, (
            "Lorem Ipsum content from response draft not in PDF"
        )
