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
  emits: ['test_event', 'toggle_expand', 'change_tag', 'submit_comment', 'delete_comment', 'delete_highlight', 'edit_para_ref', 'locate_highlight'],
  setup(props, { emit }) {
    const { ref, reactive, watch, computed, nextTick, onMounted, onBeforeUnmount } = Vue;

    const renderCount = ref(0);
    const rootRef = ref(null);
    const MIN_GAP = 8;

    // --- Expand/collapse state (sidebar-level, keyed by highlight ID) ---
    const expandedIds = reactive(new Set(props.expanded_ids));
    const detailBuiltIds = reactive(new Set(props.expanded_ids));

    // --- Comment draft state (sidebar-level, maps highlight ID → draft text) ---
    const commentDrafts = reactive(new Map());

    // --- Para ref edit state ---
    const paraRefEditMode = reactive(new Map());  // highlightId → boolean
    const paraRefDrafts = reactive(new Map());    // highlightId → draft text

    // Sync when server pushes new expanded_ids (e.g. reconnection).
    // expandedIds is server-authoritative (clear + rebuild).
    // detailBuiltIds is additive — never destroy already-built detail DOM.
    watch(
      () => props.expanded_ids,
      (newIds) => {
        expandedIds.clear();
        for (var i = 0; i < newIds.length; i++) {
          expandedIds.add(newIds[i]);
          detailBuiltIds.add(newIds[i]);
        }
      }
    );

    function toggleExpand(id) {
      if (expandedIds.has(id)) {
        expandedIds.delete(id);
        emit('toggle_expand', { id: id, expanded: false });
      } else {
        expandedIds.add(id);
        detailBuiltIds.add(id);
        emit('toggle_expand', { id: id, expanded: true });
      }
      // Reposition cards after DOM update from expand/collapse
      nextTick(function() { requestAnimationFrame(positionCards); });
    }

    // --- Mutation event handlers ---

    function onTagChange(id, newTag) {
      emit('change_tag', { id: id, new_tag: newTag });
    }

    function onSubmitComment(id) {
      var text = (commentDrafts.get(id) || '').trim();
      if (!text) return;  // AC1.11: reject empty/whitespace
      emit('submit_comment', { id: id, text: text });
      commentDrafts.set(id, '');  // Clear draft immediately (optimistic)
    }

    function onDeleteComment(highlightId, commentId) {
      emit('delete_comment', { highlight_id: highlightId, comment_id: commentId });
    }

    function onDeleteHighlight(id) {
      emit('delete_highlight', { id: id });
    }

    function getCommentDraft(id) {
      return commentDrafts.get(id) || '';
    }

    function setCommentDraft(id, value) {
      commentDrafts.set(id, value);
    }

    function startParaRefEdit(id, currentValue) {
      paraRefDrafts.set(id, currentValue || '');
      paraRefEditMode.set(id, true);
      nextTick(function() {
        var input = document.querySelector('[data-highlight-id="' + id + '"] [data-testid="para-ref-input"]');
        if (input) input.focus();
      });
    }

    function finishParaRefEdit(id) {
      var newValue = (paraRefDrafts.get(id) || '').trim();
      var item = props.items.find(function(i) { return i.id === id; });
      var oldValue = item ? item.para_ref : '';
      paraRefEditMode.delete(id);
      paraRefDrafts.delete(id);
      if (newValue !== oldValue) {
        emit('edit_para_ref', { id: id, value: newValue });
      }
    }

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
    // TODO(#457): extract shared positionCards to annotation-utils.js,
    // remove duplication with annotation-card-sync.js

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

    function onLocate(startChar, endChar) {
      emit('locate_highlight', { start_char: startChar, end_char: endChar });
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

    return {
      renderCount, rootRef,
      expandedIds, detailBuiltIds,
      commentDrafts,
      paraRefEditMode, paraRefDrafts,
      onCardHover, onCardLeave,
      toggleExpand,
      onTagChange, onSubmitComment, onDeleteComment, onDeleteHighlight,
      getCommentDraft, setCommentDraft,
      startParaRefEdit, finishParaRefEdit, onLocate,
    };
  },
  methods: {
    onItemClick(item) {
      // Test hook — fires test_event for spike tests
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
          data-testid="card-header"
          style="display: flex; align-items: center; gap: 4px; padding: 2px 8px; height: 28px; cursor: pointer;"
          @click="toggleExpand(item.id)"
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
          <button
            data-testid="locate-btn"
            @click.stop="onLocate(item.start_char, item.end_char)"
            title="Scroll to highlight"
            style="border: none; background: none; cursor: pointer; padding: 0 2px; font-size: 14px;"
          >&#x1F4CD;</button>
          <button
            data-testid="expand-btn"
            style="border: none; background: none; cursor: pointer; padding: 0 2px; font-size: 12px;"
            @click.stop="toggleExpand(item.id)"
          >{{ expandedIds.has(item.id) ? '&#9650;' : '&#9660;' }}</button>
          <button
            v-if="item.can_delete"
            data-testid="delete-highlight-btn"
            @click.stop="onDeleteHighlight(item.id)"
            style="border: none; background: none; cursor: pointer; padding: 0 2px; font-size: 12px; color: #c00;"
          >&#10005;</button>
        </div>
        <div
          v-if="detailBuiltIds.has(item.id)"
          v-show="expandedIds.has(item.id)"
          data-testid="card-detail"
          style="padding: 8px;"
        >
          <select
            v-if="permissions.can_annotate"
            data-testid="tag-select"
            :value="item.tag_key"
            @change="onTagChange(item.id, $event.target.value)"
          >
            <option v-for="(name, key) in tag_options" :key="key" :value="key" :selected="key === item.tag_key">{{ name }}</option>
            <option v-if="!tag_options[item.tag_key]" :value="item.tag_key">\u26a0 recovered</option>
          </select>
          <div data-testid="display-author">by {{ item.display_author }}</div>
          <div data-testid="text-preview">{{ item.text_preview }}</div>
          <span v-if="!paraRefEditMode.get(item.id) && permissions.can_annotate"
                @click="startParaRefEdit(item.id, item.para_ref)"
                data-testid="para-ref-label"
                style="cursor: pointer; font-size: 11px; color: #999;">
            {{ item.para_ref || '(no ref)' }}
          </span>
          <!-- Viewers only see para_ref when non-empty (no "(no ref)" affordance for read-only) -->
          <span v-if="!permissions.can_annotate && item.para_ref"
                data-testid="para-ref-label"
                style="font-size: 11px; color: #999;">
            {{ item.para_ref }}
          </span>
          <input v-if="paraRefEditMode.get(item.id)"
                 :value="paraRefDrafts.get(item.id) ?? item.para_ref"
                 @input="paraRefDrafts.set(item.id, $event.target.value)"
                 @blur="finishParaRefEdit(item.id)"
                 @keydown.enter="finishParaRefEdit(item.id)"
                 data-testid="para-ref-input"
                 style="font-size: 11px; max-width: 80px;" />
          <div v-for="comment in item.comments" :key="comment.id" data-testid="comment-item">
            <span data-testid="comment-author">{{ comment.display_author }}</span>
            <span>{{ comment.text }}</span>
            <button
              v-if="comment.can_delete"
              data-testid="comment-delete"
              @click="onDeleteComment(item.id, comment.id)"
              style="border: none; background: none; cursor: pointer; font-size: 12px; color: #c00;"
            >&times;</button>
          </div>
          <span data-testid="comment-count">{{ item.comments.length }}</span>
          <template v-if="permissions.can_annotate">
            <input
              data-testid="comment-input"
              :value="getCommentDraft(item.id)"
              @input="setCommentDraft(item.id, $event.target.value)"
              placeholder="Add comment..."
            />
            <button data-testid="post-comment-btn" @click="onSubmitComment(item.id)">Post</button>
          </template>
        </div>
      </div>
    </div>
  `,
};
