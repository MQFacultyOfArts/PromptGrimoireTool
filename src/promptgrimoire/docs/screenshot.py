"""Screenshot capture, highlight injection, thumbnails, and trimming.

Provides utilities for the Guide DSL to capture annotated, trimmed
screenshots during documentation generation via Playwright.

Public API (exported via docs/__init__.py):
    capture_screenshot   -- Full orchestration: highlight, capture, trim, write.
    generate_thumbnail   -- Resize a full-res PNG to a width-constrained thumbnail.
    trim_whitespace      -- Pillow-based margin removal from PNG bytes.

Internal helpers (not exported; used by capture_screenshot):
    highlight_elements   -- Inject a <style> element into the live Playwright page.
    remove_highlight     -- Remove a previously injected <style> element.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image, ImageChops
from PIL.Image import Resampling

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from playwright.sync_api import Page


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


def generate_thumbnail(
    source: Path,
    dest: Path,
    *,
    max_width: int = 480,
) -> Path:
    """Resize a full-res PNG to a width-constrained thumbnail.

    Maintains aspect ratio.  If the source image is already narrower
    than *max_width*, it is copied unchanged.

    Returns *dest* for chaining convenience.
    """
    img = Image.open(source)
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    dest.write_bytes(buf.getvalue())
    return dest


def highlight_elements(page: Page, test_ids: Sequence[str]) -> list[str] | None:
    """Inject highlight overlays for elements matching ``data-testid`` prefixes.

    Creates absolutely-positioned ``<div>`` elements appended to ``<body>``
    with high ``z-index``, so highlights float above all content regardless
    of parent ``overflow`` settings.  Returns a list of overlay element IDs
    for later removal via :func:`remove_highlight`.

    If *test_ids* is empty, returns ``None``.
    """
    if not test_ids:
        return None

    # JS that creates a fixed-position overlay div per matched element.
    overlay_ids: list[str] = []
    for tid in test_ids:
        oid = f"_hl_{tid}"
        overlay_ids.append(oid)
        page.evaluate(
            """([selector, overlayId]) => {
                document.querySelectorAll(selector).forEach((el, i) => {
                    const rect = el.getBoundingClientRect();
                    const pad = 4;
                    const div = document.createElement('div');
                    div.id = overlayId + '_' + i;
                    div.className = '__doc_highlight__';
                    Object.assign(div.style, {
                        position: 'fixed',
                        top: (rect.top - pad) + 'px',
                        left: (rect.left - pad) + 'px',
                        width: (rect.width + pad * 2) + 'px',
                        height: (rect.height + pad * 2) + 'px',
                        border: '3px solid #e53e3e',
                        borderRadius: '6px',
                        zIndex: '999999',
                        pointerEvents: 'none',
                    });
                    document.body.appendChild(div);
                });
            }""",
            [f'[data-testid^="{tid}"]', oid],
        )
    return overlay_ids


def remove_highlight(page: Page, overlay_ids: list[str] | None) -> None:
    """Remove previously injected highlight overlay ``<div>`` elements.

    If *overlay_ids* is ``None``, this is a no-op.
    """
    if overlay_ids is None:
        return
    page.evaluate(
        """() => {
            document.querySelectorAll('.__doc_highlight__').forEach(
                el => el.remove()
            );
        }"""
    )


def capture_screenshot(
    page: Page,
    path: Path,
    *,
    highlight: Sequence[str] = (),
    focus: str | None = None,
    trim: bool = True,
    settle_ms: int = 500,
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
    settle_ms:
        Milliseconds to wait before capture so CSS transitions (e.g.
        Quasar floating labels) finish animating.

    Returns
    -------
    Path
        The *path* argument, for chaining convenience.
    """
    overlay_ids = highlight_elements(page, highlight)

    try:
        if settle_ms > 0:
            page.wait_for_timeout(settle_ms)
        if focus is not None:
            image_bytes = page.get_by_test_id(focus).screenshot()
        else:
            image_bytes = page.screenshot()
    finally:
        remove_highlight(page, overlay_ids)

    if trim:
        image_bytes = trim_whitespace(image_bytes)

    path.write_bytes(image_bytes)
    return path
