<template>
  <div
    ref="panelRef"
    class="trigger-panel"
    :data-testid="`trigger-panel-${triggerId}`"
  >
    <div class="trigger-panel-search">
      <input
        ref="searchInputRef"
        v-model="searchValue"
        type="text"
        class="trigger-panel-search-input"
        :placeholder="searchPlaceholder"
        :data-testid="`trigger-panel-search-${triggerId}`"
        @input="handleSearchInput"
        @keydown="handleKeydown"
      />
    </div>

    <div v-if="loading" class="trigger-panel-status">加载中...</div>
    <div v-else-if="error" class="trigger-panel-status error">{{ error }}</div>
    <div v-else-if="filteredItems.length === 0" class="trigger-panel-status">
      {{ emptyHint }}
    </div>
    <div v-else class="trigger-panel-list">
      <div
        v-for="(item, index) in filteredItems"
        :key="getItemKey(item)"
        class="trigger-panel-item"
        :class="{ active: activeIndex === index }"
        :data-testid="`trigger-panel-item-${triggerId}-${index}`"
        @mousedown.prevent="selectItem(item)"
        @mouseenter="emit('update:activeIndex', index)"
      >
        <div class="trigger-panel-item-label">{{ getItemLabel(item) }}</div>
        <div v-if="getItemSubLabel(item)" class="trigger-panel-item-sub">
          {{ getItemSubLabel(item) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  triggerId: { type: String, required: true },
  items: { type: Array, default: () => [] },
  searchKeys: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  emptyHint: { type: String, default: '无可选项' },
  searchPlaceholder: { type: String, default: '搜索...' },
  getItemKey: { type: Function, required: true },
  getItemLabel: { type: Function, required: true },
  getItemSubLabel: { type: Function, default: () => '' },
})

const emit = defineEmits(['select', 'update:activeIndex', 'update:search'])

const searchValue = ref('')
const searchInputRef = ref(null)
const panelRef = ref(null)

const filteredItems = computed(() => {
  const keyword = (searchValue.value || '').trim().toLowerCase()
  if (!keyword) return props.items
  return (props.items || []).filter((item) => {
    return (props.searchKeys || []).some((k) => {
      const v = item?.[k]
      return v != null && String(v).toLowerCase().includes(keyword)
    })
  })
})

watch(filteredItems, () => {
  // 列表变化时把 activeIndex 拉回到 0，避免越界
  if (props.activeIndex !== 0) emit('update:activeIndex', 0)
})

onMounted(() => {
  nextTick(() => searchInputRef.value?.focus())
})

function handleSearchInput(event) {
  emit('update:search', event.target.value)
}

function handleKeydown(event) {
  const list = filteredItems.value
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (list.length === 0) return
    emit('update:activeIndex', (props.activeIndex + 1) % list.length)
    return
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (list.length === 0) return
    emit(
      'update:activeIndex',
      (props.activeIndex - 1 + list.length) % list.length
    )
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    const idx = props.activeIndex >= 0 ? props.activeIndex : 0
    const item = list[idx]
    if (item) selectItem(item)
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('select', null)
  }
}

function selectItem(item) {
  emit('select', item)
}

defineExpose({ panelRef, searchInputRef })
</script>

<style scoped>
.trigger-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
  padding: 8px;
  min-width: 260px;
  max-width: 360px;
  max-height: 280px;
  overflow: hidden;
}

.trigger-panel-search {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #f3f4f6;
  padding-bottom: 6px;
}

.trigger-panel-search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  padding: 4px 6px;
  background: transparent;
  color: #111827;
}

.trigger-panel-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  max-height: 220px;
}

.trigger-panel-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: #111827;
  font-size: 13px;
}

.trigger-panel-item.active,
.trigger-panel-item:hover {
  background: #eff6ff;
}

.trigger-panel-item-label {
  font-weight: 500;
  line-height: 1.3;
}

.trigger-panel-item-sub {
  font-size: 11px;
  color: #6b7280;
  line-height: 1.3;
}

.trigger-panel-status {
  font-size: 12px;
  color: #6b7280;
  padding: 10px 4px;
  text-align: center;
}

.trigger-panel-status.error {
  color: #b91c1c;
}
</style>