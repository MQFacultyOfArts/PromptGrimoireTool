"""Serialise CRDT highlights into Vue sidebar item dicts.

Relocated to ``promptgrimoire.annotation_core`` so standalone processes
(the snapshot delivery worker) can use it without importing NiceGUI via
this package's ``__init__``.  This module re-exports the names so
page-side callers are unchanged.
"""

from __future__ import annotations

from promptgrimoire.annotation_core import (
    _serialise_comments,
    serialise_items,
)

__all__ = ["_serialise_comments", "serialise_items"]
