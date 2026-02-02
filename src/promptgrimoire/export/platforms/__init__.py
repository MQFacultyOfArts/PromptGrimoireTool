"""Platform-specific HTML preprocessing for chatbot exports.

This module provides a Protocol + Registry pattern for handling different
AI platform exports (OpenAI, Claude, Gemini, AI Studio, ScienceOS).

Usage:
    from promptgrimoire.export.platforms import preprocess_for_export

    processed_html = preprocess_for_export(raw_html)
    # Or with explicit platform:
    processed_html = preprocess_for_export(raw_html, platform_hint="openai")
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

__all__ = ["PlatformHandler", "get_handler", "preprocess_for_export"]

logger = logging.getLogger(__name__)

# Registry of platform handlers, populated by autodiscovery
_handlers: dict[str, PlatformHandler] = {}


@runtime_checkable
class PlatformHandler(Protocol):
    """Protocol for platform-specific HTML preprocessing.

    Each platform handler must implement:
    - name: Identifier for the platform (e.g., "openai", "claude")
    - matches(): Detect if HTML is from this platform
    - preprocess(): Remove chrome, strip native labels, mark special blocks
    - get_turn_markers(): Return patterns for speaker label injection
    """

    name: str

    def matches(self, html: str) -> bool:
        """Return True if this handler should process the HTML."""
        ...

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome, strip native labels, mark special blocks.

        Modifies the tree in-place.
        """
        ...

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for turn boundary detection.

        Returns:
            Dict with 'user' and 'assistant' keys mapping to regex patterns.
        """
        ...


def _discover_handlers() -> None:
    """Auto-discover all platform handlers in this package.

    Scans for modules with a `handler` attribute that implements PlatformHandler.
    Import failures are logged and skipped (don't crash the registry).
    """
    for _finder, name, _ispkg in pkgutil.iter_modules(__path__, f"{__name__}."):
        if name.endswith((".base", ".__init__")):
            continue
        try:
            module = importlib.import_module(name)
            if hasattr(module, "handler"):
                handler = module.handler
                if isinstance(handler, PlatformHandler):
                    _handlers[handler.name] = handler
                    logger.debug("Registered platform handler: %s", handler.name)
                else:
                    logger.warning(
                        "Module %s has 'handler' but doesn't implement PlatformHandler",
                        name,
                    )
        except Exception:
            logger.exception("Failed to import platform handler module: %s", name)


def get_handler(html: str) -> PlatformHandler | None:
    """Find the appropriate handler for the given HTML.

    Args:
        html: Raw HTML from chatbot export.

    Returns:
        The matching PlatformHandler, or None if no handler matches.
    """
    for handler in _handlers.values():
        if handler.matches(html):
            return handler
    return None


def preprocess_for_export(html: str, platform_hint: str | None = None) -> str:
    """Main entry point: detect platform, preprocess, inject labels.

    Args:
        html: Raw HTML from chatbot export.
        platform_hint: Optional platform name to skip autodiscovery (e.g., "openai").
            Useful when autodiscovery fails or user knows the platform.

    Returns:
        Processed HTML ready for LaTeX conversion, or unchanged HTML if
        no handler matches (graceful degradation).
    """
    from selectolax.lexbor import LexborHTMLParser  # noqa: PLC0415

    if platform_hint:
        handler = _handlers.get(platform_hint)
        if handler is None:
            logger.warning(
                "Unknown platform_hint '%s', falling back to autodiscovery",
                platform_hint,
            )
            handler = get_handler(html)
    else:
        handler = get_handler(html)

    if handler is None:
        logger.debug("No platform handler matched, returning HTML unchanged")
        return html

    tree = LexborHTMLParser(html)
    handler.preprocess(tree)
    # Label injection will be added in Phase 4
    return tree.html or html


# Run autodiscovery on module import
_discover_handlers()
