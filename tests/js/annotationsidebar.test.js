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

  // --- Snapshot bundle contract (initial delivery outside NiceGUI) ---
  // See docs/design-notes/2026-08-16-initial-snapshot-delivery.md.

  test('applyBundle bumps the epoch so E2E waits observe bundle mount', () => {
    const match = source.match(/function applyBundle\(bundle\) \{[\s\S]*?\n    \}/);
    expect(match, 'applyBundle not found').toBeTruthy();
    expect(match[0]).toMatch(/bumpEpoch\(\)/);
    expect(match[0], 'stale bundle must not clobber a server push').toMatch(
      /if \(serverPushed\) return/,
    );
  });

  test('items watch drops bundle state on a genuine server push', () => {
    const match = source.match(
      /watch\(\s*\(\)\s*=>\s*props\.items([\s\S]*?)\},\s*\{[^}]*\}\s*\);/,
    );
    expect(match, 'items-watch body not found').toBeTruthy();
    const body = match[1];
    expect(body).toMatch(/serverPushed = true/);
    expect(body).toMatch(/bundleItems\.value = null/);
  });

  test('component registers the per-document bundle hook on mount', () => {
    expect(source).toMatch(/window\._sidebarBundleApply\[dcId\] = applyBundle/);
    expect(source, 'pending bundle delivered before mount must apply').toMatch(
      /__pendingSidebarBundle/,
    );
  });

  test('template renders from effectiveItems, not raw props', () => {
    expect(source).toMatch(/v-for="item in effectiveItems"/);
    expect(source).not.toMatch(/v-for="item in items"/);
  });
});
