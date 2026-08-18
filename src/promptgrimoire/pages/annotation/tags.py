"""Tag-agnostic abstraction for annotation tag metadata.

Relocated to ``promptgrimoire.annotation_core`` so standalone processes
(the snapshot delivery worker) can use it without importing NiceGUI via
this package's ``__init__``.  This module re-exports the names so
page-side callers are unchanged.
"""

from __future__ import annotations

from promptgrimoire.annotation_core import (
    TagInfo,
    workspace_tags,
    workspace_tags_from_crdt,
)

__all__ = ["TagInfo", "workspace_tags", "workspace_tags_from_crdt"]
