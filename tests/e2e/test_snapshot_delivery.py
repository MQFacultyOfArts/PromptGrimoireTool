"""E2E: initial annotation snapshot delivered from the standalone service.

The one-session go/no-go boundary for snapshot delivery (see
docs/design-notes/2026-08-16-initial-snapshot-delivery.md): with
SNAPSHOT__ENABLED the annotation page must reach the same
document/highlight/sidebar/annotation-ready contract as the NiceGUI
payload path, with the bundle observably fetched from the snapshot
service, and CRDT writes must continue to work after mount.

The app server reads SNAPSHOT__* at launch, so this file needs the flag
in the environment and is excluded from the default CI lane:

    SNAPSHOT__ENABLED=true uv run grimoire e2e run \
        tests/e2e/test_snapshot_delivery.py

The snapshot service itself is started by a module fixture against the
same test database.  Highlight-registration internals (CSS.highlights,
card epochs) are covered by the vitest bootstrap tests; this file stays
on Playwright-visible surfaces only.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import Route, expect

from promptgrimoire.config import get_settings
from tests.e2e.card_helpers import ensure_pabai_workspace
from tests.e2e.db_fixtures import grant_acl
from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.noci,
    # Service startup + Pabai rehydration + bundle mount exceed the 30 s
    # global pytest-timeout; the thread method hard-exits xdist workers.
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        os.environ.get("SNAPSHOT__ENABLED") != "true",
        reason="requires SNAPSHOT__ENABLED=true (app server reads it at launch)",
    ),
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
]

ANNOTATION_CARD = "[data-testid='annotation-card']"


@pytest.fixture(scope="module")
def snapshot_service() -> str:
    """URL of the snapshot service.

    The process itself is started by the shared conftest autouse fixture
    (active because this file requires SNAPSHOT__ENABLED=true).
    """
    return f"http://localhost:{get_settings().snapshot.port}"


def _open_pabai(page: Page, app_server: str, snapshot_service: str) -> None:
    """Authenticate, grant access, and load the Pabai workspace via bundle.

    The ``expect_response`` context is the positive evidence that the
    document arrived from the snapshot service, not the NiceGUI outbox.
    """
    email = f"snapshot-{uuid4().hex[:8]}@e2e.test"
    # Surface browser-side evidence in captured output on failure.
    page.on("console", lambda msg: print(f"[browser {msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"[pageerror] {err}"))
    page.on(
        "requestfailed",
        lambda req: print(f"[requestfailed] {req.url}: {req.failure}"),
    )
    page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(f"{app_server}/**")
    workspace_id = ensure_pabai_workspace()
    grant_acl(email, workspace_id)

    with page.expect_response(
        lambda r: f"{snapshot_service}/snapshot?" in r.url, timeout=30000
    ) as bundle_response:
        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
    assert bundle_response.value.status == 200


class TestSnapshotDelivery:
    def test_bundle_mount_reaches_annotation_contract(
        self, fresh_page: Page, app_server: str, snapshot_service: str
    ) -> None:
        """Bundle fetch fills the document and sidebar, then signals ready."""
        page = fresh_page
        _open_pabai(page, app_server, snapshot_service)

        # Readiness marker is appended by the bootstrap after mount.
        page.get_by_test_id("annotation-ready").wait_for(
            state="attached", timeout=30000
        )

        # Skeleton replaced by the real document.
        expect(page.get_by_test_id("snapshot-loading")).to_have_count(0)
        container = page.get_by_test_id("doc-container")
        assert len(container.inner_text()) > 10000, (
            "Pabai document text missing from doc-container"
        )

        # Sidebar items delivered by the bundle (Pabai carries 190
        # highlights on the main document; the assertion guards the
        # boundary without pinning the fixture's exact count).
        cards = page.locator(ANNOTATION_CARD)
        assert cards.count() >= 100, f"sidebar cards missing: {cards.count()}"

    def test_crdt_write_after_bundle_mount(
        self, fresh_page: Page, app_server: str, snapshot_service: str
    ) -> None:
        """Post-mount CRDT writes flow through NiceGUI and win over the bundle."""
        page = fresh_page
        _open_pabai(page, app_server, snapshot_service)
        page.get_by_test_id("annotation-ready").wait_for(
            state="attached", timeout=30000
        )

        cards = page.locator(ANNOTATION_CARD)
        before = cards.count()

        highlight_range = find_text_range(page, "Torres Strait Islands")
        create_highlight_with_tag(page, *highlight_range, tag_index=0)

        # The refresh push is a genuine server push: the new card comes
        # from server-authoritative items replacing the bundle state.
        expect(cards).to_have_count(before + 1, timeout=15000)

    def test_stale_bundle_converges_to_live_state(
        self,
        fresh_page: Page,
        app_server: str,
        snapshot_service: str,
        browser: Browser,
    ) -> None:
        """Adversarial freshness probe for the mint-to-mount race (#533).

        The bundle is built from persisted CRDT state, so a mutation that
        lands between the bundle build and the client mount produces a
        stale mount.  The design's healing claim is server-push-wins:
        the first genuine server props push overrides bundle state, so
        the page must converge to the live state without a reload.

        This test forces the widest possible version of that race,
        deterministically: client A's bundle request is stalled at the
        route layer; the test fetches the bundle itself (stale by
        construction, before the mutation); client B then creates a
        highlight; only afterwards is A's request fulfilled with the
        pre-mutation body.  A pass is positive evidence the healing
        refresh works; a failure means #533 needs a staleness mechanism,
        not a bigger timeout.
        """
        page = fresh_page
        email = f"snapshot-stale-a-{uuid4().hex[:8]}@e2e.test"
        page.goto(f"{app_server}/auth/callback?token=mock-token-{email}")
        page.wait_for_url(f"{app_server}/**")
        workspace_id = ensure_pabai_workspace()
        grant_acl(email, workspace_id)

        # Stall A's bundle fetch: capture the route, fulfil it later.
        held: list[Route] = []

        def stall(route: Route) -> None:
            # Playwright cannot wrap a builtin method (list.append) as a
            # route handler; it needs a plain function to instrument.
            held.append(route)

        page.route(f"{snapshot_service}/snapshot?*", stall)
        with page.expect_request(f"{snapshot_service}/snapshot?*", timeout=30000):
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")

        # Build the stale bundle NOW, before the mutation, from the URL
        # the page itself was armed with (same token), so staleness is
        # guaranteed by construction rather than by timing.  The stalled
        # route is not consulted here: expect_request unblocks on the
        # request event, which can precede the route handler running.
        bundle_url = page.get_by_test_id("doc-container").get_attribute(
            "data-snapshot-url"
        )
        assert bundle_url, "doc-container was not armed with a bundle URL"
        stale = page.request.get(bundle_url)
        assert stale.status == 200
        stale_item_count = len(stale.json()["items"])

        # Client B mutates the workspace while A is still unmounted.
        context_b = browser.new_context()
        try:
            page_b = context_b.new_page()
            email_b = f"snapshot-stale-b-{uuid4().hex[:8]}@e2e.test"
            page_b.goto(f"{app_server}/auth/callback?token=mock-token-{email_b}")
            page_b.wait_for_url(f"{app_server}/**")
            grant_acl(email_b, workspace_id)
            page_b.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page_b.get_by_test_id("annotation-ready").wait_for(
                state="attached", timeout=30000
            )
            cards_b = page_b.locator(ANNOTATION_CARD)
            before_b = cards_b.count()
            highlight_range = find_text_range(page_b, "Torres Strait Islands")
            create_highlight_with_tag(page_b, *highlight_range, tag_index=0)
            expect(cards_b).to_have_count(before_b + 1, timeout=15000)

            # Deliver the pre-mutation bundle to A: a stale mount.  By
            # now B's whole authenticated flow has pumped the event
            # loop, so the stalled route handler has long since run.
            assert held, "bundle request was never captured by the route"
            held[0].fulfill(
                status=200,
                headers=dict(stale.headers),
                body=stale.body(),
            )
            page.get_by_test_id("annotation-ready").wait_for(
                state="attached", timeout=30000
            )

            # Convergence: A must show B's highlight without a reload,
            # whichever order the stale bundle and the refresh push
            # arrived in.  The expected count is anchored to the stale
            # bundle (pre-mutation) plus B's one addition.
            expect(page.locator(ANNOTATION_CARD)).to_have_count(
                stale_item_count + 1, timeout=20000
            )
        finally:
            context_b.close()
