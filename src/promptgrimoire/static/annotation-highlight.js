/**
 * annotation-highlight.js — CSS Custom Highlight API text walker and selection.
 *
 * Provides five capabilities:
 * 1. walkTextNodes(root) — flat character offset map of all text nodes
 * 2. applyHighlights(container, highlightData, tagColors) — register CSS highlights
 * 3. clearHighlights() — remove all hl-* entries from CSS.highlights
 * 4. setupSelection(container) — mouseup listener emitting hl_demo_selection (demo)
 * 5. setupAnnotationSelection(container, emitCallback) — mouseup listener with callback
 *
 * All functions are in the global scope (no ES modules) for compatibility
 * with NiceGUI's <script src="..."> loading.
 *
 * The walkTextNodes algorithm mirrors Python extract_text_from_html() in
 * src/promptgrimoire/input_pipeline/html_input.py — both must produce
 * identical character counts for highlight coordinates to be correct.
 */

// ============================================================================
// Text Walker
// ============================================================================

const WHITESPACE_RE = /[\s\u00a0]/;
const SKIP_TAGS = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE']);
const BLOCK_TAGS = new Set([
    'TABLE','TBODY','THEAD','TFOOT','TR','TD','TH',
    'UL','OL','LI','DL','DT','DD',
    'DIV','SECTION','ARTICLE','ASIDE','HEADER','FOOTER','NAV','MAIN',
    'FIGURE','FIGCAPTION','BLOCKQUOTE'
]);

function walkTextNodes(root) {
    // Returns array of {node, startChar, endChar} for each text node
    const result = [];
    let charIdx = 0;

    function walk(el) {
        for (let child = el.firstChild; child; child = child.nextSibling) {
            if (child.nodeType === Node.ELEMENT_NODE) {
                const tag = child.tagName;
                if (SKIP_TAGS.has(tag)) continue;
                if (tag === 'BR') {
                    charIdx++;  // BR counts as 1 char (newline)
                    continue;
                }
                walk(child);
            } else if (child.nodeType === Node.TEXT_NODE) {
                const parent = child.parentElement;
                const text = child.textContent;
                // Skip whitespace-only text nodes in block containers
                if (BLOCK_TAGS.has(parent?.tagName) && /^\s*$/.test(text)) continue;
                // Collapse whitespace runs
                let nodeStart = charIdx;
                let prevWasSpace = false;
                for (const ch of text) {
                    if (WHITESPACE_RE.test(ch)) {
                        if (!prevWasSpace) {
                            charIdx++;
                            prevWasSpace = true;
                        }
                    } else {
                        charIdx++;
                        prevWasSpace = false;
                    }
                }
                result.push({node: child, startChar: nodeStart, endChar: charIdx});
            }
        }
    }
    walk(root);
    return result;
}

// ============================================================================
// Highlight Application (CSS Custom Highlight API)
// ============================================================================

/**
 * Clear annotation highlights from CSS.highlights.
 *
 * Only removes hl-{tag} entries (annotation highlights), preserving
 * hl-sel-* (remote selections) and hl-hover/hl-throb (ephemeral).
 */
function clearHighlights() {
    // Snapshot keys before iterating — deleting during iteration is
    // undefined behaviour on Map-like registries (may skip entries).
    for (const name of Array.from(CSS.highlights.keys())) {
        if (name.startsWith('hl-') && !name.startsWith('hl-sel-')
            && name !== 'hl-hover' && name !== 'hl-throb') {
            CSS.highlights.delete(name);
        }
    }
}

/**
 * Apply highlight data to a container using the CSS Custom Highlight API.
 *
 * Accepts two highlight data formats:
 * - Annotation format: {tag: [{start_char, end_char, id}, ...], ...}
 * - Demo format:       {tag: [{start, end}, ...], ...}
 *
 * @param {Element} container - DOM element containing the document text
 * @param {Object} highlightData - tag-keyed highlight ranges
 * @param {Object} [tagColors] - optional tag-to-priority map (reserved for future use)
 */
function applyHighlights(container, highlightData, tagColors) {
    const textNodes = walkTextNodes(container);
    // Keep global reference fresh for scroll-sync and hover
    window._textNodes = textNodes;
    const totalChars = textNodes.length
        ? textNodes[textNodes.length - 1].endChar : 0;

    window._highlightsReady = false;
    clearHighlights();

    if (!textNodes.length) return;

    let tagIdx = 0;
    for (const [tag, regions] of Object.entries(highlightData)) {
        const ranges = [];
        for (const region of regions) {
            // Support both annotation format (start_char/end_char) and
            // demo format (start/end)
            const startChar = region.start_char !== undefined
                ? region.start_char : region.start;
            const endChar = region.end_char !== undefined
                ? region.end_char : region.end;

            // Validate offsets (AC1.4)
            if (startChar < 0 || endChar < 0) {
                console.warn(
                    `applyHighlights: negative offset for tag "${tag}":`,
                    `start=${startChar}, end=${endChar} — skipping`);
                continue;
            }
            if (startChar >= endChar) {
                console.warn(
                    `applyHighlights: start >= end for tag "${tag}":`,
                    `start=${startChar}, end=${endChar} — skipping`);
                continue;
            }
            if (startChar >= totalChars) {
                console.warn(
                    `applyHighlights: start beyond document length for tag "${tag}":`,
                    `start=${startChar}, totalChars=${totalChars} — skipping`);
                continue;
            }

            // Clamp end to document length (don't skip, just clamp)
            const clampedEnd = Math.min(endChar, totalChars);
            const range = charOffsetToRange(textNodes, startChar, clampedEnd);
            if (range) ranges.push(range);
        }
        if (ranges.length) {
            const hl = new Highlight(...ranges);
            hl.priority = tagIdx;
            CSS.highlights.set('hl-' + tag, hl);
        }
        tagIdx++;
    }
    // Signal that highlights (and _textNodes) are ready
    window._highlightsReady = true;
    document.dispatchEvent(new Event('highlights-ready'));
}

function charOffsetToRange(textNodes, startChar, endChar) {
    let startNode = null, startOff = 0, endNode = null, endOff = 0;

    for (const tn of textNodes) {
        if (!startNode && tn.endChar > startChar) {
            startNode = tn.node;
            startOff = findLocalOffset(tn.node, startChar - tn.startChar);
        }
        if (!endNode && tn.endChar >= endChar) {
            endNode = tn.node;
            endOff = findLocalOffset(tn.node, endChar - tn.startChar);
            break;
        }
    }
    if (!startNode || !endNode) return null;
    try {
        return new StaticRange({
            startContainer: startNode, startOffset: startOff,
            endContainer: endNode, endOffset: endOff
        });
    } catch(e) {
        console.warn('StaticRange creation failed:', e);
        return null;
    }
}

function findLocalOffset(textNode, collapsedOffset) {
    // Convert collapsed-whitespace offset back to raw text offset
    const text = textNode.textContent;
    let collapsed = 0;
    let prevWasSpace = false;
    for (let i = 0; i < text.length; i++) {
        if (collapsed >= collapsedOffset) return i;
        if (WHITESPACE_RE.test(text[i])) {
            if (!prevWasSpace) { collapsed++; prevWasSpace = true; }
        } else {
            collapsed++;
            prevWasSpace = false;
        }
    }
    return text.length;
}

// ============================================================================
// Position Lookup and Highlight Interaction
// ============================================================================

/**
 * Convert a char offset to a viewport-relative DOMRect.
 *
 * Creates a live Range from the StaticRange returned by charOffsetToRange(),
 * then calls getBoundingClientRect(). Returns a zero-size DOMRect at (0,0)
 * if the offset cannot be resolved.
 */
function charOffsetToRect(textNodes, charIdx) {
    const sr = charOffsetToRange(textNodes, charIdx, charIdx + 1);
    if (!sr) return new DOMRect(0, 0, 0, 0);
    const r = document.createRange();
    r.setStart(sr.startContainer, sr.startOffset);
    r.setEnd(sr.endContainer, sr.endOffset);
    return r.getBoundingClientRect();
}

/**
 * Scroll the document so that the given char range is visible, centred vertically.
 */
function scrollToCharOffset(textNodes, startChar, endChar) {
    const sr = charOffsetToRange(textNodes, startChar, endChar);
    if (!sr) return;
    const r = document.createRange();
    r.setStart(sr.startContainer, sr.startOffset);
    r.setEnd(sr.endContainer, sr.endOffset);
    // Compute target scroll position from the range's viewport rect,
    // then use window.scrollTo which reliably fires scroll events.
    // (Previous approach: insert marker → scrollIntoView → remove marker.
    // This failed because removing the marker before the smooth scroll
    // animation started could silently cancel the scroll.)
    const rect = r.getBoundingClientRect();
    const targetY = rect.top + window.scrollY - window.innerHeight / 2 + rect.height / 2;
    window.scrollTo({ top: Math.max(0, targetY), behavior: 'smooth' });
}

/**
 * Show a hover highlight over the given char range via CSS.highlights.
 */
function showHoverHighlight(textNodes, startChar, endChar) {
    const sr = charOffsetToRange(textNodes, startChar, endChar);
    if (!sr) return;
    CSS.highlights.set('hl-hover', new Highlight(sr));
}

/**
 * Remove the hover highlight.
 */
function clearHoverHighlight() {
    CSS.highlights.delete('hl-hover');
}

/**
 * Flash a highlight over the given char range, removing it after durationMs.
 */
function throbHighlight(textNodes, startChar, endChar, durationMs) {
    const sr = charOffsetToRange(textNodes, startChar, endChar);
    if (!sr) return;
    CSS.highlights.set('hl-throb', new Highlight(sr));
    setTimeout(() => CSS.highlights.delete('hl-throb'), durationMs);
}

// ============================================================================
// Selection Detection
// ============================================================================

/**
 * Demo page selection handler — emits hl_demo_selection via NiceGUI emitEvent.
 */
function setupSelection(container) {
    // Guard against duplicate listeners on re-render
    if (window._demoSelectionBound) return;
    window._demoSelectionBound = true;
    document.addEventListener('mouseup', () => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        if (!container.contains(range.startContainer)) return;

        const textNodes = walkTextNodes(container);
        const startChar = rangePointToCharOffset(
            textNodes, range.startContainer, range.startOffset);
        const endChar = rangePointToCharOffset(
            textNodes, range.endContainer, range.endOffset);

        if (startChar !== null && endChar !== null && startChar < endChar) {
            emitEvent('hl_demo_selection', {start_char: startChar, end_char: endChar});
        }
    });
}

/**
 * Annotation page selection handler — calls emitCallback with {start_char, end_char}.
 *
 * Unlike setupSelection (demo), this:
 * - Takes a callback instead of using emitEvent (the caller wires it to NiceGUI)
 * - Checks both startContainer and endContainer are within the container (AC2.3)
 * - Silently ignores collapsed selections (AC2.4)
 *
 * @param {string} containerId - ID of the DOM element containing the document text
 * @param {Function} emitCallback - called with {start_char, end_char} on valid selection
 */
function setupAnnotationSelection(containerId, emitCallback) {
    // Guard against duplicate listeners on re-render (NiceGUI may call
    // setupAnnotationSelection multiple times if the Annotate tab is rebuilt).
    if (window._annotSelectionBound) return;
    window._annotSelectionBound = true;
    document.addEventListener('mouseup', () => {
        const container = document.getElementById(containerId);
        if (!container) return;
        const sel = window.getSelection();
        // AC2.4: ignore collapsed selection (click without drag)
        if (!sel || sel.isCollapsed || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        // AC2.3: ignore selection outside the document container
        if (!container.contains(range.startContainer)) return;
        if (!container.contains(range.endContainer)) return;

        const textNodes = walkTextNodes(container);
        const startChar = rangePointToCharOffset(
            textNodes, range.startContainer, range.startOffset);
        const endChar = rangePointToCharOffset(
            textNodes, range.endContainer, range.endOffset);

        if (startChar !== null && endChar !== null && startChar < endChar) {
            // Position highlight menu near the selection end
            var menu = document.getElementById('highlight-menu');
            if (menu) {
                var endRect = charOffsetToRect(textNodes, Math.max(endChar - 1, startChar));
                menu.style.top = endRect.bottom + 8 + 'px';
                menu.style.left = endRect.left + 'px';
            }
            emitCallback({start_char: startChar, end_char: endChar});
        }
    });
}

function rangePointToCharOffset(textNodes, node, offset) {
    // If node is an element, convert to text node reference
    if (node.nodeType === Node.ELEMENT_NODE) {
        if (offset < node.childNodes.length) {
            const child = node.childNodes[offset];
            if (child.nodeType === Node.TEXT_NODE) {
                node = child;
                offset = 0;
            } else {
                // Child is an element — find first text node
                // inside it (gives the char offset at this
                // boundary point)
                const inside = textNodes.filter(
                    tn => child.contains(tn.node));
                if (inside.length) return inside[0].startChar;
                // No text inside (BR, void elements, etc.) —
                // scan siblings for the nearest text boundary
                return _boundaryFromSiblings(
                    textNodes, node, offset);
            }
        } else {
            // Past end of element — find last text node inside
            const last = textNodes.filter(
                tn => node.contains(tn.node));
            if (last.length) return last[last.length - 1].endChar;
            return null;
        }
    }
    for (const tn of textNodes) {
        if (tn.node === node) {
            return tn.startChar + countCollapsed(
                node.textContent, offset);
        }
    }
    return null;
}

function _boundaryFromSiblings(textNodes, parent, offset) {
    // Look backwards through preceding siblings for last text boundary
    for (let i = offset - 1; i >= 0; i--) {
        const sib = parent.childNodes[i];
        if (sib.nodeType === Node.TEXT_NODE) {
            const tn = textNodes.find(t => t.node === sib);
            if (tn) return tn.endChar;
        } else {
            const found = textNodes.filter(t => sib.contains(t.node));
            if (found.length) return found[found.length - 1].endChar;
        }
    }
    // Nothing before — look forward past the void element
    for (let i = offset + 1; i < parent.childNodes.length; i++) {
        const sib = parent.childNodes[i];
        if (sib.nodeType === Node.TEXT_NODE) {
            const tn = textNodes.find(t => t.node === sib);
            if (tn) return tn.startChar;
        } else {
            const found = textNodes.filter(t => sib.contains(t.node));
            if (found.length) return found[0].startChar;
        }
    }
    return null;
}

function countCollapsed(text, rawOffset) {
    let collapsed = 0;
    let prevWasSpace = false;
    for (let i = 0; i < rawOffset && i < text.length; i++) {
        if (WHITESPACE_RE.test(text[i])) {
            if (!prevWasSpace) { collapsed++; prevWasSpace = true; }
        } else {
            collapsed++;
            prevWasSpace = false;
        }
    }
    return collapsed;
}

// ============================================================================
// Remote Presence: Cursors
// ============================================================================

/**
 * Render a remote user's cursor as a coloured vertical line with name label.
 *
 * The cursor is absolutely positioned within container.parentElement (the
 * scroll container) so it scrolls with the document content.
 *
 * @param {Element} container - The #doc-container element
 * @param {string} clientId - Unique ID for the remote client
 * @param {number} charIdx - Character offset for cursor position
 * @param {string} name - Display name for the remote user
 * @param {string} color - CSS colour for the cursor line and label
 */
function renderRemoteCursor(container, clientId, charIdx, name, color) {
    // Remove any existing cursor for this client
    const existingId = 'remote-cursor-' + clientId;
    const existing = document.getElementById(existingId);
    if (existing) existing.remove();

    // Always re-walk: NiceGUI may re-render doc-container between calls,
    // leaving window._textNodes referencing detached DOM nodes.
    const textNodes = walkTextNodes(container);
    const rect = charOffsetToRect(textNodes, charIdx);
    if (rect.width === 0 && rect.height === 0) return;

    // Get container position for relative offset calculation
    const parent = container.parentElement;
    if (!parent) return;
    const parentRect = parent.getBoundingClientRect();

    const cursor = document.createElement('div');
    cursor.className = 'remote-cursor';
    cursor.id = existingId;
    cursor.dataset.charIdx = String(charIdx);
    cursor.dataset.clientId = clientId;
    cursor.dataset.name = name;
    cursor.dataset.color = color;
    cursor.style.left = (rect.left - parentRect.left + parent.scrollLeft) + 'px';
    cursor.style.top = (rect.top - parentRect.top + parent.scrollTop) + 'px';
    cursor.style.height = rect.height + 'px';
    cursor.style.borderLeft = '2px solid ' + color;

    const label = document.createElement('span');
    label.className = 'remote-cursor-label';
    label.textContent = name;
    label.style.backgroundColor = color;
    cursor.appendChild(label);

    parent.appendChild(cursor);
}

/**
 * Remove a remote user's cursor element from the DOM.
 *
 * @param {string} clientId - The client whose cursor to remove
 */
function removeRemoteCursor(clientId) {
    const el = document.getElementById('remote-cursor-' + clientId);
    if (el) el.remove();
}

/**
 * Recalculate positions for all remote cursors.
 *
 * Call on scroll/resize to keep cursors aligned with their character
 * positions after layout changes.
 *
 * @param {Element} container - The #doc-container element
 */
function updateRemoteCursorPositions(container) {
    const textNodes = walkTextNodes(container);
    const parent = container.parentElement;
    if (!parent) return;
    const parentRect = parent.getBoundingClientRect();

    const cursors = document.querySelectorAll('.remote-cursor');
    for (const cursor of cursors) {
        const charIdx = parseInt(cursor.dataset.charIdx, 10);
        if (isNaN(charIdx)) continue;

        const rect = charOffsetToRect(textNodes, charIdx);
        if (rect.width === 0 && rect.height === 0) continue;

        cursor.style.left = (rect.left - parentRect.left + parent.scrollLeft) + 'px';
        cursor.style.top = (rect.top - parentRect.top + parent.scrollTop) + 'px';
        cursor.style.height = rect.height + 'px';
    }
}

// ============================================================================
// Remote Presence: Selections
// ============================================================================

/**
 * Render a remote user's text selection via the CSS Custom Highlight API.
 *
 * Creates a Highlight object with priority -1 (below annotation highlights
 * at priority 0+) and registers it as 'hl-sel-{clientId}'. A companion
 * <style> element provides the ::highlight() rule with a translucent
 * background colour.
 *
 * @param {string} clientId - Unique ID for the remote client
 * @param {number} startChar - Start character offset (inclusive)
 * @param {number} endChar - End character offset (exclusive)
 * @param {string} name - Display name (reserved for future label use)
 * @param {string} color - CSS colour for the selection background
 */
function renderRemoteSelection(clientId, startChar, endChar, name, color) {
    // Remove any previous selection for this client
    removeRemoteSelection(clientId);

    const container = document.getElementById('doc-container');
    if (!container) return;

    // Always re-walk: NiceGUI may re-render doc-container between calls,
    // leaving window._textNodes referencing detached DOM nodes.
    const textNodes = walkTextNodes(container);
    const range = charOffsetToRange(textNodes, startChar, endChar);
    if (!range) return;

    const hl = new Highlight(range);
    hl.priority = -1;  // Below annotation highlights
    CSS.highlights.set('hl-sel-' + clientId, hl);

    // Inject a <style> for the ::highlight() pseudo-element
    const styleId = 'remote-sel-style-' + clientId;
    const style = document.createElement('style');
    style.id = styleId;
    // Append '30' for ~19% alpha. Assumes `color` is a 6-digit hex string
    // (e.g. '#4CAF50') — server controls the palette in annotation_tags.py.
    style.textContent = '::highlight(hl-sel-' + clientId + ') { background-color: ' + color + '30; }';
    document.head.appendChild(style);
}

/**
 * Remove a remote user's selection highlight and its style element.
 *
 * @param {string} clientId - The client whose selection to remove
 */
function removeRemoteSelection(clientId) {
    CSS.highlights.delete('hl-sel-' + clientId);
    const style = document.getElementById('remote-sel-style-' + clientId);
    if (style) style.remove();
}

/**
 * Remove all remote presence indicators (cursors and selections).
 *
 * Cleans up all remote cursor DOM elements, all CSS Highlight API entries
 * for remote selections, and all companion style elements.
 */
function removeAllRemotePresence() {
    // Remove all cursor elements
    const cursors = document.querySelectorAll('.remote-cursor');
    for (const cursor of cursors) cursor.remove();

    // Remove all remote selection highlights from CSS.highlights
    for (const name of Array.from(CSS.highlights.keys())) {
        if (name.startsWith('hl-sel-')) CSS.highlights.delete(name);
    }

    // Remove all remote selection style elements
    const styles = document.querySelectorAll('[id^="remote-sel-style-"]');
    for (const style of styles) style.remove();
}
