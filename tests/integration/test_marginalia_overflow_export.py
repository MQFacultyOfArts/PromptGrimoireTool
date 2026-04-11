"""Integration test: marginalia overflow produces all annotations in PDF.

Uses the "Dog's Breakfast" workspace fixture (23 highlights on a short
document) which overflows the margin column.  The current workaround
(PR #477) detects overflow and recompiles with ALL annotations as
endnotes.  The xfail test marks the desired behaviour: per-page
selective routing where margin-fit annotations stay in the margin.

See: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/478
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import pytest_asyncio

from promptgrimoire.export.pdf_export import export_annotation_pdf
from tests.conftest import requires_full_latexmk
from tests.integration.conftest import extract_pdf_text_pymupdf

# Smart quote → ASCII mapping for PDF text comparison.
_QUOTE_TABLE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


def _normalize_for_pdf(text: str) -> str:
    """Collapse whitespace and normalise smart quotes for PDF matching."""
    return re.sub(r"\s+", " ", text).translate(_QUOTE_TABLE)


FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "workspace_dogs_breakfast_overflow.json"
)


def _load_fixture() -> dict:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def overflow_result(tmp_path_factory):
    """Compile the overflow fixture once for all tests in this module."""
    output_dir = tmp_path_factory.mktemp("dogs_breakfast")
    fixture = _load_fixture()

    pdf_path = await export_annotation_pdf(
        html_content=fixture["html_content"],
        highlights=fixture["highlights"],
        tag_colours=fixture["tag_colours"],
        output_dir=output_dir,
    )

    tex_path = output_dir / "annotated_document.tex"
    tex_content = tex_path.read_text()
    pdf_text = extract_pdf_text_pymupdf(pdf_path)

    return {
        "pdf_path": pdf_path,
        "tex_path": tex_path,
        "tex_content": tex_content,
        "pdf_text": pdf_text,
        "output_dir": output_dir,
        "fixture": fixture,
    }


@requires_full_latexmk
class TestOverflowAllAnnotationsPresent:
    """All 23 annotations must appear in the PDF output."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_pdf_is_produced(self, overflow_result) -> None:
        """Export must succeed (not crash) despite overflow."""
        pdf_path = overflow_result["pdf_path"]
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000

    @pytest.mark.asyncio(loop_scope="module")
    async def test_all_annotation_numbers_present(self, overflow_result) -> None:
        """Every annotation number (1-23) must appear in the PDF text."""
        pdf_text = overflow_result["pdf_text"]
        fixture = overflow_result["fixture"]
        n_highlights = len(fixture["highlights"])

        for i in range(1, n_highlights + 1):
            assert str(i) in pdf_text, (
                f"Annotation {i} not found in PDF text — "
                f"likely clipped by margin overflow"
            )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_all_comments_present(self, overflow_result, subtests) -> None:
        """Every annotation comment text must appear in the PDF."""
        pdf_norm = _normalize_for_pdf(overflow_result["pdf_text"])
        fixture = overflow_result["fixture"]

        for i, h in enumerate(fixture["highlights"]):
            for comment in h.get("comments", []):
                text = comment.get("text", "")
                if text:
                    text_norm = _normalize_for_pdf(text)
                    with subtests.test(msg=f"hl-{i}-comment"):
                        assert text_norm in pdf_norm, (
                            f"Highlight {i} comment {text!r} not found in PDF"
                        )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_endnotes_section_present(self, overflow_result) -> None:
        """The endnotes section must exist (overflow fallback)."""
        pdf_text = overflow_result["pdf_text"]
        assert "Annotations" in pdf_text, (
            "Annotations endnotes section not found — "
            "overflow fallback may not have triggered"
        )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_force_endnotes_flag_injected(self, overflow_result) -> None:
        r"""The recompiled .tex must contain \annotforceendnotestrue."""
        tex = overflow_result["tex_content"]
        assert r"\annotforceendnotestrue" in tex, (
            "Force-endnotes flag not found — "
            "marginalia overflow detection may have failed"
        )


@requires_full_latexmk
class TestSelectiveOverflowRouting:
    """Desired behaviour: only overflow annotations go to endnotes.

    These tests are xfail until #478 implements per-page density
    routing.  Currently ALL annotations go to endnotes on overflow.
    """

    @pytest.mark.xfail(
        reason="PR #477 sends ALL to endnotes; #478 will route selectively",
        strict=True,
    )
    @pytest.mark.asyncio(loop_scope="module")
    async def test_some_annotations_remain_in_margin(self, overflow_result) -> None:
        r"""At least some annotations should stay in the margin.

        The current workaround routes ALL to endnotes.  A smarter
        implementation would keep annotations that fit in the margin
        and only overflow the excess.  Detected by checking for
        \marginalia commands in the final .tex (force-endnotes mode
        skips all \marginalia calls).
        """
        tex = overflow_result["tex_content"]
        # In force-endnotes mode, \annot never calls \marginalia.
        # If selective routing works, some \marginalia calls should
        # still appear in the compiled output.
        assert r"\annotforceendnotestrue" not in tex, (
            "All annotations sent to endnotes — "
            "selective routing not yet implemented (#478)"
        )
