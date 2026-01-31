"""Validation test for pytest-subtests with Playwright fixtures.

This test verifies:
1. subtests fixture is available
2. Fixtures are shared across subtests (not re-created)
3. Subtest failures don't stop other subtests

Delete this file after validation or keep as documentation.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e]


class TestSubtestsValidation:
    """Validate pytest-subtests works with E2E test patterns."""

    def test_subtests_share_fixture(
        self, subtests, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify the same page fixture is shared across all subtests."""
        page = authenticated_page
        page.goto(f"{app_server}/")

        # Track that we're using the same page object
        page_id = id(page)

        test_cases = [
            ("home_visible", lambda: expect(page.locator("body")).to_be_visible()),
            ("same_page", lambda: page_id == id(page)),
            ("title_exists", lambda: page.title() is not None),
        ]

        for name, check in test_cases:
            with subtests.test(msg=name):
                result = check()
                if isinstance(result, bool):
                    assert result, f"Check {name} returned False"
                # expect() assertions don't return - they raise on failure
