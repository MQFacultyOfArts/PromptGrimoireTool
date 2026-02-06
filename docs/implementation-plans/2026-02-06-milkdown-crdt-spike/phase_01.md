# Milkdown CRDT Spike Implementation Plan

**Goal:** Build a local Vite JS bundle containing Milkdown Crepe + Yjs + collab plugin, served as NiceGUI static files.

**Architecture:** Local Vite build packages Milkdown Crepe, Yjs, and y-prosemirror into a single IIFE JS file with CSS injected by plugin. CodeMirror externalized to avoid conflicts with NiceGUI's bundled copy. Bundle committed to git so deployment doesn't require Node.js.

**Tech Stack:** Vite 6, @milkdown/crepe 7.18+, @milkdown/plugin-collab, yjs, y-prosemirror, vite-plugin-css-injected-by-js

**Scope:** 3 phases from original design (phases 1-3)

**Codebase verified:** 2026-02-06

---

## Phase 1: Vite Bundle Setup

**Type:** Infrastructure (verified operationally, no tests required — this is spike code)

<!-- START_TASK_1 -->
### Task 1: Create package.json and install dependencies

**Files:**
- Create: `src/promptgrimoire/static/milkdown/package.json`
- Create: `src/promptgrimoire/static/milkdown/.gitignore`

**Step 1: Create the package.json**

```json
{
  "name": "promptgrimoire-milkdown-bundle",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "vite build",
    "dev": "vite"
  },
  "dependencies": {
    "@milkdown/crepe": "^7.18.0",
    "@milkdown/plugin-collab": "^7.18.0",
    "yjs": "^13.6.0",
    "y-prosemirror": "^1.2.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "vite-plugin-css-injected-by-js": "^3.5.0"
  }
}
```

**Step 2: Create .gitignore for node_modules**

`src/promptgrimoire/static/milkdown/.gitignore`:
```
node_modules/
# dist/ is intentionally committed (no Node.js required for deployment)
```

**Step 3: Install dependencies**

```bash
cd src/promptgrimoire/static/milkdown
npm install
```

Expected: `node_modules/` created, no errors.

**Step 4: Commit**

```bash
git add src/promptgrimoire/static/milkdown/package.json src/promptgrimoire/static/milkdown/package-lock.json src/promptgrimoire/static/milkdown/.gitignore
git commit -m "chore: add Milkdown bundle package.json with Crepe + Yjs deps"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Vite config for library-mode build

**Files:**
- Create: `src/promptgrimoire/static/milkdown/vite.config.js`

**Step 1: Create vite.config.js**

```javascript
import { resolve } from "path";
import { defineConfig } from "vite";
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";

export default defineConfig({
  plugins: [cssInjectedByJsPlugin()],
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.js"),
      name: "MilkdownBundle",
      formats: ["iife"],
      fileName: () => "milkdown-bundle.js",
    },
    outDir: "dist",
    rollupOptions: {
      // Externalize CodeMirror — NiceGUI 3.6 already bundles it
      external: [/^@codemirror\//, /^@lezer\//],
      output: {
        globals: {},
      },
    },
  },
});
```

**Step 2: Verify config loads**

```bash
cd src/promptgrimoire/static/milkdown
npx vite --help
```

Expected: Vite help output, no config errors.

**Step 3: Commit**

```bash
git add src/promptgrimoire/static/milkdown/vite.config.js
git commit -m "chore: add Vite config for Milkdown IIFE bundle with CSS injection"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create bundle entry point and build

**Files:**
- Create: `src/promptgrimoire/static/milkdown/src/index.js`

**Step 1: Create the entry point**

```javascript
import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
// NOTE: Verify exact theme CSS path after npm install. If frame.css does not
// exist, check node_modules/@milkdown/crepe/theme/ for available theme files.
// Docs show @milkdown/crepe/theme/crepe/style.css as an alternative.
import "@milkdown/crepe/theme/frame.css";

/**
 * Create a Milkdown Crepe editor in the given root element.
 *
 * @param {HTMLElement} rootEl - DOM element to mount the editor in.
 * @param {string} initialMd - Initial markdown content.
 * @param {function} onUpdate - Callback called with (markdown: string) on content changes.
 * @returns {Promise<Crepe>} The Crepe editor instance.
 */
async function createEditor(rootEl, initialMd, onUpdate) {
  if (window.__milkdownCrepe) {
    console.error(
      "[milkdown-bundle] Crepe editor already initialized. " +
        "Multiple instances not supported in spike."
    );
    return window.__milkdownCrepe;
  }

  // Check for conflicting ProseMirror instances
  if (document.querySelector(".ProseMirror")) {
    console.error(
      "[milkdown-bundle] Existing ProseMirror instance detected. " +
        "This may cause conflicts."
    );
  }

  const crepe = new Crepe({
    root: rootEl,
    defaultValue: initialMd || "",
    features: {
      [Crepe.Feature.CodeMirror]: false,
    },
  });

  if (onUpdate) {
    crepe.on((listener) => {
      listener.markdownUpdated((ctx, markdown) => {
        onUpdate(markdown);
      });
    });
  }

  await crepe.create();
  console.log("[milkdown-bundle] Crepe editor created");

  window.__milkdownCrepe = crepe;
  return crepe;
}

// Expose globals for Python interop via ui.run_javascript()
window._createMilkdownEditor = createEditor;

window._getMilkdownMarkdown = function () {
  if (!window.__milkdownCrepe) return "";
  return window.__milkdownCrepe.getMarkdown();
};

window._setMilkdownMarkdown = function (md) {
  if (!window.__milkdownCrepe) return;
  console.warn(
    "[milkdown-bundle] setMarkdown requires editor recreation (spike limitation)"
  );
};
```

**Step 2: Build the bundle**

```bash
cd src/promptgrimoire/static/milkdown
npm run build
```

Expected: `dist/milkdown-bundle.js` created. CSS is injected into the JS file by `vite-plugin-css-injected-by-js`. File should be ~500KB-2MB.

**Step 3: Verify the bundle**

```bash
ls -lh src/promptgrimoire/static/milkdown/dist/milkdown-bundle.js
# Should exist and be >100KB
# Grep for the exposed globals:
grep -c "_createMilkdownEditor" src/promptgrimoire/static/milkdown/dist/milkdown-bundle.js
# Should output 1 or more
```

**Step 4: Commit**

```bash
git add src/promptgrimoire/static/milkdown/src/index.js src/promptgrimoire/static/milkdown/dist/
git commit -m "feat: build Milkdown Crepe bundle with IIFE output and CSS injection"
```

<!-- END_TASK_3 -->
