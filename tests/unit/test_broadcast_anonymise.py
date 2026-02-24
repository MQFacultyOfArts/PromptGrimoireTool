"""Unit tests for broadcast cursor/selection label anonymisation.

Verifies workspace-sharing-97.AC4.7: broadcast labels respect anonymity flag.

Regression tests (sensitive+specific):
- sender_is_privileged parameter exists and works (instructor cursors visible)
- No receiver_is_owner bypass exists in the API
"""

from __future__ import annotations

import inspect


class TestResolveBroadcastLabel:
    """resolve_broadcast_label returns correct name for sender→receiver pair."""

    def test_anonymises_for_non_privileged_receiver(self) -> None:
        """Non-privileged receiver sees anonymised label."""
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        label = resolve_broadcast_label(
            sender_name="Alice Smith",
            sender_user_id="user-alice",
            receiver_user_id="user-bob",
            is_anonymous=True,
            receiver_is_privileged=False,
            sender_is_privileged=False,
        )

        assert label != "Alice Smith"
        # Deterministic coolname label — calling twice gives same result
        label2 = resolve_broadcast_label(
            sender_name="Alice Smith",
            sender_user_id="user-alice",
            receiver_user_id="user-bob",
            is_anonymous=True,
            receiver_is_privileged=False,
            sender_is_privileged=False,
        )
        assert label == label2

    def test_privileged_receiver_sees_real_name(self) -> None:
        """Instructors see real name even with anonymisation on."""
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        label = resolve_broadcast_label(
            sender_name="Alice Smith",
            sender_user_id="user-alice",
            receiver_user_id="user-instructor",
            is_anonymous=True,
            receiver_is_privileged=True,
            sender_is_privileged=False,
        )

        assert label == "Alice Smith"

    def test_privileged_sender_shows_real_name(self) -> None:
        """Privileged sender (instructor) cursor is never anonymised.

        Sensitive: would TypeError on pre-fix code without sender_is_privileged.
        Specific: passes because sender_is_privileged maps to author_is_privileged.
        """
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        label = resolve_broadcast_label(
            sender_name="Prof. Smith",
            sender_user_id="user-instructor",
            receiver_user_id="user-student",
            is_anonymous=True,
            receiver_is_privileged=False,
            sender_is_privileged=True,
        )

        assert label == "Prof. Smith"

    def test_non_privileged_receiver_sees_anonymised_cursor(self) -> None:
        """Non-privileged receiver (including workspace owner) sees anonymised cursor.

        Sensitive: would fail if a receiver_is_owner bypass were added.
        Specific: passes because non-privileged receivers always get anonymised labels.
        """
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        label = resolve_broadcast_label(
            sender_name="Alice Smith",
            sender_user_id="user-alice",
            receiver_user_id="user-owner",
            is_anonymous=True,
            receiver_is_privileged=False,
            sender_is_privileged=False,
        )

        assert label != "Alice Smith"

    def test_no_anonymisation_when_disabled(self) -> None:
        """When is_anonymous is False, all receivers see real name."""
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        label = resolve_broadcast_label(
            sender_name="Alice Smith",
            sender_user_id="user-alice",
            receiver_user_id="user-bob",
            is_anonymous=False,
            receiver_is_privileged=False,
            sender_is_privileged=False,
        )

        assert label == "Alice Smith"

    def test_own_cursor_shows_real_name(self) -> None:
        """Sender seeing own cursor label gets real name."""
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        label = resolve_broadcast_label(
            sender_name="Alice Smith",
            sender_user_id="user-alice",
            receiver_user_id="user-alice",
            is_anonymous=True,
            receiver_is_privileged=False,
            sender_is_privileged=False,
        )

        assert label == "Alice Smith"


class TestResolveBroadcastLabelAPIContract:
    """Regression guards for resolve_broadcast_label API surface."""

    def test_no_receiver_is_owner_parameter(self) -> None:
        """API must NOT accept receiver_is_owner — that bypass was the bug.

        Sensitive: fails on pre-fix code where receiver_is_owner existed.
        Specific: passes on current code where it does not.
        """
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        params = inspect.signature(resolve_broadcast_label).parameters
        assert "receiver_is_owner" not in params, (
            "receiver_is_owner parameter must not exist — "
            "workspace owners must NOT bypass anonymisation in broadcasts"
        )

    def test_sender_is_privileged_parameter_exists(self) -> None:
        """API must accept sender_is_privileged for instructor cursor visibility.

        Sensitive: fails on pre-fix code that lacked this parameter.
        Specific: passes on current code where it exists.
        """
        from promptgrimoire.pages.annotation.broadcast import resolve_broadcast_label

        params = inspect.signature(resolve_broadcast_label).parameters
        assert "sender_is_privileged" in params, (
            "sender_is_privileged parameter must exist — "
            "instructor cursors must never be anonymised"
        )
