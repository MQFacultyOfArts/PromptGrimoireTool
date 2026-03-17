"""Tests for the BusinessLogicError exception taxonomy.

Verifies:
- AC1.1: All 10 domain exceptions are isinstance(exc, BusinessLogicError)
- AC1.5: str(SharePermissionError("msg")) == "msg" (message preservation)
- AC1.6: DuplicateNameError is NOT isinstance(exc, ValueError)
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.db.exceptions import (
    BusinessLogicError,
    DeletionBlockedError,
    DuplicateCodenameError,
    DuplicateEnrollmentError,
    DuplicateNameError,
    OwnershipError,
    ProtectedDocumentError,
    SharePermissionError,
    StudentIdConflictError,
    TagCreationDeniedError,
    ZeroEditorError,
)

# -- AC1.1: All 10 domain exceptions are BusinessLogicError subclasses --------


_SIMPLE_EXCEPTIONS = [
    SharePermissionError,
    OwnershipError,
    TagCreationDeniedError,
    DuplicateNameError,
]


@pytest.mark.parametrize(
    "exc_cls",
    _SIMPLE_EXCEPTIONS,
    ids=lambda c: c.__name__,
)
def test_simple_exception_is_business_logic_error(
    exc_cls: type[BusinessLogicError],
) -> None:
    """Simple (no custom __init__) exceptions are BusinessLogicError instances."""
    exc = exc_cls("test message")
    assert isinstance(exc, BusinessLogicError)


def test_deletion_blocked_error_is_business_logic_error() -> None:
    exc = DeletionBlockedError(student_workspace_count=3)
    assert isinstance(exc, BusinessLogicError)
    assert exc.student_workspace_count == 3


def test_protected_document_error_is_business_logic_error() -> None:
    doc_id, source_id = uuid4(), uuid4()
    exc = ProtectedDocumentError(document_id=doc_id, source_document_id=source_id)
    assert isinstance(exc, BusinessLogicError)
    assert exc.document_id == doc_id
    assert exc.source_document_id == source_id


def test_duplicate_codename_error_is_business_logic_error() -> None:
    activity_id = uuid4()
    exc = DuplicateCodenameError(activity_id=activity_id, codename="alpha-bravo")
    assert isinstance(exc, BusinessLogicError)
    assert exc.activity_id == activity_id
    assert exc.codename == "alpha-bravo"


def test_zero_editor_error_is_business_logic_error() -> None:
    team_id, user_id = uuid4(), uuid4()
    exc = ZeroEditorError(
        team_id=team_id,
        user_id=user_id,
        current_permission="editor",
        attempted_permission="viewer",
    )
    assert isinstance(exc, BusinessLogicError)
    assert exc.team_id == team_id
    assert exc.user_id == user_id


def test_duplicate_enrollment_error_is_business_logic_error() -> None:
    course_id, user_id = uuid4(), uuid4()
    exc = DuplicateEnrollmentError(course_id=course_id, user_id=user_id)
    assert isinstance(exc, BusinessLogicError)
    assert exc.course_id == course_id
    assert exc.user_id == user_id


def test_student_id_conflict_error_is_business_logic_error() -> None:
    conflicts = [("alice@example.com", "S001", "S999")]
    exc = StudentIdConflictError(conflicts=conflicts)
    assert isinstance(exc, BusinessLogicError)
    assert exc.conflicts == conflicts


# -- AC1.5: Message preservation for UI display --------------------------------


def test_share_permission_error_preserves_message() -> None:
    """str() on SharePermissionError returns the user-facing message verbatim.

    This matters because sharing.py:199 displays str(exc) to the user.
    """
    msg = "You do not have permission to share this workspace"
    exc = SharePermissionError(msg)
    assert str(exc) == msg


def test_ownership_error_preserves_message() -> None:
    msg = "Only the workspace owner may delete this workspace"
    exc = OwnershipError(msg)
    assert str(exc) == msg


def test_tag_creation_denied_error_preserves_message() -> None:
    msg = "Tag creation is restricted to instructors in this context"
    exc = TagCreationDeniedError(msg)
    assert str(exc) == msg


# -- AC1.6: DuplicateNameError is NOT a ValueError ----------------------------


def test_duplicate_name_error_is_not_value_error() -> None:
    """Intentional reparenting: DuplicateNameError no longer inherits ValueError.

    Callers already catch by class name, so this breaking change is safe.
    """
    exc = DuplicateNameError("duplicate tag name")
    assert not isinstance(exc, ValueError)


# -- Negative: BusinessLogicError is NOT a builtin exception type --------------


def test_business_logic_error_is_not_builtin_permission_error() -> None:
    """BusinessLogicError hierarchy is distinct from builtin PermissionError."""
    exc = SharePermissionError("test")
    assert not isinstance(exc, PermissionError)


def test_business_logic_error_is_not_builtin_value_error() -> None:
    """BusinessLogicError hierarchy is distinct from builtin ValueError."""
    exc = BusinessLogicError("test")
    assert not isinstance(exc, ValueError)
