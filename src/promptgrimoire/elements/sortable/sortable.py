"""Vendored SortableJS element for NiceGUI.

Source: NiceGUI PR #4656 — adapted for project lint/type standards.
"""

from __future__ import annotations

import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from nicegui import ui
from nicegui.element import Element

if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments, Handler

_CSS_PATH = Path(__file__).parent / "sortable.css"
_css_loaded = False


class Sortable(
    Element,
    component="sortable.js",
    esm={"nicegui-sortable": "dist"},
    default_classes="nicegui-sortable",
):
    _instances: weakref.WeakValueDictionary[int, Sortable] = (
        weakref.WeakValueDictionary()
    )

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        on_change: Handler[GenericEventArguments] | None = None,
        on_end: Handler[GenericEventArguments] | None = None,
        on_add: Handler[GenericEventArguments] | None = None,
        on_select: Handler[GenericEventArguments] | None = None,
        on_deselect: Handler[GenericEventArguments] | None = None,
        on_cancel_clone: Handler[GenericEventArguments] | None = None,
    ) -> None:
        """Create a draggable/sortable container using SortableJS.

        :param options: SortableJS options dict.
        :param on_change: Callback when the list order changes.
        :param on_end: Callback when element dragging ends.
        :param on_add: Callback when element is added from another list.
        :param on_select: Callback when an item is selected.
        :param on_deselect: Callback when an item is deselected.
        :param on_cancel_clone: Callback when clone is canceled.
        """
        global _css_loaded  # noqa: PLW0603
        if not _css_loaded:
            ui.add_css(_CSS_PATH)
            _css_loaded = True

        super().__init__()

        self._props["options"] = {
            "animation": 150,
            "fallbackClass": "nicegui-sortable-fallback",
            "ghostClass": "nicegui-sortable-ghost",
            "chosenClass": "nicegui-sortable-chosen",
            "dragClass": "nicegui-sortable-drag",
            "swapClass": "nicegui-sortable-swap-highlight",
            "selectedClass": "nicegui-sortable-multi-selected",
            **(options or {}),
        }

        Sortable._instances[self.id] = self

        if on_end:
            self.on("sort_end", on_end)
        if on_add:
            self.on("sort_add", on_add)
        if on_change:
            self.on("sort_change", on_change)
        if on_cancel_clone:
            self.on("sort_cancel_clone", on_cancel_clone)
        if on_select:
            self.on("sort_select", on_select)
        if on_deselect:
            self.on("sort_deselect", on_deselect)

        self.on("sort_end", self._handle_cross_container_add)

    def on_end(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback for when sorting is finished."""
        self.on("sort_end", callback)
        return self

    def on_add(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback for when an item is added."""
        self.on("sort_add", callback)
        return self

    def on_change(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback for when order changes."""
        self.on("sort_change", callback)
        return self

    def on_cancel_clone(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback for when cloning is canceled."""
        self.on("sort_cancel_clone", callback)
        return self

    def on_select(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback for when an item is selected."""
        self.on("sort_select", callback)
        return self

    def on_deselect(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback for when an item is deselected."""
        self.on("sort_deselect", callback)
        return self

    async def _handle_cross_container_add(self, e: GenericEventArguments) -> None:
        """Handle element being added from another sortable."""
        if e.args["from"] == e.args["to"] or self.props.get("cancelClone"):
            await self._synchronize_order_js_to_py()
            return

        element = next(
            (
                child
                for child in self.default_slot.children
                if str(child.id) == e.args["item"] or child.html_id == e.args["item"]
            ),
            None,
        )

        sortable = next(
            (
                instance
                for instance in Sortable._instances.values()
                if instance.default_slot.children
                and (
                    str(instance.id) == e.args["to"] or instance.html_id == e.args["to"]
                )
            ),
            None,
        )

        if element and sortable:
            element.move(sortable, e.args.get("newIndex", 0))

        await self._synchronize_order_js_to_py()

    async def _synchronize_order_js_to_py(self) -> None:
        dom_order = await self.run_method("getChildrenOrder")
        if not dom_order:
            return

        id_to_item = {item.html_id: item for item in self.default_slot.children}

        ordered_items = [
            id_to_item[dom_id] for dom_id in dom_order if dom_id in id_to_item
        ]
        # Append Python-side children not present in DOM (defensive).
        ordered_items += [
            id_to_item[item_id] for item_id in id_to_item if item_id not in dom_order
        ]

        if self.default_slot.children != ordered_items:
            self.default_slot.children = ordered_items

    def set_option(self, name: str, value: Any) -> None:
        """Set a specific SortableJS option."""
        self._props["options"][name] = value
        self.run_method("setOption", name, value)

    def sort(self, order: list[Element], use_animation: bool = False) -> None:
        """Sort elements according to the specified order."""
        self.default_slot.children = order
        self.run_method("sort", [item.html_id for item in order], use_animation)

    def enable(self) -> None:
        """Enable the sortable instance."""
        self.set_option("disabled", False)

    def disable(self) -> None:
        """Disable the sortable instance."""
        self.set_option("disabled", True)

    def remove_item(self, item: Element) -> None:
        """Remove an item from this sortable list (Python + DOM)."""
        self.run_method("remove", item.html_id)
        item.delete()

    def clear(self) -> Self:
        """Remove all child elements.

        Overrides Element.clear() to also remove items from the
        SortableJS DOM instance.
        """
        for slot in self.slots.values():
            for child in reversed(slot.children):
                self.remove_item(child)
        return self

    def get_child_by_id(self, html_id: str) -> Element | None:
        """Retrieve a child element by its HTML ID."""
        return next(
            (item for item in self.default_slot.children if item.html_id == html_id),
            None,
        )

    def move_item(self, item: Element, target_index: int = -1) -> None:
        """Move an item within this sortable list and sync DOM."""
        item.move(self, target_index=target_index)
        self.sort(self.default_slot.children, False)
