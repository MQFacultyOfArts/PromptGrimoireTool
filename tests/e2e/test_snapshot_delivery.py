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
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.card_helpers import ensure_pabai_workspace
from tests.e2e.db_fixtures import grant_acl
from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range
from tests.e2e.snapshot_harness import start_snapshot_service, stop_snapshot_service

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page

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
def snapshot_service() -> Generator[str]:
    """Run the standalone snapshot service against the test database.

    Inherits the worker's environment (DATABASE__URL points at this
    file's cloned test DB) and pins the storage secret to the E2E app
    server's value so minted tokens verify.  The E2E app server runs on
    a random port; the bundle endpoint's CORS grant must name that
    actual origin, not the config default.
    """
    settings = get_settings()
    port = settings.snapshot.port
    process = start_snapshot_service(
        port=port,
        allow_origin=os.environ.get("E2E_BASE_URL", settings.snapshot.allow_origin),
    )
    yield f"http://localhost:{port}"
    stop_snapshot_service(process)


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
