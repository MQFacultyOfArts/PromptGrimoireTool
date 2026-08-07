// Structural regression test for annotationsidebar.js.
//
// The items-watch at ~line 268-283 MUST include `immediate: true`.
// Without it, `window.__annotationCardsEpoch` never fires on cold page
// load (see docs/investigations/2026-04-24-vue-sidebar-epoch-missing.md),
// and the four test_vue_sidebar_cross_tab.py tests go red in nightly
// e2e slow. This is a cheap, always-in-CI gate that catches accidental
// removal.
//
// This does not run the watch (annotationsidebar.js is a Vue component
// module that needs Vue to execute). It asserts the source code has the
// correct watch-options shape by string inspection.

import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, test, expect } from 'vitest';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const SIDEBAR_JS = resolve(
  __dirname,
  '../../src/promptgrimoire/static/annotationsidebar.js',
);

describe('annotationsidebar.js', () => {
  const source = readFileSync(SIDEBAR_JS, 'utf-8');

  test('items watch exists with items source expression', () => {
    // Confirm the watch we care about is still present.
    expect(source).toMatch(/watch\(\s*\(\)\s*=>\s*props\.items/);
  });

  test('items watch increments window.__annotationCardsEpoch', () => {
    // The only writer of the scalar epoch must still live inside a
    // watch block. (See also the mount-contract E2E test.)
    expect(source).toMatch(
      /window\.__annotationCardsEpoch\s*=\s*\(window\.__annotationCardsEpoch\s*\|\|\s*0\)\s*\+\s*1/,
    );
  });

  test('items watch options include immediate: true', () => {
    // Extract the options block that follows the items-watch callback.
    // Pattern: `watch(() => props.items, () => { ... }, { ... })` — match
    // the options object at the closing of the watch() call. Be permissive
    // about whitespace and member order.
    const match = source.match(
      /watch\(\s*\(\)\s*=>\s*props\.items[\s\S]*?\},\s*(\{[^}]*\})\s*\);/,
    );
    expect(match, 'items-watch options block not found').toBeTruthy();
    const options = match[1];
    expect(options, 'items-watch options must include immediate: true').toMatch(
      /immediate:\s*true/,
    );
  });
});
