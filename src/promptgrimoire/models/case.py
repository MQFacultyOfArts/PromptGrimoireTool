"""Data models for legal case documents.

BriefTag enum and associated tag colors/shortcuts for case annotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BriefTag(StrEnum):
    """The 10 brief tags for categorizing highlights and brief sections."""

    JURISDICTION = "jurisdiction"
    PROCEDURAL_HISTORY = "procedural_history"
    LEGALLY_RELEVANT_FACTS = "legally_relevant_facts"
    LEGAL_ISSUES = "legal_issues"
    REASONS = "reasons"
    COURTS_REASONING = "courts_reasoning"
    DECISION = "decision"
    ORDER = "order"
    DOMESTIC_SOURCES = "domestic_sources"
    REFLECTION = "reflection"


# Colorblind-accessible palette for tags (tested with deuteranopia)
TAG_COLORS: dict[BriefTag, str] = {
    BriefTag.JURISDICTION: "#1f77b4",  # blue
    BriefTag.PROCEDURAL_HISTORY: "#ff7f0e",  # orange
    BriefTag.LEGALLY_RELEVANT_FACTS: "#2ca02c",  # green
    BriefTag.LEGAL_ISSUES: "#d62728",  # red
    BriefTag.REASONS: "#9467bd",  # purple
    BriefTag.COURTS_REASONING: "#8c564b",  # brown
    BriefTag.DECISION: "#e377c2",  # pink
    BriefTag.ORDER: "#7f7f7f",  # gray
    BriefTag.DOMESTIC_SOURCES: "#bcbd22",  # olive
    BriefTag.REFLECTION: "#17becf",  # cyan
}

# Keyboard shortcuts: 1-9 for first 9 tags, 0 for 10th (Reflection)
TAG_SHORTCUTS: dict[str, BriefTag] = {
    "1": BriefTag.JURISDICTION,
    "2": BriefTag.PROCEDURAL_HISTORY,
    "3": BriefTag.LEGALLY_RELEVANT_FACTS,
    "4": BriefTag.LEGAL_ISSUES,
    "5": BriefTag.REASONS,
    "6": BriefTag.COURTS_REASONING,
    "7": BriefTag.DECISION,
    "8": BriefTag.ORDER,
    "9": BriefTag.DOMESTIC_SOURCES,
    "0": BriefTag.REFLECTION,
}


@dataclass
class ParsedRTF:
    """Result of parsing an RTF file for case brief annotation.

    Attributes:
        original_blob: Raw RTF file content as bytes for DB storage.
        html: LibreOffice HTML output for faithful browser rendering.
        source_filename: Original filename for metadata.
    """

    original_blob: bytes
    html: str
    source_filename: str
