---
source: https://y-crdt.github.io/pycrdt/api_reference/
fetched: 2025-01-15
library: pycrdt
version: 0.12.44
summary: Complete API reference for pycrdt CRDT library - Text, Doc, StickyIndex, sync functions
---

# pycrdt API Reference

pycrdt provides Python bindings for Yrs (Rust port of Yjs) for building collaborative applications.

## Text

Shared data type for collaborative text editing, similar to Python `str`.

### Properties

- `doc` - The document this shared type belongs to (raises `RuntimeError` if not integrated)

### Methods

#### `__init__(init=None)`

Creates text with optional initial value:

```python
text = Text("Hello, World!")
```

#### `insert(index, value, attrs=None)`

Inserts string at given index with optional formatting attributes:

```python
Doc()["text"] = text = Text("Hello World!")
text.insert(5, ",")
assert str(text) == "Hello, World!"
```

#### `__delitem__(key)`

Removes characters at given index or slice:

```python
Doc()["text"] = text = Text("Hello, World!")
del text[5]  # Delete single character
assert str(text) == "Hello World!"

del text[5:]  # Delete from index to end
assert str(text) == "Hello"
```

Raises `RuntimeError` for negative indices or unsupported steps.

#### `__setitem__(key, value)`

Replaces characters at given index or slice:

```python
Doc()["text"] = text = Text("Hello, World!")
text[7:12] = "Brian"
assert str(text) == "Hello, Brian!"
```

#### `__getitem__(key)`

Gets characters at given index or slice:

```python
Doc()["text"] = text = Text("Hello, World!")
assert text[:5] == "Hello"
```

#### `__iadd__(value)`

Concatenates string to text:

```python
Doc()["text"] = text = Text("Hello")
text += ", World!"
assert str(text) == "Hello, World!"
```

#### `__contains__(item)`

Checks if string is in text:

```python
Doc()["text"] = text = Text("Hello, World!")
assert "World" in text
```

#### `clear()`

Removes entire range of characters.

#### `format(start, stop, attrs)`

Applies formatting attributes to section between indices:

```python
text.format(0, 5, {"bold": True})
```

#### `diff()`

Returns list of formatted chunks:

```python
list[tuple[Any, dict[str, Any] | None]]
```

Each tuple contains chunk content and formatting attributes.

#### `sticky_index(index, assoc=Assoc.AFTER)`

Creates permanent position that persists through concurrent updates:

```python
Doc()["text"] = text = Text("Hello World")
sticky = text.sticky_index(6)  # Position at "World"
text.insert(0, "Say ")
assert sticky.get_index() == 10  # Position adjusted
```

Returns `StickyIndex` object.

#### `observe(callback)`

Subscribes callback to text events:

```python
def on_change(event: TextEvent):
    print(event.delta)

subscription = text.observe(on_change)
```

#### `observe_deep(callback)`

Subscribes callback for all events from this and nested types.

#### `unobserve(subscription)`

Unsubscribes using given subscription.

#### `to_py()`

Returns text as Python `str` (or `None` if not in document).

---

## Doc

Shared document container. All shared types live within document scope.

### Properties

- `client_id` - Document's unique client identifier
- `guid` - Document's GUID

### Methods

#### `__init__(init={}, *, client_id=None, allow_multithreading=False)`

Creates document with optional initial root types:

```python
doc = Doc({"text": Text("Hello")})
# or
doc = Doc()
doc["text"] = Text("Hello")
```

#### `__getitem__(key)` / `__setitem__(key, value)`

Access/set root types:

```python
doc["text"] = Text("Hello")
text = doc["text"]
```

#### `get_state()`

Returns current document state as bytes:

```python
state: bytes = doc.get_state()
```

#### `get_update(state=None)`

Returns update from given state (or from creation if None):

```python
# Full update
full_update: bytes = doc.get_update()

# Differential update (only changes since state)
diff_update: bytes = doc.get_update(other_doc.get_state())
```

#### `apply_update(update)`

Applies binary update to document:

```python
doc.apply_update(update)
```

#### `transaction(origin=None)`

Creates or reuses transaction for mutations:

```python
with doc.transaction(origin="my-client"):
    text += "Hello"
    array.append(42)
```

If transaction exists, reuses it (origin must match).

#### `new_transaction(origin=None, timeout=None)`

Creates new transaction, waiting if one exists:

```python
# Sync context manager
with doc.new_transaction(timeout=3):
    ...

# Async context manager
async with doc.new_transaction():
    ...
```

#### `observe(callback)`

Subscribes to document changes:

```python
def on_update(event: TransactionEvent):
    update: bytes = event.update
    origin = event.origin
    # Send update to other clients

subscription = doc.observe(on_update)
```

Callback can be sync or async.

#### `observe_subdocs(callback)`

Monitors subdocument changes.

#### `unobserve(subscription)`

Unsubscribes using given subscription.

#### `keys()` / `values()` / `items()`

Iterators over root types.

---

## TransactionEvent

Event generated by `doc.observe()`, emitted during transaction commit.

### Properties

- `update: bytes` - Binary update from transaction
- `transaction` - The transaction that generated this event (ReadTransaction)
- `before_state` - Document state before the transaction
- `after_state` - Document state after the transaction
- `delete_set` - Set of deleted items

**Note:** The transaction origin is NOT available in the event callback. Origin is only
accessible during the transaction itself via `txn.origin`. For echo prevention, track
origin at the application level by wrapping update broadcasts with metadata.

---

## StickyIndex

Permanent position that maintains location despite concurrent edits.

### Class Methods

#### `new(sequence, index, assoc)`

Creates sticky index:

```python
sticky = StickyIndex.new(text, 5, Assoc.AFTER)
```

### Instance Methods

#### `get_index(transaction=None)`

Returns current index value:

```python
pos: int = sticky.get_index()
```

#### `encode()` / `decode(data, sequence=None)`

Binary serialization:

```python
data: bytes = sticky.encode()
sticky = StickyIndex.decode(data, text)
```

#### `to_json()` / `from_json(data, sequence=None)`

JSON serialization:

```python
data: dict = sticky.to_json()
sticky = StickyIndex.from_json(data, text)
```

### Properties

- `assoc` - `Assoc` enum (BEFORE or AFTER)

---

## Assoc

Enum for sticky index association.

- `Assoc.BEFORE` - Associate with item on left
- `Assoc.AFTER` - Associate with item on right

---

## Sync Functions

### `create_sync_message(ydoc)`

Creates SYNC_STEP1 message containing document state:

```python
message: bytes = create_sync_message(doc)
```

### `handle_sync_message(message, ydoc)`

Processes sync message on document:

```python
reply: bytes | None = handle_sync_message(message, doc)
# Returns SYNC_STEP2 reply if message was SYNC_STEP1
```

### `create_update_message(data)`

Wraps update in protocol message:

```python
message: bytes = create_update_message(update)
```

### `merge_updates(*updates)`

Combines multiple updates:

```python
merged: bytes = merge_updates(update1, update2, update3)
```

### `get_state(update)`

Derives state from update:

```python
state: bytes = get_state(update)
```

---

## Array

List-like shared type.

### Key Methods

- `append(value)` - Add item
- `insert(index, value)` - Insert at position
- `pop(index=-1)` - Remove and return item
- `extend(values)` - Add multiple items
- `move(source, dest)` - Move item
- `clear()` - Remove all
- `sticky_index(index, assoc)` - Create sticky position
- `observe(callback)` / `observe_deep(callback)`

---

## Map

Dict-like shared type.

### Key Methods

- `__getitem__(key)` / `__setitem__(key, value)`
- `get(key, default=None)`
- `pop(key, default)`
- `update(dict)`
- `clear()`
- `keys()` / `values()` / `items()`
- `observe(callback)` / `observe_deep(callback)`

---

## UndoManager

Undo/redo support for shared types.

```python
from pycrdt import UndoManager

undo_manager = UndoManager(doc=doc)
undo_manager.expand_scope(text)

text += ", World!"
undo_manager.undo()  # Reverts change
undo_manager.redo()  # Reapplies change
```

### Methods

- `undo()` - Undo last change
- `redo()` - Redo last undone change
- `can_undo()` / `can_redo()` - Check availability
- `expand_scope(shared_type)` - Add type to tracking
- `include_origin(origin)` / `exclude_origin(origin)` - Filter by origin
- `clear()` - Clear undo/redo stacks

---

## Awareness

Client presence/cursor tracking.

```python
from pycrdt import Awareness

awareness = Awareness(doc)
awareness.set_local_state({"user": "Alice", "cursor": 5})

# Get all client states
for client_id, state in awareness.states.items():
    print(f"{client_id}: {state}")
```

### Methods

- `set_local_state(state)` - Set local client state
- `set_local_state_field(field, value)` - Update single field
- `get_local_state()` - Get local state
- `apply_awareness_update(update, origin)` - Apply remote update
- `encode_awareness_update(client_ids)` - Create update for clients
- `observe(callback)` - Subscribe to changes

---

## Message Types

### YMessageType

- `SYNC` - Document synchronization
- `AWARENESS` - Presence protocol

### YSyncMessageType

- `SYNC_STEP1` - Initial state exchange
- `SYNC_STEP2` - Reply with missing updates
- `SYNC_UPDATE` - Incremental update
