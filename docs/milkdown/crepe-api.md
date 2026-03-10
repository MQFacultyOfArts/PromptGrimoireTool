---
source: https://milkdown.dev/docs/api/crepe
fetched: 2026-03-06
library: "@milkdown/crepe"
summary: Crepe high-level editor API — constructor, features, featureConfigs, getMarkdown, setReadonly, events
---

# Crepe Editor API

## Constructor

```typescript
import { Crepe } from '@milkdown/crepe'

const crepe = new Crepe({
  root: '#editor',           // DOM element or selector
  defaultValue: '# Hello',  // Initial markdown content
  features: { ... },        // Enable/disable features
  featureConfigs: { ... },  // Per-feature configuration
})

await crepe.create()
```

## Features

All features are **enabled by default**. Disable by setting to `false`:

```typescript
const defaultFeatures: Record<CrepeFeature, boolean> = {
  [Crepe.Feature.Cursor]: true,
  [Crepe.Feature.ListItem]: true,
  [Crepe.Feature.LinkTooltip]: true,
  [Crepe.Feature.ImageBlock]: true,
  [Crepe.Feature.BlockEdit]: true,
  [Crepe.Feature.Placeholder]: true,
  [Crepe.Feature.Toolbar]: true,
  [Crepe.Feature.CodeMirror]: true,
  [Crepe.Feature.Table]: true,
  [Crepe.Feature.Latex]: true,       // Requires CodeMirror
}
```

Example disabling features:

```typescript
const crepe = new Crepe({
  features: {
    [Crepe.Feature.CodeMirror]: false,
    [Crepe.Feature.Table]: false,
    [Crepe.Feature.Latex]: false,      // Must disable if CodeMirror disabled
    [Crepe.Feature.ImageBlock]: false,
  },
})
```

**Important:** Latex depends on CodeMirror. Disabling CodeMirror without disabling Latex causes a runtime error:
`Uncaught Error: You need to enable CodeMirror to use LaTeX feature`

## Feature Configs

```typescript
featureConfigs: {
  [Crepe.Feature.Placeholder]: {
    text: 'Start writing...',
    mode: 'block',  // 'block' | 'doc'
  },
  [Crepe.Feature.ImageBlock]: {
    onUpload: async (file: File) => string,  // Return uploaded URL
    proxyDomURL?: string,
    blockCaptionPlaceholderText?: string,
    inlineUploadPlaceholderText?: string,
  },
  [Crepe.Feature.LinkTooltip]: {
    inputPlaceholder?: string,
  },
}
```

## Instance Methods

```typescript
// Get current markdown content
const md: string = crepe.getMarkdown()

// Set readonly mode
crepe.setReadonly(true)

// Destroy the editor
await crepe.destroy()

// Access underlying Milkdown Editor instance
crepe.editor  // Editor
crepe.editor.action(...)  // Run editor actions
```

**Note:** Crepe does NOT have a `setMarkdown()` method. To programmatically replace content, use `editor.action(replaceAll(md))` from `@milkdown/utils`. See [editor-actions.md](editor-actions.md).

## Events

```typescript
crepe.on((api) => {
  api.markdownUpdated((ctx, markdown) => {
    console.log('Document updated')
    localStorage.setItem('draft', markdown)
  })

  api.listen('update', (ctx) => {
    // Handle updates
  })
})
```

## CrepeBuilder (Tree-Shakeable Alternative)

For smaller bundles, use `CrepeBuilder` to add only needed features:

```typescript
import { CrepeBuilder } from '@milkdown/crepe/builder'
import { toolbar } from '@milkdown/crepe/feature/toolbar'
import { placeholder } from '@milkdown/crepe/feature/placeholder'

const builder = new CrepeBuilder({
  root: document.getElementById('editor'),
  defaultValue: '# Minimal Editor',
})

builder
  .addFeature(toolbar, { ... })
  .addFeature(placeholder, { text: 'Start typing...', mode: 'doc' })

await builder.create()

const content = builder.getMarkdown()
```
