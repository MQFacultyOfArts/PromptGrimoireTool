"""Authentication pages for PromptGrimoire.

Provides login, callback, and protected pages using NiceGUI.
Uses either real Stytch or MockAuthClient based on DEV__AUTH_MOCK setting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from nicegui import app, ui

from promptgrimoire.auth import derive_roles_from_metadata, get_auth_client
from promptgrimoire.config import get_settings
from promptgrimoire.db import init_db, upsert_user_on_login

if TYPE_CHECKING:
    from uuid import UUID

    from starlette.requests import Request

logger = logging.getLogger(__name__)

# Time to display error message before redirecting (seconds)
_ERROR_DISPLAY_SECONDS = 0.5

# Browser feature gate: blocks unsupported browsers before any annotation code runs.
# Checks for CSS Custom Highlight API support ('highlights' in CSS).
# On unsupported browsers, creates a full-page overlay covering the login UI.
# Exposes window.__checkBrowserGate() for testability (E2E can re-invoke after
# deleting CSS.highlights to simulate an unsupported browser).
_BROWSER_GATE_JS = """
<script>
(function() {
    function checkBrowserGate() {
        if (document.getElementById('browser-gate-overlay')) return;
        if (!('highlights' in CSS)) {
            var overlay = document.createElement('div');
            overlay.id = 'browser-gate-overlay';
            overlay.style.cssText = [
                'position: fixed',
                'top: 0',
                'left: 0',
                'width: 100%',
                'height: 100%',
                'background: #fff',
                'z-index: 99999',
                'display: flex',
                'flex-direction: column',
                'align-items: center',
                'justify-content: center',
                'font-family: system-ui, sans-serif',
                'text-align: center',
                'padding: 2rem'
            ].join('; ');

            var heading = document.createElement('h1');
            heading.style.cssText = 'margin-bottom: 1rem; font-size: 1.875rem;';
            heading.textContent = 'Browser Not Supported';

            var msg = document.createElement('p');
            msg.style.cssText = 'max-width: 500px; line-height: 1.6; color: #333;';
            msg.textContent = 'Your browser does not support features required '
                + 'by PromptGrimoire. Please upgrade to Chrome 105+, Firefox 140+, '
                + 'Safari 17.2+, or Edge 105+.';

            var link = document.createElement('a');
            link.href = '/';
            link.textContent = 'Go Home';
            link.style.cssText = [
                'margin-top: 1.5rem',
                'padding: 0.75rem 2rem',
                'background: #1976d2',
                'color: #fff',
                'text-decoration: none',
                'border-radius: 4px',
                'font-size: 1rem'
            ].join('; ');

            overlay.appendChild(heading);
            overlay.appendChild(msg);
            overlay.appendChild(link);
            document.body.appendChild(overlay);
        }
    }
    // Expose for E2E testability
    window.__checkBrowserGate = checkBrowserGate;
    // Run immediately
    checkBrowserGate();
})();
</script>
"""


def _get_session_user() -> dict | None:
    """Get the current user from session storage.

    Returns:
        User dict with email, member_id, roles, etc. or None if not authenticated.
    """
    return app.storage.user.get("auth_user")


def _set_session_user(
    email: str,
    member_id: str,
    organization_id: str,
    session_token: str,
    roles: list[str],
    name: str | None = None,
    auth_method: str = "unknown",
    user_id: UUID | None = None,
    is_admin: bool = False,
) -> None:
    """Store authenticated user in session storage."""
    logger.info(
        "Login successful: email=%s, member_id=%s, auth_method=%s, user_id=%s",
        email,
        member_id,
        auth_method,
        user_id,
    )
    app.storage.user["auth_user"] = {
        "email": email,
        "member_id": member_id,
        "organization_id": organization_id,
        "session_token": session_token,
        "roles": roles,
        "name": name,
        "display_name": name,
        "auth_method": auth_method,
        "user_id": str(user_id) if user_id else None,
        "is_admin": is_admin,
    }


def _clear_session() -> None:
    """Clear the current session."""
    app.storage.user.pop("auth_user", None)


async def _upsert_local_user(
    email: str,
    stytch_member_id: str,
    display_name: str | None = None,
    roles: list[str] | None = None,
) -> tuple[UUID | None, bool]:
    """Upsert user in local database if configured.

    Args:
        email: User's email from Stytch auth.
        stytch_member_id: Stytch member_id from auth.
        display_name: Optional name from Stytch.
        roles: List of Stytch roles (checks for "stytch_admin").

    Returns:
        Tuple of (user_id, is_admin) or (None, False) if DB not configured.
    """
    if not get_settings().database.url:
        logger.debug("DATABASE__URL not configured, skipping user upsert")
        return None, False

    # Check if user has admin role from Stytch
    is_admin = "stytch_admin" in (roles or [])

    try:
        await init_db()
        user = await upsert_user_on_login(
            email=email,
            stytch_member_id=stytch_member_id,
            display_name=display_name,
            is_admin=is_admin
            if is_admin
            else None,  # Only set if admin, preserve otherwise
        )
        logger.info(
            "User upserted: id=%s, email=%s, is_admin=%s",
            user.id,
            user.email,
            user.is_admin,
        )
        return user.id, user.is_admin
    except Exception:
        logger.exception("Failed to upsert user in local database")
        return None, False


def _get_query_param(name: str) -> str | None:
    """Get a query parameter from the current request.

    Args:
        name: The query parameter name.

    Returns:
        The parameter value or None if not present.
    """
    request: Request = ui.context.client.request
    return request.query_params.get(name)


# CRIT-3: Maximum token length to prevent DoS/injection attacks
_MAX_TOKEN_LENGTH = 1000


def _validate_token(token: str | None) -> bool:
    """Validate that a token is safe to process.

    Args:
        token: The token string to validate.

    Returns:
        True if the token is valid and safe, False otherwise.
    """
    if not token:
        return False
    if len(token) > _MAX_TOKEN_LENGTH:
        logger.warning("Token exceeds max length: %d chars", len(token))
        return False
    return True


def _build_magic_link_section() -> None:
    """Build the magic link login section."""
    with ui.card().classes("w-96 p-4"):
        ui.label("Email Magic Link").classes("text-lg font-semibold mb-2")

        email_input = (
            ui.input(
                label="Email address",
                placeholder="you@example.com",
            )
            .props('data-testid="email-input"')
            .classes("w-full")
        )

        async def send_magic_link() -> None:
            email = email_input.value
            if not email:
                ui.notify("Please enter an email address", type="warning")
                return

            logger.info("Magic link requested for email=%s", email)

            auth_client = get_auth_client()
            settings = get_settings()

            if not settings.stytch.default_org_id:
                logger.error("STYTCH__DEFAULT_ORG_ID not configured")
                ui.notify("Organization not configured", type="negative")
                return

            callback_url = f"{settings.app.base_url}/auth/callback"
            logger.debug("Magic link callback_url=%s", callback_url)

            result = await auth_client.send_magic_link(
                email=email,
                organization_id=settings.stytch.default_org_id,
                callback_url=callback_url,
            )

            if result.success:
                logger.info("Magic link sent successfully to %s", email)
                ui.notify("Magic link sent! Check your email.", type="positive")
            else:
                logger.warning("Magic link failed: %s", result.error)
                ui.notify(f"Error: {result.error}", type="negative")

        ui.button(
            "Send Magic Link",
            on_click=send_magic_link,
        ).props('data-testid="send-magic-link-btn"').classes("mt-2")


def _build_sso_section() -> None:
    """Build the SSO login section."""
    with ui.card().classes("w-96 p-4"):
        ui.label("University Login (AAF)").classes("text-lg font-semibold mb-2")

        def start_sso() -> None:
            logger.info("SSO login button clicked (AAF)")
            auth_client = get_auth_client()
            settings = get_settings()

            if not settings.stytch.sso_connection_id:
                logger.error("STYTCH__SSO_CONNECTION_ID not configured")
                ui.notify("SSO not configured", type="negative")
                return

            if not settings.stytch.public_token:
                logger.error("STYTCH__PUBLIC_TOKEN not configured")
                ui.notify("SSO not configured", type="negative")
                return

            logger.info(
                "Starting SSO flow: connection_id=%s",
                settings.stytch.sso_connection_id,
            )

            result = auth_client.get_sso_start_url(
                connection_id=settings.stytch.sso_connection_id,
                public_token=settings.stytch.public_token,
            )

            if result.success and result.redirect_url:
                logger.info("SSO redirect URL generated: %s", result.redirect_url)
                ui.navigate.to(result.redirect_url)
            else:
                logger.warning("SSO start failed: %s", result.error)
                ui.notify(f"SSO Error: {result.error}", type="negative")

        ui.button(
            "Login with AAF",
            on_click=start_sso,
        ).props('data-testid="sso-login-btn"').classes("w-full")


def _build_github_oauth_section() -> None:
    """Build the GitHub OAuth login section."""
    with ui.card().classes("w-96 p-4"):
        ui.label("GitHub Login").classes("text-lg font-semibold mb-2")

        def start_github_oauth() -> None:
            logger.info("GitHub OAuth login button clicked")
            auth_client = get_auth_client()
            settings = get_settings()

            if not settings.stytch.public_token:
                logger.error("STYTCH__PUBLIC_TOKEN not configured")
                ui.notify("GitHub login not configured", type="negative")
                return

            if not settings.stytch.default_org_id:
                logger.error("STYTCH__DEFAULT_ORG_ID not configured")
                ui.notify("GitHub login not configured", type="negative")
                return

            callback_url = f"{settings.app.base_url}/auth/oauth/callback"
            logger.info(
                "Starting GitHub OAuth: org_id=%s, callback=%s",
                settings.stytch.default_org_id,
                callback_url,
            )

            result = auth_client.get_oauth_start_url(
                provider="github",
                public_token=settings.stytch.public_token,
                organization_id=settings.stytch.default_org_id,
                login_redirect_url=callback_url,
            )

            if result.success and result.redirect_url:
                logger.info("GitHub OAuth redirect URL: %s", result.redirect_url)
                ui.navigate.to(result.redirect_url)
            else:
                logger.warning("GitHub OAuth start failed: %s", result.error)
                ui.notify(f"GitHub login error: {result.error}", type="negative")

        ui.button(
            "Login with GitHub",
            on_click=start_github_oauth,
        ).props('data-testid="github-login-btn"').classes("w-full")


def _build_mock_login_section() -> None:
    """Build mock login section for testing (only when DEV__AUTH_MOCK=true)."""
    with ui.card().classes("w-96 p-4 bg-yellow-50 border-yellow-200"):
        ui.label("Mock Login (Testing Only)").classes(
            "text-lg font-semibold mb-2 text-yellow-800"
        )
        ui.label("Click to instantly log in as:").classes(
            "text-sm text-yellow-700 mb-2"
        )

        test_users = [
            ("test@example.com", "Test User"),
            ("student@uni.edu", "Student"),
            ("instructor@uni.edu", "Instructor"),
            ("admin@example.com", "Admin"),
        ]

        for email, label in test_users:
            token = f"mock-token-{email}"

            def login_as(t: str = token) -> None:
                ui.navigate.to(f"/auth/callback?{urlencode({'token': t})}")

            ui.button(
                f"{label} ({email})",
                on_click=login_as,
            ).classes("w-full mb-1").props("flat")


@ui.page("/login")
async def login_page() -> None:
    """Login page with magic link, SSO, and GitHub OAuth options."""
    user = _get_session_user()
    if user:
        ui.navigate.to("/")
        return

    # Inject before login UI so the overlay covers the form immediately.
    ui.add_body_html(_BROWSER_GATE_JS)

    ui.label("Login to PromptGrimoire").classes("text-2xl font-bold mb-4")

    # Show mock login section when in test mode
    if get_settings().dev.auth_mock:
        _build_mock_login_section()
        ui.label("— or —").classes("my-4")

    _build_magic_link_section()
    ui.label("— or —").classes("my-4")
    _build_sso_section()
    ui.label("— or —").classes("my-4")
    _build_github_oauth_section()


@ui.page("/auth/callback")
async def magic_link_callback() -> None:
    """Handle magic link callback and authenticate the token."""
    logger.info("Magic link callback received")
    token = _get_query_param("token")

    # CRIT-3: Validate token before processing
    if not _validate_token(token):
        logger.warning("Magic link callback: invalid or missing token")
        ui.label("Invalid or missing token").classes("text-xl text-red-500")
        ui.notify("Invalid or missing token", type="negative")
        ui.timer(_ERROR_DISPLAY_SECONDS, lambda: ui.navigate.to("/login"), once=True)
        return

    # Show loading while processing
    ui.label("Authenticating...").classes("text-xl")
    ui.spinner()

    # Type narrowing: _validate_token already checked token is not None
    assert token is not None

    logger.debug("Authenticating magic link token (length=%d)", len(token))
    auth_client = get_auth_client()
    result = await auth_client.authenticate_magic_link(token=token)

    if result.success:
        # Upsert user in local database
        user_id, is_admin = await _upsert_local_user(
            email=result.email or "",
            stytch_member_id=result.member_id or "",
            display_name=result.name,
            roles=result.roles,
        )

        _set_session_user(
            email=result.email or "",
            member_id=result.member_id or "",
            organization_id=result.organization_id or "",
            session_token=result.session_token or "",
            roles=result.roles,
            name=result.name,
            auth_method="magic_link",
            user_id=user_id,
            is_admin=is_admin,
        )
        ui.navigate.to("/")
    else:
        logger.warning("Magic link auth failed: %s", result.error)
        ui.label(f"Error: {result.error}").classes("text-red-500")
        ui.notify(f"Authentication failed: {result.error}", type="negative")
        ui.timer(_ERROR_DISPLAY_SECONDS, lambda: ui.navigate.to("/login"), once=True)


@ui.page("/auth/sso/callback")
async def sso_callback() -> None:
    """Handle SSO callback and authenticate the token."""
    logger.info("SSO callback received")
    token = _get_query_param("token")

    # CRIT-3: Validate token before processing
    if not _validate_token(token):
        logger.warning("SSO callback: invalid or missing token")
        ui.label("Invalid or missing SSO token").classes("text-xl text-red-500")
        ui.notify("Invalid or missing SSO token", type="negative")
        ui.timer(_ERROR_DISPLAY_SECONDS, lambda: ui.navigate.to("/login"), once=True)
        return

    ui.label("Processing SSO login...").classes("text-xl")
    ui.spinner()

    # Type narrowing: _validate_token already checked token is not None
    assert token is not None

    logger.debug("Authenticating SSO token (length=%d)", len(token))
    auth_client = get_auth_client()
    result = await auth_client.authenticate_sso(token=token)

    if result.success:
        # Derive app roles from AAF metadata and merge with Stytch roles
        derived_roles = derive_roles_from_metadata(result.trusted_metadata)
        all_roles = list(dict.fromkeys([*result.roles, *derived_roles]))

        # Upsert user in local database
        user_id, is_admin = await _upsert_local_user(
            email=result.email or "",
            stytch_member_id=result.member_id or "",
            display_name=result.name,
            roles=all_roles,
        )

        _set_session_user(
            email=result.email or "",
            member_id=result.member_id or "",
            organization_id=result.organization_id or "",
            session_token=result.session_token or "",
            roles=all_roles,
            name=result.name,
            auth_method="sso_aaf",
            user_id=user_id,
            is_admin=is_admin,
        )
        ui.navigate.to("/")
    else:
        logger.warning("SSO auth failed: %s", result.error)
        ui.label(f"Error: {result.error}").classes("text-red-500")
        ui.notify(f"SSO authentication failed: {result.error}", type="negative")
        ui.timer(_ERROR_DISPLAY_SECONDS, lambda: ui.navigate.to("/login"), once=True)


@ui.page("/auth/oauth/callback")
async def oauth_callback() -> None:
    """Handle OAuth callback and authenticate the token."""
    logger.info("OAuth callback received (GitHub)")
    token = _get_query_param("token")

    # CRIT-3: Validate token before processing
    if not _validate_token(token):
        logger.warning("OAuth callback: invalid or missing token")
        ui.label("Invalid or missing OAuth token").classes("text-xl text-red-500")
        ui.notify("Invalid or missing OAuth token", type="negative")
        ui.timer(_ERROR_DISPLAY_SECONDS, lambda: ui.navigate.to("/login"), once=True)
        return

    ui.label("Processing GitHub login...").classes("text-xl")
    ui.spinner()

    # Type narrowing: _validate_token already checked token is not None
    assert token is not None

    logger.debug("Authenticating OAuth token (length=%d)", len(token))
    auth_client = get_auth_client()
    result = await auth_client.authenticate_oauth(token=token)

    if result.success:
        # Upsert user in local database
        user_id, is_admin = await _upsert_local_user(
            email=result.email or "",
            stytch_member_id=result.member_id or "",
            display_name=result.name,
            roles=result.roles,
        )

        _set_session_user(
            email=result.email or "",
            member_id=result.member_id or "",
            organization_id=result.organization_id or "",
            session_token=result.session_token or "",
            roles=result.roles,
            name=result.name,
            auth_method="github",
            user_id=user_id,
            is_admin=is_admin,
        )
        ui.navigate.to("/")
    else:
        logger.warning("OAuth auth failed: %s", result.error)
        ui.label(f"Error: {result.error}").classes("text-red-500")
        ui.notify(f"GitHub authentication failed: {result.error}", type="negative")
        ui.timer(_ERROR_DISPLAY_SECONDS, lambda: ui.navigate.to("/login"), once=True)


@ui.page("/protected")
async def protected_page() -> None:
    """Protected page that requires authentication."""
    user = _get_session_user()

    if not user:
        ui.navigate.to("/login")
        return

    # CRIT-2: Validate session with Stytch before granting access
    session_token = user.get("session_token")
    if not session_token:
        logger.warning("Session missing token, clearing session")
        _clear_session()
        ui.navigate.to("/login")
        return

    auth_client = get_auth_client()
    session_result = await auth_client.validate_session(session_token)

    if not session_result.valid:
        logger.info("Session expired or invalid: %s", session_result.error)
        _clear_session()
        ui.navigate.to("/login")
        return

    ui.label("Protected Page").classes("text-2xl font-bold mb-4")

    with ui.card().classes("p-4"):
        ui.label("You are logged in!").classes("text-lg mb-2")

        with ui.row().classes("gap-2"):
            ui.label("Email:").classes("font-semibold")
            ui.label(user["email"])

        with ui.row().classes("gap-2"):
            ui.label("Member ID:").classes("font-semibold")
            ui.label(user["member_id"])

        with ui.row().classes("gap-2"):
            ui.label("Roles:").classes("font-semibold")
            for role in user["roles"]:
                ui.badge(role).classes("mr-1")

    def logout() -> None:
        _clear_session()
        ui.navigate.to("/login")

    ui.button(
        "Logout",
        on_click=logout,
    ).props('data-testid="logout-btn"').classes("mt-4")


@ui.page("/logout")
def logout_page() -> None:
    """Logout and redirect to login."""
    _clear_session()
    ui.navigate.to("/login")
