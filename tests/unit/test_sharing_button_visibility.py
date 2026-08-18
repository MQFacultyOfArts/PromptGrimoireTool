"""Behavioural tests for sharing-control visibility.

Exercises the production predicates on SharingUiFlags (sharing.py) —
previously these tables ran against an inline re-implementation of the
expression with an ast-grep shape-guard as the only link to production;
converted 2026-08-17 (tracker ledger 13).

AC3.1: Button visible when allow_sharing=True and can_manage_sharing=True
AC3.2: Button hidden when allow_sharing=False and non-staff
AC3.3: Button visible for staff even when allow_sharing=False
AC3.4: Class toggle has NO staff bypass (regression guard)
"""

from __future__ import annotations

import pytest

from promptgrimoire.pages.annotation.sharing import SharingUiFlags


def _flags(
    *,
    allow_sharing: bool,
    viewer_is_privileged: bool,
    can_manage_sharing: bool,
    shared_with_class: bool = False,
) -> SharingUiFlags:
    return SharingUiFlags(
        allow_sharing=allow_sharing,
        shared_with_class=shared_with_class,
        can_manage_sharing=can_manage_sharing,
        viewer_is_privileged=viewer_is_privileged,
    )


class TestShareButtonVisibility:
    """Share-with-user button: (allow_sharing or staff) and can_manage."""

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
            pytest.param(False, False, False, False, id="nothing-granted"),
            pytest.param(False, True, False, False, id="staff-without-manage"),
        ],
    )
    def test_share_button_visibility(
        self,
        allow_sharing: bool,
        viewer_is_privileged: bool,
        can_manage_sharing: bool,
        expected: bool,
    ) -> None:
        """Production predicate matches the hand-written truth table."""
        flags = _flags(
            allow_sharing=allow_sharing,
            viewer_is_privileged=viewer_is_privileged,
            can_manage_sharing=can_manage_sharing,
        )
        assert flags.shows_share_button is expected


class TestClassToggleVisibility:
    """Share-with-class toggle: allow_sharing and can_manage — no staff bypass."""

    def test_class_toggle_false_when_sharing_disabled(self) -> None:
        """AC3.4: staff bypass does NOT apply to the class toggle."""
        flags = _flags(
            allow_sharing=False,
            viewer_is_privileged=True,  # intentionally staff, to prove no bypass
            can_manage_sharing=True,
        )
        assert flags.shows_class_toggle is False

    def test_class_toggle_true_when_allowed_and_managing(self) -> None:
        flags = _flags(
            allow_sharing=True,
            viewer_is_privileged=False,
            can_manage_sharing=True,
        )
        assert flags.shows_class_toggle is True

    def test_class_toggle_false_without_manage_rights(self) -> None:
        flags = _flags(
            allow_sharing=True,
            viewer_is_privileged=False,
            can_manage_sharing=False,
        )
        assert flags.shows_class_toggle is False
