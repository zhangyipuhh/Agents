<script setup>
/**
 * InspectionScriptLibraryPanel - 巡检脚本库左侧节点列表（2026-08-04 新增）
 *
 * 顶部搜索框按 name / display_name / platform / version 过滤（不区分大小写）；
 * 点击节点通过 `select` 事件向父组件派发 script_id。
 *
 * 设计：复用 UserServerManager 风格的 search + 节点列表 + 选中态；
 * data-testid 锁定结构契约，便于 TaskSchedulerManager.spec.js 端到端断言。
 */
import { computed, onMounted, ref } from 'vue'
import { fetchInspectionScripts } from '../utils/api.js'

const scripts = ref([])
const searchKeyword = ref('')
const selectedId = ref(null)
const isLoading = ref(false)
const errorMessage = ref('')

const emit = defineEmits(['select'])

onMounted(async () => {
  isLoading.value = true
  errorMessage.value = ''
  try {
    scripts.value = await fetchInspectionScripts()
  } catch (err) {
    errorMessage.value = err?.message || '加载巡检脚本列表失败'
  } finally {
    isLoading.value = false
  }
})

const visibleNodes = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return scripts.value
  return scripts.value.filter((s) => {
    return [s.name, s.display_name, s.platform, s.version]
      .filter(Boolean)
      .some((field) => String(field).toLowerCase().includes(kw))
  })
})

function onNodeClick(node) {
  selectedId.value = node.id
  emit('select', node.id)
}
</script>

<template>
  <div class="library-panel">
    <div class="library-toolbar">
      <input
        v-model="searchKeyword"
        type="search"
        class="library-search-input"
        placeholder="搜索名称 / 平台 / 版本"
        data-testid="library-search-input"
        aria-label="搜索巡检脚本"
      />
    </div>
    <div v-if="isLoading" class="empty-state" data-testid="library-loading">正在加载...</div>
    <div v-else-if="errorMessage" class="alert error" data-testid="library-error" role="alert">
      {{ errorMessage }}
    </div>
    <div
      v-else-if="!visibleNodes.length"
      class="empty-state"
      data-testid="library-empty"
    >
      暂无巡检脚本
    </div>
    <ul v-else class="library-list" data-testid="library-list">
      <li
        v-for="node in visibleNodes"
        :key="node.id"
        class="library-node-item"
        :class="{ active: selectedId === node.id }"
        :data-testid="'library-node-item'"
        :data-node-id="node.id"
        @click="onNodeClick(node)"
      >
        <div class="library-node-name">{{ node.display_name || node.name }}</div>
        <div class="library-node-meta">
          <span class="library-node-tag">{{ node.platform || '' }}</span>
          <span class="library-node-version">{{ node.version || '' }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.library-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.library-toolbar {
  padding: 12px;
  border-bottom: 1px solid #e5e7eb;
}
.library-search-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}
.library-list {
  flex: 1;
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  min-height: 0;
}
.library-node-item {
  padding: 10px 12px;
  border-bottom: 1px solid #f3f4f6;
  cursor: pointer;
}
.library-node-item:hover {
  background: #f9fafb;
}
.library-node-item.active {
  background: #eef2ff;
  border-left: 3px solid #6366f1;
}
.library-node-name {
  font-weight: 500;
  color: #111827;
}
.library-node-meta {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}
.library-node-tag {
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 4px;
}
.library-node-version {
  color: #9ca3af;
}
.empty-state {
  padding: 24px;
  color: #6b7280;
  text-align: center;
}
.alert.error {
  padding: 12px;
  color: #b91c1c;
}
</style>
