import { describe, test, expect, afterEach, vi } from 'vitest';
import { dom } from './helpers.js';

describe('annotation-copy-protection.js', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  describe('setupCopyProtection', () => {
    test('blocks copy in protected area', () => {
      const container = dom('<div class="protected"><p>Secret</p></div>');
      document.body.appendChild(container);
      setupCopyProtection('.protected');

      const event = new Event('copy', { bubbles: true, cancelable: true });
      const spy = vi.spyOn(event, 'preventDefault');
      container.querySelector('p').dispatchEvent(event);

      expect(spy).toHaveBeenCalled();
      expect(event.defaultPrevented).toBe(true);
    });

    test('allows copy outside protected area', () => {
      const container = dom('<div class="unprotected"><p>Public</p></div>');
      document.body.appendChild(container);
      setupCopyProtection('.protected');

      const event = new Event('copy', { bubbles: true, cancelable: true });
      const spy = vi.spyOn(event, 'preventDefault');
      container.querySelector('p').dispatchEvent(event);

      expect(spy).not.toHaveBeenCalled();
      expect(event.defaultPrevented).toBe(false);
    });

    test('blocks cut in protected area', () => {
      const container = dom('<div class="protected"><p>Secret</p></div>');
      document.body.appendChild(container);
      setupCopyProtection('.protected');

      const event = new Event('cut', { bubbles: true, cancelable: true });
      container.querySelector('p').dispatchEvent(event);

      expect(event.defaultPrevented).toBe(true);
    });

    test('blocks contextmenu in protected area', () => {
      const container = dom('<div class="protected"><p>Secret</p></div>');
      document.body.appendChild(container);
      setupCopyProtection('.protected');

      const event = new Event('contextmenu', { bubbles: true, cancelable: true });
      container.querySelector('p').dispatchEvent(event);

      expect(event.defaultPrevented).toBe(true);
    });

    test('blocks dragstart in protected area', () => {
      const container = dom('<div class="protected"><p>Secret</p></div>');
      document.body.appendChild(container);
      setupCopyProtection('.protected');

      const event = new Event('dragstart', { bubbles: true, cancelable: true });
      container.querySelector('p').dispatchEvent(event);

      expect(event.defaultPrevented).toBe(true);
    });

    test('blocks paste in milkdown editor', () => {
      const container = dom('<div id="milkdown-respond-editor"></div>');
      document.body.appendChild(container);
      setupCopyProtection('.protected');

      const event = new Event('paste', { bubbles: true, cancelable: true });
      const preventSpy = vi.spyOn(event, 'preventDefault');
      const stopSpy = vi.spyOn(event, 'stopImmediatePropagation');
      container.dispatchEvent(event);

      expect(preventSpy).toHaveBeenCalled();
      expect(stopSpy).toHaveBeenCalled();
      expect(event.defaultPrevented).toBe(true);
    });

    test('blocks Ctrl+P print', () => {
      setupCopyProtection('.protected');
      const event = new KeyboardEvent('keydown', { key: 'p', ctrlKey: true, cancelable: true });
      document.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(true);
    });

    test('blocks Cmd+P print', () => {
      setupCopyProtection('.protected');
      const event = new KeyboardEvent('keydown', { key: 'p', metaKey: true, cancelable: true });
      document.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(true);
    });
  });
});
