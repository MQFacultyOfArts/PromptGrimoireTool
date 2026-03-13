"""Guide DSL context managers for documentation generation.

Provides ``Guide`` and ``Step`` context managers that build structured
markdown documents with embedded screenshot references, driven by a
Playwright ``Page`` instance.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Self

from promptgrimoire.docs.screenshot import (
    capture_screenshot,
    generate_thumbnail,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from types import TracebackType

    from playwright.sync_api import Page

#: Default inline thumbnail width in pixels.  Full-res images are
#: shown on click via glightbox.
THUMBNAIL_WIDTH: int = 480


class Guide:
    """Context manager for a single guide document.

    Screenshots are saved as full-res PNGs with width-constrained
    thumbnails for inline display.  Markdown links the thumbnail
    to the full image; glightbox opens full-res on click.

    Usage::

        with Guide("Getting Started", output_dir, page) as guide:
            with guide.step("Login") as g:
                g.note("Navigate to the login page.")
                g.screenshot("login form", highlight=["login-btn"])
    """

    def __init__(
        self,
        title: str,
        output_dir: Path,
        page: Page,
        *,
        screenshot_subdir: str = "screenshots",
        thumbnail_width: int = THUMBNAIL_WIDTH,
    ) -> None:
        self._title = title
        self._output_dir = output_dir
        self._page = page
        self._screenshot_subdir = screenshot_subdir
        self._thumbnail_width = thumbnail_width
        self._buffer: list[str] = []
        self._screenshot_counter: int = 0

    @property
    def _slug(self) -> str:
        """Derive a filename slug from the title.

        Lowercase, spaces to hyphens, strip non-alphanumeric
        (except hyphens).
        """
        slug = self._title.lower().replace(" ", "-")
        return re.sub(r"[^a-z0-9-]", "", slug)

    def __enter__(self) -> Self:
        screenshot_dir = self._output_dir / self._screenshot_subdir
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        # Remove stale screenshots from previous runs so the
        # directory only contains images referenced by the
        # current markdown.
        for old in screenshot_dir.glob(f"{self._slug}-*.png"):
            old.unlink()
        self._append(f"# {self._title}\n")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> bool:
        md_path = self._output_dir / f"{self._slug}.md"
        md_path.write_text("\n".join(self._buffer))
        return False

    def section(self, heading: str) -> None:
        """Emit a ``## section`` heading for grouping steps."""
        self._append(f"## {heading}\n")

    def step(self, heading: str, *, level: int = 2, text_only: bool = False) -> Step:
        """Create a ``Step`` context manager bound to this guide.

        When ``text_only=True``, the step will NOT auto-capture a
        screenshot on exit.  Use this for entries that contain only
        narrative text and no browser interaction.
        """
        return Step(self, heading, level=level, text_only=text_only)

    def subheading(self, heading: str, *, level: int = 3) -> None:
        """Emit a sub-heading within a step (default ``###``)."""
        prefix = "#" * level
        self._append(f"{prefix} {heading}\n")

    def _append(self, line: str) -> None:
        """Append a line to the internal markdown buffer."""
        self._buffer.append(line)

    def note(self, text: str) -> None:
        """Append a narrative paragraph to the markdown buffer."""
        self._append(f"{text}\n")

    def screenshot(
        self,
        caption: str = "",
        *,
        highlight: Sequence[str] = (),
        focus: str | None = None,
        trim: bool = True,
    ) -> Path:
        """Capture a screenshot with thumbnail for inline display.

        Saves full-res PNG and a width-constrained thumbnail.
        Emits ``[![caption](thumb)](full)`` so glightbox opens
        the full image on click.

        Returns the path to the full-res screenshot file.
        """
        self._screenshot_counter += 1
        idx = f"{self._screenshot_counter:02d}"
        full_name = f"{self._slug}-{idx}.png"
        thumb_name = f"{self._slug}-{idx}-thumb.png"
        ss_dir = self._output_dir / self._screenshot_subdir

        full_path = ss_dir / full_name
        capture_screenshot(
            self._page,
            full_path,
            highlight=highlight,
            focus=focus,
            trim=trim,
        )

        thumb_path = ss_dir / thumb_name
        generate_thumbnail(
            full_path,
            thumb_path,
            max_width=self._thumbnail_width,
        )

        sub = self._screenshot_subdir
        self._append(f"[![{caption}]({sub}/{thumb_name})]({sub}/{full_name})\n")
        return full_path


class Step:
    """Context manager for a guide step.

    On entry, appends a heading to the guide's buffer at the
    configured ``level`` (default ``##``).  On exit (if no exception
    and no explicit screenshot was taken), auto-captures a screenshot.
    Steps with explicit screenshots skip the auto-capture to avoid
    redundant images.  Returns the parent ``Guide`` from ``__enter__``
    so callers can use ``with guide.step("...") as g:`` and call
    ``g.note()``, etc.
    """

    def __init__(
        self,
        guide: Guide,
        heading: str,
        *,
        level: int = 2,
        text_only: bool = False,
    ) -> None:
        self._guide = guide
        self._heading = heading
        self._level = level
        self._text_only = text_only
        self._screenshot_count_at_entry: int = 0

    def __enter__(self) -> Guide:
        prefix = "#" * self._level
        self._guide._append(f"{prefix} {self._heading}\n")
        self._screenshot_count_at_entry = self._guide._screenshot_counter
        return self._guide

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> bool:
        if (
            exc_type is None
            and not self._text_only
            and self._guide._screenshot_counter == self._screenshot_count_at_entry
        ):
            # Auto-capture only if no explicit screenshot was
            # taken during this step and step is not text-only.
            self._guide.screenshot(caption=self._heading)
        return False
