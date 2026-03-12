"""Shared validation helpers used across domain modules."""

from __future__ import annotations


def is_valid_email(email: str) -> bool:
    """Return True when *email* has exactly one ``@`` with non-empty parts."""
    local, separator, domain = email.partition("@")
    return bool(separator and local and domain and "@" not in domain)
