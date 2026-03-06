"""Unit tests for page registry visibility filtering."""

from __future__ import annotations

from unittest.mock import patch

import promptgrimoire.pages
from promptgrimoire.pages.registry import get_visible_pages


def _privileged_user() -> dict[str, object]:
    """Build a user payload that satisfies is_privileged_user()."""
    return {
        "email": "staff@example.edu",
        "is_admin": False,
        "roles": ["instructor"],
    }


def _non_privileged_user() -> dict[str, object]:
    """Build a user payload without standalone roleplay access."""
    return {
        "email": "student@example.edu",
        "is_admin": False,
        "roles": [],
    }


def _visible_routes(
    user: dict[str, object] | None,
    *,
    roleplay_enabled: bool,
) -> set[str]:
    """Return visible routes for the provided user and feature flags."""
    _ = promptgrimoire.pages
    pages = get_visible_pages(
        user=user,
        demos_enabled=False,
        roleplay_enabled=roleplay_enabled,
    )
    return {page.route for page in pages}


class TestPageRegistryRoleplayVisibility:
    """Verify roleplay navigation visibility in the shared page registry."""

    def test_roleplay_pages_hidden_when_feature_disabled(self) -> None:
        """Roleplay-gated pages disappear when the feature flag is off."""
        all_routes = _visible_routes(_privileged_user(), roleplay_enabled=True)
        filtered_routes = _visible_routes(_privileged_user(), roleplay_enabled=False)

        assert "/roleplay" in all_routes
        assert "/logs" in all_routes
        assert "/roleplay" not in filtered_routes
        assert "/logs" not in filtered_routes

    def test_roleplay_pages_hidden_for_non_privileged_user(self) -> None:
        """Non-privileged users do not see roleplay-gated pages."""
        routes = _visible_routes(_non_privileged_user(), roleplay_enabled=True)

        assert "/roleplay" not in routes
        assert "/logs" not in routes

    def test_roleplay_pages_shown_for_privileged_user(self) -> None:
        """Privileged users retain standalone roleplay navigation access."""
        routes = _visible_routes(_privileged_user(), roleplay_enabled=True)

        assert "/roleplay" in routes
        assert "/logs" in routes

    def test_roleplay_pages_visible_to_students_when_privilege_not_required(
        self,
    ) -> None:
        """Students see roleplay nav when roleplay_require_privileged is False."""
        from promptgrimoire.pages.registry import get_settings

        settings = get_settings()
        patched = settings.model_copy(
            update={
                "features": settings.features.model_copy(
                    update={"roleplay_require_privileged": False}
                )
            }
        )
        with patch("promptgrimoire.pages.registry.get_settings", return_value=patched):
            routes = _visible_routes(_non_privileged_user(), roleplay_enabled=True)

        assert "/roleplay" in routes
        assert "/logs" in routes
