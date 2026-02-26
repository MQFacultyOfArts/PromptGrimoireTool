"""Unit tests for derive_roles_from_metadata().

Verifies AAF eduperson_affiliation attribute mapping to app roles.

Traceability:
- Design: docs/design-plans/2026-02-26-aaf-oidc-auth-188-189.md
- Impl: phase_02.md Task 2
- AC: aaf-oidc-auth-188-189.AC4.1 through AC4.5
"""

from __future__ import annotations

from promptgrimoire.auth import derive_roles_from_metadata, is_privileged_user


class TestDeriveRolesFromMetadata:
    """Verify derive_roles_from_metadata() maps AAF affiliations to roles."""

    def test_staff_affiliation_returns_instructor(self) -> None:
        """AC4.1: staff → instructor role."""
        result = derive_roles_from_metadata({"eduperson_affiliation": "staff"})
        assert result == ["instructor"]

    def test_staff_passes_is_privileged_user(self) -> None:
        """AC4.1: instructor role passes is_privileged_user check."""
        roles = derive_roles_from_metadata({"eduperson_affiliation": "staff"})
        auth_user: dict[str, object] = {"is_admin": False, "roles": roles}
        assert is_privileged_user(auth_user) is True

    def test_faculty_affiliation_returns_instructor(self) -> None:
        """AC4.2: faculty → instructor role."""
        result = derive_roles_from_metadata({"eduperson_affiliation": "faculty"})
        assert result == ["instructor"]

    def test_student_affiliation_returns_empty(self) -> None:
        """AC4.3: student → no special roles."""
        result = derive_roles_from_metadata({"eduperson_affiliation": "student"})
        assert result == []

    def test_student_fails_is_privileged_user(self) -> None:
        """AC4.3: student with no roles fails is_privileged_user."""
        roles = derive_roles_from_metadata({"eduperson_affiliation": "student"})
        auth_user: dict[str, object] = {"is_admin": False, "roles": roles}
        assert is_privileged_user(auth_user) is False

    def test_none_metadata_returns_empty(self) -> None:
        """AC4.4: None metadata → no roles."""
        assert derive_roles_from_metadata(None) == []

    def test_empty_dict_returns_empty(self) -> None:
        """AC4.4: empty dict → no roles."""
        assert derive_roles_from_metadata({}) == []

    def test_empty_affiliation_returns_empty(self) -> None:
        """AC4.4: empty string affiliation → no roles."""
        assert derive_roles_from_metadata({"eduperson_affiliation": ""}) == []

    def test_multiple_affiliations_highest_wins(self) -> None:
        """AC4.5: staff;student → instructor (highest privilege wins)."""
        result = derive_roles_from_metadata({"eduperson_affiliation": "staff;student"})
        assert result == ["instructor"]

    def test_faculty_staff_no_duplicates(self) -> None:
        """AC4.5: faculty;staff → single instructor, no duplicates."""
        result = derive_roles_from_metadata({"eduperson_affiliation": "faculty;staff"})
        assert result == ["instructor"]

    def test_case_insensitive(self) -> None:
        """Edge: case-insensitive matching."""
        result = derive_roles_from_metadata({"eduperson_affiliation": "  Staff  "})
        assert result == ["instructor"]

    def test_list_input(self) -> None:
        """Edge: list-type input from non-standard IdPs."""
        result = derive_roles_from_metadata(
            {"eduperson_affiliation": ["staff", "student"]}
        )
        assert result == ["instructor"]

    def test_non_string_non_list_returns_empty(self) -> None:
        """Edge: non-string, non-list type returns empty."""
        assert derive_roles_from_metadata({"eduperson_affiliation": 42}) == []
