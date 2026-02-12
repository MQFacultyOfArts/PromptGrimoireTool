/**
 * annotation-highlight.js — CSS Custom Highlight API text walker and selection.
 *
 * Provides three capabilities:
 * 1. walkTextNodes(root) — flat character offset map of all text nodes
 * 2. applyHighlights(container, highlightData) — register CSS highlights
 * 3. setupSelection(container) — mouseup listener emitting hl_demo_selection
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

function applyHighlights(container, highlightData) {
    const textNodes = walkTextNodes(container);
    if (!textNodes.length) return;

    // Clear existing highlights
    for (const name of CSS.highlights.keys()) {
        if (name.startsWith('hl-')) CSS.highlights.delete(name);
    }

    for (const [tag, regions] of Object.entries(highlightData)) {
        const ranges = [];
        for (const region of regions) {
            const range = charOffsetToRange(textNodes, region.start, region.end);
            if (range) ranges.push(range);
        }
        if (ranges.length) {
            const hl = new Highlight(...ranges);
            hl.priority = regionPriority(tag);
            CSS.highlights.set('hl-' + tag, hl);
        }
    }
}

function regionPriority(tag) {
    const priorities = {
        jurisdiction: 10, legal_issues: 20,
        legislation: 30, evidence: 40
    };
    return priorities[tag] || 0;
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

function rangePointToCharOffset(textNodes, node, offset) {
    // If node is an element, convert to text node reference
    if (node.nodeType === Node.ELEMENT_NODE) {
        if (offset < node.childNodes.length) {
            node = node.childNodes[offset];
            offset = 0;
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
            return tn.startChar + countCollapsed(node.textContent, offset);
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
