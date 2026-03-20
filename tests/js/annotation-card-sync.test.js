import { describe, test, expect, afterEach, vi } from 'vitest';
import { dom, domWithNodes, mockRect } from './helpers.js';

describe('annotation-card-sync.js', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    delete window._textNodes;
    delete window._positionCards;
    delete window._highlightsReady;
    delete window._toolbarObserverActive;
    vi.restoreAllMocks();
  });

  describe('setupCardPositioning', () => {
    test('registers scroll listener', () => {
      const spy = vi.spyOn(window, 'addEventListener');
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];
      expect(spy).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true });
    });

    test('onHighlightsReady attaches MutationObserver', () => {
      document.body.innerHTML = '<div id="doc"></div><div id="sidebar"></div>';
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];
      const observerSpy = vi.spyOn(MutationObserver.prototype, 'observe');
      document.dispatchEvent(new Event('highlights-ready'));
      expect(observerSpy).toHaveBeenCalled(); // Fixed ISSUE 7: actually asserts observation
    });

    test('catches up if _highlightsReady already true', () => {
      window._highlightsReady = true;
      document.body.innerHTML = '<div id="doc"></div><div id="sidebar"></div>';
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];
      expect(typeof window._positionCards).toBe('function');
    });

    // GAP 6: Missing hover tests
    test('hover shows highlight on card mouseover', () => {
      document.body.innerHTML = `
        <div id="doc"></div>
        <div id="sidebar">
          <div class="annotation-card" data-start-char="5" data-end-char="10"></div>
        </div>
      `;
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

      const spy = vi.spyOn(globalThis, 'showHoverHighlight');
      const card = document.querySelector('.annotation-card');
      card.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      expect(spy).toHaveBeenCalledWith(expect.any(Array), 5, 10);
    });

    test('hover clears on mouseout from sidebar', () => {
      document.body.innerHTML = `
        <div id="doc"></div>
        <div id="sidebar">
          <div class="annotation-card" data-start-char="5" data-end-char="10"></div>
        </div>
      `;
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

      const spy = vi.spyOn(globalThis, 'clearHoverHighlight');
      const card = document.querySelector('.annotation-card');
      // First, hover the card to set hoveredCard
      card.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

      // Then, hover outside the sidebar
      document.body.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      expect(spy).toHaveBeenCalled();
    });
  });

  describe('positionCards (via window._positionCards)', () => {
    test('filters out cards with unresolvable rects', () => {
      document.body.innerHTML = `
        <div id="doc"><p>Hello</p></div>
        <div id="sidebar">
          <div class="annotation-card" data-start-char="999"></div>
        </div>
      `;
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

      vi.spyOn(globalThis, 'charOffsetToRect').mockReturnValue({ width: 0 }); // invalid
      window._positionCards();

      const card = document.querySelector('.annotation-card');
      expect(card.style.top).toBe(''); // Didn't get positioned
    });

    test('height caching — hidden card uses cachedHeight', () => {
      document.body.innerHTML = `
        <div id="doc"><p>Hello</p></div>
        <div id="sidebar">
          <div class="annotation-card" data-start-char="0" data-cached-height="120"></div>
        </div>
      `;
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

      vi.spyOn(globalThis, 'charOffsetToRect').mockReturnValue({ width: 10, y: 50, top: 50, height: 20 });
      window._positionCards();

      const card = document.querySelector('.annotation-card');
      expect(card.style.top).toBe('50px');
    });

    test('parseInt with radix 10 for data-start-char', () => {
        document.body.innerHTML = `
          <div id="doc"><p>Hello</p></div>
          <div id="sidebar">
            <div class="annotation-card" data-start-char="010"></div>
          </div>
        `;
        setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

        const charRectSpy = vi.spyOn(globalThis, 'charOffsetToRect').mockReturnValue({ width: 10, y: 50, top: 50, height: 20 });
        window._positionCards();

        expect(charRectSpy).toHaveBeenCalledWith(expect.any(Array), 10); // Not 8
    });

    // GAP 4: Missing positionCards core algorithm tests
    test('cards pushed down to respect minGap', () => {
      document.body.innerHTML = `
        <div id="doc"><p>Hello</p></div>
        <div id="sidebar">
          <div id="card1" class="annotation-card" data-start-char="0" data-cached-height="50"></div>
          <div id="card2" class="annotation-card" data-start-char="5" data-cached-height="50"></div>
        </div>
      `;
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

      // highlight for card2 is at top: 20, but card1 spans top: 0 to 50.
      // So card2 must be pushed to 50 + minGap(10) = 60
      vi.spyOn(globalThis, 'charOffsetToRect').mockImplementation((nodes, offset) => {
        if (offset === 0) return { width: 10, y: 0, top: 0, height: 20 };
        if (offset === 5) return { width: 10, y: 20, top: 20, height: 20 };
      });

      window._positionCards();

      expect(document.getElementById('card1').style.top).toBe('0px');
      expect(document.getElementById('card2').style.top).toBe('60px');
    });

    test('cards sorted by startChar not DOM order', () => {
      document.body.innerHTML = `
        <div id="doc"><p>Hello</p></div>
        <div id="sidebar">
          <div id="card2" class="annotation-card" data-start-char="10" data-cached-height="50"></div>
          <div id="card1" class="annotation-card" data-start-char="0" data-cached-height="50"></div>
        </div>
      `;
      setupCardPositioning('doc', 'sidebar', 10);
      window._textNodes = [{ node: document.getElementById('doc') }];

      vi.spyOn(globalThis, 'charOffsetToRect').mockImplementation((nodes, offset) => {
        if (offset === 0) return { width: 10, y: 100, top: 100, height: 20 };
        if (offset === 10) return { width: 10, y: 110, top: 110, height: 20 };
      });

      window._positionCards();

      // Card1 processed first, at 100
      // Card2 processed second, overlaps, pushed to 100 + 50 + 10 = 160
      expect(document.getElementById('card1').style.top).toBe('100px');
      expect(document.getElementById('card2').style.top).toBe('160px');
    });
  });

  describe('initToolbarObserver', () => {
    test('guard prevents duplicate observers', () => {
      window._toolbarObserverActive = true;
      const spy = vi.spyOn(globalThis, 'ResizeObserver');
      initToolbarObserver();
      expect(spy).not.toHaveBeenCalled();
    });
  });
});
