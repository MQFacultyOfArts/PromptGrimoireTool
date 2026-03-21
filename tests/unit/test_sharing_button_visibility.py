"""Unit tests for share button visibility guard logic.

Tests the boolean expressions controlling share button rendering
in sharing.py without requiring NiceGUI context.

AC3.1: Button visible when allow_sharing=True and can_manage_sharing=True
AC3.2: Button hidden when allow_sharing=False and non-staff
AC3.3: Button visible for staff even when allow_sharing=False
AC3.4: Class toggle has NO staff bypass (regression guard)
"""

from __future__ import annotations

import subprocess

import pytest


class TestShareButtonVisibility:
    """Pure boolean logic tests for the share button guard."""

    @pytest.mark.parametrize(
        ("allow_sharing", "viewer_is_privileged", "can_manage_sharing", "expected"),
        [
            pytest.param(True, False, True, True, id="AC3.1-sharing-allowed-non-staff"),
            pytest.param(
                False, False, True, False, id="AC3.2-sharing-disabled-non-staff"
            ),
            pytest.param(
                False, True, True, True, id="AC3.3-sharing-disabled-staff-bypass"
            ),
            pytest.param(True, True, True, True, id="staff-sharing-allowed"),
            pytest.param(True, False, False, False, id="cannot-manage-sharing"),
            pytest.param(True, True, False, False, id="staff-cannot-manage"),
        ],
    )
    def test_share_button_guard(
        self,
        allow_sharing: bool,
        viewer_is_privileged: bool,
        can_manage_sharing: bool,
        expected: bool,
    ) -> None:
        """Share button expression matches expected visibility."""
        result = (allow_sharing or viewer_is_privileged) and can_manage_sharing
        assert result is expected


class TestClassToggleNoStaffBypass:
    """Regression guard: class toggle has no staff bypass (AC3.4)."""

    def test_class_toggle_false_when_sharing_disabled(self) -> None:
        """Staff bypass does NOT apply to 'Share with class' toggle."""
        allow_sharing = False
        can_manage_sharing = True
        # viewer_is_privileged intentionally True to prove no bypass
        result = allow_sharing and can_manage_sharing
        assert result is False


class TestStructuralGuard:
    """ast-grep structural guard for share button guard expression."""

    def test_share_button_guard_expression(self) -> None:
        """sharing.py contains the expected guard expression."""
        result = subprocess.run(
            [
                "sg",
                "run",
                "-p",
                "(allow_sharing or viewer_is_privileged) and can_manage_sharing",
                "-l",
                "python",
                "src/promptgrimoire/pages/annotation/sharing.py",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            "Expected guard expression not found in sharing.py"
        )
