"""Annotation card interaction helpers for E2E tests.

Extracted from annotation_helpers.py to keep file sizes manageable.
These helpers handle card expand/collapse, commenting, comment
inspection, and Pabai workspace rehydration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

ANNOTATION_CARD = "[data-testid='annotation-card']"

PABAI_WORKSPACE_ID = "0e5e9b04-de94-4728-a8c9-e625c141fea3"
PABAI_FIXTURE_JSON = (
    Path(__file__).parent.parent / "fixtures" / "pabai_workspace_scrubbed.json"
)


def test_db_conninfo() -> str:
    """Build psycopg conninfo for the branch-specific test database."""
    from urllib.parse import urlparse

    from promptgrimoire.config import get_settings

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


def ensure_pabai_workspace() -> str:
    """Rehydrate the Pabai workspace into the test DB (idempotent).

    The rehydrate script deletes then re-inserts, so calling this
    unconditionally is safe. Returns the workspace ID.

    Raises ``pytest.skip`` if the fixture JSON doesn't exist.
    """
    import pytest

    if not PABAI_FIXTURE_JSON.exists():
        pytest.skip(
            f"Workspace JSON not found at {PABAI_FIXTURE_JSON}. "
            "Extract from prod or dev DB first."
        )

    from scripts.rehydrate_workspace import rehydrate

    conninfo = test_db_conninfo()
    result = rehydrate(PABAI_FIXTURE_JSON, conninfo)
    assert result["workspace_id"] == PABAI_WORKSPACE_ID
    return PABAI_WORKSPACE_ID


def select_tag(page: Page, label: str, *, card_index: int = 0) -> None:
    """Change an annotation card's tag via the Quasar q-select dropdown.

    Clicks the q-select to open its popup menu, then clicks the option
    matching *label*. Works with the Vue sidebar's Quasar select (not
    a native ``<select>``).
    """
    card = page.locator(ANNOTATION_CARD).nth(card_index)
    tag_select = card.get_by_test_id("tag-select")
    tag_select.click()
    # Quasar q-select opens a popup menu with role="listbox"
    page.locator(".q-menu .q-item").filter(has_text=label).click()


def expand_card(page: Page, card_index: int = 0) -> None:
    """Expand an annotation card's detail section.

    Clicks the card's expand button and waits for the detail section
    to become visible, then waits one animation frame for
    ``positionCards()`` to re-run.
    """
    card = page.locator(ANNOTATION_CARD).nth(card_index)
    card.wait_for(state="visible", timeout=10000)

    detail = card.get_by_test_id("card-detail")
    if detail.is_visible():
        return  # already expanded

    expand_btn = card.get_by_test_id("expand-btn")
    expand_btn.click()

    detail.wait_for(state="visible", timeout=5000)
    page.wait_for_function("new Promise(r => requestAnimationFrame(r))")


def collapse_card(page: Page, card_index: int = 0) -> None:
    """Collapse an annotation card's detail section.

    Clicks the card's expand button (toggles to collapse) and waits
    for the detail section to become hidden, then waits one animation
    frame for ``positionCards()`` to re-run.
    """
    card = page.locator(ANNOTATION_CARD).nth(card_index)
    card.wait_for(state="visible", timeout=10000)

    detail = card.get_by_test_id("card-detail")
    if not detail.is_visible():
        return  # already collapsed

    expand_btn = card.get_by_test_id("expand-btn")
    expand_btn.click()

    detail.wait_for(state="hidden", timeout=5000)
    page.wait_for_function("new Promise(r => requestAnimationFrame(r))")


def add_comment_to_highlight(
    page: Page,
    text: str,
    *,
    card_index: int = 0,
) -> None:
    """Add a comment to an annotation card via the Post button.

    Automatically expands the card if collapsed, since the comment
    input is inside the detail section.
    """
    expand_card(page, card_index)

    card = page.locator(ANNOTATION_CARD).nth(card_index)

    comment_input = card.get_by_test_id("comment-input")
    comment_input.fill(text)

    # Capture the scalar epoch BEFORE clicking.  The scalar
    # ``__annotationCardsEpoch`` tracks the most-recent broadcast from
    # whichever document is currently active, so it always increments
    # when the current tab's cards rebuild.  The per-document map
    # ``__cardEpochs`` is unsuitable because Math.max() across all docs
    # can stay flat when a lower-epoch document increments to match a
    # higher-epoch sibling (see #186 multi-doc export test).
    old_epoch = page.evaluate("() => window.__annotationCardsEpoch || 0")

    card.get_by_test_id("post-comment-btn").click()

    # Wait for the server to process the comment, rebuild the DOM,
    # and signal completion via the epoch increment. This guarantees
    # the old DOM is dead and the new DOM is fully settled.
    page.wait_for_function(
        "(oldEpoch) => {"
        "  const m = window.__cardEpochs;"
        "  if (m) {"
        "    const v = Object.values(m);"
        "    if (v.length) return Math.max(...v) > oldEpoch;"
        "  }"
        "  return (window.__annotationCardsEpoch || 0) > oldEpoch;"
        "}",
        arg=old_epoch,
        timeout=10000,
    )

    # Reacquire locators from the *new* DOM.
    # Do NOT reuse `card` or `comment_input` from above.
    new_card = page.locator(ANNOTATION_CARD).nth(card_index)

    # The card detail section must be visible before we can find the
    # comment text inside it.  After container.clear() + rebuild, the
    # detail visibility is restored from state.expanded_cards on the
    # server and pushed to the client — wait for that push to land.
    new_detail = new_card.get_by_test_id("card-detail")
    new_detail.wait_for(state="visible", timeout=5000)

    # Wait for the specific comment text to be visible in the new card
    new_comment = new_card.get_by_test_id("comment-item").filter(has_text=text)
    try:
        new_comment.wait_for(state="visible", timeout=5000)
    except Exception:
        # Diagnostic: capture what comments are actually in the DOM
        diag = page.evaluate(
            """(cardIdx) => {
                const cards = document.querySelectorAll(
                    '[data-testid="annotation-card"]'
                );
                const card = cards[cardIdx];
                if (!card) return { error: 'card not found', cardCount: cards.length };
                const detail = card.querySelector('[data-testid="card-detail"]');
                const comments = card.querySelectorAll('[data-testid="comment-item"]');
                return {
                    cardCount: cards.length,
                    detailVisible: detail ? detail.offsetHeight > 0 : null,
                    commentCount: comments.length,
                    commentTexts: Array.from(comments).map(
                        c => c.textContent.substring(0, 80)
                    ),
                };
            }""",
            card_index,
        )
        logger.debug(
            "add_comment VISIBILITY FAILED: text=%r diag=%s",
            text,
            diag,
        )
        raise


def get_comment_authors(page: Page, *, card_index: int = 0) -> list[str]:
    """Get author names from comments on an annotation card.

    Automatically expands the card if collapsed, since comments
    are inside the detail section.
    """
    expand_card(page, card_index)

    card = page.locator(ANNOTATION_CARD).nth(card_index)
    labels = card.locator("[data-testid='comment-author']")
    return [labels.nth(i).inner_text() for i in range(labels.count())]


def count_comment_delete_buttons(page: Page, *, card_index: int = 0) -> int:
    """Count visible delete buttons on an annotation card.

    Automatically expands the card if collapsed, since delete
    buttons are inside the detail section.
    """
    expand_card(page, card_index)

    card = page.locator(ANNOTATION_CARD).nth(card_index)
    return card.locator("[data-testid='comment-delete']").count()
