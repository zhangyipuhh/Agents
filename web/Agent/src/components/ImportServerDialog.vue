<script setup>
/**
 * ImportServerDialog - 导入已有配置弹出面板（2026-07-24 新增）
 *
 * 复用 fetchDevOpsServers() 拉取 devops_servers 脱敏列表（id / business_name /
 * server_type / updated_at），以 label 卡片方式多选。确认后调
 * importDevopsServers(parentId, businessNames) 批量创建 user_server_nodes。
 *
 * 父组件：UserServerManager.vue
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchDevOpsServers } from '../utils/api.js'
import { importDevopsServers } from '../utils/api.js'

const props = defineProps({
  parentId: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['close', 'done'])

// 弹窗状态
const isLoading = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')
const searchKeyword = ref('')
const allServers = ref([])
const selectedNames = ref(new Set())

/**
 * 加载 devops_servers 脱敏列表。
 * @returns {Promise<void>} 无返回值
 */
async function loadServers() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await fetchDevOpsServers()
    allServers.value = Array.isArray(data) ? data : []
  } catch (err) {
    errorMessage.value = err.message || '加载服务器列表失败'
    allServers.value = []
  } finally {
    isLoading.value = false
  }
}

/**
 * 过滤后的服务器列表（按 business_name 模糊匹配）。
 * @returns {Array<Object>} 过滤后的服务器列表
 */
const filteredServers = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return allServers.value
  return allServers.value.filter((s) =>
    (s.business_name || '').toLowerCase().includes(kw)
  )
})

/**
 * 是否全选。
 * @returns {boolean} true = 当前可见项全部已选
 */
const isAllSelected = computed(() => {
  if (!filteredServers.value.length) return false
  return filteredServers.value.every((s) => selectedNames.value.has(s.business_name))
})

/**
 * 已勾选数。
 * @returns {number} 选中数量
 */
const selectedCount = computed(() => selectedNames.value.size)

/**
 * 切换单条勾选状态。
 * @param {Object} row - 服务器行
 * @param {boolean} checked - 是否勾选
 * @returns {void}
 */
function toggleSelection(row, checked) {
  const name = row.business_name
  if (!name) return
  if (checked) {
    const next = new Set(selectedNames.value)
    next.add(name)
    selectedNames.value = next
  } else {
    const next = new Set(selectedNames.value)
    next.delete(name)
    selectedNames.value = next
  }
}

/**
 * 切换全选。
 * @returns {void}
 */
function toggleSelectAll() {
  if (isAllSelected.value) {
    // 取消全选：只移除当前可见项的勾选
    const next = new Set(selectedNames.value)
    filteredServers.value.forEach((s) => next.delete(s.business_name))
    selectedNames.value = next
  } else {
    // 全选：把当前可见项全部加入
    const next = new Set(selectedNames.value)
    filteredServers.value.forEach((s) => next.add(s.business_name))
    selectedNames.value = next
  }
}

/**
 * 判断某行是否被勾选。
 * @param {Object} row - 服务器行
 * @returns {boolean} true = 已选
 */
function isSelected(row) {
  return selectedNames.value.has(row.business_name)
}

/**
 * 关闭弹窗。
 * @returns {void}
 */
function closeDialog() {
  emit('close')
}

/**
 * 确认导入。
 * @returns {Promise<void>} 无返回值
 */
async function submitImport() {
  if (isSubmitting.value) return
  if (selectedCount.value === 0) return
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    const result = await importDevopsServers(
      props.parentId,
      Array.from(selectedNames.value)
    )
    emit('done', result)
  } catch (err) {
    errorMessage.value = err.message || '导入失败'
  } finally {
    isSubmitting.value = false
  }
}

// ESC 关闭弹窗
function handleKeydown(e) {
  if (e.key === 'Escape') closeDialog()
}

onMounted(async () => {
  document.addEventListener('keydown', handleKeydown)
  await loadServers()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div
    class="isd-overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby="isd-title"
    data-testid="isd-overlay"
    @click.self="closeDialog"
  >
    <div class="isd-card" data-testid="isd-card">
      <header class="isd-header">
        <h3 id="isd-title">导入已有配置</h3>
        <button
          type="button"
          class="isd-close"
          aria-label="关闭"
          data-testid="isd-close"
          @click="closeDialog"
        >
          ×
        </button>
      </header>

      <div class="isd-toolbar">
        <div class="isd-search-wrapper">
          <svg
            class="isd-search-icon"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9 17a8 8 0 100-16 8 8 0 000 16zM14 14l4 4"
            />
          </svg>
          <input
            v-model="searchKeyword"
            type="text"
            class="isd-search-input"
            placeholder="按业务名搜索"
            aria-label="搜索"
            data-testid="isd-search-input"
          />
        </div>
        <button
          type="button"
          class="isd-select-all"
          :disabled="!filteredServers.length"
          data-testid="isd-select-all"
          @click="toggleSelectAll"
        >
          {{ isAllSelected ? '取消全选' : '全选当前' }}
        </button>
        <span class="isd-selected-count" data-testid="isd-selected-count">
          已选 {{ selectedCount }}
        </span>
      </div>

      <div
        v-if="errorMessage"
        class="alert error"
        role="alert"
        data-testid="isd-error"
      >
        {{ errorMessage }}
      </div>

      <div v-if="isLoading" class="empty-state" data-testid="isd-loading">
        正在加载服务器列表...
      </div>
      <div
        v-else-if="!filteredServers.length"
        class="empty-state"
        data-testid="isd-empty"
      >
        暂无可导入的服务器
      </div>

      <ul
        v-else
        class="server-options isd-grid"
        role="listbox"
        aria-multiselectable="true"
        aria-label="可导入的服务器列表"
        data-testid="isd-server-list"
      >
        <li
          v-for="row in filteredServers"
          :key="row.id"
          class="server-option"
          :class="{ selected: isSelected(row) }"
        >
          <label class="server-option__label">
            <input
              type="checkbox"
              :checked="isSelected(row)"
              :data-testid="`isd-option-${row.id}`"
              @change="toggleSelection(row, $event.target.checked)"
            />
            <span class="server-option__main">{{ row.business_name }}</span>
            <span class="server-option__meta">{{ row.server_type }}</span>
          </label>
        </li>
      </ul>

      <footer class="isd-footer">
        <button
          type="button"
          class="isd-btn secondary"
          data-testid="isd-cancel"
          @click="closeDialog"
        >
          取消
        </button>
        <button
          type="button"
          class="isd-btn primary"
          :disabled="selectedCount === 0 || isSubmitting"
          data-testid="isd-confirm"
          @click="submitImport"
        >
          <span v-if="isSubmitting">导入中...</span>
          <span v-else>确认导入 ({{ selectedCount }})</span>
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.isd-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.isd-card {
  background: #fff;
  border-radius: 8px;
  width: 720px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}
.isd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
}
.isd-header h3 {
  margin: 0;
  font-size: 16px;
  color: #111827;
}
.isd-close {
  background: none;
  border: none;
  font-size: 22px;
  color: #6b7280;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.isd-close:hover {
  color: #111827;
}
.isd-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #f3f4f6;
  background: #fafbfc;
}
.isd-search-wrapper {
  position: relative;
  flex: 1;
}
.isd-search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: #6b7280;
}
.isd-search-input {
  width: 100%;
  padding: 6px 8px 6px 28px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.isd-search-input:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}
.isd-select-all {
  padding: 4px 10px;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  color: #374151;
  white-space: nowrap;
}
.isd-select-all:hover:not(:disabled) {
  background: #f3f4f6;
}
.isd-select-all:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.isd-selected-count {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}
.isd-grid {
  list-style: none;
  padding: 12px 16px;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
  overflow-y: auto;
  flex: 1;
}
.isd-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e5e7eb;
  background: #fafbfc;
}
.isd-btn {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}
.isd-btn.secondary {
  background: #fff;
  border: 1px solid #d1d5db;
  color: #374151;
}
.isd-btn.secondary:hover {
  background: #f3f4f6;
}
.isd-btn.primary {
  background: #2563eb;
  color: #fff;
}
.isd-btn.primary:hover:not(:disabled) {
  background: #1d4ed8;
}
.isd-btn.primary:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
.alert {
  padding: 6px 10px;
  margin: 6px 16px 0;
  border-radius: 4px;
  font-size: 12px;
}
.alert.error {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}
.empty-state {
  padding: 32px 16px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}
</style>
