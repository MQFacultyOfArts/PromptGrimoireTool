"""Guide DSL context managers for documentation generation.

Provides ``Guide`` and ``Step`` context managers that build structured
markdown documents with embedded screenshot references, driven by a
Playwright ``Page`` instance.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Self

from promptgrimoire.docs.screenshot import capture_screenshot

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from types import TracebackType

    from playwright.sync_api import Page


class Guide:
    """Context manager for a single guide document.

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
    ) -> None:
        self._title = title
        self._output_dir = output_dir
        self._page = page
        self._screenshot_subdir = screenshot_subdir
        self._buffer: list[str] = []
        self._screenshot_counter: int = 0

    @property
    def _slug(self) -> str:
        """Derive a filename slug from the title.

        Lowercase, spaces to hyphens, strip non-alphanumeric (except hyphens).
        """
        slug = self._title.lower().replace(" ", "-")
        return re.sub(r"[^a-z0-9-]", "", slug)

    def __enter__(self) -> Self:
        (self._output_dir / self._screenshot_subdir).mkdir(parents=True, exist_ok=True)
        self._append(f"# {self._title}\n")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        md_path = self._output_dir / f"{self._slug}.md"
        md_path.write_text("\n".join(self._buffer))
        return False

    def step(self, heading: str) -> Step:
        """Create a ``Step`` context manager bound to this guide."""
        return Step(self, heading)

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
        """Capture a screenshot and append a markdown image reference.

        Returns the path to the saved screenshot file.
        """
        self._screenshot_counter += 1
        filename = f"{self._slug}-{self._screenshot_counter:02d}.png"
        path = self._output_dir / self._screenshot_subdir / filename
        capture_screenshot(
            self._page, path, highlight=highlight, focus=focus, trim=trim
        )
        self._append(f"![{caption}]({self._screenshot_subdir}/{filename})\n")
        return path


class Step:
    """Context manager for a guide step.

    On entry, appends a ``## heading`` to the guide's buffer.
    On exit (if no exception), auto-captures a screenshot.
    Returns the parent ``Guide`` from ``__enter__`` so callers can
    use ``with guide.step("...") as g:`` and call ``g.note()``, etc.
    """

    def __init__(self, guide: Guide, heading: str) -> None:
        self._guide = guide
        self._heading = heading

    def __enter__(self) -> Guide:
        self._guide._append(f"## {self._heading}\n")
        return self._guide

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_type is None:
            # Auto-capture failures propagate — callers should handle Playwright
            # errors (e.g. browser crash, page closed) raised by guide.screenshot().
            self._guide.screenshot(caption=self._heading)
        return False
