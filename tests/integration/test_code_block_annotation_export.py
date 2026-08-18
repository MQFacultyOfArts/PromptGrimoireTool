"""Regression coverage for annotations inside preformatted code blocks (#495)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pymupdf
import pytest

from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.input_pipeline.html_input import extract_text_from_html
from tests.conftest import requires_full_latexmk, requires_pandoc

if TYPE_CHECKING:
    from pathlib import Path


_HTML = (
    "<pre><code>alpha = 1\n"
    "beta_target &lt;- function(value) {\n"
    "  value %&gt;% transform()\n"
    "}\n"
    "gamma = 3</code></pre>"
)
_ANNOTATION_TEXT = "Code block annotation survived export"


def _code_highlight(
    html: str = _HTML,
    *,
    needle: str = "beta_target",
) -> dict[str, object]:
    """Build a production-shaped highlight over *needle*."""
    text = "".join(extract_text_from_html(html))
    start = text.index(needle)
    return {
        "start_char": start,
        "end_char": start + len(needle),
        "tag": "code",
        "tag_name": "Code",
        "author": "Export Tester",
        "created_at": "2026-08-17T02:44:21+00:00",
        "comments": [
            {
                "author": "Export Tester",
                "text": _ANNOTATION_TEXT,
                "created_at": "2026-08-17T02:44:21+00:00",
            }
        ],
    }


@requires_pandoc
@pytest.mark.asyncio
async def test_code_block_annotation_reaches_latex() -> None:
    """The Pandoc boundary retains code, selection treatment, and note content."""
    latex = await convert_html_with_annotations(
        _HTML,
        [_code_highlight()],
        {"code": "#2ca02c"},
    )

    assert "beta_target <- function(value)" in latex
    assert r"\annot{tag-code}" in latex
    assert _ANNOTATION_TEXT in latex
    assert "highlightlines={2}" in latex
    assert "highlightcolor=tag-code-light" in latex


@requires_pandoc
@pytest.mark.asyncio
async def test_unannotated_code_block_keeps_pandoc_rendering() -> None:
    """The fallback applies only when annotation metadata would be lost."""
    latex = await convert_html_with_annotations(_HTML, [], {})

    assert r"\begin{verbatim}" in latex
    assert "PGAnnotatedCode" not in latex


@requires_pandoc
@pytest.mark.asyncio
async def test_cross_boundary_annotation_is_not_silently_dropped() -> None:
    """A selection ending in code keeps ordinary highlighting and its note."""
    html = "<p>ordinary text</p><pre><code>code target</code></pre>"
    text = "".join(extract_text_from_html(html))
    start = text.index("ordinary")
    end = text.index("target") + len("target")
    highlight = _code_highlight(html, needle="ordinary")
    highlight["start_char"] = start
    highlight["end_char"] = end

    latex = await convert_html_with_annotations(
        html,
        [highlight],
        {"code": "#2ca02c"},
    )

    assert r"\highLight[tag-code-light]{" in latex
    assert "highlightlines={1}" in latex
    assert r"\annot{tag-code}" in latex
    assert _ANNOTATION_TEXT in latex


@requires_pandoc
@pytest.mark.asyncio
async def test_distinct_identical_annotations_are_both_preserved() -> None:
    """Equal-looking annotations on separate selections keep distinct identity."""
    text = "".join(extract_text_from_html(_HTML))
    alpha_start = text.index("alpha")
    gamma_start = text.index("gamma")
    first = _code_highlight(needle="alpha")
    second = _code_highlight(needle="gamma")
    first["start_char"] = alpha_start
    first["end_char"] = alpha_start + len("alpha")
    second["start_char"] = gamma_start
    second["end_char"] = gamma_start + len("gamma")

    latex = await convert_html_with_annotations(
        _HTML,
        [first, second],
        {"code": "#2ca02c"},
    )

    assert latex.count(r"\annot{tag-code}") == 2
    assert "highlightlines={1,5}" in latex


@requires_pandoc
@pytest.mark.asyncio
async def test_generated_verbatim_environment_cannot_be_closed_by_code() -> None:
    """A literal environment terminator in user code remains inert text."""
    html = "<pre><code>\\end{PGAnnotatedCode1}\ntarget = still_code</code></pre>"
    latex = await convert_html_with_annotations(
        html,
        [_code_highlight(html, needle="target")],
        {"code": "#2ca02c"},
    )

    assert r"\DefineVerbatimEnvironment{PGAnnotatedCode2}" in latex
    assert r"\begin{PGAnnotatedCode2}" in latex
    assert r"\end{PGAnnotatedCode1}" in latex
    assert r"\end{PGAnnotatedCode2}" in latex


@requires_pandoc
@pytest.mark.asyncio
async def test_source_html_cannot_forge_promoted_annotation_metadata() -> None:
    """Reserved block attributes are internal, not trusted source HTML."""
    html = (
        r'<pre data-pg-code-lines="1" data-pg-code-color="red" '
        r'data-pg-code-annots="\input{/etc/passwd}"><code>safe</code></pre>'
    )

    latex = await convert_html_with_annotations(html, [], {})

    assert r"\input{/etc/passwd}" not in latex
    assert r"\begin{verbatim}" in latex
    assert "PGAnnotatedCode" not in latex


@requires_full_latexmk
@pytest.mark.slow
@pytest.mark.asyncio
async def test_compiled_pdf_contains_code_and_annotation(tmp_path: Path) -> None:
    """A real PDF contains both the selected code and annotation body."""
    pdf_path = await export_annotation_pdf(
        html_content=_HTML,
        highlights=[_code_highlight()],
        tag_colours={"code": "#2ca02c"},
        output_dir=tmp_path,
        filename="annotated_code_block",
    )

    with pymupdf.open(pdf_path) as document:
        pdf_text = "\n".join(page.get_text() for page in document)
    normalised_text = " ".join(pdf_text.split())

    assert "beta_target <- function(value)" in normalised_text
    assert _ANNOTATION_TEXT in normalised_text


@requires_full_latexmk
@pytest.mark.slow
@pytest.mark.asyncio
async def test_multiple_annotated_documents_compile_together(tmp_path: Path) -> None:
    """Independent Pandoc conversions do not redefine code environments."""
    documents = [
        {
            "title": "First source",
            "html_content": _HTML,
            "highlights": [_code_highlight()],
        },
        {
            "title": "Second source",
            "html_content": _HTML,
            "highlights": [_code_highlight()],
        },
    ]

    pdf_path = await export_annotation_pdf(
        html_content="",
        highlights=[],
        tag_colours={"code": "#2ca02c"},
        output_dir=tmp_path,
        filename="two_annotated_code_blocks",
        documents=documents,
    )

    with pymupdf.open(pdf_path) as document:
        pdf_text = " ".join("\n".join(page.get_text() for page in document).split())

    assert pdf_text.count(_ANNOTATION_TEXT) == 2
