---
source: https://milkdown.dev/docs/guide/faq
fetched: 2026-03-06
library: "@milkdown/kit"
summary: Editor actions — replaceAll, insert, getMarkdown, callCommand, direct ProseMirror access
---

# Editor Actions & Utility Macros

## Import Paths

```typescript
// Modern import (v7.x+)
import { getMarkdown, insert, replaceAll, callCommand } from '@milkdown/kit/utils'

// Legacy import (also works)
import { insert, replaceAll } from '@milkdown/utils'
```

## replaceAll — Replace Entire Document Content

Replaces all editor content with new markdown. This is the correct way to programmatically set content (Crepe has no `setMarkdown()` method).

```typescript
import { replaceAll } from '@milkdown/kit/utils'

// Replace entire document
editor.action(replaceAll('# New Document\n\nFresh start!'))
```

**For Crepe:** Access via `crepe.editor`:

```typescript
import { replaceAll } from '@milkdown/utils'

crepe.editor.action(replaceAll(newMarkdown))
```

## insert — Insert at Cursor

```typescript
import { insert } from '@milkdown/kit/utils'

// Insert as block (default)
editor.action(insert('**bold text** and _italic text_'))

// Insert as inline (preserves current block)
editor.action(insert('inline content', true))
```

## getMarkdown — Get Current Content

```typescript
import { getMarkdown } from '@milkdown/kit/utils'

const markdown = editor.action(getMarkdown())
```

**For Crepe:** Use `crepe.getMarkdown()` directly (convenience wrapper).

## callCommand — Execute Editor Commands

```typescript
import { callCommand } from '@milkdown/kit/utils'
import { wrapInHeadingCommand } from '@milkdown/kit/preset/commonmark'

// Convert current block to H2
editor.action(callCommand(wrapInHeadingCommand.key, 2))
```

## Direct ProseMirror Access

```typescript
import { editorViewCtx } from '@milkdown/kit/core'

editor.action((ctx) => {
  const view = ctx.get(editorViewCtx)
  console.log('Selection:', view.state.selection)
  console.log('Document size:', view.state.doc.content.size)
})
```

## Collab Plugin (Yjs)

```typescript
import { collab, collabServiceCtx } from '@milkdown/plugin-collab'

// Register before create()
crepe.editor.use(collab)

await crepe.create()

// Bind Yjs doc or fragment
crepe.editor.action((ctx) => {
  const service = ctx.get(collabServiceCtx)

  // Option A: Bind entire doc
  service.bindDoc(ydoc).connect()

  // Option B: Bind named XmlFragment (for multi-editor setups)
  const fragment = ydoc.getXmlFragment('my-fragment')
  service.bindXmlFragment(fragment).connect()
})
```

**Important:** When using collab with `defaultValue`, the Yjs full-state sync may overwrite the default value. If seeding content into a collab-enabled editor, use `replaceAll` AFTER the Yjs sync completes, not `defaultValue`.
