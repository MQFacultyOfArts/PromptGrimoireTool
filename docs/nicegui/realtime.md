---
source: https://nicegui.io/documentation
fetched: 2025-01-13
summary: NiceGUI WebSocket, reactivity, multi-client handling, JS integration
---

# NiceGUI Real-Time & Reactivity

NiceGUI uses WebSocket connections for client-server communication with async/await event loop.

## Automatic UI Synchronization

Properties can be bound to data models for automatic UI updates:

```python
from nicegui import ui

class Model:
    value = 42

model = Model()
label = ui.label()
label.bind_value_to(model, 'value')
# Label updates automatically when model.value changes
```

## Reactive State Management

Observable collections that notify observers when contents change:

- `ObservableDict`
- `ObservableList`
- `ObservableSet`

```python
from nicegui.observables import ObservableList

items = ObservableList([1, 2, 3])
items.subscribe(lambda: print("Changed!"))
items.append(4)  # Triggers subscription callback
```

## Multi-Client Handling

### Storage Per Client

NiceGUI distinguishes between different connection scopes:

```python
from nicegui import app

# Per-tab storage (unique per browser tab)
app.storage.tab['key'] = 'value'

# Per-client storage (unique per connected client)
app.storage.client['key'] = 'value'

# User storage (persists across sessions)
app.storage.user['key'] = 'value'
```

### Lifecycle Events

Handle multiple clients with connection hooks:

```python
@app.on_connect()
def on_connect(client):
    print(f"Client {client.id} connected")

@app.on_disconnect()
def on_disconnect(client):
    print(f"Client {client.id} disconnected")
```

## Custom JavaScript Integration

### Running JavaScript

Execute client-side code directly:

```python
result = await ui.run_javascript("return 42")
print(result)  # Output: 42
```

### Generic Event Handlers

Combine Python and JavaScript:

```python
button = ui.button('Click me')
button.on('click',
    lambda: print("Clicked"),
    js_handler="console.log('JS: clicked')"
)
```

### Client Method Execution

Invoke Vue/Quasar methods on elements:

```python
element.run_method('scrollIntoView')
computed_value = await element.get_computed_prop('offsetHeight')
```

## Element Customization

```python
element = ui.button('Submit')

# Quasar properties
element.props('flat outlined size="lg"')

# Tailwind/CSS classes
element.classes('px-4 py-2 rounded')

# Direct CSS
element.style('color: blue; font-weight: bold')
```

## Performance Optimization

For data-heavy scenarios, use `binding.BindableProperty` for minimal overhead.

## Integration Notes for PromptGrimoire

- NiceGUI handles WebSocket connections automatically
- Use `app.on_connect`/`app.on_disconnect` for presence tracking
- `ui.run_javascript` enables click-drag text selection handling
- Storage scopes map to our needs: `tab` = session, `user` = persistent
