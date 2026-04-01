export default {
  props: {
    items: {
      type: Array,
      default: () => [],
    },
  },
  setup(props) {
    // Validate Composition API works inside NiceGUI
    const { ref, watch } = Vue;

    const renderCount = ref(0);

    watch(
      () => props.items,
      () => {
        renderCount.value++;
      },
      { deep: true }
    );

    return { renderCount };
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
        style="padding: 4px; cursor: pointer;"
        @click="onItemClick(item)"
      >
        {{ item.id }}
      </div>
    </div>
  `,
};
