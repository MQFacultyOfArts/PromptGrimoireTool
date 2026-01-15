---
source: https://github.com/zauberzeug/nicegui/blob/main/nicegui/events.py
fetched: 2026-01-15
library: nicegui
summary: Event handler types and GenericEventArguments for ui.on() handlers
---

# NiceGUI Event Types

## Event Argument Classes

All event argument classes inherit from `EventArguments`:

| Class | Key Fields | Use Case |
|-------|-----------|----------|
| `UiEventArguments` | `sender: Element`, `client: Client` | Base for UI events |
| `GenericEventArguments` | `args: Any` | Custom events via `ui.on()` |
| `ClickEventArguments` | click position data | Button clicks |
| `ValueChangeEventArguments` | `value: Any`, `previous_value: Any` | Input changes |
| `KeyEventArguments` | `action`, `key`, `modifiers` | Keyboard events |

## Handler Type Signature

```python
from typing import Union, Callable, Any

# Handler can accept event arg or no args
Handler = Union[Callable[[EventT], Any], Callable[[], Any]]
```

NiceGUI auto-detects handler signature and calls appropriately.

## Using GenericEventArguments

For custom events emitted via JavaScript `emitEvent()`:

```python
from nicegui.events import GenericEventArguments

def handle_custom_event(e: GenericEventArguments) -> None:
    # e.args contains the data passed from JavaScript
    text = e.args.get("text", "")
    start = e.args.get("start", 0)

ui.on("my_custom_event", handle_custom_event)
```

JavaScript side:
```javascript
emitEvent('my_custom_event', { text: 'hello', start: 0 });
```

## Import

```python
from nicegui.events import (
    GenericEventArguments,
    ClickEventArguments,
    ValueChangeEventArguments,
    KeyEventArguments,
)
```
