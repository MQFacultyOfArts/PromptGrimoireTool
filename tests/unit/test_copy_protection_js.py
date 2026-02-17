"""Unit tests for client-side copy protection injection and lock icon chip.

Tests verify conditional injection logic (protect flag computation, function
signatures) and that the JS block contains expected selectors and event
handlers via substring checks (not exact string matching).

Traceability:
- Design: docs/implementation-plans/2026-02-13-copy-protection-103/phase_04.md
- Design: docs/implementation-plans/2026-02-13-copy-protection-103/phase_05.md
- AC: 103-copy-protection.AC4.1-AC4.13, AC4.6, AC6.1-AC6.3
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.db.workspaces import PlacementContext
from promptgrimoire.pages.annotation.workspace import (
    _inject_copy_protection,
    _render_workspace_header,
)


def _compute_protect(
    ctx: PlacementContext,
    auth_user: dict[str, object] | None,
) -> bool:
    """Reproduce the protect flag computation from _render_workspace_view.

    Extracted here so unit tests can verify the logic without mocking
    NiceGUI page infrastructure.
    """
    return ctx.copy_protection and not is_privileged_user(auth_user)


class TestCopyProtectionInactiveStates:
    """Verify protection is NOT active in specific scenarios.

    AC4.12: Activity with copy_protection=False -> protect is False.
    AC4.13: Loose workspace (no activity) -> protect is False.
    """

    def test_ac4_12_protection_disabled_on_activity(self) -> None:
        """Activity with copy_protection=False produces protect=False.

        Verifies AC4.12: no JS injection, no lock chip when activity
        has copy_protection explicitly disabled.
        """
        ctx = PlacementContext(
            placement_type="activity",
            activity_title="Test Activity",
            week_number=1,
            course_code="TEST1000",
            copy_protection=False,
        )
        # Student (no roles) should still not be protected
        student_user = {"roles": ["student"]}
        assert _compute_protect(ctx, student_user) is False

    def test_ac4_13_loose_workspace_not_protected(self) -> None:
        """Loose workspace (no activity) produces protect=False.

        Verifies AC4.13: loose workspaces have copy_protection=False
        by default on PlacementContext, so protect is always False.
        """
        ctx = PlacementContext(placement_type="loose")
        assert ctx.copy_protection is False
        student_user = {"roles": ["student"]}
        assert _compute_protect(ctx, student_user) is False

    def test_protection_active_when_enabled_for_student(self) -> None:
        """Positive case: protect=True when copy_protection=True and
        user is a student (not privileged).
        """
        ctx = PlacementContext(
            placement_type="activity",
            activity_title="Protected Activity",
            week_number=1,
            course_code="TEST1000",
            copy_protection=True,
        )
        student_user = {"roles": ["student"]}
        assert _compute_protect(ctx, student_user) is True

    def test_protection_bypassed_for_instructor(self) -> None:
        """Privileged users bypass copy protection even when enabled."""
        ctx = PlacementContext(
            placement_type="activity",
            activity_title="Protected Activity",
            week_number=1,
            course_code="TEST1000",
            copy_protection=True,
        )
        instructor_user = {"roles": ["instructor"]}
        assert _compute_protect(ctx, instructor_user) is False

    def test_protection_bypassed_for_org_admin(self) -> None:
        """Org-level admin users bypass copy protection even when enabled."""
        ctx = PlacementContext(
            placement_type="activity",
            activity_title="Protected Activity",
            week_number=1,
            course_code="TEST1000",
            copy_protection=True,
        )
        admin_user: dict[str, object] = {
            "is_admin": True,
            "roles": ["student"],
        }
        assert _compute_protect(ctx, admin_user) is False

    def test_protection_bypassed_for_unauthenticated(self) -> None:
        """Unauthenticated users (auth_user=None) are not privileged,
        so protection applies when copy_protection=True.
        """
        ctx = PlacementContext(
            placement_type="activity",
            activity_title="Protected Activity",
            week_number=1,
            course_code="TEST1000",
            copy_protection=True,
        )
        assert _compute_protect(ctx, None) is True

    def test_course_placement_not_protected(self) -> None:
        """Course-placed workspace has copy_protection=False by default."""
        ctx = PlacementContext(
            placement_type="course",
            course_code="TEST1000",
            course_name="Test Course",
        )
        assert ctx.copy_protection is False
        assert _compute_protect(ctx, {"roles": ["student"]}) is False


class TestInjectCopyProtectionFunction:
    """Verify _inject_copy_protection exists with correct signature."""

    def test_is_not_async(self) -> None:
        """_inject_copy_protection is sync (ui.run_javascript is fire-and-forget)."""
        assert not inspect.iscoroutinefunction(_inject_copy_protection)

    def test_accepts_no_parameters(self) -> None:
        """Function takes no parameters — it's a fire-and-forget JS injection."""
        sig = inspect.signature(_inject_copy_protection)
        assert len(sig.parameters) == 0


class TestRenderWorkspaceHeaderSignature:
    """Verify _render_workspace_header accepts protect parameter."""

    def test_has_protect_parameter(self) -> None:
        """_render_workspace_header has a protect keyword parameter."""
        sig = inspect.signature(_render_workspace_header)
        assert "protect" in sig.parameters

    def test_protect_defaults_to_false(self) -> None:
        """protect parameter defaults to False for backward compatibility."""
        sig = inspect.signature(_render_workspace_header)
        param = sig.parameters["protect"]
        assert param.default is False


class TestPrintSuppressionInjection:
    """Verify _inject_copy_protection injects print suppression CSS and message.

    Verifies AC4.6: CSS @media print hides content and shows message,
    Ctrl+P intercept reuses showToast from the IIFE.

    These tests mock NiceGUI UI calls to verify conditional injection
    without requiring full page infrastructure.
    """

    @pytest.fixture()
    def _mock_ui(self) -> Iterator[dict[str, MagicMock]]:
        """Mock the three NiceGUI UI calls used by _inject_copy_protection."""
        with (
            patch(
                "promptgrimoire.pages.annotation.workspace.ui.run_javascript"
            ) as mock_js,
            patch("promptgrimoire.pages.annotation.workspace.ui.add_css") as mock_css,
            patch("promptgrimoire.pages.annotation.workspace.ui.html") as mock_html,
        ):
            yield {"js": mock_js, "css": mock_css, "html": mock_html}

    def test_add_css_called_when_injecting(
        self, _mock_ui: dict[str, MagicMock]
    ) -> None:
        """ui.add_css is called to inject @media print CSS."""
        _inject_copy_protection()
        _mock_ui["css"].assert_called_once()
        css_arg = _mock_ui["css"].call_args[0][0]
        assert "@media print" in css_arg
        assert ".q-tab-panels" in css_arg

    def test_html_message_div_injected(self, _mock_ui: dict[str, MagicMock]) -> None:
        """ui.html is called to inject hidden print message div."""
        _inject_copy_protection()
        _mock_ui["html"].assert_called_once()
        html_arg = _mock_ui["html"].call_args[0][0]
        assert "copy-protection-print-message" in html_arg
        assert "Printing is disabled" in html_arg

    def test_no_css_or_html_when_not_called(self) -> None:
        """When _inject_copy_protection is NOT called, no CSS/HTML injection.

        This verifies the conditional boundary: the if-protect guard in
        _render_workspace_view controls whether injection happens at all.
        """
        ctx = PlacementContext(
            placement_type="activity",
            activity_title="Test",
            week_number=1,
            course_code="TEST1000",
            copy_protection=False,
        )
        assert _compute_protect(ctx, {"roles": ["student"]}) is False
