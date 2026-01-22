---
source: https://nicegui.io/documentation
fetched: 2025-01-14
summary: NiceGUI UI patterns - timer, refreshable, pages, events, storage, styling
---

# NiceGUI UI Patterns

Detailed patterns for building PromptGrimoire with NiceGUI.

## ui.timer - Periodic Updates

Execute callbacks at intervals. Useful for CRDT sync heartbeats.

```python
from nicegui import ui

# Basic periodic update
label = ui.label()
ui.timer(1.0, lambda: label.set_text(f'{datetime.now():%X}'))

# Controllable timer
timer = ui.timer(0.1, lambda: do_something())
ui.switch('Active').bind_value_to(timer, 'active')
ui.button('Cancel', on_click=timer.cancel)

# One-shot delayed execution
ui.timer(1.0, lambda: ui.notify('Delayed!'), once=True)

# App-level timer (shared across all clients)
from nicegui import app
app.timer(5.0, lambda: sync_crdt_state())
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `interval` | Seconds between executions |
| `callback` | Function or coroutine to call |
| `active` | Boolean to enable/disable (bindable) |
| `once` | Execute only once after delay |
| `immediate` | Run immediately (default True) |

### Methods

- `activate()` - Enable timer
- `deactivate()` - Pause timer
- `cancel()` - Permanently stop timer

## @ui.refreshable - Reactive UI

Decorator that adds `refresh()` method to recreate UI elements.

```python
from nicegui import ui

@ui.refreshable
def annotation_list():
    for annotation in annotations:
        ui.label(annotation.text)

annotation_list()
ui.button('Refresh', on_click=annotation_list.refresh)

# With parameters
@ui.refreshable
def user_card(user_id: str):
    user = get_user(user_id)
    ui.label(user.name)

user_card('user-123')
# Change user:
user_card.refresh('user-456')
```

### State Management with ui.state()

```python
@ui.refreshable
def counter():
    count, set_count = ui.state(0)
    ui.label(f'Count: {count}')
    ui.button('+1', on_click=lambda: set_count(count + 1))

counter()
```

### Async Refresh

```python
@ui.refreshable
async def load_data():
    data = await fetch_data()
    ui.label(data)

async def handle_refresh(e):
    e.sender.disable()
    await load_data.refresh()
    e.sender.enable()

ui.button('Reload', on_click=handle_refresh)
await load_data()
```

## @ui.page - Routing

Define pages with routes. Each user gets private instance.

```python
from nicegui import ui

@ui.page('/')
def home():
    ui.label('Home')

@ui.page('/conversation/{conv_id}')
def conversation(conv_id: str):
    ui.label(f'Viewing: {conv_id}')

@ui.page('/user/{user_id:int}')
def user_profile(user_id: int):
    ui.label(f'User ID: {user_id}')

ui.run()
```

### With Request/Client Access

```python
@ui.page('/dashboard')
async def dashboard(request):
    # Access request object
    token = request.query_params.get('token')

    # Wait for WebSocket connection
    await ui.context.client.connected()

    # Now can use JavaScript
    await ui.run_javascript('console.log("connected")')
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `path` | Route path (must start with /) |
| `title` | Page title |
| `dark` | Dark mode |
| `response_timeout` | Max build time (default 3.0s) |

## ui.run_javascript - Browser Interaction

Execute JavaScript and get results.

```python
# Fire and forget
ui.run_javascript('alert("Hello!")')

# Get result (must await)
async def get_selection():
    result = await ui.run_javascript('''
        const sel = window.getSelection();
        return {
            text: sel.toString(),
            start: sel.anchorOffset,
            end: sel.focusOffset
        };
    ''')
    return result

# With timeout
result = await ui.run_javascript('heavyOperation()', timeout=5.0)

# Access NiceGUI elements
ui.run_javascript(f'getHtmlElement({label.id}).innerText = "Hello"')
```

### Important Notes

- Automatically waits for client connection
- Must `await` to get return value
- Use `getElement(id)` for NiceGUI elements
- Use `getHtmlElement(id)` for DOM elements

## element.on() - Generic Events

Handle any DOM or Quasar event.

```python
# Basic click
ui.button('Click').on('click', lambda: ui.notify('Clicked!'))

# With event data
async def handle_click(e):
    print(e.args)  # Event arguments

ui.button('Info').on('click', handle_click, ['clientX', 'clientY'])

# JavaScript-only handler (no server round-trip)
ui.button('Copy').on('click', js_handler='''() => {
    navigator.clipboard.writeText("Copied!");
}''')

# Throttled events
ui.html('<div>Hover me</div>').on(
    'mousemove',
    lambda e: print(e.args),
    throttle=0.5  # Max once per 0.5s
)

# Key modifiers
ui.input().on('keydown.enter', lambda: ui.notify('Enter pressed'))
ui.input().on('keydown.ctrl.s', lambda: save())
```

### Custom Events from JavaScript

```python
# Emit from JS
ui.add_head_html('''
<script>
document.addEventListener('selectionchange', () => {
    const text = window.getSelection().toString();
    if (text) emitEvent('textselected', { text });
});
</script>
''')

# Handle in Python
ui.on('textselected', lambda e: handle_selection(e.args))
```

## Storage - Persistence

### Storage Types

| Type | Scope | Persists | Use Case |
|------|-------|----------|----------|
| `app.storage.tab` | Per browser tab | Across reloads | Tab-specific state |
| `app.storage.client` | Single connection | Until reload | Sensitive/temp data |
| `app.storage.user` | Per user (all tabs) | Forever | User preferences |
| `app.storage.browser` | Per browser | Until reload | Session data |
| `app.storage.general` | All users | Forever | App-wide state |

### Examples

```python
from nicegui import app, ui

@ui.page('/')
async def index():
    # Tab storage (needs connection)
    await ui.context.client.connected()
    app.storage.tab['visits'] = app.storage.tab.get('visits', 0) + 1

    # User storage (persists forever)
    app.storage.user['theme'] = 'dark'

    # Bind to UI
    ui.switch('Dark mode').bind_value(app.storage.user, 'dark_mode')

# Requires storage_secret for user/browser storage
ui.run(storage_secret='your-secret-key')
```

## Styling - CSS and HTML

### Add CSS

```python
# Page-specific CSS
ui.add_css('''
.annotation-highlight {
    background-color: rgba(255, 235, 59, 0.4);
    border-bottom: 2px solid #ffc107;
}
''')

# Shared across all pages
ui.add_css('.global-style { color: red; }', shared=True)
```

### Add Head/Body HTML

```python
# Add to <head>
ui.add_head_html('''
<script src="https://cdn.example.com/lib.js"></script>
<style>.custom { color: blue; }</style>
''')

# Add to <body>
ui.add_body_html('<div id="portal"></div>')
```

### Query and Style Elements

```python
# Style body
ui.query('body').style('background-color: #f0f0f0')

# Style by class
ui.query('.conversation-text').classes('text-lg font-mono')
```

## ui.notify - User Feedback

```python
# Basic notification
ui.notify('Saved!')

# Types
ui.notify('Success!', type='positive')
ui.notify('Error!', type='negative')
ui.notify('Warning!', type='warning')
ui.notify('Info', type='info')

# Position
ui.notify('Top right', position='top-right')

# With close button
ui.notify('Click to dismiss', close_button='OK')

# Multi-line
ui.notify('Line 1\nLine 2', multi_line=True)
```

## Page Layout Components

For app-level layout with fixed headers, footers, drawers, etc., use Quasar's layout components.

### ui.header() - Fixed Header

Creates a sticky header at the top of the page. Content scrolls beneath it.

```python
from nicegui import ui

# Basic header
with ui.header().classes('bg-primary'):
    ui.label('My App')

# Header with custom styling
with ui.header().classes('bg-gray-100 q-py-xs'):
    with ui.row().classes('w-full items-center'):
        ui.button(icon='menu').props('flat')
        ui.label('Title').classes('text-h6')

# The rest of the page content scrolls under the header
ui.label('Page content here')

ui.run()
```

**Why use ui.header() instead of CSS position: fixed?**

- NiceGUI/Quasar wraps content in layout containers
- CSS `position: fixed` doesn't work reliably inside these containers
- `ui.header()` is Quasar's built-in solution and integrates properly

### ui.footer() - Fixed Footer

```python
with ui.footer(value=False) as footer:  # value=False means hidden initially
    ui.label('Footer content')

ui.button('Toggle footer', on_click=footer.toggle)
```

### ui.left_drawer() / ui.right_drawer() - Side Panels

```python
with ui.left_drawer().classes('bg-blue-100') as drawer:
    ui.label('Side menu')
    ui.button('Item 1')
    ui.button('Item 2')

# Toggle from a button in header
with ui.header():
    ui.button(icon='menu', on_click=drawer.toggle).props('flat')
```

### ui.page_sticky() - Floating Action Button

```python
with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20):
    ui.button(icon='add').props('fab')
```

### Complete Layout Example

```python
from nicegui import ui

with ui.header().classes('items-center'):
    ui.button(icon='menu', on_click=lambda: drawer.toggle()).props('flat color=white')
    with ui.tabs() as tabs:
        ui.tab('Home')
        ui.tab('Settings')

with ui.left_drawer() as drawer:
    ui.label('Navigation')

with ui.footer(value=False) as footer:
    ui.label('Footer')

with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20):
    ui.button(icon='help', on_click=footer.toggle).props('fab')

with ui.tab_panels(tabs, value='Home').classes('w-full'):
    with ui.tab_panel('Home'):
        ui.label('Home content')
    with ui.tab_panel('Settings'):
        ui.label('Settings content')

ui.run()
```

## Complete Example: Annotation UI

```python
from nicegui import app, ui

annotations = []

@ui.refreshable
def annotation_list():
    for ann in annotations:
        with ui.card().classes('w-full'):
            ui.label(ann['text']).classes('annotation-highlight')
            ui.label(f"By {ann['user']}").classes('text-xs text-gray-500')

@ui.page('/conversation/{conv_id}')
async def conversation_page(conv_id: str):
    await ui.context.client.connected()

    # Add annotation CSS
    ui.add_css('''
    .annotation-highlight {
        background: rgba(255, 235, 59, 0.4);
        cursor: pointer;
    }
    .selectable { user-select: text; }
    ''')

    # Add selection handler
    ui.add_head_html('''
    <script>
    document.addEventListener('mouseup', () => {
        const sel = window.getSelection();
        if (sel.toString().trim()) {
            emitEvent('textselected', {
                text: sel.toString(),
                start: sel.anchorOffset,
                end: sel.focusOffset
            });
        }
    });
    </script>
    ''')

    # Handle selection
    async def on_selection(e):
        annotations.append({
            'text': e.args['text'],
            'user': app.storage.user.get('email', 'Anonymous')
        })
        annotation_list.refresh()
        ui.notify('Annotation created!')

    ui.on('textselected', on_selection)

    # UI
    ui.label('Conversation').classes('text-h4')

    with ui.row().classes('w-full gap-4'):
        with ui.card().classes('w-2/3'):
            ui.html('''
                <div class="selectable">
                    <p>This is the conversation text that users can select.</p>
                    <p>Select any portion to create an annotation.</p>
                </div>
            ''', sanitize=False)

        with ui.card().classes('w-1/3'):
            ui.label('Annotations').classes('text-h6')
            annotation_list()

    # Periodic sync
    ui.timer(5.0, lambda: sync_to_server())

ui.run(storage_secret='secret')
```
