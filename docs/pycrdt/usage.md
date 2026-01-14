---
source: https://y-crdt.github.io/pycrdt/usage/
fetched: 2025-01-13
summary: pycrdt usage guide - CRDT data types, sync, transactions, observers
---

# pycrdt Usage Guide

pycrdt provides Python bindings for Yrs (Rust port of Yjs) for building collaborative applications.

## Core Shared Data Types

- `Text` - string-like
- `Array` - list-like
- `Map` - dict-like
- XML types (for structured documents)

These are "placeholders waiting to be inserted in a shared document."

## Initialization

```python
from pycrdt import Doc, Text, Array, Map

doc = Doc()
text0 = Text("Hello")
array0 = Array([0, "foo"])
map0 = Map({"key0": "value0"})

doc["text0"] = text0
doc["array0"] = array0
doc["map0"] = map0
```

## Operating on Shared Types

```python
text0 += ", World!"
array0.append("bar")
map0["key1"] = "value1"

# Nesting shared types
map1 = Map({"baz": 1})
array1 = Array([5, 6, 7])
array0.append(map1)
map0["key2"] = array1
```

## Document Synchronization

Generate and apply updates to synchronize documents:

```python
update = doc.get_update()

# On remote machine:
remote_doc = Doc()
remote_doc.apply_update(update)
remote_doc["text0"] = Text()
remote_doc["array0"] = Array()
remote_doc["map0"] = Map()
```

The technology ensures "applying the changes will lead to the same data on all objects" despite concurrent modifications.

## Transactions

### Non-Blocking (Standard)

**Synchronous:**

```python
with doc.transaction():
    text0 += ", World!"
    array0.append("bar")
    map0["key1"] = "value1"
```

Transactions nest naturally—inner transactions use the outer one.

**Asynchronous:**

```python
async def async_callback(event):
    await send(event.update)

doc.observe(async_callback)
async with doc.transaction():
    # changes here
```

### Blocking Transactions

**Multithreading:**

```python
doc = Doc(allow_multithreading=True)

def create_new_transaction():
    with doc.new_transaction(timeout=3):
        pass
```

**Async:**

```python
async with doc.new_transaction(timeout=3):
    pass
```

## Observing Changes

### Shared Data Events

```python
from pycrdt import TextEvent

def handle_changes(event: TextEvent):
    pass

subscription_id = text0.observe(handle_changes)
text0.unobserve(subscription_id)
```

For nested structures, use `observe_deep`:

```python
from pycrdt import ArrayEvent

def handle_deep_changes(events: list[ArrayEvent]):
    pass

array0.observe_deep(handle_deep_changes)
```

### Document Events

```python
from pycrdt import TransactionEvent

def handle_doc_changes(event: TransactionEvent):
    update: bytes = event.update
    # Send over wire

doc.observe(handle_doc_changes)
remote_doc.apply_update(update)
```

**Async iteration:**

```python
async with doc.events() as events:
    async for event in events:
        update: bytes = event.update
```

## Undo Manager

```python
from pycrdt import UndoManager

undo_manager = UndoManager(doc=doc)
undo_manager.expand_scope(text)

text += ", World!"
undo_manager.undo()
undo_manager.redo()
```

## Type Annotations

```python
doc = Doc[Array[int]]()
array0 = doc.get("array0", type=Array[int])

# TypedDoc for schema validation:
from pycrdt import TypedDoc, TypedMap

class MyMap(TypedMap):
    name: str
    toggle: bool

class MyDoc(TypedDoc):
    map0: MyMap
    array0: Array[int]

doc = MyDoc()
untyped_doc: Doc = doc._
```

## Integration Notes

- pycrdt handles CRDT sync but NOT network transport
- You need to implement WebSocket/HTTP layer for transmitting updates
- Updates are binary (`bytes`) - efficient for network transmission
- State can be persisted by storing `doc.get_update()` result
