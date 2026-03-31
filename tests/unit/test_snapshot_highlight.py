"""Unit tests for _snapshot_highlight change-detection helper.

Extracted from tests/integration/test_annotation_cards_charac.py to prevent
import-poisoning of the NiceGUI user_simulation fixture.  Importing
``promptgrimoire.pages.annotation.cards`` triggers the full
``promptgrimoire.pages`` import chain, which registers ``@ui.page`` routes
against whatever NiceGUI app state exists at import time.  When these sync
tests ran before the first ``user_simulation`` context in the NiceGUI lane,
``sys.modules`` was pre-populated and ``runpy.run_path`` inside
``user_simulation`` could not re-register routes — causing 404 on ``/login``
for every subsequent ``nicegui_user`` fixture invocation.

Moving these pure-function tests to the unit lane eliminates the trigger.

Verifies: _snapshot_highlight produces deterministic, comparable dicts
Traceability: phase_01.md Task 3 (multi-doc-tabs-186-plan-a)
"""

from __future__ import annotations


class TestSnapshotHighlight:
    """Unit tests for _snapshot_highlight change-detection helper."""

    def test_snapshot_captures_tag(self) -> None:
        """Snapshot includes the tag value."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {"id": "h1", "tag": "jurisdiction", "comments": []}
        snap = _snapshot_highlight(hl)
        assert snap["tag"] == "jurisdiction"

    def test_snapshot_captures_comment_count(self) -> None:
        """Snapshot includes the number of comments."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {
            "id": "h1",
            "tag": "evidence",
            "comments": [
                {"text": "first", "created_at": "2026-01-01"},
                {"text": "second", "created_at": "2026-01-02"},
            ],
        }
        snap = _snapshot_highlight(hl)
        assert snap["comment_count"] == 2

    def test_snapshot_captures_comment_texts(self) -> None:
        """Snapshot includes sorted comment texts as a tuple."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {
            "id": "h1",
            "tag": "t",
            "comments": [
                {"text": "beta", "created_at": "2026-01-02"},
                {"text": "alpha", "created_at": "2026-01-01"},
            ],
        }
        snap = _snapshot_highlight(hl)
        # Sorted by created_at, so alpha first
        assert snap["comment_texts"] == ("alpha", "beta")

    def test_snapshot_detects_tag_change(self) -> None:
        """Two snapshots with different tags are not equal."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl1 = {"id": "h1", "tag": "jurisdiction", "comments": []}
        hl2 = {"id": "h1", "tag": "evidence", "comments": []}
        assert _snapshot_highlight(hl1) != _snapshot_highlight(hl2)

    def test_snapshot_detects_comment_addition(self) -> None:
        """Adding a comment changes the snapshot."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl_before = {"id": "h1", "tag": "t", "comments": []}
        hl_after = {
            "id": "h1",
            "tag": "t",
            "comments": [{"text": "new", "created_at": "2026-01-01"}],
        }
        assert _snapshot_highlight(hl_before) != _snapshot_highlight(hl_after)

    def test_snapshot_same_data_equal(self) -> None:
        """Identical highlight data produces equal snapshots."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl_one = {
            "id": "h1",
            "tag": "t",
            "comments": [{"text": "c", "created_at": "2026-01-01"}],
        }
        hl_two = {
            "id": "h1",
            "tag": "t",
            "comments": [{"text": "c", "created_at": "2026-01-01"}],
        }
        expected = {
            "tag": "t",
            "para_ref": "",
            "comment_count": 1,
            "comment_texts": ("c",),
        }
        assert _snapshot_highlight(hl_one) == expected
        assert _snapshot_highlight(hl_two) == expected

    def test_snapshot_captures_para_ref(self) -> None:
        """Snapshot includes the para_ref value."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl = {"id": "h1", "tag": "t", "para_ref": "[3]", "comments": []}
        snap = _snapshot_highlight(hl)
        assert snap["para_ref"] == "[3]"

    def test_snapshot_detects_para_ref_change(self) -> None:
        """Changing para_ref changes the snapshot."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl1 = {"id": "h1", "tag": "t", "para_ref": "[3]", "comments": []}
        hl2 = {"id": "h1", "tag": "t", "para_ref": "[4]", "comments": []}
        assert _snapshot_highlight(hl1) != _snapshot_highlight(hl2)

    def test_snapshot_missing_fields_use_defaults(self) -> None:
        """Highlights with missing fields use sensible defaults."""
        from promptgrimoire.pages.annotation.cards import _snapshot_highlight

        hl: dict[str, object] = {"id": "h1"}
        snap = _snapshot_highlight(hl)
        assert snap["tag"] == ""
        assert snap["para_ref"] == ""
        assert snap["comment_count"] == 0
        assert snap["comment_texts"] == ()
