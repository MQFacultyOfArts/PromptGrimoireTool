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
 * Clear all hl-* entries from CSS.highlights.
 */
function clearHighlights() {
    for (const name of CSS.highlights.keys()) {
        if (name.startsWith('hl-')) CSS.highlights.delete(name);
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
    const totalChars = textNodes.length
        ? textNodes[textNodes.length - 1].endChar : 0;

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
            hl.priority = regionPriority(tag, tagIdx);
            CSS.highlights.set('hl-' + tag, hl);
        }
        tagIdx++;
    }
}

function regionPriority(tag, tagIdx) {
    const priorities = {
        jurisdiction: 10, legal_issues: 20,
        legislation: 30, evidence: 40
    };
    return priorities[tag] || (tagIdx !== undefined ? tagIdx : 0);
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
// Selection Detection
// ============================================================================

/**
 * Demo page selection handler — emits hl_demo_selection via NiceGUI emitEvent.
 */
function setupSelection(container) {
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
 * @param {Element} container - DOM element containing the document text
 * @param {Function} emitCallback - called with {start_char, end_char} on valid selection
 */
function setupAnnotationSelection(container, emitCallback) {
    document.addEventListener('mouseup', () => {
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
