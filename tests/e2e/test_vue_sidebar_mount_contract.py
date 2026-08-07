"""Vue sidebar mount-contract regression test.

Asserts that ``window.__annotationCardsEpoch`` becomes >= 1 shortly after
the Vue annotation sidebar mounts with a non-empty ``items`` prop. If this
contract breaks (e.g. someone removes ``immediate: true`` from the watch
in ``annotationsidebar.js``) the four ``test_vue_sidebar_cross_tab.py``
tests go red under nightly ``e2e slow``; this test catches it in the
default CI lane at seconds-scale.

Runs against the lightweight ``/test/vue-sidebar-spike`` page, so there
is no database, no CRDT, and no authenticated workspace needed.

Background: see ``docs/investigations/2026-04-24-vue-sidebar-epoch-missing.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from playwright.sync_api import Browser

pytestmark = [pytest.mark.e2e]


def test_epoch_becomes_one_on_mount(browser: Browser, app_server: str) -> None:
    """__annotationCardsEpoch must be >= 1 within 5 s of sidebar mount.

    The spike page renders the Vue sidebar with two highlights. The watch
    callback at ``annotationsidebar.js:268-283`` increments the epoch
    whenever ``props.items`` is observed. With ``immediate: true`` the
    callback fires once on mount; without it, the callback never fires on
    cold load.
    """
    context = browser.new_context()
    page = context.new_page()
    try:
        _authenticate_page(page, app_server)
        page.goto(f"{app_server}/test/vue-sidebar-spike")
        page.wait_for_selector("[data-testid='annotation-card']", timeout=15_000)
        # wait_for_function is the assertion: it raises TimeoutError if
        # the epoch never reaches 1. No page.evaluate() needed (and forbidden
        # by tests/unit/test_e2e_compliance.py policy).
        page.wait_for_function(
            "() => (window.__annotationCardsEpoch || 0) >= 1",
            timeout=5_000,
        )
    finally:
        page.goto("about:blank")
        page.close()
        context.close()
