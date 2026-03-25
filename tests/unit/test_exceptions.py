"""Unit tests for DB exception classes.

Verifies instantiation, attribute storage, message formatting,
and inheritance for deletion guard exceptions.
"""

from __future__ import annotations

from uuid import uuid4

from promptgrimoire.db.exceptions import (
    BusinessLogicError,
    HasAnnotationsError,
    HasChildTagsError,
    HasHighlightsError,
)


class TestHasChildTagsError:
    """Tests for HasChildTagsError."""

    def test_stores_attributes(self) -> None:
        gid = uuid4()
        err = HasChildTagsError(gid, 3)
        assert err.group_id == gid
        assert err.tag_count == 3

    def test_singular_message(self) -> None:
        gid = uuid4()
        err = HasChildTagsError(gid, 1)
        assert "1 tag " in str(err)
        assert "1 tags" not in str(err)

    def test_plural_message(self) -> None:
        gid = uuid4()
        err = HasChildTagsError(gid, 5)
        assert "5 tags" in str(err)

    def test_is_business_logic_error(self) -> None:
        assert issubclass(HasChildTagsError, BusinessLogicError)


class TestHasHighlightsError:
    """Tests for HasHighlightsError."""

    def test_stores_attributes(self) -> None:
        tid = uuid4()
        err = HasHighlightsError(tid, 7)
        assert err.tag_id == tid
        assert err.highlight_count == 7

    def test_singular_message(self) -> None:
        tid = uuid4()
        err = HasHighlightsError(tid, 1)
        assert "1 highlight " in str(err)
        assert "1 highlights" not in str(err)

    def test_plural_message(self) -> None:
        tid = uuid4()
        err = HasHighlightsError(tid, 2)
        assert "2 highlights" in str(err)

    def test_is_business_logic_error(self) -> None:
        assert issubclass(HasHighlightsError, BusinessLogicError)


class TestHasAnnotationsError:
    """Tests for HasAnnotationsError."""

    def test_stores_attributes(self) -> None:
        did = uuid4()
        err = HasAnnotationsError(did, 4)
        assert err.document_id == did
        assert err.highlight_count == 4

    def test_singular_message(self) -> None:
        did = uuid4()
        err = HasAnnotationsError(did, 1)
        assert "1 annotation " in str(err)
        assert "1 annotations" not in str(err)

    def test_plural_message(self) -> None:
        did = uuid4()
        err = HasAnnotationsError(did, 10)
        assert "10 annotations" in str(err)

    def test_is_business_logic_error(self) -> None:
        assert issubclass(HasAnnotationsError, BusinessLogicError)
