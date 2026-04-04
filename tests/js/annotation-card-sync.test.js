import { describe, test, expect, afterEach, vi } from 'vitest';
import { dom, domWithNodes, mockRect } from './helpers.js';

// Card positioning and hover interaction are now handled by the Vue
// annotation sidebar component (annotationsidebar.js).
// This file only tests initToolbarObserver, which remains in
// annotation-card-sync.js.
describe('annotation-card-sync.js', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    delete window._toolbarObserverActive;
    vi.restoreAllMocks();
  });

  describe('initToolbarObserver', () => {
    test('guard prevents duplicate observers', () => {
      window._toolbarObserverActive = true;
      const spy = vi.spyOn(globalThis, 'ResizeObserver');
      initToolbarObserver();
      expect(spy).not.toHaveBeenCalled();
    });

    test('does nothing when toolbar element missing', () => {
      delete window._toolbarObserverActive;
      const spy = vi.spyOn(globalThis, 'ResizeObserver');
      initToolbarObserver();
      expect(spy).not.toHaveBeenCalled();
    });

    test('observes toolbar when present', () => {
      delete window._toolbarObserverActive;
      document.body.innerHTML = '<div id="tag-toolbar-wrapper"></div>';
      const observeSpy = vi.spyOn(ResizeObserver.prototype, 'observe');
      initToolbarObserver();
      expect(observeSpy).toHaveBeenCalled();
      expect(window._toolbarObserverActive).toBe(true);
    });
  });
});
