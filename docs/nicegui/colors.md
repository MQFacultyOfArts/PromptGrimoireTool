---
source: https://nicegui.io/documentation/colors
fetched: 2026-01-21
library: nicegui
summary: Quasar color theming with ui.colors(), custom colors for branding
---

# NiceGUI Color Theming

## ui.colors()

Sets the main colors (primary, secondary, accent, ...) used by Quasar.

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `primary` | Primary color | `"#5898d4"` |
| `secondary` | Secondary color | `"#26a69a"` |
| `accent` | Accent color | `"#9c27b0"` |
| `dark` | Dark color | `"#1d1d1d"` |
| `dark_page` | Dark page color | `"#121212"` |
| `positive` | Positive color | `"#21ba45"` |
| `negative` | Negative color | `"#c10015"` |
| `info` | Info color | `"#31ccec"` |
| `warning` | Warning color | `"#f2c037"` |
| `custom_colors` | Custom color definitions for branding | - |

### Basic Usage

```python
from nicegui import ui

ui.button('Default', on_click=lambda: ui.colors())
ui.button('Gray', on_click=lambda: ui.colors(primary='#555'))

ui.run()
```

## Custom Colors for Branding

You can add custom color definitions for branding. **Important:** `ui.colors()` must be called before the custom color is ever used.

*Added in version 2.2.0*

```python
from nicegui import ui
from random import randint

# Register custom color BEFORE using it
ui.colors(brand='#424242')

# Use custom color on text with Tailwind
ui.label('This is your custom brand color').classes('text-brand')

# Use custom color on buttons with color parameter
ui.button('Randomize', color='brand',
          on_click=lambda: ui.colors(brand=f'#{randint(0, 0xffffff):06x}'))

ui.run()
```

### Multiple Custom Colors

You can register multiple custom colors at once:

```python
from nicegui import ui

# Register multiple custom colors
ui.colors(
    tag_jurisdiction='#1f77b4',
    tag_facts='#2ca02c',
    tag_issues='#d62728',
)

# Use on buttons
ui.button('Jurisdiction', color='tag-jurisdiction')
ui.button('Facts', color='tag-facts')
ui.button('Issues', color='tag-issues')
```

**Note:** Color names use underscores in Python (`tag_jurisdiction`) but hyphens in CSS/class usage (`tag-jurisdiction`).

## Using Colors on Elements

### Buttons

Use the `color` parameter directly:

```python
ui.button('Click me', color='primary')
ui.button('Brand Button', color='brand')  # custom color
```

### Text with Tailwind

Use `text-{colorname}` class:

```python
ui.label('Primary text').classes('text-primary')
ui.label('Brand text').classes('text-brand')
```

### Background with Tailwind

Use `bg-{colorname}` class:

```python
ui.element('div').classes('bg-primary p-4')
ui.element('div').classes('bg-brand p-4')
```

## Dynamic Color Changes

Colors can be changed at runtime:

```python
from nicegui import ui

ui.colors(primary='#5898d4')  # Initial

def change_to_red():
    ui.colors(primary='#ff0000')

ui.button('Make Primary Red', on_click=change_to_red)
```

## Inheritance

`ui.colors` inherits from `Element` and has all standard element properties:
- `classes`, `style`, `props`
- `visible`, `is_deleted`
- Event handlers via `.on()`
