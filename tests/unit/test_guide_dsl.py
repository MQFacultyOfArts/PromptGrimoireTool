"""Unit tests for Guide DSL section/level/subheading features."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from promptgrimoire.docs.guide import Guide

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture
def guide(tmp_path: Path) -> Generator[Guide]:
    """Create a Guide with a mock Page for buffer-only tests.

    Patches ``Guide.screenshot`` so auto-capture on Step exit
    does not try to use the mock Page for real image operations.
    """
    mock_page = MagicMock()
    g = Guide("Test Guide", tmp_path, mock_page)
    # Manually enter the context to initialise the buffer.
    g.__enter__()
    with patch.object(g, "screenshot", return_value=tmp_path / "fake.png"):
        yield g


class TestSection:
    """Tests for Guide.section() method."""

    def test_section_emits_h2(self, guide: Guide) -> None:
        guide.section("Getting Started")
        assert "## Getting Started\n" in guide._buffer

    def test_section_appends_to_buffer(self, guide: Guide) -> None:
        guide.section("First")
        guide.section("Second")
        section_lines = [line for line in guide._buffer if line.startswith("## ")]
        assert section_lines == ["## First\n", "## Second\n"]


class TestStepLevel:
    """Tests for step() level parameter."""

    def test_step_default_emits_h2(self, guide: Guide) -> None:
        """Backward compatibility: default step still emits ##."""
        with guide.step("Login"):
            pass
        assert "## Login\n" in guide._buffer

    def test_step_level_3_emits_h3(self, guide: Guide) -> None:
        with guide.step("I want to log in", level=3):
            pass
        assert "### I want to log in\n" in guide._buffer

    def test_step_level_4_emits_h4(self, guide: Guide) -> None:
        with guide.step("Sub-entry", level=4):
            pass
        assert "#### Sub-entry\n" in guide._buffer


class TestSubheading:
    """Tests for Guide.subheading() method."""

    def test_subheading_default_emits_h3(self, guide: Guide) -> None:
        guide.subheading("Viewing Your Tags")
        assert "### Viewing Your Tags\n" in guide._buffer

    def test_subheading_level_4_emits_h4(self, guide: Guide) -> None:
        guide.subheading("Details", level=4)
        assert "#### Details\n" in guide._buffer

    def test_subheading_level_2_emits_h2(self, guide: Guide) -> None:
        guide.subheading("Big Heading", level=2)
        assert "## Big Heading\n" in guide._buffer
