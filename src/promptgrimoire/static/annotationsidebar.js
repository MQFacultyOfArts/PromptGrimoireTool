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
    const { ref, watch, computed } = Vue;

    const renderCount = ref(0);

    watch(
      () => props.items,
      () => {
        renderCount.value++;
        // Global epoch for E2E test synchronisation
        window.__annotationCardsEpoch = (window.__annotationCardsEpoch || 0) + 1;
        // Per-document epoch (Phase 5 will provide doc_container_id)
        if (props.doc_container_id) {
          window.__cardEpochs = window.__cardEpochs || {};
          window.__cardEpochs[props.doc_container_id] = window.__annotationCardsEpoch;
        }
      },
      { deep: true, flush: 'post' }
    );

    const expandedSet = computed(() => new Set(props.expanded_ids));

    return { renderCount, expandedSet };
  },
  methods: {
    onItemClick(item) {
      this.$emit("test_event", { id: item.id });
    },
  },
  template: `
    <div>
      <div
        v-for="item in items"
        :key="item.id"
        data-testid="annotation-card"
        :data-highlight-id="item.id"
        :data-start-char="item.start_char"
        :data-end-char="item.end_char"
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
