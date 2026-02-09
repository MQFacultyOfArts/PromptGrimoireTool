"""Vendored SortableJS element for NiceGUI.

Source: NiceGUI PR #4656 (https://github.com/zauberzeug/nicegui/pull/4656)
SortableJS version: 1.15.6
Licence: MIT (SortableJS and NiceGUI PR code)
Why vendored: PR not yet merged into NiceGUI as of 2026-02-08.

When NiceGUI merges PR #4656, this vendored copy can be replaced with
``from nicegui.elements.sortable import Sortable``.
"""

from .sortable import Sortable

__all__ = ["Sortable"]
