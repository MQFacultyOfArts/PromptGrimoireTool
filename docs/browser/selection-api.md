---
source: https://developer.mozilla.org/en-US/docs/Web/API/Selection
fetched: 2025-01-14
summary: Browser Selection API for text selection and annotation
---

# Browser Selection API

The Selection API represents text selected by the user or caret position. Essential for building text annotation features.

## Getting the Selection

```javascript
const selection = window.getSelection();
// or
const selection = document.getSelection();
```

## Key Properties

| Property | Description |
|----------|-------------|
| `anchorNode` | Node where selection began |
| `anchorOffset` | Offset within anchorNode |
| `focusNode` | Node where selection ended |
| `focusOffset` | Offset within focusNode |
| `isCollapsed` | True if start and end are same position |
| `rangeCount` | Number of ranges (usually 1) |
| `type` | Selection type string |

## Essential Methods

```javascript
const selection = window.getSelection();

// Get selected text
const text = selection.toString();

// Get Range object
const range = selection.getRangeAt(0);

// Clear selection
selection.removeAllRanges();

// Add a range
selection.addRange(range);
```

## Capture Selection with Position

```javascript
function captureSelection() {
    const selection = window.getSelection();

    if (selection.rangeCount === 0 || selection.isCollapsed) {
        return null;
    }

    const range = selection.getRangeAt(0);
    const text = selection.toString();

    return {
        text: text,
        anchorNode: selection.anchorNode,
        anchorOffset: selection.anchorOffset,
        focusNode: selection.focusNode,
        focusOffset: selection.focusOffset,
        range: range
    };
}
```

## Get Selection Coordinates

```javascript
function getSelectionCoordinates() {
    const selection = window.getSelection();

    if (selection.rangeCount === 0) return null;

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    return {
        top: rect.top,
        left: rect.left,
        bottom: rect.bottom,
        right: rect.right,
        width: rect.width,
        height: rect.height
    };
}
```

## Listen for Selection Changes

```javascript
// Fires when selection changes
document.addEventListener('selectionchange', () => {
    const text = window.getSelection().toString();
    if (text) {
        console.log('Selected:', text);
    }
});

// Fires when selection starts
document.addEventListener('selectstart', (event) => {
    console.log('Selection started');
});

// On mouseup - selection likely complete
document.addEventListener('mouseup', () => {
    const selection = window.getSelection();
    if (!selection.isCollapsed) {
        handleSelection(selection);
    }
});
```

## NiceGUI Integration for Annotations

### Python Backend

```python
from nicegui import ui

async def handle_selection(event):
    """Handle text selection from browser."""
    text = event.args.get('text', '')
    start = event.args.get('start', 0)
    end = event.args.get('end', 0)
    container_id = event.args.get('containerId', '')

    if text:
        ui.notify(f'Selected: "{text[:50]}..."')
        # Create annotation in database
        # annotation = await create_annotation(text, start, end)

# Page with selectable content
@ui.page('/')
def main():
    # Add selection handler JavaScript
    ui.add_head_html('''
    <script>
    function setupSelectionHandler(containerId, callback) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.addEventListener('mouseup', function(e) {
            const selection = window.getSelection();
            if (selection.isCollapsed) return;

            const text = selection.toString().trim();
            if (!text) return;

            const range = selection.getRangeAt(0);

            // Calculate offsets relative to container
            const preRange = document.createRange();
            preRange.selectNodeContents(container);
            preRange.setEnd(range.startContainer, range.startOffset);
            const start = preRange.toString().length;

            callback({
                text: text,
                start: start,
                end: start + text.length,
                containerId: containerId,
                rect: range.getBoundingClientRect()
            });
        });
    }
    </script>
    ''')

    # Conversation content
    with ui.card().classes('w-full'):
        content = ui.html('''
            <div id="conversation-content" class="selectable-text">
                <p>This is a sample conversation that users can select text from.</p>
                <p>Select any text to create an annotation.</p>
            </div>
        ''', sanitize=False)

    # Setup selection handling
    ui.run_javascript('''
        setupSelectionHandler('conversation-content', function(data) {
            // Send to Python
            emitEvent('text_selected', data);
        });
    ''')

    # Handle selection event
    ui.on('text_selected', handle_selection)

ui.run()
```

### Highlight Selected Text with CSS

```javascript
function highlightRange(range, className) {
    const span = document.createElement('span');
    span.className = className;
    range.surroundContents(span);
}

// Usage
const selection = window.getSelection();
if (selection.rangeCount > 0) {
    const range = selection.getRangeAt(0);
    highlightRange(range, 'annotation-highlight');
    selection.removeAllRanges();
}
```

### CSS for Annotations

```css
.annotation-highlight {
    background-color: rgba(255, 235, 59, 0.4);
    border-bottom: 2px solid #ffc107;
    cursor: pointer;
}

.annotation-highlight:hover {
    background-color: rgba(255, 235, 59, 0.6);
}

.selectable-text {
    user-select: text;
    cursor: text;
}
```

## Complete Annotation Flow

```javascript
// 1. User selects text
// 2. Capture selection data
// 3. Send to server
// 4. Server creates annotation
// 5. Apply highlight to DOM
// 6. Store range info for later reference

class AnnotationManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.annotations = [];
        this.setupListeners();
    }

    setupListeners() {
        this.container.addEventListener('mouseup', () => {
            this.handleSelection();
        });
    }

    handleSelection() {
        const selection = window.getSelection();
        if (selection.isCollapsed) return;

        const text = selection.toString().trim();
        if (!text) return;

        const range = selection.getRangeAt(0);

        // Check if selection is within container
        if (!this.container.contains(range.commonAncestorContainer)) {
            return;
        }

        // Get position info
        const rect = range.getBoundingClientRect();
        const containerRect = this.container.getBoundingClientRect();

        const annotationData = {
            text: text,
            startOffset: this.getTextOffset(range.startContainer, range.startOffset),
            endOffset: this.getTextOffset(range.endContainer, range.endOffset),
            position: {
                top: rect.top - containerRect.top,
                left: rect.left - containerRect.left
            }
        };

        // Emit to Python backend
        this.onAnnotationCreate(annotationData);
    }

    getTextOffset(node, offset) {
        const range = document.createRange();
        range.selectNodeContents(this.container);
        range.setEnd(node, offset);
        return range.toString().length;
    }

    onAnnotationCreate(data) {
        // Override this or emit event
        console.log('Annotation created:', data);
    }

    applyHighlight(startOffset, endOffset, annotationId) {
        // Re-create range from offsets and wrap in span
        // This is complex - consider using a library like Mark.js
    }
}
```

## Key Concepts

- **Anchor**: Where user started selecting (mousedown)
- **Focus**: Where user ended selecting (mouseup)
- **Range**: Contiguous document fragment
- **Offset**: Character position within a text node

## Browser Support

Widely available since July 2015. Works in all modern browsers.
