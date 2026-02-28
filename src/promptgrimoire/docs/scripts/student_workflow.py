"""Student workflow guide — stub for Phase 2, replaced in Phase 4."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide

GUIDE_OUTPUT_DIR = Path("docs/guides")


def run_student_guide(page: Page, base_url: str) -> None:  # noqa: ARG001
    """Run the student workflow guide, producing markdown and screenshots."""
    with (
        Guide("Student Workflow", GUIDE_OUTPUT_DIR, page) as guide,
        guide.step("Placeholder") as g,
    ):
        g.note("This is a stub guide. Full content will be added in Phase 4.")
