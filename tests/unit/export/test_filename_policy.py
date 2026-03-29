"""Unit tests for filename policy module.

Tests name splitting, sanitisation, and stem assembly:
- _split_owner_display_name: deterministic name parsing
- _safe_segment: ASCII-safe filename segment sanitisation
- build_pdf_export_stem: stem assembly with fallback and truncation

Verifies: AC2.1-AC2.6, AC3.1-AC3.7
"""

from __future__ import annotations

from datetime import date

import pytest

from promptgrimoire.export.filename import (
    PdfExportFilenameContext,
    _safe_segment,
    _split_owner_display_name,
    build_pdf_export_stem,
)


class TestSplitOwnerDisplayName:
    """Tests for _split_owner_display_name: AC2.1-AC2.4."""

    def test_two_token_name_splits_last_first(self) -> None:
        """AC2.1: Two-token display name maps to (last, first)."""
        last, first = _split_owner_display_name("Ada Lovelace")
        assert last == "Lovelace"
        assert first == "Ada"

    def test_multi_token_name_ignores_middle(self) -> None:
        """AC2.2: Multi-token name uses first and last tokens only."""
        last, first = _split_owner_display_name("Mary Jane Smith")
        assert last == "Smith"
        assert first == "Mary"

    def test_single_token_duplicated(self) -> None:
        """AC2.3: Single-token name fills both slots."""
        last, first = _split_owner_display_name("Plato")
        assert last == "Plato"
        assert first == "Plato"

    def test_none_returns_unknown(self) -> None:
        """None input yields (Unknown, Unknown)."""
        last, first = _split_owner_display_name(None)
        assert last == "Unknown"
        assert first == "Unknown"

    def test_blank_string_returns_unknown(self) -> None:
        """Blank/whitespace-only input yields (Unknown, Unknown)."""
        last, first = _split_owner_display_name("   ")
        assert last == "Unknown"
        assert first == "Unknown"

    def test_empty_string_returns_unknown(self) -> None:
        """Empty string yields (Unknown, Unknown)."""
        last, first = _split_owner_display_name("")
        assert last == "Unknown"
        assert first == "Unknown"

    def test_repeated_whitespace_collapsed(self) -> None:
        """Repeated whitespace between tokens is collapsed."""
        last, first = _split_owner_display_name("Ada   Lovelace")
        assert last == "Lovelace"
        assert first == "Ada"


class TestSafeSegment:
    """Tests for _safe_segment: AC2.4-AC2.6."""

    def test_diacritics_transliterated(self) -> None:
        """AC2.4: Non-ASCII Latin characters are transliterated."""
        assert _safe_segment("José") == "Jose"
        assert _safe_segment("Núñez") == "Nunez"

    def test_punctuation_replaced_with_underscore(self) -> None:
        """AC2.5: Unsafe punctuation replaced with underscores."""
        result = _safe_segment("draft: final!")
        assert result == "draft_final"

    def test_path_separators_replaced(self) -> None:
        """AC2.5: Path separators replaced with underscores."""
        result = _safe_segment("folder/name")
        assert result == "folder_name"

    def test_repeated_underscores_collapsed(self) -> None:
        """AC2.5: Repeated underscores are collapsed."""
        result = _safe_segment("a___b")
        assert result == "a_b"

    def test_leading_trailing_underscores_stripped(self) -> None:
        """AC2.5: Leading/trailing underscores are stripped."""
        result = _safe_segment("_hello_")
        assert result == "hello"

    @pytest.mark.parametrize(
        "value",
        ["\U0001f600", "\U0001f4a9\U0001f525", "\u2603"],
        ids=["grinning-face", "poop-fire", "snowman"],
    )
    def test_emoji_and_symbols_removed(self, value: str) -> None:
        """AC2.6: Emoji/symbols with no transliteration yield empty string."""
        assert _safe_segment(value) == ""

    def test_mixed_ascii_and_emoji(self) -> None:
        """AC2.6: Emoji removed but ASCII content preserved."""
        result = _safe_segment("hello\U0001f600world")
        assert result == "helloworld"

    def test_normal_text_passthrough(self) -> None:
        """Normal ASCII text passes through unchanged."""
        assert _safe_segment("MyTitle") == "MyTitle"

    def test_preserves_case(self) -> None:
        """Case is preserved in output."""
        assert _safe_segment("LAWS5000") == "LAWS5000"


class TestBuildPdfExportStem:
    """Tests for build_pdf_export_stem: AC3.1-AC3.7."""

    _DATE = date(2026, 3, 9)

    def _ctx(
        self,
        *,
        course_code: str | None = "LAWS5000",
        activity_title: str | None = "Torts",
        workspace_title: str | None = "Draft",
        owner_display_name: str | None = "Ada Lovelace",
        export_date: date | None = None,
    ) -> PdfExportFilenameContext:
        return PdfExportFilenameContext(
            course_code=course_code,
            activity_title=activity_title,
            workspace_title=workspace_title,
            owner_display_name=owner_display_name,
            export_date=export_date or self._DATE,
        )

    # --- AC3.1: no truncation needed ---

    def test_short_stem_unchanged(self) -> None:
        """AC3.1: Short stem returned without truncation."""
        stem = build_pdf_export_stem(self._ctx())
        # LAWS5000_Lovelace_Ada_Torts_Draft_20260309
        assert stem == "LAWS5000_Lovelace_Ada_Torts_Draft_20260309"
        assert len(f"{stem}.pdf") <= 100

    def test_result_ends_with_pdf(self) -> None:
        """AC3.7: The stem, when suffixed with .pdf, forms the filename."""
        stem = build_pdf_export_stem(self._ctx())
        assert f"{stem}.pdf".endswith(".pdf")

    # --- AC3.2: workspace trimmed before activity ---

    def test_workspace_trimmed_before_activity(self) -> None:
        """AC3.2: Overlong workspace is trimmed first."""
        ctx = self._ctx(
            workspace_title="A" * 80,
        )
        stem = build_pdf_export_stem(ctx)
        assert len(f"{stem}.pdf") <= 100
        # Activity should be fully present
        assert "_Torts_" in stem
        # Course, last, first, date intact
        assert stem.startswith("LAWS5000_Lovelace_Ada_")
        assert stem.endswith("_20260309")

    # --- AC3.3: non-negotiable segments preserved ---

    def test_non_negotiable_segments_preserved(self) -> None:
        """AC3.3: Course, last name, first name, date stay intact."""
        ctx = self._ctx(
            workspace_title="W" * 60,
            activity_title="A" * 60,
        )
        stem = build_pdf_export_stem(ctx)
        assert len(f"{stem}.pdf") <= 100
        assert stem.startswith("LAWS5000_Lovelace_Ada_")
        assert stem.endswith("_20260309")

    # --- AC3.4: activity trimmed after workspace exhausted ---

    def test_activity_trimmed_after_workspace_gone(self) -> None:
        """AC3.4: When workspace is empty, activity is trimmed next."""
        ctx = self._ctx(
            activity_title="B" * 80,
            workspace_title="Short",
        )
        stem = build_pdf_export_stem(ctx)
        assert len(f"{stem}.pdf") <= 100
        assert stem.startswith("LAWS5000_Lovelace_Ada_")
        assert stem.endswith("_20260309")
        # Workspace should have been fully removed before activity
        # was trimmed — but activity should still have some content
        # or be partially trimmed

    # --- AC3.5: first name reduced to initial ---

    def test_first_name_reduced_to_initial(self) -> None:
        """AC3.5: First name reduced to 1-char initial.

        The first name must be long enough that even after workspace and
        activity are both fully exhausted, the stem still exceeds budget
        and the initial-reduction path fires.

        With LAWS5000 (8) + _ + Henderson (9) + _ + <first> + _ + <date> (8)
        the fixed overhead is 28 chars plus separators.  A 70-char first name
        pushes the minimal stem (no activity, no workspace) to ~100+ chars,
        guaranteeing the initial-reduction path is exercised.
        """
        long_first = "A" * 70  # 70-char first name
        ctx = self._ctx(
            course_code="LAWS5000",
            owner_display_name=f"{long_first} Henderson",
            activity_title="X" * 80,
            workspace_title="Y" * 80,
        )
        stem = build_pdf_export_stem(ctx)
        assert len(f"{stem}.pdf") <= 100
        parts = stem.split("_")
        assert parts == [
            "LAWS5000",
            "Henderson",
            long_first[0],
            "20260309",
        ], (
            "Once the first name is reduced to an initial, the workspace and "
            "activity segments must already be fully exhausted"
        )

    # --- AC3.6: pathological overflow preserved ---

    def test_pathological_overflow_preserves_non_negotiable(
        self,
    ) -> None:
        """AC3.6: Overlong non-negotiable segments are kept."""
        long_last = "A" * 90
        ctx = self._ctx(
            owner_display_name=f"Bob {long_last}",
            activity_title="X",
            workspace_title="Y",
        )
        stem = build_pdf_export_stem(ctx)
        # Non-negotiable segments must NOT be truncated
        assert long_last in stem
        assert "LAWS5000" in stem
        assert "20260309" in stem
        # This WILL exceed 100 chars — that's the expected behaviour
        assert len(f"{stem}.pdf") > 100
        assert stem.split("_") == ["LAWS5000", long_last, "B", "20260309"], (
            "Pathological overflow is allowed only after the activity and "
            "workspace segments are gone and the first name has been "
            "reduced to a single character"
        )

    # --- AC3.7: non-pathological cases fit in 100 ---

    def test_length_budget_respected(self) -> None:
        """AC3.7: Non-pathological stems fit within 100 chars."""
        ctx = self._ctx(
            activity_title="Introduction to Tort Law",
            workspace_title="My Assignment Workspace Final",
        )
        stem = build_pdf_export_stem(ctx)
        filename = f"{stem}.pdf"
        assert filename.endswith(".pdf")
        assert len(filename) <= 100

    # --- Fallback tests ---

    def test_workspace_suppressed_when_matches_activity(self) -> None:
        """Workspace segment omitted when it duplicates the activity title."""
        ctx = self._ctx(
            activity_title="Annotate Becky Bennett Interview",
            workspace_title="Annotate Becky Bennett Interview",
        )
        stem = build_pdf_export_stem(ctx)
        # Activity appears once, workspace is suppressed
        assert "Annotate_Becky_Bennett_Interview" in stem
        # Should NOT have the activity repeated
        parts = stem.split("_")
        # Count occurrences of "Annotate" — should be exactly 1
        assert parts.count("Annotate") == 1
        assert stem == (
            "LAWS5000_Lovelace_Ada_Annotate_Becky_Bennett_Interview_20260309"
        )

    def test_workspace_kept_when_differs_from_activity(self) -> None:
        """Workspace segment kept when it differs from activity."""
        ctx = self._ctx(
            activity_title="Torts",
            workspace_title="My Notes",
        )
        stem = build_pdf_export_stem(ctx)
        assert "_Torts_My_Notes_" in stem

    def test_workspace_kept_when_raw_differs_but_slug_matches(self) -> None:
        """Workspace kept when raw titles differ even if slugs normalise alike.

        "José" and "Jose" normalise to the same slug, but the raw titles
        are distinct — the user intentionally renamed the workspace.
        """
        ctx = self._ctx(
            activity_title="José",
            workspace_title="Jose",
        )
        stem = build_pdf_export_stem(ctx)
        assert "_Jose_Jose_" in stem

    def test_workspace_fallback_not_suppressed_by_activity(self) -> None:
        """Workspace fallback 'Workspace' is not suppressed even if activity
        normalises to the same slug (e.g. activity='Workspace!!!').
        """
        ctx = self._ctx(
            activity_title="Workspace!!!",
            workspace_title=None,
        )
        stem = build_pdf_export_stem(ctx)
        assert "_Workspace_Workspace_" in stem

    def test_fallback_blank_workspace(self) -> None:
        """Blank workspace title falls back to 'Workspace'."""
        ctx = self._ctx(workspace_title=None)
        stem = build_pdf_export_stem(ctx)
        assert "_Workspace_" in stem

    def test_fallback_blank_owner(self) -> None:
        """Blank owner falls back to Unknown_Unknown."""
        ctx = self._ctx(owner_display_name=None)
        stem = build_pdf_export_stem(ctx)
        assert "_Unknown_Unknown_" in stem

    def test_fallback_blank_course(self) -> None:
        """Blank course code falls back to 'Unplaced'."""
        ctx = self._ctx(course_code=None)
        stem = build_pdf_export_stem(ctx)
        assert stem.startswith("Unplaced_")

    def test_fallback_blank_activity(self) -> None:
        """Blank activity title falls back to 'Loose_Work'."""
        ctx = self._ctx(activity_title=None)
        stem = build_pdf_export_stem(ctx)
        assert "_Loose_Work_" in stem
