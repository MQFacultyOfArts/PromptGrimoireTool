/**
 * Build a DOM tree from HTML and return the container element.
 * Uses happy-dom's parser (document.createElement + innerHTML).
 */
export function dom(html) {
  const container = document.createElement('div');
  container.innerHTML = html;
  return container;
}

/**
 * Build a DOM tree and return both the container and the
 * walkTextNodes result for convenience.
 */
export function domWithNodes(html) {
  const container = dom(html);
  const textNodes = walkTextNodes(container);
  return { container, textNodes };
}

/**
 * Mock getBoundingClientRect on an element to return a specific DOMRect.
 * Useful for positionCards tests where happy-dom returns all zeros.
 */
export function mockRect(element, rect) {
  element.getBoundingClientRect = () => new DOMRect(
    rect.x ?? 0, rect.y ?? 0, rect.width ?? 0, rect.height ?? 0
  );
}
