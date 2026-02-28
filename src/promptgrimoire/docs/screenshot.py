"""Screenshot capture, CSS highlight injection, and whitespace trimming.

Provides utilities for the Guide DSL to capture annotated, trimmed
screenshots during documentation generation via Playwright.

Public API (exported via docs/__init__.py):
    capture_screenshot  -- Full orchestration: highlight, capture, trim, write.
    trim_whitespace     -- Pillow-based margin removal from PNG bytes.

Internal helpers (not exported; used by capture_screenshot):
    highlight_elements  -- Inject a <style> element into the live Playwright page.
    remove_highlight    -- Remove a previously injected <style> element.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image, ImageChops

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from playwright.sync_api import ElementHandle, Page


def trim_whitespace(image_bytes: bytes) -> bytes:
    """Remove empty white margins from a PNG image.

    Detects the bounding box of non-white content using
    ``ImageChops.difference()`` against a white background, then crops
    to that region.  If the image has no whitespace margins (bbox matches
    the full image), returns the input bytes unchanged.
    """
    img = Image.open(io.BytesIO(image_bytes))
    # Convert to RGB so ImageChops.difference() works for all input modes
    # (e.g. palette-mode 'P' images).  Playwright always outputs RGB/RGBA,
    # but this guard makes trim_whitespace robust to edge cases.
    img = img.convert("RGB")
    bg = Image.new(img.mode, img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()

    if bbox is None:
        # Entirely white image -- return as-is
        return image_bytes

    if bbox == (0, 0, img.size[0], img.size[1]):
        # Content fills the entire image -- no trimming needed
        return image_bytes

    cropped = img.crop(bbox)
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


def highlight_elements(page: Page, test_ids: Sequence[str]) -> ElementHandle | None:
    """Inject a ``<style>`` element highlighting elements by ``data-testid``.

    Applies ``outline: 3px solid #e53e3e; outline-offset: 2px;`` to each
    selector.  Returns the ``ElementHandle`` for later removal via
    :func:`remove_highlight`.  If *test_ids* is empty, returns ``None``.
    """
    if not test_ids:
        return None

    selectors = ", ".join(f'[data-testid="{tid}"]' for tid in test_ids)
    css = f"{selectors} {{ outline: 3px solid #e53e3e; outline-offset: 2px; }}"
    return page.add_style_tag(content=css)


def remove_highlight(page: Page, style_handle: ElementHandle | None) -> None:
    """Remove a previously injected highlight ``<style>`` element.

    If *style_handle* is ``None``, this is a no-op.
    """
    if style_handle is None:
        return
    # page.evaluate() with a JS arrow function is the documented Playwright way
    # to call methods on ElementHandles that have no Python-side equivalent
    # (ElementHandle has no .remove() method).  This is docs-generation library
    # code — not an E2E test — so JS injection via evaluate() is appropriate and
    # intentional.  See: https://playwright.dev/python/docs/api/class-page#page-evaluate
    page.evaluate("el => el.remove()", style_handle)


def capture_screenshot(
    page: Page,
    path: Path,
    *,
    highlight: Sequence[str] = (),
    focus: str | None = None,
    trim: bool = True,
) -> Path:
    """Capture a screenshot with optional highlight injection and trimming.

    Parameters
    ----------
    page:
        Playwright ``Page`` instance.
    path:
        Destination file path for the PNG.
    highlight:
        Sequence of ``data-testid`` values to outline before capture.
    focus:
        If provided, capture only the element matching this ``data-testid``
        via ``locator.screenshot()`` instead of a full-page capture.
    trim:
        If ``True``, remove empty white margins from the captured image.

    Returns
    -------
    Path
        The *path* argument, for chaining convenience.
    """
    style_handle = highlight_elements(page, highlight) if highlight else None

    try:
        if focus is not None:
            image_bytes = page.get_by_test_id(focus).screenshot()
        else:
            image_bytes = page.screenshot()
    finally:
        if style_handle is not None:
            remove_highlight(page, style_handle)

    if trim:
        image_bytes = trim_whitespace(image_bytes)

    path.write_bytes(image_bytes)
    return path
