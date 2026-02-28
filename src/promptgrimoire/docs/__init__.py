"""Documentation generation package.

Public API for the Guide DSL and screenshot utilities.
"""

from promptgrimoire.docs.guide import Guide
from promptgrimoire.docs.screenshot import capture_screenshot, trim_whitespace

__all__ = ["Guide", "capture_screenshot", "trim_whitespace"]
