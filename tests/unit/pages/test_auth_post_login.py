"""Unit tests for post-login return URL handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_storage(data: dict | None = None) -> MagicMock:
    """Create a mock app.storage.user dict."""
    storage = MagicMock()
    _data = dict(data) if data else {}
    storage.pop = lambda key, default=None: _data.pop(key, default)
    storage.__getitem__ = lambda _, key: _data[key]
    storage.__setitem__ = lambda _, key, val: _data.__setitem__(key, val)
    storage.__contains__ = lambda _, key: key in _data
    return storage


class TestPostLoginDestination:
    """Tests for _post_login_destination return URL resolution."""

    def test_returns_root_when_no_stash(self) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage()
            assert _post_login_destination() == "/"

    def test_returns_stashed_url(self) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage(
                {"post_login_return": "/annotation?workspace_id=abc"}
            )
            result = _post_login_destination()
            assert result == "/annotation?workspace_id=abc"

    def test_clears_stash_after_read(self) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        data: dict[str, str] = {"post_login_return": "/courses"}
        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage(data)
            _post_login_destination()
            # Second call should return "/" since stash was consumed
            assert _post_login_destination() == "/"

    def test_rejects_absolute_url(self) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage(
                {"post_login_return": "https://evil.com/steal"}
            )
            assert _post_login_destination() == "/"

    def test_rejects_protocol_relative(self) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage({"post_login_return": "//evil.com"})
            assert _post_login_destination() == "/"

    @pytest.mark.parametrize(
        "bad_value",
        [42, None, True, ["/"]],
    )
    def test_rejects_non_string(self, bad_value: object) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage({"post_login_return": bad_value})
            assert _post_login_destination() == "/"

    def test_accepts_path_with_hash(self) -> None:
        from promptgrimoire.pages.auth import _post_login_destination

        with patch("promptgrimoire.pages.auth.app") as mock_app:
            mock_app.storage.user = _mock_storage(
                {"post_login_return": "/annotation?ws=abc#highlight-5"}
            )
            assert _post_login_destination() == "/annotation?ws=abc#highlight-5"
