"""Instructor setup guide — stub for Phase 2, replaced in Phase 3."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide

GUIDE_OUTPUT_DIR = Path("docs/guides")


def run_instructor_guide(page: Page, base_url: str) -> None:  # noqa: ARG001
    """Run the instructor setup guide, producing markdown and screenshots."""
    with (
        Guide("Instructor Setup", GUIDE_OUTPUT_DIR, page) as guide,
        guide.step("Placeholder") as g,
    ):
        g.note("This is a stub guide. Full content will be added in Phase 3.")
