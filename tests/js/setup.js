import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const STATIC_DIR = resolve(__dirname, '../../src/promptgrimoire/static');

const files = [
  'annotation-highlight.js',     // Must be first (others depend on it)
  'annotation-card-sync.js',
  'annotation-copy-protection.js',
  'idle-tracker.js',
];

for (const file of files) {
  const code = readFileSync(resolve(STATIC_DIR, file), 'utf-8');
  // indirect eval runs in global scope
  (0, eval)(code);
}

// Mock CSS.highlights
globalThis.CSS = globalThis.CSS || {};
globalThis.CSS.highlights = new Map();

globalThis.Highlight = class Highlight {
  constructor(...ranges) {
    this.ranges = ranges;
    this.priority = 0;
  }
};

globalThis.StaticRange = class StaticRange {
  constructor({ startContainer, startOffset, endContainer, endOffset }) {
    this.startContainer = startContainer;
    this.startOffset = startOffset;
    this.endContainer = endContainer;
    this.endOffset = endOffset;
  }
};

// Mock ResizeObserver
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock Quasar
globalThis.Quasar = {
  Notify: {
    create: () => {}
  }
};

// Explicitly bind evaluated global functions to globalThis so vi.spyOn works on them
const functionNames = [
  'setupCardPositioning', 'initToolbarObserver', 'setupCopyProtection',
  'walkTextNodes', 'clearHighlights', 'applyHighlights', 'charOffsetToRange',
  'findLocalOffset', 'charOffsetToRect', 'scrollToCharOffset', 'showHoverHighlight',
  'clearHoverHighlight', 'throbHighlight', 'setupSelection', 'setupAnnotationSelection',
  'rangePointToCharOffset', '_boundaryFromSiblings', 'countCollapsed',
  'renderRemoteCursor', 'removeRemoteCursor', 'updateRemoteCursorPositions',
  'renderRemoteSelection', 'removeRemoteSelection', 'removeAllRemotePresence',
  'initIdleTracker', 'cleanupIdleTracker'
];

for (const name of functionNames) {
  if (typeof globalThis[name] === 'undefined') {
    // We must evaluate them to access the dynamically created function declaration
    globalThis[name] = eval(name);
  }
}
