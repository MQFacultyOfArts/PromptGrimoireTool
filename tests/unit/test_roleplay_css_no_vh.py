"""Guard test: roleplay.css must not use hardcoded viewport-height values.

Flexbox layout should determine chat area height responsively.
Any ``height: Nvh`` or ``min-height: Nvh`` declaration is a regression
— except in ``.roleplay-bg`` which is a fixed full-screen background overlay.
"""

from __future__ import annotations

import re
from pathlib import Path

_CSS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "promptgrimoire"
    / "static"
    / "roleplay.css"
)

_VH_PATTERN = re.compile(r"(min-)?height\s*:\s*\d+vh")

# Match CSS rule blocks: selector { ... }
_RULE_PATTERN = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)

# Selectors allowed to use vh (fixed background overlay)
_VH_ALLOWED_SELECTORS = {".roleplay-bg"}


def test_no_viewport_height_in_roleplay_css() -> None:
    """Layout rules in roleplay.css must not use hardcoded vh heights."""
    css_text = _CSS_PATH.read_text()
    violations: list[str] = []

    for rule_match in _RULE_PATTERN.finditer(css_text):
        selector = rule_match.group(1).strip()
        body = rule_match.group(2)

        if any(allowed in selector for allowed in _VH_ALLOWED_SELECTORS):
            continue

        for vh_match in _VH_PATTERN.finditer(body):
            violations.append(f"{selector}: {vh_match.group()}")

    assert not violations, (
        f"Found viewport-height declarations in roleplay.css: {violations}. "
        "Use flexbox layout instead of hardcoded vh values."
    )
