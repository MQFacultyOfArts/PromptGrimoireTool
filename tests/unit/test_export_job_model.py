"""Unit tests for ExportJob and ExportJobStatus model definitions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptgrimoire.db.models import ExportJob, ExportJobStatus


class TestExportJobStatus:
    """Tests for ExportJobStatus reference table model."""

    def test_instantiates_with_name(self) -> None:
        """ExportJobStatus stores a name string as primary key."""
        status = ExportJobStatus(name="queued")
        assert status.name == "queued"

    def test_description_defaults_to_empty(self) -> None:
        """ExportJobStatus.description defaults to empty string."""
        status = ExportJobStatus(name="running")
        assert status.description == ""

    def test_stores_description(self) -> None:
        """ExportJobStatus preserves a provided description."""
        status = ExportJobStatus(name="failed", description="Job encountered an error")
        assert status.description == "Job encountered an error"


class TestExportJob:
    """Tests for ExportJob entity model."""

    def test_instantiates_with_required_fields(self) -> None:
        """ExportJob can be created with user_id, workspace_id, and payload."""
        uid = uuid4()
        wid = uuid4()
        job = ExportJob(user_id=uid, workspace_id=wid, payload={"format": "pdf"})
        assert job.user_id == uid
        assert job.workspace_id == wid
        assert job.payload == {"format": "pdf"}

    def test_default_id_is_uuid(self) -> None:
        """ExportJob gets an auto-generated UUID if not provided."""
        job = ExportJob(user_id=uuid4(), workspace_id=uuid4(), payload={})
        assert job.id is not None
        assert isinstance(job.id, UUID)

    def test_default_status_is_queued(self) -> None:
        """ExportJob.status defaults to 'queued'."""
        job = ExportJob(user_id=uuid4(), workspace_id=uuid4(), payload={})
        assert job.status == "queued"

    def test_created_at_set_by_default(self) -> None:
        """ExportJob.created_at is populated via _utcnow default factory."""
        before = datetime.now(UTC)
        job = ExportJob(user_id=uuid4(), workspace_id=uuid4(), payload={})
        after = datetime.now(UTC)
        assert job.created_at is not None
        assert isinstance(job.created_at, datetime)
        assert before <= job.created_at <= after

    def test_created_at_is_timezone_aware(self) -> None:
        """ExportJob.created_at should be timezone-aware UTC."""
        job = ExportJob(user_id=uuid4(), workspace_id=uuid4(), payload={})
        assert job.created_at.tzinfo == UTC

    def test_optional_fields_default_to_none(self) -> None:
        """Optional fields start as None."""
        job = ExportJob(user_id=uuid4(), workspace_id=uuid4(), payload={})
        assert job.download_token is None
        assert job.token_expires_at is None
        assert job.pdf_path is None
        assert job.error_message is None
        assert job.started_at is None
        assert job.completed_at is None
