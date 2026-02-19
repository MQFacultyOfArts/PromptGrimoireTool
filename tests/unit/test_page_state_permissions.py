"""Tests for PageState permission capability fields.

Verifies:
- AC8.5: Permission threaded via PageState.effective_permission
- Capability booleans computed correctly from effective_permission
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.pages.annotation import PageState


class TestPageStateDefaults:
    """Verify default values for permission fields."""

    def test_default_effective_permission_is_viewer(self) -> None:
        """Default permission level is 'viewer' (most restrictive)."""
        state = PageState(workspace_id=uuid4())
        assert state.effective_permission == "viewer"

    def test_default_can_annotate_is_false(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.can_annotate is False

    def test_default_can_upload_is_false(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.can_upload is False

    def test_default_can_manage_acl_is_false(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.can_manage_acl is False

    def test_default_is_anonymous_is_false(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.is_anonymous is False

    def test_default_viewer_is_privileged_is_false(self) -> None:
        state = PageState(workspace_id=uuid4())
        assert state.viewer_is_privileged is False


class TestPageStateViewerPermission:
    """Viewer sees read-only UI -- no annotation, upload, or ACL management."""

    def test_viewer_cannot_annotate(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="viewer")
        assert state.can_annotate is False

    def test_viewer_cannot_upload(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="viewer")
        assert state.can_upload is False

    def test_viewer_cannot_manage_acl(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="viewer")
        assert state.can_manage_acl is False


class TestPageStatePeerPermission:
    """Peer can annotate but not upload or manage ACL."""

    def test_peer_can_annotate(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="peer")
        assert state.can_annotate is True

    def test_peer_cannot_upload(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="peer")
        assert state.can_upload is False

    def test_peer_cannot_manage_acl(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="peer")
        assert state.can_manage_acl is False


class TestPageStateEditorPermission:
    """Editor can annotate and upload but not manage ACL."""

    def test_editor_can_annotate(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="editor")
        assert state.can_annotate is True

    def test_editor_can_upload(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="editor")
        assert state.can_upload is True

    def test_editor_cannot_manage_acl(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="editor")
        assert state.can_manage_acl is False


class TestPageStateOwnerPermission:
    """Owner has full control -- annotate, upload, and ACL management."""

    def test_owner_can_annotate(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="owner")
        assert state.can_annotate is True

    def test_owner_can_upload(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="owner")
        assert state.can_upload is True

    def test_owner_can_manage_acl(self) -> None:
        state = PageState(workspace_id=uuid4(), effective_permission="owner")
        assert state.can_manage_acl is True


class TestPageStateAnonymisationFields:
    """is_anonymous and viewer_is_privileged are pass-through fields."""

    def test_is_anonymous_set_true(self) -> None:
        state = PageState(workspace_id=uuid4(), is_anonymous=True)
        assert state.is_anonymous is True

    def test_viewer_is_privileged_set_true(self) -> None:
        state = PageState(workspace_id=uuid4(), viewer_is_privileged=True)
        assert state.viewer_is_privileged is True


@pytest.mark.parametrize(
    ("permission", "can_annotate", "can_upload", "can_manage_acl"),
    [
        ("viewer", False, False, False),
        ("peer", True, False, False),
        ("editor", True, True, False),
        ("owner", True, True, True),
    ],
    ids=["viewer", "peer", "editor", "owner"],
)
def test_capability_matrix(
    permission: str,
    can_annotate: bool,
    can_upload: bool,
    can_manage_acl: bool,
) -> None:
    """AC8.5: Full capability matrix for all permission levels."""
    state = PageState(workspace_id=uuid4(), effective_permission=permission)
    assert state.can_annotate is can_annotate
    assert state.can_upload is can_upload
    assert state.can_manage_acl is can_manage_acl
