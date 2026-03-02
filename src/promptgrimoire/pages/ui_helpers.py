"""Shared UI helper utilities for NiceGUI page components."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nicegui import ui

_OPTION_SLOT_TEMPLATE = (
    '<q-item v-bind="props.itemProps" '
    ":data-testid=\"'{prefix}-' + props.opt.value\">"
    "<q-item-section>"
    '<q-item-label v-html="props.opt.label"></q-item-label>'
    "</q-item-section>"
    "</q-item>"
)


def add_option_testids(select: ui.select, prefix: str) -> None:
    """Add data-testid to each dropdown option via a Quasar slot template.

    Each option receives a testid in the form ``{prefix}-{option_value}``.
    """
    select.add_slot("option", _OPTION_SLOT_TEMPLATE.replace("{prefix}", prefix))
