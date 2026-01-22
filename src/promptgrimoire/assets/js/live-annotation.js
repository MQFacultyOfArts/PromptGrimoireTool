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

        // Helper to find word span from a node (handles text nodes and elements)
        function findWordSpan(node) {
            if (!node) return null;
            const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
            if (!el) return null;
            return el.closest('[data-w]') || el.querySelector('[data-w]');
        }

        // Find all word spans that intersect with a range
        function getWordRangeFromSelection(selection) {
            if (!selection.rangeCount) return null;

            const allWordSpans = container.querySelectorAll('[data-w]');
            let minWord = Infinity;
            let maxWord = -Infinity;

            for (const span of allWordSpans) {
                if (selection.containsNode(span, true)) {
                    const wordIdx = parseInt(span.dataset.w);
                    minWord = Math.min(minWord, wordIdx);
                    maxWord = Math.max(maxWord, wordIdx);
                }
            }

            if (minWord === Infinity || maxWord === -Infinity) {
                const anchorSpan = findWordSpan(selection.anchorNode);
                const focusSpan = findWordSpan(selection.focusNode);
                if (anchorSpan && focusSpan) {
                    const start = parseInt(anchorSpan.dataset.w);
                    const end = parseInt(focusSpan.dataset.w);
                    return { start: Math.min(start, end), end: Math.max(start, end) };
                }
                return null;
            }

            return { start: minWord, end: maxWord };
        }

        document.addEventListener('selectionchange', () => {
            if (!_emitEvent) return;

            const selection = window.getSelection();
            if (!selection || selection.isCollapsed) {
                _emitEvent('selection_cleared', {});
                return;
            }

            if (!container.contains(selection.anchorNode) ||
                !container.contains(selection.focusNode)) {
                return;
            }

            const wordRange = getWordRangeFromSelection(selection);
            if (wordRange) {
                const range = selection.getRangeAt(0);
                const rect = range.getBoundingClientRect();

                _emitEvent('words_selected', {
                    start: wordRange.start,
                    end: wordRange.end,
                    clientX: rect.left + rect.width / 2,
                    clientY: rect.bottom
                });
            }
        });

        let lastCursorWord = null;
        container.addEventListener('mousemove', (e) => {
            if (!_emitEvent) return;

            const span = e.target.closest('[data-w]');
            if (span) {
                const wordIndex = parseInt(span.dataset.w);
                if (wordIndex !== lastCursorWord) {
                    lastCursorWord = wordIndex;
                    _emitEvent('cursor_moved', { word: wordIndex });
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

            // DEBUG: Log coordinate system info
            const scrollY = window.scrollY;
            const docRect = docContainer.getBoundingClientRect();
            const annRect = annContainer.getBoundingClientRect();

            console.log('=== positionCards DEBUG ===');
            console.log(`scrollY: ${scrollY}`);
            console.log(`docContainer: top=${docRect.top.toFixed(0)} (viewport), offsetTop=${docContainer.offsetTop}`);
            console.log(`annContainer: top=${annRect.top.toFixed(0)} (viewport), offsetTop=${annContainer.offsetTop}`);
            console.log(`annContainer.offsetParent:`, annContainer.offsetParent);

            // Offset between doc container top and annotation container top
            // (they should be aligned, but may differ due to padding/margins)
            const containerOffset = annRect.top - docRect.top;
            console.log(`containerOffset (ann.top - doc.top): ${containerOffset.toFixed(0)}`);

            // Build card info
            const cardInfos = cards.map(card => {
                const startWord = parseInt(card.dataset.startWord);
                const wordSpan = docContainer.querySelector(`[data-w="${startWord}"]`);
                if (!wordSpan) return null;

                const wordRect = wordSpan.getBoundingClientRect();

                // Calculate offset from doc container top using offsetTop chain
                let offsetFromDoc = 0;
                let el = wordSpan;
                while (el && el !== docContainer && docContainer.contains(el)) {
                    offsetFromDoc += el.offsetTop;
                    el = el.offsetParent;
                }

                // Target Y: word position relative to doc container, adjusted for annotation container offset
                // This gives us where the word is relative to the annotation container's coordinate system
                const targetY = (wordRect.top - docRect.top) - containerOffset;

                console.log(`  Word ${startWord}: getBoundingClientRect().top=${wordRect.top.toFixed(0)}, offsetFromDoc=${offsetFromDoc}, targetY=${targetY.toFixed(0)}`);

                return {
                    card,
                    startWord,
                    targetY,
                    height: card.offsetHeight
                };
            }).filter(Boolean);

            // Sort by document order
            cardInfos.sort((a, b) => a.startWord - b.startWord);

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
                const startWordSpan = docContainer.querySelector(`[data-w="${info.startWord}"]`);
                const endWord = parseInt(info.card.dataset.endWord) || info.startWord;
                const endWordSpan = docContainer.querySelector(`[data-w="${endWord - 1}"]`) || startWordSpan;

                const startRect = startWordSpan.getBoundingClientRect();
                const endRect = endWordSpan.getBoundingClientRect();

                // Highlight is visible if its bottom is below viewport top AND its top is above viewport bottom
                const wordInViewport = endRect.bottom > viewportTop && startRect.top < viewportBottom;

                // Force absolute positioning via JS (CSS !important can't beat Quasar)
                info.card.style.position = 'absolute';

                if (!wordInViewport) {
                    // Hide cards whose words are off-screen
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
