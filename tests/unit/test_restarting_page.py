"""Unit tests for restarting page helper functions."""

from __future__ import annotations

import pytest

from promptgrimoire.pages.restarting import _return_title, _safe_return_url


class TestSafeReturnUrl:
    """Tests for _safe_return_url path validation."""

    def test_accepts_root(self) -> None:
        assert _safe_return_url("/") == "/"

    def test_accepts_relative_path(self) -> None:
        assert (
            _safe_return_url("/annotation?workspace_id=abc")
            == "/annotation?workspace_id=abc"
        )

    def test_rejects_absolute_url(self) -> None:
        assert _safe_return_url("https://evil.com") == "/"

    def test_rejects_protocol_relative(self) -> None:
        assert _safe_return_url("//evil.com") == "/"

    def test_rejects_empty(self) -> None:
        assert _safe_return_url("") == "/"


class TestReturnTitle:
    """Tests for _return_title page title derivation."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("/", "Home"),
            ("/annotation", "Annotation"),
            ("/annotation?workspace_id=abc-123", "Annotation"),
            ("/courses", "Units"),
            ("/courses/some-uuid", "Courses"),
            ("/login", "Login"),
            ("/some-page", "Some Page"),
            ("/some_page", "Some Page"),
            ("", "Home"),
        ],
    )
    def test_derives_title(self, url: str, expected: str) -> None:
        assert _return_title(url) == expected
