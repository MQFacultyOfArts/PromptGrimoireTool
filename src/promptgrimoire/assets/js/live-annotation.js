/**
 * Live Annotation JavaScript
 *
 * Handles text selection, keyboard shortcuts, and scroll-synced card positioning
 * for the live annotation demo page.
 *
 * Scroll sync algorithm inspired by Gwern's sidenotes.js (MIT license, Said Achmiz 2019)
 * https://gwern.net/sidenote
 *
 * Usage: After loading this script, call window.LiveAnnotation.init(emitEvent)
 * where emitEvent is NiceGUI's event emitter function.
 */

window.LiveAnnotation = (function() {
    'use strict';

    let _emitEvent = null;

    // ============================================================
    // Selection Handling
    // ============================================================

    function initSelectionHandling() {
        const container = document.getElementById('doc-container');
        if (!container) return;

        // Helper to find char span from a node (handles text nodes and elements)
        function findCharSpan(node) {
            if (!node) return null;
            const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
            if (!el) return null;
            return el.closest('[data-char-index]') || el.querySelector('[data-char-index]');
        }

        // Find all char spans that intersect with a range
        // Uses range.intersectsNode() which is more robust than selection.containsNode()
        // when selecting text that starts/ends on already-highlighted spans
        function getCharRangeFromSelection(selection) {
            if (!selection.rangeCount) return null;

            const range = selection.getRangeAt(0);
            const allCharSpans = container.querySelectorAll('[data-char-index]');
            let minChar = Infinity;
            let maxChar = -Infinity;

            for (const span of allCharSpans) {
                // intersectsNode is more reliable than containsNode for styled elements
                if (range.intersectsNode(span)) {
                    const charIdx = parseInt(span.dataset.charIndex);
                    minChar = Math.min(minChar, charIdx);
                    maxChar = Math.max(maxChar, charIdx);
                }
            }

            if (minChar === Infinity || maxChar === -Infinity) {
                // Fallback: use anchor/focus nodes directly
                const anchorSpan = findCharSpan(selection.anchorNode);
                const focusSpan = findCharSpan(selection.focusNode);
                if (anchorSpan && focusSpan) {
                    const start = parseInt(anchorSpan.dataset.charIndex);
                    const end = parseInt(focusSpan.dataset.charIndex);
                    return { start: Math.min(start, end), end: Math.max(start, end) };
                }
                return null;
            }

            return { start: minChar, end: maxChar };
        }

        // Shared function to process current selection
        function processSelection(source) {
            if (!_emitEvent) return;

            const selection = window.getSelection();
            if (!selection || selection.isCollapsed) {
                if (source === 'selectionchange') {
                    _emitEvent('selection_cleared', {});
                }
                return;
            }

            if (!container.contains(selection.anchorNode) ||
                !container.contains(selection.focusNode)) {
                return;
            }

            const charRange = getCharRangeFromSelection(selection);
            if (charRange) {
                const range = selection.getRangeAt(0);
                const rect = range.getBoundingClientRect();

                _emitEvent('chars_selected', {
                    start: charRange.start,
                    end: charRange.end,
                    clientX: rect.left + rect.width / 2,
                    clientY: rect.bottom
                });
            }
        }

        // Use both selectionchange and mouseup to catch all selection events
        // selectionchange sometimes doesn't fire when drag-selecting from highlighted text
        document.addEventListener('selectionchange', () => processSelection('selectionchange'));

        // mouseup on container catches selections that selectionchange misses
        container.addEventListener('mouseup', () => {
            // Small delay to let selection finalize
            setTimeout(() => processSelection('mouseup'), 10);
        });

        let lastCursorChar = null;
        container.addEventListener('mousemove', (e) => {
            if (!_emitEvent) return;

            const span = e.target.closest('[data-char-index]');
            if (span) {
                const charIndex = parseInt(span.dataset.charIndex);
                if (charIndex !== lastCursorChar) {
                    lastCursorChar = charIndex;
                    _emitEvent('cursor_moved', { char: charIndex });
                }
            }
        });
    }

    // ============================================================
    // Keyboard Shortcuts
    // ============================================================

    function initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (!_emitEvent) return;

            if (['1','2','3','4','5','6','7','8','9','0'].includes(e.key)) {
                _emitEvent('keydown', { key: e.key });
            }
        });
    }

    // ============================================================
    // Scroll-Synced Card Positioning
    // ============================================================

    function initScrollSync() {
        const docContainer = document.getElementById('doc-container');
        const annContainer = document.getElementById('annotations-container');
        if (!docContainer || !annContainer) return;

        const MIN_GAP = 8;

        function positionCards() {
            const cards = Array.from(annContainer.querySelectorAll('[data-start-word]'));
            if (cards.length === 0) return;

            const docRect = docContainer.getBoundingClientRect();
            const annRect = annContainer.getBoundingClientRect();

            // Offset between doc container top and annotation container top
            // (they should be aligned, but may differ due to padding/margins)
            const containerOffset = annRect.top - docRect.top;

            // Build card info
            const cardInfos = cards.map(card => {
                const startChar = parseInt(card.dataset.startWord);
                const charSpan = docContainer.querySelector(`[data-char-index="${startChar}"]`);
                if (!charSpan) return null;

                const charRect = charSpan.getBoundingClientRect();

                // Target Y: char position relative to doc container, adjusted for annotation container offset
                // This gives us where the char is relative to the annotation container's coordinate system
                const targetY = (charRect.top - docRect.top) - containerOffset;

                return {
                    card,
                    startChar,
                    targetY,
                    height: card.offsetHeight
                };
            }).filter(Boolean);

            // Sort by document order
            cardInfos.sort((a, b) => a.startChar - b.startChar);

            // Viewport bounds for visibility check (account for sticky header)
            const header = document.querySelector('header, .q-header, [class*="nicegui-header"]');
            const headerHeight = header ? header.getBoundingClientRect().height : 0;
            const viewportTop = headerHeight;
            const viewportBottom = window.innerHeight;

            // Position each card, pushing down only if it would overlap previous visible card
            let minY = 0;

            for (const info of cardInfos) {
                // Check if any part of the highlight is in the viewport
                // Visible when: highlight bottom is below viewport top AND highlight top is above viewport bottom
                const startCharSpan = docContainer.querySelector(`[data-char-index="${info.startChar}"]`);
                const endChar = parseInt(info.card.dataset.endWord) || info.startChar;
                const endCharSpan = docContainer.querySelector(`[data-char-index="${endChar - 1}"]`) || startCharSpan;

                const startRect = startCharSpan.getBoundingClientRect();
                const endRect = endCharSpan.getBoundingClientRect();

                // Highlight is visible if its bottom is below viewport top AND its top is above viewport bottom
                const charInViewport = endRect.bottom > viewportTop && startRect.top < viewportBottom;

                // Force absolute positioning via JS (CSS !important can't beat Quasar)
                info.card.style.position = 'absolute';

                if (!charInViewport) {
                    // Hide cards whose chars are off-screen
                    info.card.style.display = 'none';
                    continue;
                }

                // Show and position the card
                info.card.style.display = '';

                // Card goes at targetY, but not above minY (to avoid overlap with previous visible card)
                const y = Math.max(info.targetY, minY);
                info.card.style.top = y + 'px';

                minY = y + info.height + MIN_GAP;
            }
        }

        // Throttled scroll handler
        let ticking = false;
        function onScroll() {
            if (!ticking) {
                requestAnimationFrame(() => {
                    positionCards();
                    ticking = false;
                });
                ticking = true;
            }
        }

        window.addEventListener('scroll', onScroll, { passive: true });
        requestAnimationFrame(positionCards);

        const observer = new MutationObserver(() => {
            requestAnimationFrame(positionCards);
        });
        observer.observe(annContainer, { childList: true, subtree: true });
    }

    // ============================================================
    // Public API
    // ============================================================

    return {
        init: function(emitEvent) {
            _emitEvent = emitEvent;
            initSelectionHandling();
            initKeyboardShortcuts();
            initScrollSync();
        }
    };

})();
