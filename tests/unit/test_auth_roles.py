"""Unit tests for is_privileged_user() role check.

Verifies that the auth module correctly identifies privileged users (admins,
instructors) versus unprivileged users (students, tutors, unauthenticated).

Traceability:
- Design: docs/implementation-plans/2026-02-13-copy-protection-103/phase_03.md Task 1
- AC: 103-copy-protection.AC5.1 through AC5.6
"""

from __future__ import annotations

from promptgrimoire.auth import is_privileged_user


class TestIsPrivilegedUser:
    """Verify is_privileged_user() returns correct privilege status."""

    def test_admin_is_privileged(self) -> None:
        """AC5.1: Org-level admin bypasses copy protection."""
        auth_user: dict[str, object] = {"is_admin": True, "roles": []}
        assert is_privileged_user(auth_user) is True

    def test_instructor_role_is_privileged(self) -> None:
        """AC5.2: User with 'instructor' role bypasses copy protection."""
        auth_user: dict[str, object] = {"is_admin": False, "roles": ["instructor"]}
        assert is_privileged_user(auth_user) is True

    def test_stytch_admin_role_is_privileged(self) -> None:
        """AC5.3: User with 'stytch_admin' role bypasses copy protection."""
        auth_user: dict[str, object] = {"is_admin": False, "roles": ["stytch_admin"]}
        assert is_privileged_user(auth_user) is True

    def test_student_is_not_privileged(self) -> None:
        """AC5.4: Student (no privileged roles) sees protection."""
        auth_user: dict[str, object] = {"is_admin": False, "roles": []}
        assert is_privileged_user(auth_user) is False

    def test_tutor_is_not_privileged(self) -> None:
        """AC5.5: Tutor role is NOT a privileged role."""
        auth_user: dict[str, object] = {"is_admin": False, "roles": ["tutor"]}
        assert is_privileged_user(auth_user) is False

    def test_unauthenticated_is_not_privileged(self) -> None:
        """AC5.6: None (unauthenticated) sees protection."""
        assert is_privileged_user(None) is False

    def test_empty_dict_is_not_privileged(self) -> None:
        """Edge: Empty auth_user dict (missing keys) returns False."""
        assert is_privileged_user({}) is False

    def test_none_roles_is_not_privileged(self) -> None:
        """Edge: roles=None does not crash, returns False."""
        auth_user: dict[str, object] = {"is_admin": False, "roles": None}
        assert is_privileged_user(auth_user) is False
