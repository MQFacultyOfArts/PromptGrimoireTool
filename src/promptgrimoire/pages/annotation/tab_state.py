"""Per-document tab state for the annotation workspace.

Holds UI element references and rendering state for each source tab
in a multi-document workspace. Created in Phase 6, consumed in Phase 7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from nicegui import ui


@dataclass
class DocumentTabState:
    """Per-document state for a source tab in the annotation workspace."""

    document_id: UUID
    tab: ui.tab | None
    panel: ui.tab_panel | None
    document_container: ui.column | None = None
    cards_container: ui.element | None = None
    annotation_cards: dict[str, Any] = field(default_factory=dict)
    card_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    rendered: bool = False
    cards_epoch: int = 0
