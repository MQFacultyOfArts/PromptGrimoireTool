"""Unit tests for _import_notification in tag_import.

Verifies AC4.5: notification text includes created/skipped
counts with correct pluralisation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from promptgrimoire.db.tags import ImportResult
from promptgrimoire.pages.annotation.tag_import import (
    _import_notification,
)


def _fake_tags(n: int) -> list[Any]:
    """Return n mock Tag objects (only len() matters)."""
    return [MagicMock() for _ in range(n)]


def _fake_groups(n: int) -> list[Any]:
    """Return n mock TagGroup objects (only len() matters)."""
    return [MagicMock() for _ in range(n)]


class TestImportNotification:
    """Verify notification messages for various ImportResult states."""

    def test_no_created_items(self) -> None:
        result = ImportResult()
        msg, ntype = _import_notification(result)
        assert msg == "No new tags to import"
        assert ntype == "info"

    def test_tags_only(self) -> None:
        result = ImportResult(created_tags=_fake_tags(3))  # type: ignore[arg-type]
        msg, ntype = _import_notification(result)
        assert msg == "Imported 3 tags"
        assert ntype == "positive"

    def test_single_tag_no_plural(self) -> None:
        result = ImportResult(created_tags=_fake_tags(1))  # type: ignore[arg-type]
        msg, _ = _import_notification(result)
        assert msg == "Imported 1 tag"

    def test_groups_only(self) -> None:
        result = ImportResult(created_groups=_fake_groups(2))  # type: ignore[arg-type]
        msg, ntype = _import_notification(result)
        assert msg == "Imported 2 groups"
        assert ntype == "positive"

    def test_tags_and_groups(self) -> None:
        result = ImportResult(
            created_tags=_fake_tags(2),  # type: ignore[arg-type]
            created_groups=_fake_groups(1),  # type: ignore[arg-type]
        )
        msg, _ = _import_notification(result)
        assert msg == "Imported 2 tags, 1 group"

    def test_with_skipped_tags(self) -> None:
        result = ImportResult(
            created_tags=_fake_tags(1),  # type: ignore[arg-type]
            skipped_tags=3,
        )
        msg, _ = _import_notification(result)
        assert msg == "Imported 1 tag (3 tags already existed)"

    def test_with_skipped_groups(self) -> None:
        result = ImportResult(
            created_tags=_fake_tags(2),  # type: ignore[arg-type]
            created_groups=_fake_groups(1),  # type: ignore[arg-type]
            skipped_groups=1,
        )
        msg, _ = _import_notification(result)
        assert msg == "Imported 2 tags, 1 group (1 group already existed)"

    def test_with_all_skipped(self) -> None:
        result = ImportResult(
            created_tags=_fake_tags(1),  # type: ignore[arg-type]
            skipped_tags=2,
            created_groups=_fake_groups(1),  # type: ignore[arg-type]
            skipped_groups=1,
        )
        msg, _ = _import_notification(result)
        assert "2 tags" in msg
        assert "1 group already existed" in msg

    @pytest.mark.parametrize(
        ("skipped_tags", "expected_fragment"),
        [
            (1, "1 tag already existed"),
            (5, "5 tags already existed"),
        ],
    )
    def test_skipped_pluralisation(
        self,
        skipped_tags: int,
        expected_fragment: str,
    ) -> None:
        result = ImportResult(
            created_tags=_fake_tags(1),  # type: ignore[arg-type]
            skipped_tags=skipped_tags,
        )
        msg, _ = _import_notification(result)
        assert expected_fragment in msg
