"""Integration test for standalone worker job claiming.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Acceptance Criteria:
- infra-split.AC1.2: Create a queued ExportJob, run claim_next_job(),
  verify the job transitions to 'running' (claimed and processed).

NOTE: Full PDF production is a smoke test requiring LaTeX. This test
verifies the worker's DB interaction (claiming via FOR UPDATE SKIP LOCKED).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _create_user_and_workspace() -> tuple:
    """Create a test user and workspace, returning (user_id, workspace_id)."""
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.workspaces import create_workspace

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"standalone-worker-{tag}@test.local",
        display_name=f"Standalone Worker Test {tag}",
    )
    workspace = await create_workspace()
    return user.id, workspace.id


class TestWorkerClaimJob:
    """AC1.2: Standalone worker claims a queued job from the database."""

    @pytest.mark.asyncio
    async def test_claim_next_job_transitions_to_running(self) -> None:
        """A queued ExportJob is claimed and transitions to 'running'."""
        from promptgrimoire.db.export_jobs import create_export_job, get_job
        from tests.integration.conftest import claim_own_job

        user_id, workspace_id = await _create_user_and_workspace()

        payload = {
            "html_content": "<p>Standalone worker test</p>",
            "highlights": [],
            "tag_colours": {},
            "general_notes": "",
            "notes_latex": "",
            "filename": "standalone_test",
        }
        created = await create_export_job(user_id, workspace_id, payload)

        # Verify initial state is queued
        initial = await get_job(created.id)
        assert initial is not None
        assert initial.status == "queued"

        # Claim the job (scoped to our test's job ID for xdist safety)
        job = await claim_own_job({created.id})

        assert job is not None
        assert job.status == "running"
        assert job.started_at is not None

        # Verify via fresh DB read
        refreshed = await get_job(created.id)
        assert refreshed is not None
        assert refreshed.status == "running"

    @pytest.mark.asyncio
    async def test_claim_returns_none_when_no_queued_jobs(self) -> None:
        """claim_own_job returns None when no matching jobs are queued."""
        from tests.integration.conftest import claim_own_job

        # Use a random UUID that won't match any real job
        result = await claim_own_job({uuid4()})
        assert result is None
