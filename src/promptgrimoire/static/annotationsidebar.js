export default {
  props: {
    items: {
      type: Array,
      default: () => [],
    },
    tag_options: {
      type: Object,
      default: () => ({}),
    },
    permissions: {
      type: Object,
      default: () => ({}),
    },
    expanded_ids: {
      type: Array,
      default: () => [],
    },
    doc_container_id: {
      type: String,
      default: '',
    },
  },
  setup(props) {
    const { ref, watch, computed, onMounted, onBeforeUnmount } = Vue;

    const renderCount = ref(0);
    const rootRef = ref(null);
    const MIN_GAP = 8;

    // --- Text node helpers (shared with annotation-highlight.js) ---

    function getTextNodes() {
      var dcId = props.doc_container_id;
      if (!dcId) return null;
      var dc = document.getElementById(dcId);
      var t = window._textNodes;
      if (!dc || !t || !t.length) return null;
      // Re-walk if text nodes are stale (container replaced by NiceGUI/Vue)
      if (!dc.contains(t[0].node)) {
        if (typeof walkTextNodes !== 'function') return null;
        t = walkTextNodes(dc);
        window._textNodes = t;
      }
      return t;
    }

    // --- positionCards: port from annotation-card-sync.js:44-83 ---

    function positionCards() {
      if (window.__perfInstrumented) console.time('positionCards');
      var nodes = getTextNodes();
      if (!nodes || !nodes.length) {
        if (window.__perfInstrumented) console.timeEnd('positionCards');
        return;
      }
      var dcId = props.doc_container_id;
      var dc = document.getElementById(dcId);
      var ac = rootRef.value;
      if (!dc || !ac) {
        if (window.__perfInstrumented) console.timeEnd('positionCards');
        return;
      }
      var cards = Array.from(ac.querySelectorAll('[data-start-char]'));
      if (!cards.length) {
        if (window.__perfInstrumented) console.timeEnd('positionCards');
        return;
      }
      if (typeof charOffsetToRect !== 'function') {
        if (window.__perfInstrumented) console.timeEnd('positionCards');
        return;
      }
      var docRect = dc.getBoundingClientRect();
      var annRect = ac.getBoundingClientRect();
      var cOff = annRect.top - docRect.top;
      var cardInfos = cards.map(function(card) {
        var sc = parseInt(card.dataset.startChar, 10);
        var cr = charOffsetToRect(nodes, sc);
        if (cr.width === 0 && cr.height === 0) return null;
        // Cache height so hidden cards (display:none, offsetHeight=0)
        // use their last-known height (#284).
        var h = card.offsetHeight;
        if (h > 0) {
          card.dataset.cachedHeight = h;
        } else {
          h = parseInt(card.dataset.cachedHeight, 10) || 80;
        }
        return {
          card: card,
          startChar: sc,
          height: h,
          targetY: (cr.top - docRect.top) - cOff,
        };
      }).filter(Boolean);
      cardInfos.sort(function(a, b) { return a.startChar - b.startChar; });
      var minY = 0;
      for (var i = 0; i < cardInfos.length; i++) {
        var info = cardInfos[i];
        info.card.style.position = 'absolute';
        info.card.style.display = '';
        var y = Math.max(info.targetY, minY);
        info.card.style.top = y + 'px';
        minY = y + info.height + MIN_GAP;
      }
      if (window.__perfInstrumented) console.timeEnd('positionCards');
    }

    // --- Scroll listener with rAF throttle ---

    let ticking = false;
    function onScroll() {
      if (!ticking) {
        requestAnimationFrame(function() { positionCards(); ticking = false; });
        ticking = true;
      }
    }

    // --- Hover highlight handlers (pure client-side, no server round-trip) ---

    function onCardHover(item) {
      var nodes = window._textNodes;
      if (nodes && typeof showHoverHighlight === 'function') {
        showHoverHighlight(nodes, item.start_char, item.end_char);
      }
    }

    function onCardLeave() {
      if (typeof clearHoverHighlight === 'function') {
        clearHoverHighlight();
      }
    }

    // --- Highlights-ready listener ---

    function onHighlightsReady() {
      requestAnimationFrame(positionCards);
    }

    // --- Lifecycle ---

    onMounted(function() {
      window.addEventListener('scroll', onScroll, { passive: true });
      document.addEventListener('highlights-ready', onHighlightsReady);

      // Register in per-document positionCards map for tab switching
      var dcId = props.doc_container_id;
      if (dcId) {
        window._positionCardsMap = window._positionCardsMap || {};
        window._positionCardsMap[dcId] = positionCards;
        window._positionCards = positionCards;
        window._activeDocContainerId = dcId;
      }

      // If highlights already applied before mount, position now
      if (window._highlightsReady) {
        requestAnimationFrame(positionCards);
      }
    });

    onBeforeUnmount(function() {
      window.removeEventListener('scroll', onScroll);
      document.removeEventListener('highlights-ready', onHighlightsReady);

      // Clean up per-document registration
      var dcId = props.doc_container_id;
      if (dcId && window._positionCardsMap) {
        delete window._positionCardsMap[dcId];
      }
      if (window._activeDocContainerId === dcId) {
        window._activeDocContainerId = null;
      }
    });

    // --- Watch items for repositioning after DOM update ---

    watch(
      () => props.items,
      () => {
        renderCount.value++;
        // Global epoch for E2E test synchronisation
        window.__annotationCardsEpoch = (window.__annotationCardsEpoch || 0) + 1;
        // Per-document epoch
        if (props.doc_container_id) {
          window.__cardEpochs = window.__cardEpochs || {};
          window.__cardEpochs[props.doc_container_id] = window.__annotationCardsEpoch;
        }
        // Reposition after DOM update (flush: 'post' ensures DOM is ready)
        requestAnimationFrame(positionCards);
      },
      { deep: true, flush: 'post' }
    );

    const expandedSet = computed(() => new Set(props.expanded_ids));

    return { renderCount, expandedSet, onCardHover, onCardLeave, rootRef };
  },
  methods: {
    onItemClick(item) {
      this.$emit("test_event", { id: item.id });
    },
  },
  template: `
    <div ref="rootRef" data-testid="annotation-sidebar-root" style="position: relative;">
      <div
        v-for="item in items"
        :key="item.id"
        data-testid="annotation-card"
        :data-highlight-id="item.id"
        :data-start-char="item.start_char"
        :data-end-char="item.end_char"
        @mouseenter="onCardHover(item)"
        @mouseleave="onCardLeave()"
      >
        <div
          style="display: flex; align-items: center; gap: 4px; padding: 2px 8px; height: 28px; cursor: pointer;"
          @click="onItemClick(item)"
        >
          <span
            :style="{ width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0, backgroundColor: item.color }"
          ></span>
          <span
            :style="{ fontSize: '12px', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: item.color }"
          >{{ item.tag_display }}</span>
          <span style="font-size: 12px; color: #888;">{{ item.initials }}</span>
          <span v-if="item.para_ref" style="font-size: 11px; color: #999;">{{ item.para_ref }}</span>
          <span
            v-if="item.comments.length > 0"
            data-testid="comment-count-badge"
            style="font-size: 11px; background: #e0e0e0; border-radius: 8px; padding: 0 5px; min-width: 16px; text-align: center;"
          >{{ item.comments.length }}</span>
          <span style="flex-grow: 1;"></span>
          <button data-testid="expand-btn" disabled style="border: none; background: none; cursor: pointer; padding: 0 2px; font-size: 12px;">&#9660;</button>
          <button
            v-if="item.can_delete"
            data-testid="delete-highlight-btn"
            disabled
            style="border: none; background: none; cursor: pointer; padding: 0 2px; font-size: 12px; color: #c00;"
          >&#10005;</button>
        </div>
        <div data-testid="card-detail" v-show="expandedSet.has(item.id)" style="padding: 8px;">
          <select data-testid="tag-select" disabled>
            <option v-for="(name, key) in tag_options" :key="key" :value="key">{{ name }}</option>
          </select>
          <div data-testid="text-preview">{{ item.text_preview }}</div>
          <div v-for="comment in item.comments" :key="comment.id" data-testid="comment-item">
            <span>{{ comment.display_author }}: {{ comment.text }}</span>
          </div>
          <input data-testid="comment-input" disabled placeholder="Add comment..." />
          <button data-testid="post-comment-btn" disabled>Post</button>
          <span data-testid="comment-count">{{ item.comments.length }}</span>
        </div>
      </div>
    </div>
  `,
};
