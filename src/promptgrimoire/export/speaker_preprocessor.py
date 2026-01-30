"""Speaker preprocessor for HTML conversation exports.

Detects conversation platform (Claude, Gemini, OpenAI, ScienceOS, AustLII)
and injects speaker labels for PDF export readability.
"""

from __future__ import annotations

from enum import Enum

from lxml import html as lxml_html
from lxml.html import HtmlElement


class Platform(Enum):
    """Supported conversation export platforms."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENAI = "openai"
    SCIENCEOS = "scienceos"
    AUSTLII = "austlii"
    UNKNOWN = "unknown"


# Platform detection markers: list of (marker_strings, platform) tuples
_PLATFORM_MARKERS: list[tuple[tuple[str, ...], Platform]] = [
    (
        ("font-user-message", "font-claude-response"),
        Platform.CLAUDE,
    ),
    (
        ("ng-version", "user-query-container"),
        Platform.GEMINI,
    ),
    (
        ("agent-turn", "user-message-bubble-color"),
        Platform.OPENAI,
    ),
    (
        ("tabler-icon-robot", "tabler-icon-medal"),
        Platform.SCIENCEOS,
    ),
    (
        ("the-document", "ribbon-jurisdiction"),
        Platform.AUSTLII,
    ),
]

# Speaker label selectors per platform: (user_xpath, assistant_xpath)
# Use parent selector "//.." for icon-based detection (ScienceOS)
_SPEAKER_SELECTORS: dict[Platform, tuple[str, str]] = {
    Platform.CLAUDE: (
        "//*[contains(@class, 'font-user-message')]",
        "//*[contains(@class, 'font-claude-response')]",
    ),
    Platform.GEMINI: (
        "//*[contains(@class, 'user-query-container')]",
        "//*[contains(@class, 'model-response-container')]",
    ),
    Platform.OPENAI: (
        "//*[contains(@class, 'items-end')]",
        "//*[contains(@class, 'agent-turn')]",
    ),
    Platform.SCIENCEOS: (
        "//*[contains(@class, 'tabler-icon-medal')]/..",
        "//*[contains(@class, 'tabler-icon-robot')]/..",
    ),
}


def detect_platform(html_content: str) -> Platform:
    """Detect the conversation platform from HTML structure.

    Args:
        html_content: Raw HTML string from conversation export.

    Returns:
        Detected Platform enum value.
    """
    if not html_content:
        return Platform.UNKNOWN

    for markers, platform in _PLATFORM_MARKERS:
        if any(marker in html_content for marker in markers):
            return platform

    return Platform.UNKNOWN


def _inject_label(element: HtmlElement, label: str) -> None:
    """Inject a speaker label at the start of an element.

    Args:
        element: The HTML element to modify.
        label: The label text (e.g., "User:" or "Assistant:").
    """
    strong = lxml_html.Element("strong")
    strong.text = label
    strong.tail = " "

    if len(element) > 0:
        element.insert(0, strong)
    else:
        original_text = element.text or ""
        element.text = None
        strong.tail = " " + original_text
        element.insert(0, strong)


def _inject_labels_for_selector(tree: HtmlElement, xpath: str, label: str) -> None:
    """Inject labels for all elements matching an XPath selector.

    Args:
        tree: The parsed HTML tree.
        xpath: XPath selector for elements to label.
        label: The label text to inject.
    """
    for elem in tree.xpath(xpath):
        if isinstance(elem, HtmlElement):
            _inject_label(elem, label)


def inject_speaker_labels(html_content: str, platform: Platform) -> str:
    """Inject User:/Assistant: labels into conversation turns.

    Args:
        html_content: Raw HTML string.
        platform: Detected platform for turn identification.

    Returns:
        HTML with speaker labels injected.
    """
    if platform in (Platform.UNKNOWN, Platform.AUSTLII):
        return html_content

    selectors = _SPEAKER_SELECTORS.get(platform)
    if selectors is None:
        return html_content

    try:
        tree = lxml_html.fromstring(html_content)
    except Exception:
        return html_content

    user_xpath, assistant_xpath = selectors
    _inject_labels_for_selector(tree, user_xpath, "User:")
    _inject_labels_for_selector(tree, assistant_xpath, "Assistant:")

    return lxml_html.tostring(tree, encoding="unicode")


def preprocess_speakers(html_content: str) -> str:
    """Main entry point for speaker preprocessing.

    Detects platform and injects speaker labels.

    Args:
        html_content: Raw HTML string.

    Returns:
        HTML with speaker labels injected (if applicable).
    """
    platform = detect_platform(html_content)
    return inject_speaker_labels(html_content, platform)
