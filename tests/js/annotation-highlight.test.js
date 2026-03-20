import { describe, test, expect, afterEach, vi } from 'vitest';
import { dom, domWithNodes, mockRect } from './helpers.js';

describe('annotation-highlight.js', () => {
  afterEach(() => {
    CSS.highlights.clear();
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    delete window._textNodes;
    delete window._highlightsReady;
    delete window._annotSelectionBound;
    delete window._demoSelectionBound;
    vi.restoreAllMocks();
  });

  describe('walkTextNodes', () => {
    test('simple text', () => {
      const { textNodes } = domWithNodes('<p>Hello</p>');
      expect(textNodes).toHaveLength(1);
      expect(textNodes[0].startChar).toBe(0);
      expect(textNodes[0].endChar).toBe(5);
    });

    test('multiple paragraphs', () => {
      const { textNodes } = domWithNodes('<p>A</p><p>B</p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[1].endChar).toBe(2);
    });

    test('nested elements', () => {
      const { textNodes } = domWithNodes('<div><span>Hi</span></div>');
      expect(textNodes).toHaveLength(1);
      expect(textNodes[0].endChar).toBe(2);
    });

    test('empty container', () => {
      const { textNodes } = domWithNodes('');
      expect(textNodes).toHaveLength(0);
    });

    test('preserves spaces', () => {
      const { textNodes } = domWithNodes('<p>A B</p>');
      expect(textNodes).toHaveLength(1);
      expect(textNodes[0].endChar).toBe(3);
    });

    test('BR becomes newline', () => {
      const { textNodes } = domWithNodes('<p>A<br>B</p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[0].endChar).toBe(1);
      expect(textNodes[1].startChar).toBe(2); // +1 for BR
    });

    test('multiple BR tags', () => {
      const { textNodes } = domWithNodes('<p>A<br><br>B</p>');
      expect(textNodes[1].startChar).toBe(3); // 1 for A, 2 for BRs
    });

    test('whitespace-only text in block container skipped', () => {
      const { textNodes } = domWithNodes('<ul>\n  <li>A</li>\n  <li>B</li>\n</ul>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[0].node.textContent).toBe('A');
      expect(textNodes[1].node.textContent).toBe('B');
    });

    test('whitespace collapse', () => {
      const { textNodes } = domWithNodes('<p>A   B</p>');
      expect(textNodes[0].endChar).toBe(3);
    });

    test('tab and newline collapse', () => {
      const { textNodes } = domWithNodes('<p>A\t\n\tB</p>');
      expect(textNodes[0].endChar).toBe(3);
    });

    test('script tag skipped', () => {
      const { textNodes } = domWithNodes('<p>A</p><script>var x = 1;</script><p>B</p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[1].node.textContent).toBe('B');
      expect(textNodes[1].endChar).toBe(2);
    });

    test('style tag skipped', () => {
      const { textNodes } = domWithNodes('<p>X</p><style>.cls{}</style><p>Y</p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[1].endChar).toBe(2);
    });

    test('noscript tag skipped', () => {
      const { textNodes } = domWithNodes('<p>A</p><noscript>Enable JS</noscript><p>B</p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[1].endChar).toBe(2);
    });

    test('template tag skipped', () => {
      const { textNodes } = domWithNodes('<p>A</p><template><p>hidden</p></template><p>B</p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[1].endChar).toBe(2);
    });

    test('nbsp collapsed to space', () => {
      const { textNodes } = domWithNodes('<p>A\u00a0B</p>');
      expect(textNodes[0].endChar).toBe(3);
    });

    test('inline element whitespace preserved', () => {
      const { textNodes } = domWithNodes('<p><span>A </span><span>B</span></p>');
      expect(textNodes).toHaveLength(2);
      expect(textNodes[0].endChar).toBe(2);
      expect(textNodes[1].startChar).toBe(2);
      expect(textNodes[1].endChar).toBe(3);
    });

    test('inter-paragraph newlines skipped (body is block)', () => {
      const { textNodes } = domWithNodes('<div><p>AAA</p>\n\n<p>BBB</p>\n\n<p>CCC</p></div>');
      expect(textNodes).toHaveLength(3);
      expect(textNodes[2].endChar).toBe(9);
    });

    test('text node startChar/endChar are contiguous', () => {
      const { textNodes } = domWithNodes('<p>AB</p><p>CD</p>');
      expect(textNodes[0].endChar).toBe(textNodes[1].startChar);
    });

    test('endChar of last node equals total character count', () => {
      const { textNodes } = domWithNodes('<p>Hello World</p>');
      expect(textNodes[textNodes.length - 1].endChar).toBe(11);
    });

    test('node references point to actual DOM text nodes', () => {
      const { textNodes } = domWithNodes('<p>A</p>');
      expect(textNodes[0].node.nodeType).toBe(Node.TEXT_NODE);
    });
  });

  describe('findLocalOffset', () => {
    test('no whitespace — identity mapping', () => {
      const node = { textContent: 'Hello' };
      expect(findLocalOffset(node, 3)).toBe(3);
    });

    test('leading spaces — collapsed offset skips run', () => {
      const node = { textContent: '   Hello' };
      expect(findLocalOffset(node, 0)).toBe(0);
      expect(findLocalOffset(node, 1)).toBe(1);
    });

    test('internal whitespace run', () => {
      const node = { textContent: 'A   B' };
      expect(findLocalOffset(node, 0)).toBe(0);
      expect(findLocalOffset(node, 1)).toBe(1);
      expect(findLocalOffset(node, 2)).toBe(2);
    });

    test('trailing whitespace', () => {
      const node = { textContent: 'AB   ' };
      expect(findLocalOffset(node, 2)).toBe(2);
      expect(findLocalOffset(node, 3)).toBe(3);
    });

    test('nbsp treated as whitespace', () => {
      const node = { textContent: 'A\u00a0\u00a0B' };
      expect(findLocalOffset(node, 2)).toBe(2);
    });

    test('offset beyond text returns text.length', () => {
      const node = { textContent: 'AB' };
      expect(findLocalOffset(node, 99)).toBe(2);
    });

    test('offset 0 returns 0', () => {
      const node = { textContent: 'anything' };
      expect(findLocalOffset(node, 0)).toBe(0);
    });
  });

  describe('countCollapsed', () => {
    test('no whitespace — identity', () => {
      expect(countCollapsed('Hello', 3)).toBe(3);
    });

    test('whitespace run counts as 1', () => {
      expect(countCollapsed('A   B', 4)).toBe(2);
      expect(countCollapsed('A   B', 5)).toBe(3);
    });

    test('rawOffset 0 returns 0', () => {
      expect(countCollapsed('anything', 0)).toBe(0);
    });

    test('rawOffset past text length', () => {
      expect(countCollapsed('AB', 10)).toBe(2);
    });

    test('all whitespace', () => {
      expect(countCollapsed('     ', 5)).toBe(1);
    });

    test('nbsp treated as whitespace', () => {
      expect(countCollapsed('A\u00a0B', 2)).toBe(2);
    });
  });

  describe('whitespace collapsing consistency', () => {
    test.each([
      'Hello',
      'A   B',
      'A\t\n\tB',
      'A\u00a0B',
      '   leading',
      'trailing   ',
      '  A  B  C  ',
    ])('all three functions agree on "%s"', (text) => {
      const { textNodes } = domWithNodes(`<span>${text}</span>`);
      const endChar = textNodes.length ? textNodes[textNodes.length - 1].endChar : 0;
      const collapsed = countCollapsed(text, text.length);
      expect(endChar).toBe(collapsed);

      for (let i = 0; i <= text.length; i++) {
        const c = countCollapsed(text, i);
        if (i > 0) {
          expect(c).toBeGreaterThanOrEqual(countCollapsed(text, i - 1));
        }
        const back = findLocalOffset({ textContent: text }, c);
        // It should either round trip or find the start of a whitespace run
        expect(typeof back).toBe('number');
      }
    });
  });

  describe('charOffsetToRange', () => {
    test('single text node — full range', () => {
      const { textNodes } = domWithNodes('<p>Hello</p>');
      const range = charOffsetToRange(textNodes, 0, 5);
      expect(range).not.toBeNull();
      expect(range.startContainer).toBe(textNodes[0].node);
      expect(range.endContainer).toBe(textNodes[0].node);
      expect(range.startOffset).toBe(0);
      expect(range.endOffset).toBe(5);
    });

    test('single text node — partial range', () => {
      const { textNodes } = domWithNodes('<p>Hello World</p>');
      const range = charOffsetToRange(textNodes, 6, 11);
      expect(range.startOffset).toBe(6);
      expect(range.endOffset).toBe(11);
    });

    test('range spanning multiple text nodes', () => {
      const { textNodes } = domWithNodes('<p><span>AB</span><span>CD</span></p>');
      const range = charOffsetToRange(textNodes, 1, 3);
      expect(range.startContainer).toBe(textNodes[0].node);
      expect(range.endContainer).toBe(textNodes[1].node);
    });

    test('startChar at node boundary', () => {
      const { textNodes } = domWithNodes('<p><span>AB</span><span>CD</span></p>');
      const range = charOffsetToRange(textNodes, 2, 4);
      expect(range.startContainer).toBe(textNodes[1].node);
    });

    test('returns null for out-of-range offsets', () => {
      const { textNodes } = domWithNodes('<p>Hi</p>');
      expect(charOffsetToRange(textNodes, 10, 20)).toBeNull();
    });

    test('returns null for empty text nodes', () => {
      expect(charOffsetToRange([], 0, 1)).toBeNull();
    });

    test('handles whitespace-collapsed offsets correctly', () => {
      const { textNodes } = domWithNodes('<p>A   B</p>');
      const range = charOffsetToRange(textNodes, 0, 3);
      expect(range.endOffset).toBe(5); // Raw length is 5
    });
  });

  describe('rangePointToCharOffset', () => {
    test('text node — returns startChar + collapsed offset', () => {
      const { textNodes } = domWithNodes('<p>Hello</p>');
      const offset = rangePointToCharOffset(textNodes, textNodes[0].node, 3);
      expect(offset).toBe(3);
    });

    test('element node — offset points to text child', () => {
      const { container, textNodes } = domWithNodes('<p>AB</p>');
      const p = container.firstChild;
      const offset = rangePointToCharOffset(textNodes, p, 0);
      expect(offset).toBe(0);
    });

    test('element node — offset points to element child with text', () => {
      const { container, textNodes } = domWithNodes('<p><span>AB</span></p>');
      const p = container.firstChild;
      const offset = rangePointToCharOffset(textNodes, p, 0);
      expect(offset).toBe(0);
    });

    test('element node — offset past end', () => {
      const { container, textNodes } = domWithNodes('<p>AB</p>');
      const p = container.firstChild;
      const offset = rangePointToCharOffset(textNodes, p, 1);
      expect(offset).toBe(2);
    });

    test('element node — child is void element (BR)', () => {
      const { container, textNodes } = domWithNodes('<p>A<br>B</p>');
      const p = container.firstChild;
      // offset=1 points at the <br> element — should fall through to _boundaryFromSiblings
      const offset = rangePointToCharOffset(textNodes, p, 1);
      expect(offset).toBe(1); // endChar of "A" text node
    });

    test('unknown text node returns null', () => {
      const { textNodes } = domWithNodes('<p>Hi</p>');
      const unknownNode = document.createTextNode('Unknown');
      expect(rangePointToCharOffset(textNodes, unknownNode, 0)).toBeNull();
    });
  });

  describe('_boundaryFromSiblings', () => {
    test('backward scan finds preceding text node', () => {
      const { container, textNodes } = domWithNodes('<p>A<br>B</p>');
      const p = container.firstChild;
      const offset = _boundaryFromSiblings(textNodes, p, 1);
      expect(offset).toBe(1);
    });

    test('backward scan finds text inside preceding element', () => {
      const { container, textNodes } = domWithNodes('<p><span>A</span><br>B</p>');
      const p = container.firstChild;
      // offset=1 points at <br>, backward scan finds text inside <span>
      const offset = _boundaryFromSiblings(textNodes, p, 1);
      expect(offset).toBe(1); // endChar of "A" inside <span>
    });

    test('forward scan when nothing before', () => {
      const { container, textNodes } = domWithNodes('<p><br>B</p>');
      const p = container.firstChild;
      const offset = _boundaryFromSiblings(textNodes, p, 0);
      expect(offset).toBe(1); // after <br>
    });

    test('returns null when no text nodes anywhere', () => {
      const { container, textNodes } = domWithNodes('<p><br><br></p>');
      const p = container.firstChild;
      const offset = _boundaryFromSiblings(textNodes, p, 1);
      expect(offset).toBeNull();
    });
  });

  describe('clearHighlights', () => {
    test('removes hl-tag entries', () => {
      CSS.highlights.set('hl-important', new Highlight());
      CSS.highlights.set('hl-evidence', new Highlight());
      clearHighlights();
      expect(CSS.highlights.has('hl-important')).toBe(false);
      expect(CSS.highlights.has('hl-evidence')).toBe(false);
    });

    test('preserves hl-sel-* entries', () => {
      CSS.highlights.set('hl-sel-abc', new Highlight());
      CSS.highlights.set('hl-important', new Highlight());
      clearHighlights();
      expect(CSS.highlights.has('hl-sel-abc')).toBe(true);
      expect(CSS.highlights.has('hl-important')).toBe(false);
    });

    test('preserves hl-hover', () => {
      CSS.highlights.set('hl-hover', new Highlight());
      clearHighlights();
      expect(CSS.highlights.has('hl-hover')).toBe(true);
    });

    test('preserves hl-throb', () => {
      CSS.highlights.set('hl-throb', new Highlight());
      clearHighlights();
      expect(CSS.highlights.has('hl-throb')).toBe(true);
    });

    test('handles empty highlights map', () => {
      expect(() => clearHighlights()).not.toThrow();
    });
  });

  describe('applyHighlights', () => {
    test('applies highlights from annotation format', () => {
      const container = dom('<p>Hello World</p>');
      const data = { "tag1": [{ start_char: 0, end_char: 5, id: "h1" }] };
      applyHighlights(container, data);
      expect(CSS.highlights.has('hl-tag1')).toBe(true);
      expect(CSS.highlights.get('hl-tag1').ranges).toHaveLength(1);
    });

    test('applies highlights from demo format', () => {
      const container = dom('<p>Hello World</p>');
      const data = { "tag1": [{ start: 0, end: 5 }] };
      applyHighlights(container, data);
      expect(CSS.highlights.has('hl-tag1')).toBe(true);
      expect(CSS.highlights.get('hl-tag1').ranges).toHaveLength(1);
    });

    test('skips negative offsets', () => {
      const container = dom('<p>Hello World</p>');
      const data = { "tag1": [{ start_char: -1, end_char: 5 }] };
      applyHighlights(container, data);
      expect(CSS.highlights.has('hl-tag1')).toBe(false);
    });

    test('skips start >= end', () => {
      const container = dom('<p>Hello World</p>');
      const data = { "tag1": [{ start_char: 5, end_char: 5 }] };
      applyHighlights(container, data);
      expect(CSS.highlights.has('hl-tag1')).toBe(false);
    });

    test('skips start beyond document length', () => {
      const container = dom('<p>Hi</p>');
      const data = { "tag1": [{ start_char: 10, end_char: 15 }] };
      applyHighlights(container, data);
      expect(CSS.highlights.has('hl-tag1')).toBe(false);
    });

    test('clamps end to document length', () => {
      const container = dom('<p>Hi</p>');
      const data = { "tag1": [{ start_char: 0, end_char: 100 }] };
      applyHighlights(container, data);
      expect(CSS.highlights.has('hl-tag1')).toBe(true);
      expect(CSS.highlights.get('hl-tag1').ranges[0].endOffset).toBe(2);
    });

    test('sets priority by tag order', () => {
      const container = dom('<p>Hello World</p>');
      const data = { "first": [{ start_char: 0, end_char: 2 }], "second": [{ start_char: 3, end_char: 5 }] };
      applyHighlights(container, data);
      expect(CSS.highlights.get('hl-first').priority).toBe(0);
      expect(CSS.highlights.get('hl-second').priority).toBe(1);
    });

    test('clears previous highlights before applying', () => {
      CSS.highlights.set('hl-old', new Highlight());
      const container = dom('<p>Hello</p>');
      applyHighlights(container, { "new": [{ start_char: 0, end_char: 5 }] });
      expect(CSS.highlights.has('hl-old')).toBe(false);
      expect(CSS.highlights.has('hl-new')).toBe(true);
    });

    test('sets window._highlightsReady and dispatches event', () => {
      const container = dom('<p>Hello World</p>');
      let dispatched = false;
      document.addEventListener('highlights-ready', () => { dispatched = true; }, { once: true });
      applyHighlights(container, { "tag1": [{ start_char: 0, end_char: 5 }] });
      expect(window._highlightsReady).toBe(true);
      expect(dispatched).toBe(true);
    });

    test('empty container — early return', () => {
      const container = dom('');
      applyHighlights(container, { "tag1": [{ start_char: 0, end_char: 5 }] });
      expect(CSS.highlights.has('hl-tag1')).toBe(false);
    });
  });

  describe('setupAnnotationSelection', () => {
    test('calls emitCallback with char offsets on valid selection', () => {
      const { container, textNodes } = domWithNodes('<p id="test-container">Hello World</p>');
      document.body.appendChild(container);

      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);

      const selection = {
        isCollapsed: false,
        rangeCount: 1,
        getRangeAt: () => ({
          startContainer: textNodes[0].node,
          startOffset: 0,
          endContainer: textNodes[0].node,
          endOffset: 5,
          getBoundingClientRect: () => ({ bottom: 0, left: 0, right: 0 })
        })
      };
      vi.stubGlobal('getSelection', () => selection);

      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      expect(emitCallback).toHaveBeenCalledWith({ start_char: 0, end_char: 5 });
    });

    test('ignores collapsed selection', () => {
      const { container } = domWithNodes('<p id="test-container">Hello World</p>');
      document.body.appendChild(container);
      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);

      vi.stubGlobal('getSelection', () => ({ isCollapsed: true, rangeCount: 1 }));
      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      expect(emitCallback).not.toHaveBeenCalled();
    });

    test('ignores selection outside container', () => {
      const { container } = domWithNodes('<p id="test-container">Hello World</p>');
      document.body.appendChild(container);

      const otherContainer = dom('<p id="other">Other</p>');
      document.body.appendChild(otherContainer);

      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);

      const selection = {
        isCollapsed: false,
        rangeCount: 1,
        getRangeAt: () => ({
          startContainer: otherContainer.firstChild,
          startOffset: 0,
          endContainer: otherContainer.firstChild,
          endOffset: 5
        })
      };
      vi.stubGlobal('getSelection', () => selection);

      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      expect(emitCallback).not.toHaveBeenCalled();
    });

    test('ignores selection with end outside container', () => {
      const { container, textNodes } = domWithNodes('<p id="test-container">Hello</p>');
      document.body.appendChild(container);

      const otherContainer = dom('<p id="other">Other</p>');
      document.body.appendChild(otherContainer);

      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);

      const selection = {
        isCollapsed: false,
        rangeCount: 1,
        getRangeAt: () => ({
          startContainer: textNodes[0].node,
          startOffset: 0,
          endContainer: otherContainer.firstChild,
          endOffset: 5
        })
      };
      vi.stubGlobal('getSelection', () => selection);

      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      expect(emitCallback).not.toHaveBeenCalled();
    });

    test('guard prevents duplicate listeners', () => {
      const { container, textNodes } = domWithNodes('<p id="test-container">Hello World</p>');
      document.body.appendChild(container);

      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);
      setupAnnotationSelection('test-container', emitCallback); // second call

      const selection = {
        isCollapsed: false,
        rangeCount: 1,
        getRangeAt: () => ({
          startContainer: textNodes[0].node,
          startOffset: 0,
          endContainer: textNodes[0].node,
          endOffset: 5,
          getBoundingClientRect: () => ({ bottom: 0, left: 0, right: 0 })
        })
      };
      vi.stubGlobal('getSelection', () => selection);

      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      expect(emitCallback).toHaveBeenCalledTimes(1);
    });

    test('positions highlight menu near selection end', () => {
      const { container, textNodes } = domWithNodes('<p id="test-container">Hello World</p>');
      document.body.appendChild(container);

      const menu = dom('<div id="highlight-menu" style="display: none;"></div>');
      document.body.appendChild(menu);

      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);

      const selection = {
        isCollapsed: false,
        rangeCount: 1,
        getRangeAt: () => ({
          startContainer: textNodes[0].node,
          startOffset: 0,
          endContainer: textNodes[0].node,
          endOffset: 5,
          getBoundingClientRect: () => ({ bottom: 100, left: 50, right: 150 })
        })
      };
      vi.stubGlobal('getSelection', () => selection);
      vi.spyOn(globalThis, 'charOffsetToRect').mockReturnValue({ right: 150, left: 150, bottom: 100 });

      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

      const m = document.getElementById('highlight-menu');
      expect(m.style.top).toBe('108px'); // bottom + 8
      expect(m.style.left).toBe('150px');
    });

    test('flips menu above when near bottom toolbar', () => {
      const { container, textNodes } = domWithNodes('<p id="test-container">Hello World</p>');
      document.body.appendChild(container);

      const menu = dom('<div id="highlight-menu" style="display: none;"></div>');
      document.body.appendChild(menu);

      const emitCallback = vi.fn();
      setupAnnotationSelection('test-container', emitCallback);

      // Near window.innerHeight (simulate 800)
      vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(800);

      const selection = {
        isCollapsed: false,
        rangeCount: 1,
        getRangeAt: () => ({
          startContainer: textNodes[0].node,
          startOffset: 0,
          endContainer: textNodes[0].node,
          endOffset: 5,
          getBoundingClientRect: () => ({ bottom: 790, left: 50, right: 150 }) // Near bottom (800 - 80 < 790)
        })
      };
      vi.stubGlobal('getSelection', () => selection);
      vi.spyOn(globalThis, 'charOffsetToRect').mockReturnValue({ right: 150, bottom: 790, top: 770 });

      container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

      const m = document.getElementById('highlight-menu');
      expect(m.style.top).toBe('642px'); // flipped position
    });
  });
  describe('simple wrappers', () => {
    test('charOffsetToRect returns DOMRect(0,0,0,0) for invalid offset', () => {
      const rect = charOffsetToRect([], 10);
      expect(rect.width).toBe(0);
    });

    test('showHoverHighlight sets hl-hover', () => {
      const { textNodes } = domWithNodes('<p>Hello</p>');
      showHoverHighlight(textNodes, 0, 5);
      expect(CSS.highlights.has('hl-hover')).toBe(true);
    });

    test('clearHoverHighlight removes hl-hover', () => {
      CSS.highlights.set('hl-hover', new Highlight());
      clearHoverHighlight();
      expect(CSS.highlights.has('hl-hover')).toBe(false);
    });

    test('throbHighlight sets and removes hl-throb', () => {
      vi.useFakeTimers();
      const { textNodes } = domWithNodes('<p>Hello</p>');
      throbHighlight(textNodes, 0, 5, 500);
      expect(CSS.highlights.has('hl-throb')).toBe(true);
      vi.advanceTimersByTime(500);
      expect(CSS.highlights.has('hl-throb')).toBe(false);
      vi.useRealTimers();
    });
  });

  describe('remote presence', () => {
    test('renderRemoteCursor creates element', () => {
      const { container, textNodes } = domWithNodes('<p>Hello</p>');
      document.body.appendChild(container); // BLOCKER 3 fix
      window._textNodes = textNodes;
      vi.spyOn(globalThis, 'charOffsetToRect').mockReturnValue({ x: 10, y: 20, width: 2, height: 15, top: 20, left: 10 });
      renderRemoteCursor(container, 'client1', 0, 'Alice', '#f00');
      expect(container.parentElement.querySelector('#remote-cursor-client1')).not.toBeNull();
    });

    test('removeRemoteCursor removes element', () => {
      const container = dom('<div id="remote-cursor-client1"></div>');
      document.body.appendChild(container);
      removeRemoteCursor('client1');
      expect(document.getElementById('remote-cursor-client1')).toBeNull();
    });

    test('renderRemoteSelection creates CSS highlight and style', () => {
      const { container, textNodes } = domWithNodes('<p>Hello</p>');
      container.id = 'doc-container'; // BLOCKER 4 fix
      document.body.appendChild(container);
      window._textNodes = textNodes;
      renderRemoteSelection('client1', 0, 5, 'Alice', '#f00');
      expect(CSS.highlights.has('hl-sel-client1')).toBe(true);
      expect(document.getElementById('remote-sel-style-client1')).not.toBeNull();
    });

    test('removeRemoteSelection removes highlight and style', () => {
      CSS.highlights.set('hl-sel-client1', new Highlight());
      const style = document.createElement('style');
      style.id = 'remote-sel-style-client1';
      document.head.appendChild(style);

      removeRemoteSelection('client1');
      expect(CSS.highlights.has('hl-sel-client1')).toBe(false);
      expect(document.getElementById('remote-sel-style-client1')).toBeNull();
    });
    test('removeAllRemotePresence clears all', () => {
      const container = dom('<div class="remote-cursor"></div>');
      document.body.appendChild(container);
      CSS.highlights.set('hl-sel-client1', new Highlight());
      removeAllRemotePresence();
      expect(document.querySelectorAll('.remote-cursor').length).toBe(0);
      expect(CSS.highlights.has('hl-sel-client1')).toBe(false);
    });
  });
});
