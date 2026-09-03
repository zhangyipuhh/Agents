<!--
  帮助页右侧「此页内容」anchor 索引
  - 列出当前文档的 h2/h3 headings
  - 点击 anchor 触发 emit('jump', id) 平滑滚动
  - 监听 hashchange 高亮当前 heading
-->
<template>
  <aside class="help-toc" aria-label="此页内容">
    <div class="help-toc-title">此页内容</div>
    <ul v-if="headings.length > 0" class="help-toc-list">
      <li
        v-for="h in headings"
        :key="h.id"
        class="help-toc-item"
        :class="[`help-toc-item--level-${h.level}`, { 'help-toc-item--active': h.id === activeId }]"
      >
        <a
          :href="`#${h.id}`"
          class="help-toc-link"
          @click.prevent="handleClick(h.id)"
        >{{ h.text }}</a>
      </li>
    </ul>
    <div v-else class="help-toc-empty">无章节</div>
  </aside>
</template>

<script setup>
defineProps({
  /** headings: Array<{level: 2|3, text: string, id: string}> */
  headings: {
    type: Array,
    default: () => [],
  },
  /** 当前高亮的 anchor id */
  activeId: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['jump'])

/**
 * 处理 anchor 点击
 * @param {string} id
 * @returns {void}
 */
function handleClick(id) {
  emit('jump', id)
}
</script>