/**
 * annotation-card-sync.js — Scroll-synced card positioning and hover interaction.
 *
 * Positions annotation sidebar cards to track their highlight's vertical
 * position in the document. All cards are always visible (collapsed cards
 * are small enough that hiding off-screen cards is unnecessary).
 *
 * Depends on globals from annotation-highlight.js (loaded first):
 *   - walkTextNodes(root)
 *   - charOffsetToRect(textNodes, charIdx)
 *   - showHoverHighlight(nodes, startChar, endChar)
 *   - clearHoverHighlight()
 *
 * Uses window._textNodes (shared with annotation-highlight.js).
 */

/**
 * Set up scroll-synced card positioning and hover interaction.
 *
 * All DOM lookups are dynamic (getElementById on every call) because
 * NiceGUI/Vue can REPLACE the entire Annotate tab panel DOM when
 * another tab initialises (e.g. Respond tab's Milkdown editor).
 * Closured DOM references become dead after replacement.
 *
 * @param {string} docContainerId - Element ID for the document container
 * @param {string} sidebarId - Element ID for the annotations sidebar
 * @param {number} minGap - Minimum vertical gap (px) between cards
 */
function setupCardPositioning(docContainerId, sidebarId, minGap) {
  var _obs = null;
  var _lastAnnC = null;

  function tn() {
    var dc = document.getElementById(docContainerId);
    var t = window._textNodes;
    if (!dc || !t || !t.length) return null;
    if (!dc.contains(t[0].node)) {
      t = walkTextNodes(dc);
      window._textNodes = t;
    }
    return t;
  }

  function positionCards() {
    var nodes = tn();
    if (!nodes || !nodes.length) return;
    var dc = document.getElementById(docContainerId);
    var ac = document.getElementById(sidebarId);
    if (!dc || !ac) return;
    var cards = Array.from(ac.querySelectorAll('[data-start-char]'));
    if (!cards.length) return;
    var docRect = dc.getBoundingClientRect();
    var annRect = ac.getBoundingClientRect();
    var cOff = annRect.top - docRect.top;
    var cardInfos = cards.map(function(card) {
      var sc = parseInt(card.dataset.startChar, 10);
      var cr = charOffsetToRect(nodes, sc);
      if (cr.width === 0 && cr.height === 0) return null;
      // Cache height on the element so hidden cards (display:none,
      // offsetHeight=0) use their last-known height (#284).
      var h = card.offsetHeight;
      if (h > 0) {
        card.dataset.cachedHeight = h;
      } else {
        h = parseInt(card.dataset.cachedHeight, 10) || 80;
      }
      return {card: card, startChar: sc,
        height: h,
        targetY: (cr.top - docRect.top) - cOff};
    }).filter(Boolean);
    cardInfos.sort(function(a, b) { return a.startChar - b.startChar; });
    var minY = 0;
    for (var i = 0; i < cardInfos.length; i++) {
      var info = cardInfos[i];
      info.card.style.position = 'absolute';
      info.card.style.display = '';
      var y = Math.max(info.targetY, minY);
      info.card.style.top = y + 'px';
      minY = y + info.height + minGap;
    }
  }

  var ticking = false;
  function onScroll() {
    if (!ticking) {
      requestAnimationFrame(function() { positionCards(); ticking = false; });
      ticking = true;
    }
  }

  // Store per-document positionCards function. window._positionCards
  // always delegates to the active document's function.
  window._positionCardsMap = window._positionCardsMap || {};
  window._positionCardsMap[docContainerId] = positionCards;
  window._positionCards = positionCards;
  window._activeDocContainerId = docContainerId;
  window.addEventListener('scroll', onScroll, {passive: true});

  // Attach MutationObserver and position cards.
  // Called on each highlights-ready event AND at setup if highlights
  // are already ready (fixes race where init_js fires highlights-ready
  // before this listener is registered — #236).
  function onHighlightsReady() {
    var ac = document.getElementById(sidebarId);
    if (!ac) return;
    if (ac !== _lastAnnC) {
      if (_obs) _obs.disconnect();
      _obs = new MutationObserver(function() { requestAnimationFrame(positionCards); });
      _obs.observe(ac, {childList: true, subtree: true});
      _lastAnnC = ac;
    }
    requestAnimationFrame(positionCards);
  }

  document.addEventListener('highlights-ready', onHighlightsReady);

  // If highlights were already applied before this listener was
  // registered (SPA navigation with cached scripts), catch up now.
  if (window._highlightsReady) {
    onHighlightsReady();
  }

  // Card hover via event delegation on document
  // (survives DOM replacement)
  var hoveredCard = null;
  document.addEventListener('mouseover', function(e) {
    var ac = document.getElementById(sidebarId);
    if (!ac || !ac.contains(e.target)) {
      if (hoveredCard) { clearHoverHighlight(); hoveredCard = null; }
      return;
    }
    var card = e.target.closest('[data-start-char]');
    if (card === hoveredCard) return;
    clearHoverHighlight();
    hoveredCard = null;
    if (!card) return;
    hoveredCard = card;
    var sc = parseInt(card.dataset.startChar, 10);
    var ec = parseInt(card.dataset.endChar, 10) || sc;
    var nodes = tn();
    if (nodes) showHoverHighlight(nodes, sc, ec);
  });
}

// --- ResizeObserver: track toolbar height for card viewport bounds ---
// Exposed as a global so init_js in document.py can call it after DOM is ready.
// Also self-invokes as best-effort for SPA navigations where elements may
// already exist when the script loads.
//
// When the toolbar lives inside a Quasar q-footer (class "q-footer"),
// q-page handles padding automatically — we only track _toolbarHeight
// for card visibility calculations.  When using the legacy fixed-div
// fallback, we also set paddingBottom on the layout wrapper.
function initToolbarObserver() {
  if (window._toolbarObserverActive) return;
  var toolbar = document.getElementById('tag-toolbar-wrapper');
  if (!toolbar) return;

  window._toolbarObserverActive = true;
  var isQuasarFooter = toolbar.classList.contains('q-footer');
  var ro = new ResizeObserver(function(entries) {
    for (var i = 0; i < entries.length; i++) {
      var h = entries[i].target.offsetHeight;
      window._toolbarHeight = h;
      if (!isQuasarFooter) {
        // Update all layout wrappers (one per rendered source tab)
        document.querySelectorAll('.annotation-layout-wrapper').forEach(function(layout) {
          layout.style.paddingBottom = h + 'px';
        });
      }
    }
  });
  ro.observe(toolbar);
}
initToolbarObserver();
