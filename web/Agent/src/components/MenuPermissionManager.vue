<script setup>
/**
 * MenuPermissionManager - 菜单权限管理
 *
 * 布局：左侧人员选择 + 右侧菜单树形 checkbox
 * 流程：先选人再选菜单 → 保存（PUT 全量覆盖）
 *
 * 详见 docs/superpowers/specs/2026-07-23-menu-permission-design.md § 6.2
 */

import { ref, computed, onMounted, watch } from 'vue'
import {
  fetchMenuCatalog,
  fetchUserMenuGrants,
  saveUserMenuGrants,
  fetchUserList
} from '../utils/api.js'

const catalog = ref([])        // 全量 MenuItem（含 enabled=False）
const users = ref([])          // 人员列表
const selectedUserId = ref(null)
const searchKeyword = ref('')
const grants = ref(new Set(['profile']))  // 当前选中用户的 menu_id 集合（默认含 profile，最低可用性）
const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref('')
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const [cat, ulist] = await Promise.all([
      fetchMenuCatalog(),
      fetchUserList()
    ])
    catalog.value = (cat.items || []).filter(m => m.enabled)
    users.value = ulist || []
  } catch (err) {
    console.error('[MenuPermissionManager] 加载失败:', err)
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

// 一级菜单（仅 enabled）
const level1Menus = computed(() =>
  catalog.value
    .filter(m => m.level === 1)
    .sort((a, b) => a.sort_order - b.sort_order)
)

// 某个一级菜单的二级菜单
function getChildren(parentId) {
  return catalog.value
    .filter(m => m.level === 2 && m.parent_id === parentId)
    .sort((a, b) => a.sort_order - b.sort_order)
}

// 切换人员 → 自动加载 grants
watch(selectedUserId, async (uid) => {
  if (uid == null) {
    grants.value = new Set(['profile'])
    return
  }
  saveError.value = ''
  saveSuccess.value = ''
  try {
    const data = await fetchUserMenuGrants(uid)
    grants.value = new Set(data.menu_ids || [])
  } catch (err) {
    console.error('[MenuPermissionManager] 加载授权失败:', err)
    grants.value = new Set()
  }
})

// 父级 checkbox 状态：checked / indeterminate / unchecked
function parentState(parentId) {
  const children = getChildren(parentId)
  if (children.length === 0) {
    return { checked: grants.value.has(parentId), indeterminate: false }
  }
  const grantedChildren = children.filter(c => grants.value.has(c.id)).length
  if (grantedChildren === 0) {
    return { checked: false, indeterminate: false }
  }
  if (grantedChildren === children.length) {
    return { checked: true, indeterminate: false }
  }
  return { checked: false, indeterminate: true }
}

function toggleParent(parentId, checked) {
  // 「个人设置」不可取消
  if (parentId === 'profile') return
  const children = getChildren(parentId)
  const next = new Set(grants.value)
  if (children.length === 0) {
    if (checked) next.add(parentId)
    else next.delete(parentId)
  } else {
    children.forEach(c => {
      if (checked) next.add(c.id)
      else next.delete(c.id)
    })
    if (!checked) next.delete(parentId)
    else next.add(parentId)
  }
  grants.value = next
}

function toggleChild(parentId, childId, checked) {
  const next = new Set(grants.value)
  if (checked) next.add(childId)
  else next.delete(childId)
  // 同步父级：所有子级都勾 → 勾父；任一子级未勾 → 不勾父
  const children = getChildren(parentId)
  const allChecked = children.every(c => next.has(c.id))
  if (allChecked) next.add(parentId)
  else next.delete(parentId)
  grants.value = next
}

async function handleSave() {
  if (selectedUserId.value == null) return
  saving.value = true
  saveError.value = ''
  saveSuccess.value = ''
  try {
    const data = await saveUserMenuGrants(selectedUserId.value, Array.from(grants.value))
    grants.value = new Set(data.menu_ids || [])
    saveSuccess.value = '已保存'
  } catch (err) {
    saveError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="menu-permission-manager">
    <!-- 左侧人员选择 -->
    <aside class="user-panel">
      <input
        v-model="searchKeyword"
        data-testid="user-search"
        type="text"
        class="user-search"
        placeholder="搜索用户名..."
      />
      <div class="user-list" data-testid="user-list">
        <button
          v-for="u in filteredUsers"
          :key="u.id"
          class="user-list-item"
          :class="{ active: selectedUserId === u.id }"
          data-testid="user-list-item"
          @click="selectedUserId = u.id"
        >
          <span class="user-list-name">{{ u.username }}</span>
          <span class="user-list-role" :class="u.role">{{ u.role }}</span>
        </button>
      </div>
    </aside>

    <!-- 右侧菜单树 -->
    <main class="menu-panel">
      <div v-if="loading" class="loading-hint">加载中...</div>
      <template v-else>
        <div v-if="selectedUserId == null" class="empty-hint">请先选择左侧人员</div>
        <div v-if="selectedUserId != null" class="menu-panel-header">
          <span class="user-info">用户：{{ users.find(u => u.id === selectedUserId)?.username }}</span>
          <button
            data-testid="save-button"
            class="save-btn"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>

        <div v-if="saveError" class="error-message">{{ saveError }}</div>
        <div v-if="saveSuccess" class="success-message">{{ saveSuccess }}</div>

        <div class="menu-tree" data-testid="menu-tree">
          <div v-for="parent in level1Menus" :key="parent.id" class="menu-tree-row">
            <label class="menu-checkbox-row parent">
              <input
                type="checkbox"
                :data-testid="'menu-checkbox-' + parent.id"
                :checked="parentState(parent.id).checked"
                :indeterminate.prop="parentState(parent.id).indeterminate"
                :disabled="parent.id === 'profile'"
                @change="e => toggleParent(parent.id, e.target.checked)"
              />
              <span class="menu-label">{{ parent.label }}</span>
            </label>
            <div v-if="getChildren(parent.id).length > 0" class="children">
              <label
                v-for="child in getChildren(parent.id)"
                :key="child.id"
                class="menu-checkbox-row child"
              >
                <input
                  type="checkbox"
                  :data-testid="'menu-checkbox-' + child.id"
                  :checked="grants.has(child.id)"
                  @change="e => toggleChild(parent.id, child.id, e.target.checked)"
                />
                <span class="menu-label">{{ child.label }}</span>
              </label>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.menu-permission-manager {
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

.menu-panel {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.menu-panel-header {
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

.save-btn {
  padding: 6px 16px;
  background-color: var(--color-accent);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.menu-tree-row {
  margin-bottom: 6px;
}

.menu-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
  user-select: none;
}

.menu-checkbox-row.child {
  padding-left: 24px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.children {
  margin-left: 12px;
}

.menu-label {
  font-size: var(--font-size-base);
}

.loading-hint,
.empty-hint,
.error-message,
.success-message {
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

.success-message {
  color: var(--color-success);
  background-color: var(--color-success-bg, #efe);
  margin-bottom: 8px;
}
</style>