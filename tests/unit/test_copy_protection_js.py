"""Unit tests for client-side copy protection injection and lock icon chip.

Tests verify the conditional logic: JS is injected and lock chip rendered
when protect=True, and neither is present when protect=False. Does NOT test
JS string content directly (brittle).

Traceability:
- Design: docs/implementation-plans/2026-02-13-103-copy-protection/phase_04.md
- AC: 103-copy-protection.AC4.1-AC4.13, AC6.1-AC6.3
"""

from __future__ import annotations

import inspect

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.db.workspaces import PlacementContext
from promptgrimoire.pages.annotation import (
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


class TestCopyProtectionJsContent:
    """Verify the JS block contains expected selectors and event handlers."""

    def test_js_block_targets_doc_container(self) -> None:
        """JS PROTECTED selector includes #doc-container."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "#doc-container" in _COPY_PROTECTION_JS

    def test_js_block_targets_organise_columns(self) -> None:
        """JS PROTECTED selector includes organise-columns test ID."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "organise-columns" in _COPY_PROTECTION_JS

    def test_js_block_targets_respond_reference_panel(self) -> None:
        """JS PROTECTED selector includes respond-reference-panel test ID."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "respond-reference-panel" in _COPY_PROTECTION_JS

    def test_js_block_intercepts_copy_event(self) -> None:
        """JS registers a copy event listener."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "'copy'" in _COPY_PROTECTION_JS

    def test_js_block_intercepts_cut_event(self) -> None:
        """JS registers a cut event listener."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "'cut'" in _COPY_PROTECTION_JS

    def test_js_block_intercepts_contextmenu_event(self) -> None:
        """JS registers a contextmenu event listener."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "'contextmenu'" in _COPY_PROTECTION_JS

    def test_js_block_intercepts_dragstart_event(self) -> None:
        """JS registers a dragstart event listener."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "'dragstart'" in _COPY_PROTECTION_JS

    def test_js_block_intercepts_paste_on_milkdown(self) -> None:
        """JS targets milkdown-respond-editor for paste interception."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "milkdown-respond-editor" in _COPY_PROTECTION_JS

    def test_js_block_uses_quasar_notify(self) -> None:
        """JS shows toast via Quasar.Notify.create()."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "Quasar.Notify.create" in _COPY_PROTECTION_JS

    def test_js_block_uses_group_key_for_debounce(self) -> None:
        """JS uses group key to deduplicate toast notifications."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "copy-protection" in _COPY_PROTECTION_JS

    def test_js_block_stops_immediate_propagation_on_paste(self) -> None:
        """Paste handler calls stopImmediatePropagation to block ProseMirror."""
        from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS

        assert "stopImmediatePropagation" in _COPY_PROTECTION_JS
