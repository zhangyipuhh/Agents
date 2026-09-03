<!--
  帮助页左侧目录导航
  - 递归渲染 nav-tree（来自 index.json）
  - 当前文档高亮
  - 点击触发 emit('select', path) 切换内容
-->
<template>
  <aside class="help-sidebar" aria-label="帮助文档目录">
    <nav>
      <ul class="help-nav-list" role="tree">
        <HelpSidebarItem
          v-for="node in tree"
          :key="node.path || node.title"
          :node="node"
          :active-path="activePath"
          @select="handleSelect"
        />
      </ul>
    </nav>
  </aside>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'
import HelpSidebarItem from './HelpSidebarItem.vue'

defineProps({
  /** 目录树数据（来自 index.json::tree） */
  tree: {
    type: Array,
    default: () => [],
  },
  /** 当前激活的文档路径 */
  activePath: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['select'])

/**
 * 处理子节点选中事件
 * @param {string} path
 * @returns {void}
 */
function handleSelect(path) {
  emit('select', path)
}
</script>