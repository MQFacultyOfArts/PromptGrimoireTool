"""ScienceOS platform handler for HTML preprocessing.

Handles ScienceOS exports, which have:
- Mantine CSS classes with hash suffixes (e.g., _prompt_abc123)
- _prompt_ class pattern for user queries
- _markdown_ class pattern for model responses
- tabler-icon-robot-face SVG icons (alternative detection)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection patterns (either matches)
# Two detection patterns for backward compatibility:
# - _prompt_ is the primary Mantine CSS class pattern
# - tabler-icon-robot-face is present in ScienceOS UI and tested in test_css_fidelity.py
_PROMPT_PATTERN = re.compile(r'class="[^"]*_prompt_[^"]*"', re.IGNORECASE)
_TABLER_PATTERN = re.compile(r"tabler-icon-robot-face", re.IGNORECASE)


class ScienceOSHandler:
    """Handler for ScienceOS HTML exports."""

    name: str = "scienceos"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from ScienceOS.

        Detection is based on either:
        - '_prompt_' class pattern (Mantine CSS with hash suffixes)
        - 'tabler-icon-robot-face' SVG icon class
        """
        return bool(_PROMPT_PATTERN.search(html) or _TABLER_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Preprocess ScienceOS HTML.

        ScienceOS uses Mantine CSS classes as semantic markers,
        so minimal preprocessing needed. Chrome removal handled by
        common patterns.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # ScienceOS uses CSS class patterns as turn markers - no native labels
        pass

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for ScienceOS turn boundaries.

        ScienceOS uses Mantine CSS classes with hash suffixes.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*class="[^"]*_prompt_[^"]*"[^>]*>)',
            "assistant": r'(<[^>]*class="[^"]*_markdown_[^"]*"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = ScienceOSHandler()
