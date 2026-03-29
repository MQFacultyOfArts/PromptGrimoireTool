import { describe, test, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Verify that the Python f-string in respond.py emits both `update` and
 * `markdown` fields in the `respond_yjs_update` event payload.
 *
 * This is a static source analysis test — it reads the Python source and
 * checks the JS template string structure.
 */
describe('respond_yjs_update event payload', () => {
  const respondSrc = readFileSync(
    resolve(__dirname, '../../src/promptgrimoire/pages/annotation/respond.py'),
    'utf-8'
  );

  test('emitEvent includes update field', () => {
    expect(respondSrc).toContain("emitEvent('respond_yjs_update'");
    expect(respondSrc).toMatch(/emitEvent\('respond_yjs_update'.*update:\s*b64Update/s);
  });

  test('emitEvent includes markdown field from _getMilkdownMarkdown', () => {
    // The emitEvent call must include markdown: window._getMilkdownMarkdown()
    expect(respondSrc).toMatch(
      /emitEvent\('respond_yjs_update'.*markdown:\s*window\._getMilkdownMarkdown\(\)/s
    );
  });

  test('both fields appear in the same emitEvent call', () => {
    // Extract the emitEvent block for respond_yjs_update
    const match = respondSrc.match(
      /emitEvent\('respond_yjs_update',\s*\{\{([\s\S]*?)\}\}\)/
    );
    expect(match).not.toBeNull();
    const payload = match[1];
    expect(payload).toContain('update: b64Update');
    expect(payload).toContain('markdown: window._getMilkdownMarkdown()');
  });
});
