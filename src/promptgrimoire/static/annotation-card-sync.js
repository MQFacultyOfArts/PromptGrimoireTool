/**
 * annotation-card-sync.js — Scroll-synced card positioning and hover interaction.
 *
 * Positions annotation sidebar cards to track their highlight's vertical
 * position in the document. Cards for off-screen highlights are hidden.
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
      var sc = parseInt(card.dataset.startChar);
      var cr = charOffsetToRect(nodes, sc);
      if (cr.width === 0 && cr.height === 0) return null;
      return {card: card, startChar: sc,
        height: card.offsetHeight,
        targetY: (cr.top - docRect.top) - cOff};
    }).filter(Boolean);
    cardInfos.sort(function(a, b) { return a.startChar - b.startChar; });
    var hH = 60, vT = hH, vB = window.innerHeight;
    var minY = 0;
    for (var i = 0; i < cardInfos.length; i++) {
      var info = cardInfos[i];
      var sc2 = info.startChar;
      var ec2 = parseInt(info.card.dataset.endChar) || sc2;
      var sr = charOffsetToRect(nodes, sc2);
      var er = charOffsetToRect(nodes, Math.max(ec2 - 1, sc2));
      var inView = er.bottom > vT && sr.top < vB;
      info.card.style.position = 'absolute';
      if (!inView) { info.card.style.display = 'none'; continue; }
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

  window._positionCards = positionCards;
  window.addEventListener('scroll', onScroll, {passive: true});

  // Re-attach MutationObserver on each highlights-ready
  // because the annotations-container DOM element may have
  // been replaced by Vue re-rendering.
  document.addEventListener('highlights-ready', function() {
    var ac = document.getElementById(sidebarId);
    if (!ac) return;
    if (ac !== _lastAnnC) {
      if (_obs) _obs.disconnect();
      _obs = new MutationObserver(function() { requestAnimationFrame(positionCards); });
      _obs.observe(ac, {childList: true, subtree: true});
      _lastAnnC = ac;
    }
    requestAnimationFrame(positionCards);
  });

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
    var sc = parseInt(card.dataset.startChar);
    var ec = parseInt(card.dataset.endChar) || sc;
    var nodes = tn();
    if (nodes) showHoverHighlight(nodes, sc, ec);
  });
}
