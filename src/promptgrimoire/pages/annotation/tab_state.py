"""Per-document tab state for the annotation workspace.

Holds UI element references and rendering state for each source tab
in a multi-document workspace. Every field that
``_render_document_with_highlights`` writes to ``PageState`` must have
a corresponding slot here so the save/restore cycle on tab switch
preserves per-document isolation.
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
    # Card state — Vue sidebar re-renders from props
    cards_container: ui.element | None = None
    cards_epoch: int = 0
    # Document content state
    document_chars: list[str] | None = None
    paragraph_map: dict[str, int] = field(default_factory=dict)
    document_content: str = ""
    auto_number_paragraphs: bool = True
    # Per-document HTML element IDs (parameterised to prevent cross-tab collisions)
    doc_container_id: str = "doc-container"
    ann_container_id: str = "annotations-container"
    highlight_menu_id: str = "highlight-menu"
    # UI element refs (per-document DOM elements)
    doc_container: ui.element | None = None
    highlight_style: ui.element | None = None
    highlight_menu: ui.element | None = None
    toolbar_container: Any = None
    # Rendering flag
    rendered: bool = False
