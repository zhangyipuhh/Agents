<script setup>
/**
 * AgentAccessManager - 智能体访问权限管理（2026-07-24 新增）
 *
 * 布局：左侧人员选择 + 右侧智能体 checkbox 列表
 * 流程：先选人 → 勾选/取消智能体 → 自动保存（debounce 300ms）
 *
 * 与 MenuPermissionManager.vue 的 UX 模式一致，仅数据源不同：
 * - MenuPermission: 菜单注册表（catelog） + user_menu_acl
 * - AgentAccess: 智能体注册表（catalog） + user_agent_acl
 */

import { ref, computed, onMounted, watch } from 'vue'
import {
  fetchAgentPermissionCatalog,
  fetchUserAgentGrants,
  replaceUserAgentGrants,
  fetchUserList
} from '../utils/api.js'

/**
 * 2026-07-24 新增：组件 props。
 * - isAdmin：父组件传入的角色标记。
 *   用途：onMounted 内做 fail-safe 兜底 —— 即便父组件忘了用 v-if 隔离，
 *   非 admin 用户也不会触发 /api/admin/permissions/agents/catalog 等
 *   admin-only 请求，避免被后端 403 拒绝。
 */
const props = defineProps({
  isAdmin: {
    type: Boolean,
    default: false
  }
})

const catalog = ref([])        // 全量 AgentItem（name + display_name）
const users = ref([])          // 人员列表
const selectedUserId = ref(null)
const searchKeyword = ref('')
const selectedAgentNames = ref(new Set())  // 当前用户的已授权 agent_name 集合
const loading = ref(false)
const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref('')
let saveTimer = null           // debounce 句柄

onMounted(async () => {
  // 2026-07-24 fail-safe：非 admin 用户不触发 admin-only 请求
  if (!props.isAdmin) {
    console.warn('[AgentAccessManager] 非 admin 用户挂载本组件，已跳过数据加载')
    return
  }
  loading.value = true
  try {
    const [cat, ulist] = await Promise.all([
      fetchAgentPermissionCatalog(),
      fetchUserList()
    ])
    catalog.value = cat.items || []
    users.value = ulist || []
  } catch (err) {
    console.error('[AgentAccessManager] 加载失败:', err)
  } finally {
    loading.value = false
  }
})

// 过滤后的人员列表（实时搜索）
const filteredUsers = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return users.value
  return users.value.filter(u => (u.username || '').toLowerCase().includes(kw))
})

// 切换人员 → 自动加载该用户的已授权智能体
watch(selectedUserId, async (uid) => {
  if (uid == null) {
    selectedAgentNames.value = new Set()
    saveError.value = ''
    saveSuccess.value = ''
    return
  }
  saveError.value = ''
  saveSuccess.value = ''
  try {
    const data = await fetchUserAgentGrants(uid)
    selectedAgentNames.value = new Set(data.agent_names || [])
  } catch (err) {
    console.error('[AgentAccessManager] 加载用户授权失败:', err)
    selectedAgentNames.value = new Set()
  }
})

/**
 * 切换智能体 checkbox（debounce 300ms 自动保存）
 */
function toggleAgent(agentName, checked) {
  const next = new Set(selectedAgentNames.value)
  if (checked) next.add(agentName)
  else next.delete(agentName)
  selectedAgentNames.value = next
  scheduleSave()
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveAgentAccess()
  }, 300)
}

async function saveAgentAccess() {
  if (selectedUserId.value == null) return
  saving.value = true
  saveError.value = ''
  saveSuccess.value = ''
  try {
    const data = await replaceUserAgentGrants(
      selectedUserId.value,
      Array.from(selectedAgentNames.value)
    )
    selectedAgentNames.value = new Set(data.agent_names || [])
    saveSuccess.value = '已保存'
    // 同时刷新左侧用户名旁的"已授权智能体数"（如果有展示需要）
  } catch (err) {
    saveError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// 全选 / 清空
function selectAll() {
  selectedAgentNames.value = new Set(catalog.value.map(a => a.name))
  scheduleSave()
}

function selectNone() {
  selectedAgentNames.value = new Set()
  scheduleSave()
}
</script>

<template>
  <div class="agent-access-manager">
    <!-- 左侧人员选择 -->
    <aside class="user-panel">
      <input
        v-model="searchKeyword"
        data-testid="agent-access-user-search"
        type="text"
        class="user-search"
        placeholder="搜索用户名..."
      />
      <div class="user-list" data-testid="agent-access-user-list">
        <button
          v-for="u in filteredUsers"
          :key="u.id"
          class="user-list-item"
          :class="{ active: selectedUserId === u.id }"
          data-testid="agent-access-user-list-item"
          @click="selectedUserId = u.id"
        >
          <span class="user-list-name">{{ u.username }}</span>
          <span class="user-list-role" :class="u.role">{{ u.role }}</span>
        </button>
      </div>
    </aside>

    <!-- 右侧智能体勾选 -->
    <main class="agent-panel">
      <div v-if="loading" class="loading-hint">加载中...</div>
      <template v-else>
        <div v-if="selectedUserId == null" class="empty-hint">请先选择左侧人员</div>
        <div v-if="selectedUserId != null" class="agent-panel-header">
          <span class="user-info">用户：{{ users.find(u => u.id === selectedUserId)?.username }}</span>
          <span v-if="saving" class="saving-hint">保存中...</span>
          <span v-else-if="saveSuccess" class="saved-hint">{{ saveSuccess }}</span>
        </div>

        <div v-if="saveError" class="error-message">{{ saveError }}</div>

        <div v-if="selectedUserId != null" class="agent-checkbox-list">
          <div class="agent-checkbox-actions">
            <button
              type="button"
              class="table-btn btn-edit"
              data-testid="agent-access-select-all"
              :disabled="saving || catalog.length === 0"
              @click="selectAll"
            >全选</button>
            <button
              type="button"
              class="table-btn btn-back"
              data-testid="agent-access-select-none"
              :disabled="saving"
              @click="selectNone"
            >清空</button>
          </div>
          <div v-if="catalog.length === 0" class="agent-empty">暂无可配置智能体</div>
          <label
            v-for="agent in catalog"
            :key="agent.name"
            class="agent-checkbox-item"
            :data-testid="'agent-access-checkbox-' + agent.name"
          >
            <input
              type="checkbox"
              :checked="selectedAgentNames.has(agent.name)"
              :disabled="saving"
              @change="e => toggleAgent(agent.name, e.target.checked)"
            />
            <span class="agent-checkbox-name">{{ agent.display_name || agent.name }}</span>
          </label>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.agent-access-manager {
  display: flex;
  height: 100%;
  gap: 16px;
  min-height: 400px;
}

.user-panel {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-right: 1px solid var(--color-border);
  padding-right: 12px;
}

.user-search {
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: var(--font-size-sm);
}

.user-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  border-radius: 4px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  text-align: left;
}

.user-list-item.active {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.user-list-item:hover {
  background-color: var(--color-bg-hover);
}

.user-list-role {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--color-bg-tertiary);
  color: var(--color-text-muted);
}

.user-list-role.admin {
  background: var(--color-accent);
  color: white;
}

.agent-panel {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.agent-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light);
}

.user-info {
  font-weight: var(--font-weight-medium);
}

.saving-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.saved-hint {
  font-size: var(--font-size-sm);
  color: var(--color-success);
}

.loading-hint,
.empty-hint,
.error-message {
  padding: 12px;
  border-radius: 4px;
  text-align: center;
}

.empty-hint {
  color: var(--color-text-muted);
}

.error-message {
  color: var(--color-error);
  background-color: var(--color-error-bg, #fee);
  margin-bottom: 8px;
}

/* 2026-07-24 复用用户表单中的智能体权限样式（与 UserSettingsDialog 一致） */
.agent-checkbox-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.agent-checkbox-actions {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.agent-checkbox-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 6px 8px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  user-select: none;
}

.agent-checkbox-item:hover {
  background-color: var(--color-bg-hover);
}

.agent-checkbox-name {
  font-size: var(--font-size-base);
}

.agent-empty {
  padding: 12px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.table-btn {
  padding: 4px 12px;
  font-size: var(--font-size-sm);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  cursor: pointer;
  background: white;
}

.table-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-edit {
  background-color: #DBEAFE;
  color: #2563EB;
}

.btn-back {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}
</style>
