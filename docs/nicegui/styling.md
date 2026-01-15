---
source: https://nicegui.io/documentation/section_styling_appearance
fetched: 2026-01-15
library: nicegui
summary: NiceGUI styling with CSS, Tailwind, Quasar props, and static files
---

# NiceGUI Styling & Static Files

## Styling Elements

NiceGUI uses Quasar Framework. Elements support three styling methods:

```python
# Quasar props
ui.radio(['x', 'y', 'z'], value='x').props('inline color=green')
ui.button(icon='touch_app').props('outline round').classes('shadow-lg')

# Tailwind CSS classes
ui.label('Hello').classes('text-xl font-bold')

# Inline styles (use sparingly)
ui.label('Stylish!').style('color: #6E93D6; font-size: 200%')
```

## ui.add_css() - Add CSS Styles

Add CSS style definitions to the page head.

```python
# From string
ui.add_css('''
    .red {
        color: red;
    }
''')

# From file path (string or Path object)
ui.add_css('static/styles.css')
ui.add_css(Path(__file__).parent / 'styles.css')
```

**Parameters:**
- `content`: CSS content (string or file path)
- `shared`: Whether to add to all pages (default: False, added in 2.14.0)

## CSS Layers

NiceGUI defines CSS layers in priority order:
1. theme
2. base
3. quasar
4. nicegui
5. components
6. utilities
7. overrides
8. quasar_importants

To override Quasar's `!important` rules, use the appropriate layer:

```python
ui.add_css('''
    @layer utilities {
       .red-background {
           background-color: red !important;
        }
    }
''')
ui.button('Red Button').classes('red-background')
```

## Tailwind CSS Layers

Use `type="text/tailwindcss"` for Tailwind-aware styles:

```python
ui.add_head_html('''
    <style type="text/tailwindcss">
        @layer components {
            .blue-box {
                @apply bg-blue-500 p-12 text-center shadow-lg rounded-lg text-white;
            }
        }
    </style>
''')
ui.label('Hello').classes('blue-box')
```

## app.add_static_files() - Serve Static Files

Makes a local directory available at a URL endpoint.

```python
from nicegui import app, ui

app.add_static_files('/static', 'assets')
# Files in assets/ are now available at /static/
```

**Parameters:**
- `url_path`: URL path starting with "/" (e.g., '/static')
- `local_directory`: Local folder path
- `follow_symlink`: Whether to follow symlinks (default: False)
- `max_cache_age`: Cache-Control header max-age (added in 2.8.0)

## ui.query() - Select and Style Elements

Style elements by CSS selector:

```python
# Style body
ui.query('body').style('background-color: #f0f0f0')

# Style by class
ui.query('.conversation-text').classes('text-lg font-mono')
```

## CSS Variables

Customize NiceGUI appearance:

```python
ui.add_css('''
    :root {
        --nicegui-default-padding: 0.5rem;
        --nicegui-default-gap: 3rem;
    }
''')
```

## Color Theming

Set Quasar color theme:

```python
ui.colors(
    primary='#5898d4',
    secondary='#26a69a',
    accent='#9c27b0',
    positive='#21ba45',
    negative='#c10015',
)
```
