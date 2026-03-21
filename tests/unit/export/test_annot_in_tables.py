"""Tests for \\annot splitting in longtable environments (#351).

Verifies that \\annot{} commands inside table cells are split into
\\annotref{} (inline) + \\annotendnote{} (after table), preventing
the CJK + annotated table crash.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from promptgrimoire.export.pandoc import convert_html_to_latex
from tests.conftest import requires_pandoc

FILTERS_DIR = (
    Path(__file__).parents[3] / "src" / "promptgrimoire" / "export" / "filters"
)
HIGHLIGHT_FILTER = FILTERS_DIR / "highlight.lua"
LIBREOFFICE_FILTER = FILTERS_DIR / "libreoffice.lua"
BOTH_FILTERS = [HIGHLIGHT_FILTER, LIBREOFFICE_FILTER]

FIXTURE = Path(__file__).parents[2] / "fixtures" / "workspace_cjk_annotated_table.html"


def _load_fixture() -> str:
    return FIXTURE.read_text()


def _extract_longtable_regions(tex: str) -> list[str]:
    """Extract all \\begin{longtable}...\\end{longtable} regions."""
    return re.findall(
        r"\\begin\{longtable\}.*?\\end\{longtable\}",
        tex,
        re.DOTALL,
    )


class TestAnnotNotInLongtable:
    """AC4.1: No \\annot{} inside longtable environments."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_no_annot_inside_longtable(self) -> None:
        """\\annot{ must not appear between longtable delimiters."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        regions = _extract_longtable_regions(result)
        assert len(regions) >= 1, "Expected at least one longtable"
        for region in regions:
            assert "\\annot{" not in region

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_annotref_inside_longtable(self) -> None:
        """\\annotref{ appears inside the longtable (inline refs)."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        regions = _extract_longtable_regions(result)
        assert len(regions) >= 1
        # At least one region contains \annotref
        combined = "".join(regions)
        assert "\\annotref{" in combined

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_annotendnote_after_longtable(self) -> None:
        """\\annotendnote{ appears after \\end{longtable}."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        end_pos = result.rfind("\\end{longtable}")
        assert end_pos != -1
        after_table = result[end_pos:]
        assert "\\annotendnote{" in after_table

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_nontable_annot_unchanged(self) -> None:
        """Non-table annotations still use \\annot{}."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        # The fixture has a non-table annotation after the table
        end_pos = result.rfind("\\end{longtable}")
        assert end_pos != -1
        after_endnotes = result[end_pos:]
        assert "\\annot{" in after_endnotes


class TestAnnotSequentialNumbering:
    """AC2.3/AC2.4: Sequential numbering across table and non-table."""

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_two_annotref_in_table(self) -> None:
        """AC2.4: Two annotated cells produce two \\annotref."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        regions = _extract_longtable_regions(result)
        combined = "".join(regions)
        count = combined.count("\\annotref{")
        assert count == 2, f"Expected 2 \\annotref, got {count}"

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_two_annotendnote_after_table(self) -> None:
        """AC2.4: Two deferred endnotes appear after the table."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        end_pos = result.rfind("\\end{longtable}")
        after = result[end_pos:]
        count = after.count("\\annotendnote{")
        assert count == 2, f"Expected 2 \\annotendnote, got {count}"

    @requires_pandoc
    @pytest.mark.asyncio
    async def test_sequential_counter_values(self) -> None:
        """AC2.3: Annotation numbers are sequential (1, 2, 3)."""
        html = _load_fixture()
        result = await convert_html_to_latex(
            html,
            filter_paths=BOTH_FILTERS,
        )

        # The fixture has 3 annotations:
        # 2 in-table (\annotref + \annotendnote) + 1 non-table (\annot)
        # The \textbf{N.} numbers in content are the user-visible
        # annotation sequence. Verify they appear in order 1, 2, 3.
        annot_numbers = re.findall(
            r"\\textbf\{(\d+)\.\}",
            result,
        )
        assert annot_numbers == ["1", "2", "3"], (
            f"Expected sequential [1,2,3], got {annot_numbers}"
        )

        # Verify endnote counter arithmetic is consistent:
        # \annotendnote{colour}{\the\numexpr\value{annotnum}-N+K\relax}
        # N = total deferred count, K = 1-based index within deferred
        endnote_counters = re.findall(
            r"\\the\\numexpr\\value\{annotnum\}-(\d+)\+(\d+)",
            result,
        )
        assert len(endnote_counters) == 2
        # Both should reference the same total (2 deferred)
        totals = [int(n) for n, _ in endnote_counters]
        assert totals == [2, 2]
        # Indices should be sequential (1, 2)
        indices = [int(k) for _, k in endnote_counters]
        assert indices == [1, 2]
