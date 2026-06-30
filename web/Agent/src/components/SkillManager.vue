<!--
  SkillManager - skill 管理组件

  提供 skill 注册中心的完整管理界面（admin 权限）：
  - 已注册 skill 列表，按 category 分组展示（可折叠）
  - 扫描未注册 skill 文件（POST /api/admin/skills/scan）
  - 注册新 skill 弹窗（从扫描结果选择，补充 category + display_name 后提交）
  - 编辑 skill 的 display_name / category（其他字段只读）
  - 启用/禁用 skill toggle（PUT /api/admin/skills/{name}/enabled）
  - 删除 skill（DELETE /api/admin/skills/{name}，带 confirm 确认）

  数据加载由组件自管理（onMounted 触发 listSkills），
  在 UserSettingsDialog 中通过 v-show 始终挂载，切换 Tab 时仅 display 切换。
-->
<template>
  <div class="skill-manager">
    <!-- 顶部头部：标题 + 操作按钮 -->
    <div class="manager-header">
      <h3>Skill 管理</h3>
      <div class="header-actions">
        <button class="header-btn btn-scan" :disabled="scanning" @click="onScanSkills">
          <span v-if="scanning" class="btn-loading-dot"></span>
          {{ scanning ? '扫描中...' : '扫描未注册 skill' }}
        </button>
        <button class="header-btn btn-refresh" :disabled="loading" @click="loadSkills">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="manager-body">
      <!-- 左侧：已注册 skill 列表（按 category 分组） -->
      <div class="skill-list-panel">
        <div v-if="loading && skills.length === 0" class="empty-state">
          加载中...
        </div>
        <div v-else-if="groupedSkills.length === 0" class="empty-state">
          暂无已注册 skill
        </div>
        <!-- 按 category 分组渲染 -->
        <div
          v-for="group in groupedSkills"
          :key="group.category"
          class="category-group"
        >
          <div class="category-header" @click="toggleCategory(group.category)">
            <span class="category-arrow" :class="{ expanded: expandedCategories.has(group.category) }">
              ▶
            </span>
            <span class="category-name">{{ group.category }}</span>
            <span class="category-count">{{ group.skills.length }}</span>
          </div>
          <div v-show="expandedCategories.has(group.category)" class="category-skills">
            <div
              v-for="skill in group.skills"
              :key="skill.name"
              class="skill-item"
              :class="{ selected: selectedSkill?.name === skill.name }"
              @click="selectSkill(skill)"
            >
              <div class="skill-item-header">
                <span class="skill-name">{{ skill.display_name || skill.name }}</span>
                <label class="skill-toggle-wrapper" @click.stop>
                  <input
                    type="checkbox"
                    class="skill-toggle"
                    :checked="skill.enabled"
                    @change="onToggleSkill(skill, $event.target.checked, $event)"
                  />
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <div class="skill-item-meta">
                <span class="skill-name-id">{{ skill.name }}</span>
                <span v-if="!skill.enabled" class="skill-disabled-tag">已禁用</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：详情/扫描结果面板 -->
      <div class="skill-detail-panel">
        <!-- 扫描结果视图 -->
        <div v-if="viewMode === 'scan'" class="scan-result">
          <div class="scan-header">
            <h4>未注册 skill 扫描结果</h4>
            <button class="detail-btn btn-back" @click="exitScanView">返回</button>
          </div>
          <div v-if="unregisteredSkills.length === 0" class="empty-state">
            未发现未注册 skill
          </div>
          <div
            v-for="item in unregisteredSkills"
            :key="item.name"
            class="unregistered-item"
          >
            <div class="unregistered-info">
              <div class="unregistered-name">{{ item.name }}</div>
              <div v-if="item.location" class="unregistered-path">{{ item.location }}</div>
              <div v-if="item.description" class="unregistered-desc">
                {{ item.description }}
              </div>
            </div>
            <button class="detail-btn btn-register" @click="openRegisterForm(item)">
              注册
            </button>
          </div>
        </div>

        <!-- skill 详情视图（编辑表单） -->
        <div v-else-if="selectedSkill" class="skill-detail">
          <h4>{{ selectedSkill.display_name || selectedSkill.name }}</h4>

          <!-- 名称（只读） -->
          <div class="form-group">
            <label class="form-label">名称（只读）</label>
            <input class="form-input readonly-input" :value="selectedSkill.name" readonly />
          </div>

          <!-- 展示名（可编辑） -->
          <div class="form-group">
            <label class="form-label">展示名</label>
            <input
              v-model="editForm.display_name"
              class="form-input"
              placeholder="请输入展示名称"
            />
          </div>

          <!-- 分类（可编辑） -->
          <div class="form-group">
            <label class="form-label">分类 <span class="required-mark">*</span></label>
            <input
              v-model="editForm.category"
              class="form-input"
              placeholder="如 workflow / data / custom"
            />
          </div>

          <!-- 描述（只读） -->
          <div class="form-group">
            <label class="form-label">描述（只读）</label>
            <textarea
              class="form-input readonly-input"
              :value="selectedSkill.description || ''"
              rows="3"
              readonly
            ></textarea>
          </div>

          <!-- location（只读） -->
          <div class="form-group">
            <label class="form-label">位置（只读）</label>
            <input class="form-input readonly-input" :value="selectedSkill.location || ''" readonly />
          </div>

          <!-- base_dir（只读） -->
          <div class="form-group">
            <label class="form-label">所在目录（只读）</label>
            <input class="form-input readonly-input" :value="selectedSkill.base_dir || ''" readonly />
          </div>

          <!-- content（只读，长文本） -->
          <div class="form-group">
            <label class="form-label">正文（只读）</label>
            <textarea
              class="form-input readonly-input content-textarea"
              :value="selectedSkill.content || ''"
              rows="8"
              readonly
            ></textarea>
          </div>

          <!-- 启用状态 -->
          <div class="form-group">
            <label class="form-label">
              <input type="checkbox" v-model="editForm.enabled" />
              启用 skill
            </label>
          </div>

          <div v-if="editError" class="error-message">{{ editError }}</div>

          <div class="detail-actions">
            <button class="detail-btn btn-toggle" @click="onToggleSkill(selectedSkill, !editForm.enabled, $event)">
              {{ editForm.enabled ? '禁用' : '启用' }}
            </button>
            <button class="detail-btn btn-submit" :disabled="saving" @click="submitEdit">
              <span v-if="saving" class="btn-loading-dot"></span>
              {{ saving ? '保存中...' : '保存' }}
            </button>
            <button class="detail-btn btn-delete" @click="onDeleteSkill(selectedSkill)">删除</button>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="no-selection">
          请从左侧选择一个 skill 查看详情，或点击"扫描未注册 skill"
        </div>
      </div>
    </div>

    <!-- 注册新 skill 弹窗 -->
    <Transition name="dialog-fade">
      <div v-if="registerFormVisible" class="register-overlay" @click="closeRegisterForm">
        <div class="register-card" @click.stop>
          <div class="register-header">
            <h3>注册新 skill</h3>
            <button class="register-close" @click="closeRegisterForm" aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5l10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          </div>
          <div class="register-body">
            <!-- 只读：自动解析的字段 -->
            <div class="form-group">
              <label class="form-label">名称（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.name" readonly />
            </div>
            <div class="form-group">
              <label class="form-label">位置（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.location" readonly />
            </div>
            <div class="form-group">
              <label class="form-label">所在目录（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.base_dir" readonly />
            </div>
            <div class="form-group" v-if="registerData.description">
              <label class="form-label">描述（自动解析）</label>
              <textarea class="form-input readonly-input" :value="registerData.description" rows="3" readonly></textarea>
            </div>
            <div class="form-group" v-if="registerData.content">
              <label class="form-label">正文（自动解析）</label>
              <textarea class="form-input readonly-input content-textarea" :value="registerData.content" rows="6" readonly></textarea>
            </div>

            <div class="form-divider"></div>

            <!-- 可编辑：需补充的字段 -->
            <div class="form-group">
              <label class="form-label">展示名</label>
              <input
                v-model="registerData.display_name"
                class="form-input"
                placeholder="请输入展示名称（可选）"
              />
            </div>
            <div class="form-group">
              <label class="form-label">分类 <span class="required-mark">*</span></label>
              <input
                v-model="registerData.category"
                class="form-input"
                placeholder="如 workflow / data / custom"
              />
            </div>
            <div class="form-group">
              <label class="form-label">
                <input type="checkbox" v-model="registerData.enabled" />
                启用 skill
              </label>
            </div>

            <div v-if="registerError" class="error-message">{{ registerError }}</div>
            <div class="form-actions">
              <button class="detail-btn btn-back" @click="closeRegisterForm" :disabled="registering">取消</button>
              <button class="detail-btn btn-submit" :disabled="registering" @click="submitRegister">
                <span v-if="registering" class="btn-loading-dot"></span>
                {{ registering ? '注册中...' : '注册' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
/**
 * SkillManager - skill 管理组件
 *
 * 提供 skill 注册中心的完整管理界面（admin 权限）：
 * - 已注册 skill 列表，按 category 分组展示（可折叠）
 * - 扫描未注册 skill 文件（POST /api/admin/skills/scan）
 * - 注册新 skill 弹窗（从扫描结果选择，补充 category + display_name 后提交）
 * - 编辑 skill 的 display_name / category（其他字段只读）
 * - 启用/禁用 skill toggle（PUT /api/admin/skills/{name}/enabled）
 * - 删除 skill（DELETE /api/admin/skills/{name}，带 confirm 确认）
 *
 * 数据加载由组件自管理（onMounted 触发 listSkills），
 * 在 UserSettingsDialog 中通过 v-show 始终挂载，切换 Tab 时仅 display 切换。
 */
import { ref, computed, watch, onMounted } from 'vue'
import {
  listSkills,
  listUnregisteredSkills,
  registerSkill,
  updateSkill,
  deleteSkill,
  setSkillEnabled,
  scanSkills,
} from '../utils/api.js'

/** @type {import('vue').Ref<Array>} 已注册 skill 列表 */
const skills = ref([])

/** @type {import('vue').Ref<Object|null>} 当前选中的 skill */
const selectedSkill = ref(null)

/** @type {import('vue').Ref<Array>} 未注册 skill 扫描结果 */
const unregisteredSkills = ref([])

/** @type {import('vue').Ref<boolean>} 列表加载中 */
const loading = ref(false)

/** @type {import('vue').Ref<boolean>} 扫描中 */
const scanning = ref(false)

/** @type {import('vue').Ref<boolean>} 保存中 */
const saving = ref(false)

/** @type {import('vue').Ref<'detail'|'scan'>} 右侧面板视图模式 */
const viewMode = ref('detail')

/** @type {import('vue').Ref<Set<string>>} 已展开的分类集合 */
const expandedCategories = ref(new Set())

/** @type {import('vue').Ref<boolean>} 注册弹窗是否可见 */
const registerFormVisible = ref(false)

/** @type {import('vue').Ref<boolean>} 注册提交中 */
const registering = ref(false)

/** @type {import('vue').Ref<string>} 注册错误信息 */
const registerError = ref('')

/** @type {import('vue').Ref<string>} 编辑错误信息 */
const editError = ref('')

/** 编辑表单数据（display_name / category / enabled 可编辑，其余只读） */
const editForm = ref({
  display_name: '',
  category: '',
  enabled: true,
})

/** 注册表单数据（含自动解析的只读字段 + 可编辑字段） */
const registerData = ref({
  name: '',
  location: '',
  base_dir: '',
  description: '',
  content: '',
  display_name: '',
  category: '',
  enabled: true,
})

/**
 * 按 category 分组的 skill 列表（计算属性）
 * @returns {Array<{category: string, skills: Array}>} 分组后的 skill 列表
 */
const groupedSkills = computed(() => {
  const map = new Map()
  for (const skill of skills.value) {
    const category = skill.category || '未分类'
    if (!map.has(category)) {
      map.set(category, [])
    }
    map.get(category).push(skill)
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([category, skillList]) => ({
      category,
      skills: skillList.sort((a, b) => (a.name || '').localeCompare(b.name || '')),
    }))
})

onMounted(loadSkills)

/**
 * 监听选中 skill 变化，同步表单字段
 * 切换 skill 时把 display_name / category / enabled 写入 editForm
 */
watch(
  selectedSkill,
  (next) => {
    if (next) {
      editForm.value = {
        display_name: next.display_name || '',
        category: next.category || '',
        enabled: next.enabled !== false,
      }
    }
    editError.value = ''
  },
  { immediate: false }
)

/**
 * 加载已注册 skill 列表
 * 首次加载时自动展开所有分类
 * @returns {Promise<void>} 无返回值；成功时更新 skills.value，失败时仅 console.error
 * @throws {Error} 内部捕获，不向上抛出
 */
async function loadSkills() {
  loading.value = true
  try {
    const data = await listSkills()
    skills.value = Array.isArray(data) ? data : []
    if (expandedCategories.value.size === 0 && groupedSkills.value.length > 0) {
      expandedCategories.value = new Set(groupedSkills.value.map(g => g.category))
    }
  } catch (err) {
    console.error('加载 skill 列表失败:', err)
    skills.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 切换分类的展开/折叠状态
 * @param {string} category - 分类名称
 */
function toggleCategory(category) {
  const next = new Set(expandedCategories.value)
  if (next.has(category)) {
    next.delete(category)
  } else {
    next.add(category)
  }
  expandedCategories.value = next
}

/**
 * 选中 skill 并切换到详情视图
 * @param {Object} skill - skill 对象
 */
function selectSkill(skill) {
  selectedSkill.value = skill
  viewMode.value = 'detail'
}

/**
 * 扫描未注册 skill 并切换到扫描结果视图
 * 优先调用 scanSkills（POST 语义），失败时降级到 listUnregisteredSkills（GET）
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function onScanSkills() {
  scanning.value = true
  try {
    let data
    try {
      data = await scanSkills()
    } catch {
      data = await listUnregisteredSkills()
    }
    unregisteredSkills.value = Array.isArray(data) ? data : []
    viewMode.value = 'scan'
    selectedSkill.value = null
  } catch (err) {
    alert('扫描未注册 skill 失败: ' + err.message)
  } finally {
    scanning.value = false
  }
}

/**
 * 退出扫描结果视图，返回详情视图
 */
function exitScanView() {
  viewMode.value = 'detail'
}

/**
 * 打开注册新 skill 弹窗，回填自动解析的只读字段
 * @param {Object} unregisteredItem - 扫描结果中的未注册 skill 项
 */
function openRegisterForm(unregisteredItem) {
  registerData.value = {
    name: unregisteredItem.name || '',
    location: unregisteredItem.location || '',
    base_dir: unregisteredItem.base_dir || '',
    description: unregisteredItem.description || '',
    content: unregisteredItem.content || '',
    display_name: unregisteredItem.name || '',
    category: '',
    enabled: true,
  }
  registerError.value = ''
  registerFormVisible.value = true
}

/**
 * 关闭注册弹窗并重置状态
 */
function closeRegisterForm() {
  registerFormVisible.value = false
  registerError.value = ''
}

/**
 * 提交注册新 skill
 * 校验 category 必填后调用 registerSkill，成功后刷新列表并关闭弹窗
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function submitRegister() {
  if (!registerData.value.category.trim()) {
    registerError.value = '请输入 skill 分类'
    return
  }
  if (!registerData.value.name) {
    registerError.value = 'skill 名称缺失'
    return
  }

  registering.value = true
  registerError.value = ''
  try {
    const payload = {
      name: registerData.value.name,
      display_name: registerData.value.display_name.trim() || null,
      category: registerData.value.category.trim(),
      description: registerData.value.description || null,
      location: registerData.value.location || null,
      base_dir: registerData.value.base_dir || null,
      content: registerData.value.content || null,
      enabled: registerData.value.enabled,
      sort_order: 0,
    }
    await registerSkill(payload)
    closeRegisterForm()
    await loadSkills()
    unregisteredSkills.value = unregisteredSkills.value.filter(
      item => item.name !== payload.name
    )
  } catch (err) {
    registerError.value = err.message || '注册失败'
  } finally {
    registering.value = false
  }
}

/**
 * 提交编辑（display_name / category / enabled）
 * @returns {Promise<void>} 无返回值；失败时显示错误信息
 * @throws {Error} 内部捕获，不向上抛出
 */
async function submitEdit() {
  if (!editForm.value.category.trim()) {
    editError.value = '请输入 skill 分类'
    return
  }

  saving.value = true
  editError.value = ''
  try {
    const payload = {
      display_name: editForm.value.display_name.trim() || null,
      category: editForm.value.category.trim(),
      enabled: editForm.value.enabled,
    }
    const result = await updateSkill(selectedSkill.value.name, payload)
    console.log('[submitEdit] result:', result)
    // 同步刷新本地列表与当前选中项
    const idx = skills.value.findIndex(s => s.name === result.name)
    if (idx >= 0) {
      skills.value[idx] = { ...skills.value[idx], ...result }
    }
    selectedSkill.value = skills.value[idx] || null
    console.log('[submitEdit] selectedSkill after merge:', selectedSkill.value)
  } catch (err) {
    editError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

/**
 * 切换 skill 启用状态
 * API 失败时回滚 DOM checkbox 到原状态
 * @param {Object} skill - skill 对象
 * @param {boolean} enabled - 目标启用状态
 * @param {Event} event - change/click 事件对象，用于失败时回滚 DOM
 * @returns {Promise<void>} 无返回值；失败时回滚 DOM 并 alert
 * @throws {Error} 内部捕获，不向上抛出
 */
async function onToggleSkill(skill, enabled, event) {
  try {
    await setSkillEnabled(skill.name, enabled)
    skill.enabled = enabled
    if (selectedSkill.value?.name === skill.name) {
      editForm.value.enabled = enabled
    }
  } catch (err) {
    if (event && event.target && event.target.type === 'checkbox') {
      event.target.checked = skill.enabled
    }
    alert('切换失败: ' + err.message)
  }
}

/**
 * 删除 skill（含 confirm 确认）
 * @param {Object} skill - 待删除的 skill 对象
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function onDeleteSkill(skill) {
  if (!confirm(`确认删除 skill "${skill.name}"？此操作不可恢复。`)) return
  try {
    await deleteSkill(skill.name)
    selectedSkill.value = null
    await loadSkills()
  } catch (err) {
    alert('删除失败: ' + err.message)
  }
}
</script>

<style scoped>
/* 主容器 */
.skill-manager {
  padding: var(--space-md);
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 顶部头部 */
.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.manager-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.header-actions {
  display: flex;
  gap: var(--space-sm);
}

.header-btn {
  padding: 6px 14px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.header-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.btn-scan {
  background-color: var(--color-accent);
}

.btn-scan:hover:not(:disabled) {
  background-color: var(--color-accent-hover);
}

.btn-refresh {
  background-color: var(--color-bg-active);
  color: var(--color-text-primary);
}

.btn-refresh:hover:not(:disabled) {
  background-color: var(--color-border);
}

/* 主体左右分栏 */
.manager-body {
  display: flex;
  gap: var(--space-md);
  flex: 1;
  min-height: 0;
}

/* 左侧 skill 列表面板 */
.skill-list-panel {
  width: 260px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-sm);
  background-color: var(--color-bg-secondary);
}

.empty-state,
.no-selection {
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-xl);
  font-size: var(--font-size-sm);
}

/* 分类分组 */
.category-group {
  margin-bottom: var(--space-sm);
}

.category-header {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  cursor: pointer;
  border-radius: var(--radius-sm);
  user-select: none;
  transition: var(--transition-colors);
}

.category-header:hover {
  background-color: var(--color-bg-hover);
}

.category-arrow {
  font-size: 10px;
  color: var(--color-text-muted);
  transition: var(--transition-transform);
  display: inline-block;
}

.category-arrow.expanded {
  transform: rotate(90deg);
}

.category-name {
  flex: 1;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.category-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background-color: var(--color-bg-active);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.category-skills {
  margin-top: var(--space-xs);
}

/* skill 项 */
.skill-item {
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 2px;
  border: 1px solid transparent;
  transition: var(--transition-colors);
}

.skill-item:hover {
  background-color: var(--color-bg-hover);
}

.skill-item.selected {
  background-color: var(--color-accent-light);
  border-color: var(--color-accent);
}

.skill-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.skill-name {
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.skill-item-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.skill-name-id {
  font-family: monospace;
}

.skill-disabled-tag {
  background-color: var(--color-tag-beta);
  color: var(--color-tag-beta-text);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-size: 10px;
}

/* toggle 开关 */
.skill-toggle-wrapper {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}

.skill-toggle-wrapper input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--color-border);
  border-radius: 20px;
  transition: var(--transition-colors);
}

.skill-toggle-wrapper input:checked + .toggle-slider {
  background-color: var(--color-accent);
}

.toggle-slider:before {
  position: absolute;
  content: '';
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background-color: var(--color-text-inverse);
  border-radius: 50%;
  transition: var(--transition-transform);
}

.skill-toggle-wrapper input:checked + .toggle-slider:before {
  transform: translateX(16px);
}

/* 右侧详情面板 */
.skill-detail-panel {
  flex: 1;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  overflow-y: auto;
  background-color: var(--color-bg-primary);
}

.skill-detail h4,
.scan-result h4 {
  margin: 0 0 var(--space-md) 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

/* 表单字段（详情视图中的编辑表单） */
.skill-detail .form-group {
  margin-bottom: var(--space-md);
}

.skill-detail .form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.skill-detail .form-input {
  width: 100%;
  padding: 8px var(--space-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors), var(--transition-shadow);
  box-sizing: border-box;
  font-family: inherit;
}

.skill-detail .form-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-light);
  background-color: var(--color-bg-primary);
  outline: none;
}

.skill-detail .readonly-input {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: not-allowed;
}

.content-textarea {
  resize: vertical;
  font-family: monospace;
  font-size: var(--font-size-xs);
}

.required-mark {
  color: var(--color-error);
}

/* 详情操作按钮 */
.detail-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-md);
  flex-wrap: wrap;
}

.detail-btn {
  padding: 6px 16px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.btn-toggle {
  background-color: var(--color-tag-beta);
  color: var(--color-tag-beta-text);
}

.btn-toggle:hover {
  background-color: var(--color-warning);
  color: var(--color-text-inverse);
}

.btn-delete {
  background-color: #FEE2E2;
  color: #DC2626;
}

.btn-delete:hover {
  background-color: #FECACA;
}

.btn-back {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.btn-back:hover {
  background-color: #D6E4F5;
}

.btn-submit {
  background-color: var(--color-accent);
  color: var(--color-text-inverse);
  min-width: 100px;
  justify-content: center;
}

.btn-submit:hover:not(:disabled) {
  background-color: var(--color-accent-hover);
}

.btn-submit:disabled,
.detail-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

/* 扫描结果 */
.scan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.unregistered-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-sm);
  background-color: var(--color-bg-secondary);
}

.unregistered-info {
  flex: 1;
  min-width: 0;
}

.unregistered-name {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-family: monospace;
}

.unregistered-path {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
  word-break: break-all;
}

.unregistered-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-xs);
  white-space: pre-wrap;
}

.btn-register {
  background-color: var(--color-accent);
  color: var(--color-text-inverse);
  flex-shrink: 0;
}

.btn-register:hover {
  background-color: var(--color-accent-hover);
}

/* 注册弹窗 */
.register-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 2100;
  background-color: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl);
}

.register-card {
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.register-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.register-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.register-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  transition: var(--transition-colors);
  background: none;
  border: none;
  cursor: pointer;
}

.register-close:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.register-body {
  padding: var(--space-lg);
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: var(--space-md);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.form-input {
  width: 100%;
  padding: 8px var(--space-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors), var(--transition-shadow);
  box-sizing: border-box;
  font-family: inherit;
}

.form-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-light);
  background-color: var(--color-bg-primary);
  outline: none;
}

.form-input::placeholder {
  color: var(--color-text-muted);
}

textarea.form-input {
  resize: vertical;
  font-family: monospace;
}

.readonly-input {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: not-allowed;
}

.form-divider {
  height: 1px;
  background-color: var(--color-border);
  margin: var(--space-md) 0;
}

.error-message {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--color-error);
  background-color: #FEF2F2;
  border-radius: var(--radius-sm);
  border: 1px solid #FECACA;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

/* 加载小圆点 */
.btn-loading-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: skill-spin 0.6s linear infinite;
}

/* 弹窗过渡动画 */
.dialog-fade-enter-active {
  transition: opacity 0.25s ease;
}

.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-active .register-card {
  animation: skill-scale-in 0.25s ease;
}

.dialog-fade-leave-active .register-card {
  animation: skill-scale-out 0.2s ease;
}

@keyframes skill-scale-in {
  from {
    transform: scale(0.95);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes skill-scale-out {
  from {
    transform: scale(1);
    opacity: 1;
  }
  to {
    transform: scale(0.95);
    opacity: 0;
  }
}

@keyframes skill-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>