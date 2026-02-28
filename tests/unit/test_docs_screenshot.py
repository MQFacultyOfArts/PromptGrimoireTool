"""Tests for the docs screenshot module.

Verifies:
- docs-platform-208.AC2.1: CSS injection adds outline to data-testid elements
- docs-platform-208.AC2.2: Injected style element is removed after capture
- docs-platform-208.AC2.3: Multiple elements highlighted simultaneously
- docs-platform-208.AC2.4: Highlighting non-existent data-testid is a no-op
- docs-platform-208.AC3.1: Pillow-based trimming removes empty margins
- docs-platform-208.AC3.2: Trimmed image retains all non-empty content
- docs-platform-208.AC3.3: Image with no margins is returned unchanged
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PIL import Image, ImageChops, ImageDraw

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers: create test PNG images
# ---------------------------------------------------------------------------


def _make_png_with_margins(
    content_size: tuple[int, int] = (50, 50),
    margin: int = 20,
    bg_color: tuple[int, int, int] = (255, 255, 255),
    fg_color: tuple[int, int, int] = (255, 0, 0),
) -> bytes:
    """Create a PNG with a coloured rectangle centred in a white background."""
    w = content_size[0] + 2 * margin
    h = content_size[1] + 2 * margin
    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [margin, margin, margin + content_size[0] - 1, margin + content_size[1] - 1],
        fill=fg_color,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_png_no_margins(
    size: tuple[int, int] = (50, 50),
    color: tuple[int, int, int] = (128, 64, 32),
) -> bytes:
    """Create a PNG filled entirely with a single colour (no margins)."""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ===========================================================================
# AC3: Whitespace trimming
# ===========================================================================


class TestTrimWhitespace:
    """Tests for trim_whitespace()."""

    def test_removes_white_margins(self) -> None:
        """AC3.1: Trimming removes empty margins from captured screenshots."""
        from promptgrimoire.docs.screenshot import trim_whitespace

        raw = _make_png_with_margins(content_size=(50, 50), margin=20)
        trimmed = trim_whitespace(raw)

        original = Image.open(io.BytesIO(raw))
        result = Image.open(io.BytesIO(trimmed))

        assert result.size[0] < original.size[0]
        assert result.size[1] < original.size[1]

    def test_retains_all_content(self) -> None:
        """AC3.2: Trimmed image retains all non-empty content (no content cropped)."""
        from promptgrimoire.docs.screenshot import trim_whitespace

        raw = _make_png_with_margins(content_size=(50, 50), margin=20)
        trimmed = trim_whitespace(raw)

        # Compute expected content bbox from original
        original = Image.open(io.BytesIO(raw))
        bg = Image.new(original.mode, original.size, (255, 255, 255))
        diff = ImageChops.difference(original, bg)
        bbox = diff.getbbox()
        assert bbox is not None
        expected_crop = original.crop(bbox)

        result = Image.open(io.BytesIO(trimmed))

        assert expected_crop.tobytes() == result.tobytes()

    def test_no_margins_returns_unchanged(self) -> None:
        """AC3.3: Image with no whitespace margins is returned unchanged."""
        from promptgrimoire.docs.screenshot import trim_whitespace

        raw = _make_png_no_margins(size=(50, 50), color=(128, 64, 32))
        trimmed = trim_whitespace(raw)

        # Bytes should be identical
        assert trimmed == raw


# ===========================================================================
# AC2: CSS highlight injection
# ===========================================================================


class TestHighlightElements:
    """Tests for highlight_elements() and remove_highlight()."""

    def test_injects_css_for_test_ids(self) -> None:
        """AC2.1: CSS injection adds outline to data-testid elements."""
        from promptgrimoire.docs.screenshot import highlight_elements

        mock_page = MagicMock()
        mock_handle = MagicMock()
        mock_page.add_style_tag.return_value = mock_handle

        result = highlight_elements(mock_page, ["btn-save", "input-name"])

        mock_page.add_style_tag.assert_called_once()
        content = mock_page.add_style_tag.call_args.kwargs["content"]

        assert '[data-testid="btn-save"]' in content
        assert '[data-testid="input-name"]' in content
        assert "outline" in content
        assert result is mock_handle

    def test_remove_highlight_calls_evaluate(self) -> None:
        """AC2.2: Injected style element is removed after capture."""
        from promptgrimoire.docs.screenshot import remove_highlight

        mock_page = MagicMock()
        mock_handle = MagicMock()

        remove_highlight(mock_page, mock_handle)

        mock_page.evaluate.assert_called_once_with("el => el.remove()", mock_handle)

    def test_multiple_elements_highlighted(self) -> None:
        """AC2.3: Multiple elements can be highlighted simultaneously."""
        from promptgrimoire.docs.screenshot import highlight_elements

        mock_page = MagicMock()
        mock_page.add_style_tag.return_value = MagicMock()

        highlight_elements(mock_page, ["a", "b", "c"])

        # Single style tag call (all selectors in one CSS block)
        mock_page.add_style_tag.assert_called_once()
        content = mock_page.add_style_tag.call_args.kwargs["content"]
        assert '[data-testid="a"]' in content
        assert '[data-testid="b"]' in content
        assert '[data-testid="c"]' in content

    def test_empty_test_ids_returns_none(self) -> None:
        """AC2.4: Highlighting with empty test_ids does not inject CSS."""
        from promptgrimoire.docs.screenshot import highlight_elements

        mock_page = MagicMock()

        result = highlight_elements(mock_page, [])

        mock_page.add_style_tag.assert_not_called()
        assert result is None

    def test_remove_highlight_none_handle_is_noop(self) -> None:
        """AC2.4: remove_highlight with None handle is a no-op."""
        from promptgrimoire.docs.screenshot import remove_highlight

        mock_page = MagicMock()

        remove_highlight(mock_page, None)

        mock_page.evaluate.assert_not_called()


# ===========================================================================
# capture_screenshot orchestration
# ===========================================================================


class TestCaptureScreenshot:
    """Tests for capture_screenshot() orchestration."""

    def test_full_page_capture_with_trim(self, tmp_path: Path) -> None:
        """Full-page screenshot is captured, trimmed, and written to path."""
        from promptgrimoire.docs.screenshot import capture_screenshot

        test_png = _make_png_with_margins(content_size=(30, 30), margin=10)
        mock_page = MagicMock()
        mock_page.screenshot.return_value = test_png

        out = tmp_path / "shot.png"
        result = capture_screenshot(mock_page, out)

        assert result == out
        assert out.exists()
        # Should be trimmed (smaller than original)
        saved = Image.open(out)
        original = Image.open(io.BytesIO(test_png))
        assert saved.size[0] < original.size[0]

    def test_capture_with_highlight_and_cleanup(self, tmp_path: Path) -> None:
        """Highlights are injected before capture and removed after."""
        from promptgrimoire.docs.screenshot import capture_screenshot

        test_png = _make_png_no_margins()
        mock_page = MagicMock()
        mock_page.screenshot.return_value = test_png
        mock_handle = MagicMock()
        mock_page.add_style_tag.return_value = mock_handle

        out = tmp_path / "shot.png"
        capture_screenshot(mock_page, out, highlight=["btn-1"])

        # Style was injected
        mock_page.add_style_tag.assert_called_once()
        # Style was removed
        mock_page.evaluate.assert_called_once_with("el => el.remove()", mock_handle)

    def test_capture_with_focus_uses_locator(self, tmp_path: Path) -> None:
        """Focus capture uses page.get_by_test_id().screenshot()."""
        from promptgrimoire.docs.screenshot import capture_screenshot

        test_png = _make_png_no_margins()
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.screenshot.return_value = test_png
        mock_page.get_by_test_id.return_value = mock_locator

        out = tmp_path / "shot.png"
        capture_screenshot(mock_page, out, focus="my-element")

        mock_page.get_by_test_id.assert_called_once_with("my-element")
        mock_locator.screenshot.assert_called_once()
        # page.screenshot should NOT have been called
        mock_page.screenshot.assert_not_called()

    def test_capture_no_trim(self, tmp_path: Path) -> None:
        """When trim=False, the image is written as-is."""
        from promptgrimoire.docs.screenshot import capture_screenshot

        test_png = _make_png_with_margins(content_size=(30, 30), margin=10)
        mock_page = MagicMock()
        mock_page.screenshot.return_value = test_png

        out = tmp_path / "shot.png"
        capture_screenshot(mock_page, out, trim=False)

        assert out.read_bytes() == test_png
