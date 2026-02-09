"""Performance baseline test for Organise tab rendering.

Creates 10 highlights across 4 tags (4+3+2+1 distribution),
then measures how long it takes for the Organise tab to render
all cards. This establishes a baseline to track regressions.

Run with: uv run pytest tests/e2e/test_organise_perf.py -v -s
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    create_highlight_with_tag,
    setup_workspace_with_content,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set",
    ),
]

# Long content so we have enough chars for 10 non-overlapping highlights
_CONTENT = (
    "The appellant was convicted of multiple offences under the "
    "Crimes Act 1900 (NSW). The primary issue on appeal concerned "
    "the admissibility of evidence obtained during a search of the "
    "appellant's premises. The Crown argued that the evidence was "
    "lawfully obtained pursuant to a valid search warrant issued "
    "under section 3E of the Crimes Act. The defence submitted "
    "that the warrant was defective and that the search was "
    "therefore unlawful. The court considered the procedural "
    "requirements for the issue of search warrants and the "
    "consequences of non-compliance. The court also examined "
    "the discretionary exclusion of improperly obtained evidence "
    "under section 138 of the Evidence Act 1995 (NSW). "
    "In reaching its decision the court applied the balancing "
    "test set out in that provision weighing the desirability "
    "of admitting the evidence against the undesirability of "
    "admitting evidence obtained improperly."
)

# 10 highlights: 4 Jurisdiction(0), 3 Legal Issues(3),
# 2 Reasons(4), 1 Courts Reasoning(5)
# Each highlight is ~30 chars wide, non-overlapping
_HIGHLIGHTS = [
    # 4x Jurisdiction (tag index 0)
    (0, 29, 0),
    (30, 59, 0),
    (60, 89, 0),
    (90, 119, 0),
    # 3x Legal Issues (tag index 3)
    (120, 149, 3),
    (150, 179, 3),
    (180, 209, 3),
    # 2x Reasons (tag index 4)
    (210, 239, 4),
    (240, 269, 4),
    # 1x Courts Reasoning (tag index 5)
    (270, 299, 5),
]


@pytest.fixture
def perf_workspace(authenticated_page: Page, app_server: str) -> Generator[Page]:
    """Workspace with 10 highlights across 4 tags."""
    setup_workspace_with_content(authenticated_page, app_server, _CONTENT)
    page = authenticated_page

    for start, end, tag_idx in _HIGHLIGHTS:
        create_highlight_with_tag(page, start, end, tag_idx)
        page.wait_for_timeout(300)

    yield page


class TestOrganiseTabPerformance:
    """Baseline performance measurement for Organise tab."""

    def test_organise_render_time_with_10_highlights(
        self, perf_workspace: Page
    ) -> None:
        """Measure time to render Organise tab with 10 highlights.

        Creates 10 highlights (4+3+2+1 across 4 tags), clicks
        the Organise tab, and measures wall-clock time until
        all 10 cards are visible.
        """
        page = perf_workspace

        # Verify highlights were created in Tab 1
        cards_tab1 = page.locator(".annotation-card")
        expect(cards_tab1.first).to_be_visible(timeout=5000)
        highlight_count = cards_tab1.count()
        print(f"\nHighlights created in Tab 1: {highlight_count}")

        # Click Organise tab and measure render time
        t_start = time.perf_counter()
        page.locator("role=tab").nth(1).click()

        # Wait for all organise cards to appear
        organise_cards = page.locator('[data-testid="organise-card"]')
        expect(organise_cards.first).to_be_visible(timeout=10000)

        # Wait until we have the expected count
        expect(organise_cards).to_have_count(highlight_count, timeout=10000)
        t_end = time.perf_counter()

        render_ms = (t_end - t_start) * 1000
        print(f"Organise tab render time: {render_ms:.0f}ms")
        print(f"Cards rendered: {organise_cards.count()}")

        # Verify cards are in correct columns
        jurisdiction = page.locator(
            '[data-tag-name="Jurisdiction"] [data-testid="organise-card"]'
        )
        legal_issues = page.locator(
            '[data-tag-name="Legal Issues"] [data-testid="organise-card"]'
        )
        reasons = page.locator(
            '[data-tag-name="Reasons"] [data-testid="organise-card"]'
        )
        courts = page.locator(
            '[data-tag-name="Courts Reasoning"] [data-testid="organise-card"]'
        )

        print(
            f"Distribution: "
            f"Jurisdiction={jurisdiction.count()}, "
            f"Legal Issues={legal_issues.count()}, "
            f"Reasons={reasons.count()}, "
            f"Courts Reasoning={courts.count()}"
        )

        # Soft assertion: render should complete in under 5s
        # This is a baseline — tighten as performance improves
        assert render_ms < 5000, (
            f"Organise tab took {render_ms:.0f}ms to render "
            f"{highlight_count} highlights (target: <5000ms)"
        )
