"""Unit tests for magic link domain enforcement.

Verifies that only MQ email domains are accepted for magic link login.

Traceability:
- Impl: phase_04.md Task 1
- AC: aaf-oidc-auth-188-189.AC7.1 through AC7.4
"""

from __future__ import annotations

from promptgrimoire.pages.auth import _is_allowed_magic_link_domain


class TestIsAllowedMagicLinkDomain:
    """Verify _is_allowed_magic_link_domain() enforces MQ domains."""

    def test_mq_staff_domain_allowed(self) -> None:
        """AC7.1: @mq.edu.au accepted."""
        assert _is_allowed_magic_link_domain("user@mq.edu.au") is True

    def test_mq_student_domain_allowed(self) -> None:
        """AC7.2: @students.mq.edu.au accepted."""
        assert _is_allowed_magic_link_domain("student@students.mq.edu.au") is True

    def test_gmail_rejected(self) -> None:
        """AC7.3: @gmail.com rejected."""
        assert _is_allowed_magic_link_domain("user@gmail.com") is False

    def test_arbitrary_domain_rejected(self) -> None:
        """AC7.3: arbitrary domain rejected."""
        assert _is_allowed_magic_link_domain("user@example.com") is False

    def test_empty_string_rejected(self) -> None:
        """Edge: empty string rejected."""
        assert _is_allowed_magic_link_domain("") is False

    def test_no_at_sign_rejected(self) -> None:
        """Edge: no @ sign rejected."""
        assert _is_allowed_magic_link_domain("notanemail") is False

    def test_subdomain_not_allowed(self) -> None:
        """Edge: sub.mq.edu.au not in allowed set."""
        assert _is_allowed_magic_link_domain("user@sub.mq.edu.au") is False

    def test_case_insensitive(self) -> None:
        """Edge: domain matching is case-insensitive."""
        assert _is_allowed_magic_link_domain("user@MQ.EDU.AU") is True
        assert _is_allowed_magic_link_domain("user@Students.MQ.EDU.AU") is True
