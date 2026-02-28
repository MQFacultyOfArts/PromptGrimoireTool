"""Tests for the Guide DSL context managers.

Verifies:
- docs-platform-208.AC1.1: Guide creates output dir and writes markdown on exit
- docs-platform-208.AC1.2: Step appends ``## heading`` to buffer on entry
- docs-platform-208.AC1.3: ``guide.note(text)`` appends paragraphs to buffer
- docs-platform-208.AC1.4: ``guide.screenshot()`` captures PNG and appends image ref
- docs-platform-208.AC1.5: Step exit auto-captures a screenshot
- docs-platform-208.AC1.6: Multiple steps produce sequential headings and images
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path


class TestGuideContextManager:
    """Tests for the Guide context manager."""

    def test_creates_output_dir_and_writes_markdown(self, tmp_path: Path) -> None:
        """AC1.1: Guide creates output directory and writes .md file on exit."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()
        output_dir = tmp_path / "guide-output"

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = output_dir / "screenshots" / "test.png"
            with Guide("Test Guide", output_dir, mock_page):
                pass

        assert output_dir.exists()
        assert (output_dir / "screenshots").exists()

        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) == 1
        assert md_files[0].name == "test-guide.md"

        content = md_files[0].read_text()
        assert content.startswith("# Test Guide\n")

    def test_step_appends_heading(self, tmp_path: Path) -> None:
        """AC1.2: Step appends ``## heading`` to the guide buffer on entry."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = tmp_path / "shot.png"
            with Guide("Test", tmp_path, mock_page) as guide, guide.step("Login"):
                pass

        content = (tmp_path / "test.md").read_text()
        assert "## Login\n" in content

    def test_note_appends_text(self, tmp_path: Path) -> None:
        """AC1.3: ``guide.note(text)`` appends narrative paragraphs to buffer."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = tmp_path / "shot.png"
            with Guide("Test", tmp_path, mock_page) as guide:
                guide.note("This is a paragraph.")

        content = (tmp_path / "test.md").read_text()
        assert "This is a paragraph.\n" in content

    def test_screenshot_appends_image_ref(self, tmp_path: Path) -> None:
        """AC1.4: ``guide.screenshot()`` appends ``![caption](path)`` to buffer."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = tmp_path / "screenshots" / "test-01.png"
            with Guide("Test", tmp_path, mock_page) as guide:
                guide.screenshot("Login page")

        content = (tmp_path / "test.md").read_text()
        assert "![Login page](screenshots/test-01.png)\n" in content

    def test_screenshot_calls_capture(self, tmp_path: Path) -> None:
        """AC1.4: screenshot() delegates to capture_screenshot with correct args."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = tmp_path / "screenshots" / "test-01.png"
            with Guide("Test", tmp_path, mock_page) as guide:
                guide.screenshot("cap", highlight=["btn"], focus="el", trim=False)

        mock_cap.assert_called_once()
        _, kwargs = mock_cap.call_args
        assert kwargs["highlight"] == ["btn"]
        assert kwargs["focus"] == "el"
        assert kwargs["trim"] is False

    def test_step_exit_auto_captures_screenshot(self, tmp_path: Path) -> None:
        """AC1.5: Step exit auto-captures a screenshot without explicit call."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = tmp_path / "screenshots" / "test-01.png"
            with (
                Guide("Test", tmp_path, mock_page) as guide,
                guide.step("Do Something"),
            ):
                pass  # No explicit screenshot call

        # capture_screenshot should have been called once (auto-capture)
        mock_cap.assert_called_once()

    def test_multiple_steps_produce_sequential_content(self, tmp_path: Path) -> None:
        """AC1.6: Multiple steps produce sequential headings and image refs."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()
        call_count = 0

        def _fake_capture(_page: object, path: object, **_kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            return path

        with (
            patch(
                "promptgrimoire.docs.guide.capture_screenshot",
                side_effect=_fake_capture,
            ),
            Guide("Test", tmp_path, mock_page) as guide,
        ):
            with guide.step("Step One") as g:
                g.note("First step text.")
            with guide.step("Step Two") as g:
                g.note("Second step text.")

        content = (tmp_path / "test.md").read_text()

        # Both headings present in order
        pos_one = content.index("## Step One\n")
        pos_two = content.index("## Step Two\n")
        assert pos_one < pos_two

        # Both image references present
        assert "test-01.png" in content
        assert "test-02.png" in content

        # Image refs in order
        pos_img1 = content.index("test-01.png")
        pos_img2 = content.index("test-02.png")
        assert pos_img1 < pos_img2

        # Two screenshots captured (one per step exit)
        assert call_count == 2

    def test_step_does_not_capture_on_exception(self, tmp_path: Path) -> None:
        """Step exit does not auto-capture if an exception occurred."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with (
            patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap,
            contextlib.suppress(ValueError),
        ):
            mock_cap.return_value = tmp_path / "screenshots" / "test-01.png"
            with Guide("Test", tmp_path, mock_page) as guide, guide.step("Failing"):
                raise ValueError("boom")

        mock_cap.assert_not_called()

    def test_slug_derivation(self, tmp_path: Path) -> None:
        """Slug derived from title: lowercase, hyphens, no special chars."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()
        guide = Guide("Getting Started! (2026)", output_dir=tmp_path, page=mock_page)
        assert guide._slug == "getting-started-2026"

    def test_screenshot_counter_increments(self, tmp_path: Path) -> None:
        """Screenshot filenames use incrementing counter."""
        from promptgrimoire.docs.guide import Guide

        mock_page = MagicMock()

        with patch("promptgrimoire.docs.guide.capture_screenshot") as mock_cap:
            mock_cap.return_value = tmp_path / "screenshots" / "dummy.png"
            with Guide("Test", tmp_path, mock_page) as guide:
                guide.screenshot("first")
                guide.screenshot("second")

        # Two calls with incrementing filenames
        calls = mock_cap.call_args_list
        assert len(calls) == 2
        first_path = calls[0][0][1]  # second positional arg (path)
        second_path = calls[1][0][1]
        assert "test-01.png" in str(first_path)
        assert "test-02.png" in str(second_path)
