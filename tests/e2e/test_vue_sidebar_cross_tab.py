"""E2E tests for Vue annotation sidebar cross-tab interaction (#457 Phase 10 Task 6).

Validates the Vue sidebar with the Pabai fixture (190 highlights):
- Initial render and card positioning on the Source tab
- Expand/collapse of individual cards
- Organise tab renders with all highlights
- State preserved after switching tabs and back

These tests are marked ``noci`` — they are too heavy for default CI.
They run in ``e2e slow`` and the nightly workflow only.

Run with:
    uv run grimoire e2e run tests/e2e/test_vue_sidebar_cross_tab.py
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from promptgrimoire.docs.helpers import wait_for_text_walker

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page

PABAI_WORKSPACE_ID = "0e5e9b04-de94-4728-a8c9-e625c141fea3"
_WORKSPACE_JSON = (
    Path(__file__).parent.parent / "fixtures" / "pabai_workspace_scrubbed.json"
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.noci,  # heavy — only e2e slow + nightly
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]


def _test_db_conninfo() -> str:
    """Build psycopg conninfo for the test database."""
    from urllib.parse import urlparse

    url = get_settings().dev.test_database_url
    if not url:
        msg = "DEV__TEST_DATABASE_URL not configured"
        raise RuntimeError(msg)
    parsed = urlparse(url)
    user = parsed.username or "brian"
    dbname = parsed.path.lstrip("/")
    host = parsed.hostname or "/var/run/postgresql"
    if "host=" in (parsed.query or ""):
        for param in parsed.query.split("&"):
            if param.startswith("host="):
                host = param.split("=", 1)[1]
    return f"user={user} dbname={dbname} host={host}"


@pytest.fixture(scope="session")
def pabai_workspace() -> str:
    """Ensure the Pabai workspace is rehydrated into the test DB.

    Session-scoped: runs once, rehydrates from JSON extraction if
    the workspace is missing. Skips if the JSON file doesn't exist.

    Returns the workspace ID.
    """
    import psycopg

    if not _WORKSPACE_JSON.exists():
        pytest.skip(
            f"Workspace JSON not found at {_WORKSPACE_JSON}. "
            "Extract from prod or dev DB first."
        )

    conninfo = _test_db_conninfo()

    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM workspace WHERE id = %s::uuid",
            (PABAI_WORKSPACE_ID,),
        )
        if cur.fetchone() is not None:
            return PABAI_WORKSPACE_ID

    from scripts.rehydrate_workspace import rehydrate

    result = rehydrate(_WORKSPACE_JSON, conninfo)
    assert result["workspace_id"] == PABAI_WORKSPACE_ID
    return PABAI_WORKSPACE_ID


@pytest.fixture
def pabai_page(
    browser: Browser,
    app_server: str,
    pabai_workspace: str,
) -> Generator[Page]:
    """Authenticated page with owner ACL on the Pabai workspace.

    Creates a fresh browser context, authenticates via mock auth,
    grants owner ACL on the Pabai workspace via direct SQL, and
    navigates to the annotation page. Yields the loaded page.
    """
    import psycopg

    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid4().hex[:8]
    email = f"vue-cross-tab-{unique_id}@test.example.edu.au"
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10_000)

    conninfo = _test_db_conninfo()
    with psycopg.connect(conninfo) as conn:
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM "user" WHERE email = %s',
            (email,),
        )
        row = cur.fetchone()
        assert row is not None, f"Mock auth didn't create user {email}"
        user_id = row[0]
        cur.execute(
            "INSERT INTO acl_entry"
            " (id, workspace_id, user_id, permission, created_at)"
            " VALUES (gen_random_uuid(), %s::uuid, %s, 'owner', now())"
            " ON CONFLICT DO NOTHING",
            (pabai_workspace, user_id),
        )
        conn.commit()

    ws_url = f"{app_server}/annotation?workspace_id={pabai_workspace}"
    page.goto("about:blank")
    page.goto(ws_url, wait_until="networkidle")
    wait_for_text_walker(page, timeout=30_000)

    # Wait for Vue sidebar epoch — confirms cards have been rendered
    page.wait_for_function(
        "() => (window.__annotationCardsEpoch || 0) >= 1",
        timeout=30_000,
    )

    yield page

    page.goto("about:blank")
    page.close()
    context.close()


class TestVueSidebarCrossTab:
    """Vue annotation sidebar: cross-tab interaction with 190-highlight Pabai fixture.

    Uses the Pabai workspace fixture (session-scoped rehydration from JSON).
    All tests are ``noci`` — they only run in ``e2e slow`` and nightly.
    """

    def test_source_tab_initial_render(
        self,
        pabai_page: Page,
    ) -> None:
        """Cards render, are positioned, and do not overlap on the Source tab.

        Verifies:
        - 190+ annotation cards exist
        - Each card has a numeric ``style.top`` (positioned)
        - Sorted tops are strictly increasing (no overlap)
        """
        page = pabai_page

        # Wait until all cards are positioned
        page.wait_for_function(
            """() => {
                const cards = Array.from(
                    document.querySelectorAll('[data-testid="annotation-card"]')
                );
                return (
                    cards.length > 100
                    && cards.every(c => Number.isFinite(parseFloat(c.style.top)))
                );
            }""",
            timeout=30_000,
        )

        card_count = page.locator('[data-testid="annotation-card"]').count()
        assert card_count >= 190, f"Expected 190+ annotation cards, got {card_count}"

        # Verify strictly increasing tops (no overlap)
        tops: list[float] = page.evaluate(
            """() => Array.from(
                document.querySelectorAll('[data-testid="annotation-card"]')
            ).map(c => parseFloat(c.style.top))"""
        )
        assert all(t >= 0 for t in tops), (
            f"Some card tops are negative: {[t for t in tops if t < 0]}"
        )
        for i in range(len(tops) - 1):
            assert tops[i] < tops[i + 1], (
                f"Cards {i} and {i + 1} overlap: top[{i}]={tops[i]}, "
                f"top[{i + 1}]={tops[i + 1]}"
            )

    def test_source_tab_expand_collapse(
        self,
        pabai_page: Page,
    ) -> None:
        """Expand and collapse the first card via the expand button.

        Verifies:
        - ``card-detail`` becomes visible after clicking ``expand-btn``
        - ``card-detail`` becomes hidden after clicking again
        """
        page = pabai_page

        page.wait_for_function(
            "() => (window.__annotationCardsEpoch || 0) >= 1",
            timeout=30_000,
        )

        first_card = page.locator('[data-testid="annotation-card"]').first
        expect(first_card).to_be_visible(timeout=15_000)

        expand_btn = first_card.locator('[data-testid="expand-btn"]')
        expect(expand_btn).to_be_visible(timeout=5_000)

        card_detail = first_card.locator('[data-testid="card-detail"]')

        # Expand
        expand_btn.click()
        expect(card_detail).to_be_visible(timeout=5_000)

        # Collapse
        expand_btn.click()
        expect(card_detail).to_be_hidden(timeout=5_000)

    def test_organise_tab_renders(
        self,
        pabai_page: Page,
    ) -> None:
        """Switching to the Organise tab renders all highlights in columns.

        Verifies:
        - ``organise-columns`` container appears
        - Total ``organise-card`` count across all columns matches 190+
        """
        page = pabai_page

        page.wait_for_function(
            "() => (window.__annotationCardsEpoch || 0) >= 1",
            timeout=30_000,
        )

        page.locator('[data-testid="tab-organise"]').click()

        expect(page.locator('[data-testid="organise-columns"]')).to_be_visible(
            timeout=15_000
        )

        organise_card_count = page.locator('[data-testid="organise-card"]').count()
        assert organise_card_count >= 190, (
            f"Expected 190+ organise cards, got {organise_card_count}"
        )

    def test_source_tab_state_preserved_after_tab_switch(
        self,
        pabai_page: Page,
    ) -> None:
        """Cards survive a round-trip through the Organise tab.

        Switches to Organise, then back to the Source tab. Verifies
        that 190+ cards are still present and each has a positioned
        ``style.top``.
        """
        page = pabai_page

        page.wait_for_function(
            "() => (window.__annotationCardsEpoch || 0) >= 1",
            timeout=30_000,
        )

        # Switch to Organise tab
        page.locator('[data-testid="tab-organise"]').click()
        expect(page.locator('[data-testid="organise-columns"]')).to_be_visible(
            timeout=15_000
        )

        # Switch back to Source tab
        page.locator('[data-testid="tab-source-1"]').click()

        # Epoch may reset on tab switch — wait for it to be > 0
        page.wait_for_function(
            "() => (window.__annotationCardsEpoch || 0) > 0",
            timeout=30_000,
        )

        # Wait for cards to re-appear and be positioned
        page.wait_for_function(
            """() => {
                const cards = Array.from(
                    document.querySelectorAll('[data-testid="annotation-card"]')
                );
                return (
                    cards.length > 100
                    && cards.every(c => Number.isFinite(parseFloat(c.style.top)))
                );
            }""",
            timeout=30_000,
        )

        card_count = page.locator('[data-testid="annotation-card"]').count()
        assert card_count >= 190, (
            f"Expected 190+ cards after tab switch, got {card_count}"
        )

        has_positioned = page.evaluate(
            """() => Array.from(
                document.querySelectorAll('[data-testid="annotation-card"]')
            ).every(c => Number.isFinite(parseFloat(c.style.top)))"""
        )
        assert has_positioned, "Cards lost positioning after tab switch"
