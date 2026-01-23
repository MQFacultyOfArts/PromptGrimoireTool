"""Authentication pages for PromptGrimoire.

Provides login, callback, and protected pages using NiceGUI.
Uses either real Stytch or MockAuthClient based on AUTH_MOCK env var.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nicegui import app, ui

from promptgrimoire.auth import get_auth_client, get_config

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger(__name__)

# Time to display error message before redirecting (seconds)
_ERROR_DISPLAY_SECONDS = 0.5


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
) -> None:
    """Store authenticated user in session storage."""
    logger.info(
        "Login successful: email=%s, member_id=%s, auth_method=%s",
        email,
        member_id,
        auth_method,
    )
    app.storage.user["auth_user"] = {
        "email": email,
        "member_id": member_id,
        "organization_id": organization_id,
        "session_token": session_token,
        "roles": roles,
        "name": name,
        "auth_method": auth_method,
    }


def _clear_session() -> None:
    """Clear the current session."""
    app.storage.user.pop("auth_user", None)


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
            config = get_config()

            if not config.default_org_id:
                logger.error("STYTCH_DEFAULT_ORG_ID not configured")
                ui.notify("Organization not configured", type="negative")
                return

            callback_url = f"{config.base_url}/auth/callback"
            logger.debug("Magic link callback_url=%s", callback_url)

            result = await auth_client.send_magic_link(
                email=email,
                organization_id=config.default_org_id,
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
            config = get_config()

            if not config.sso_connection_id:
                logger.error("STYTCH_SSO_CONNECTION_ID not configured")
                ui.notify("SSO not configured", type="negative")
                return

            if not config.public_token:
                logger.error("STYTCH_PUBLIC_TOKEN not configured")
                ui.notify("SSO not configured", type="negative")
                return

            logger.info(
                "Starting SSO flow: connection_id=%s",
                config.sso_connection_id,
            )

            result = auth_client.get_sso_start_url(
                connection_id=config.sso_connection_id,
                public_token=config.public_token,
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
            config = get_config()

            if not config.public_token:
                logger.error("STYTCH_PUBLIC_TOKEN not configured")
                ui.notify("GitHub login not configured", type="negative")
                return

            if not config.default_org_id:
                logger.error("STYTCH_DEFAULT_ORG_ID not configured")
                ui.notify("GitHub login not configured", type="negative")
                return

            callback_url = f"{config.base_url}/auth/oauth/callback"
            logger.info(
                "Starting GitHub OAuth: org_id=%s, callback=%s",
                config.default_org_id,
                callback_url,
            )

            result = auth_client.get_oauth_start_url(
                provider="github",
                public_token=config.public_token,
                organization_id=config.default_org_id,
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


@ui.page("/login")
async def login_page() -> None:
    """Login page with magic link, SSO, and GitHub OAuth options."""
    user = _get_session_user()
    if user:
        ui.navigate.to("/")
        return

    ui.label("Login to PromptGrimoire").classes("text-2xl font-bold mb-4")

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
        _set_session_user(
            email=result.email or "",
            member_id=result.member_id or "",
            organization_id=result.organization_id or "",
            session_token=result.session_token or "",
            roles=result.roles,
            name=result.name,
            auth_method="magic_link",
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
        _set_session_user(
            email=result.email or "",
            member_id=result.member_id or "",
            organization_id=result.organization_id or "",
            session_token=result.session_token or "",
            roles=result.roles,
            name=result.name,
            auth_method="sso_aaf",
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
        _set_session_user(
            email=result.email or "",
            member_id=result.member_id or "",
            organization_id=result.organization_id or "",
            session_token=result.session_token or "",
            roles=result.roles,
            name=result.name,
            auth_method="github",
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
