<!--
  帮助页左侧导航单项（递归）
  - 有 children → 渲染为分组标题 + 递归子项
  - 无 children → 渲染为可点击链接
-->
<template>
  <li class="help-nav-item" role="treeitem">
    <div
      v-if="hasChildren"
      class="help-nav-group"
    >
      <span class="help-nav-group-label">{{ node.title }}</span>
      <ul class="help-nav-sublist" role="group">
        <HelpSidebarItem
          v-for="child in node.children"
          :key="child.path || child.title"
          :node="child"
          :active-path="activePath"
          @select="handleSelect"
        />
      </ul>
    </div>
    <button
      v-else
      type="button"
      class="help-nav-link"
      :class="{ 'help-nav-link--active': isActive }"
      @click="handleClick"
    >
      {{ node.title }}
    </button>
  </li>
</template>

<script setup>
import { defineProps, defineEmits, computed } from 'vue'

const props = defineProps({
  /** 节点数据：{ title, path?, children? } */
  node: {
    type: Object,
    required: true,
  },
  /** 当前激活路径 */
  activePath: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['select'])

/** 是否有子节点 */
const hasChildren = computed(() => Array.isArray(props.node.children) && props.node.children.length > 0)

/** 是否为当前激活项 */
const isActive = computed(() => {
  if (!props.node.path) return false
  return props.activePath === props.node.path
})

/**
 * 处理点击事件
 * @returns {void}
 */
function handleClick() {
  if (props.node.path) {
    emit('select', props.node.path)
  }
}

/**
 * 处理子节点选中事件（递归透传）
 * @param {string} path
 * @returns {void}
 */
function handleSelect(path) {
  emit('select', path)
}
</script>