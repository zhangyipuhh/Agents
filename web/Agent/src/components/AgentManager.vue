<script setup>
/**
 * AgentManager - 智能体管理组件（admin）
 *
 * 提供完整 CRUD + config_schema 三层嵌套字段编辑能力：
 * - 左侧栏：智能体列表（卡片视图）
 * - 右侧主区域：
 *   - 编辑视图：AgentConfig 字段 / State 字段 / Context 字段 三组表格
 *   - 新增视图：弹窗表单（含 8 个字段 + 内嵌 config_schema 编辑器）
 *
 * Date: 2026-06-24
 * Author: AI Assistant
 */
import { ref, reactive, computed, onMounted, watch } from 'vue'
import {
  fetchAdminAgentList,
  fetchAdminAgentConfig,
  createAdminAgent,
  deleteAdminAgent,
  setAdminAgentEnabled,
  updateAdminAgentConfigSchema,
  addAdminAgentConfigField,
  updateAdminAgentConfigField,
  deleteAdminAgentConfigField,
  fetchAgentConfigFieldTemplates,
  validateAgentMdPath,
  checkAgentNameUnique,
} from '../utils/api.js'

// === 列表与详情状态 ===
const agentList = ref([])
const selectedAgentName = ref('')
const selectedAgent = ref(null)
const isLoadingList = ref(false)
const isLoadingDetail = ref(false)
const errorMessage = ref('')

// === 字段模板 ===
const fieldTemplates = ref({ root: [], state_fields: [], context_fields: [] })
const templateByName = computed(() => {
  const section = newField.section
  const templates = fieldTemplates.value[section] || []
  const m = {}
  for (const t of templates) m[t.field_name] = t
  return m
})

// === 编辑视图：变更跟踪 ===
const pendingChanges = reactive({
  root: { added: {}, deleted: [], modified: {} },
  state_fields: { added: {}, deleted: [], modified: {} },
  context_fields: { added: {}, deleted: [], modified: {} },
})
const hasPendingChanges = computed(() => {
  for (const s of ['root', 'state_fields', 'context_fields']) {
    const c = pendingChanges[s]
    if (Object.keys(c.added).length || c.deleted.length || Object.keys(c.modified).length) {
      return true
    }
  }
  return false
})

// === 弹窗状态 ===
const showAddFieldDialog = ref(false)
const showCreateDialog = ref(false)
const showDeleteConfirm = ref(false)
const showAgentDeleteConfirm = ref(false)
const agentToDelete = ref(null)

// === 新增字段表单 ===
const newField = reactive({
  section: 'root',          // root / state_fields / context_fields
  source: 'agent_config',   // agent_config (从 AgentConfig 已有字段) / custom
  fieldName: '',
  type: 'str',
  defaultValue: '',
})
const newFieldError = ref('')

// === 新增智能体表单 ===
const createForm = reactive({
  name: '',
  display_name: '',
  description: '',
  agents_md_path: '',
  mcp_tags: '',
  enabled: true,
  sort_order: 0,
  configSchema: {
    state_fields: {},
    context_fields: {},
  },
})
const createFormError = ref('')
const mdPathValidating = ref(false)
const mdPathValid = ref(false)
const nameAvailable = ref(false)
const nameValidating = ref(false)

const SUPPORTED_TYPES = ['str', 'int', 'float', 'bool', 'dict', 'list']

// === 加载与刷新 ===

async function loadAgentList() {
  isLoadingList.value = true
  errorMessage.value = ''
  try {
    agentList.value = await fetchAdminAgentList()
    if (!selectedAgentName.value && agentList.value.length > 0) {
      selectAgent(agentList.value[0].name)
    }
  } catch (err) {
    errorMessage.value = err.message || '加载智能体列表失败'
  } finally {
    isLoadingList.value = false
  }
}

async function loadFieldTemplates() {
  try {
    const [root, state, context] = await Promise.all([
      fetchAgentConfigFieldTemplates('root'),
      fetchAgentConfigFieldTemplates('state_fields'),
      fetchAgentConfigFieldTemplates('context_fields'),
    ])
    fieldTemplates.value = { root, state_fields: state, context_fields: context }
  } catch (err) {
    console.error('加载字段模板失败', err)
  }
}

async function selectAgent(name) {
  selectedAgentName.value = name
  isLoadingDetail.value = true
  errorMessage.value = ''
  resetPendingChanges()
  try {
    selectedAgent.value = await fetchAdminAgentConfig(name)
  } catch (err) {
    errorMessage.value = err.message || '加载智能体详情失败'
    selectedAgent.value = null
  } finally {
    isLoadingDetail.value = false
  }
}

function resetPendingChanges() {
  for (const s of ['root', 'state_fields', 'context_fields']) {
    pendingChanges[s].added = {}
    pendingChanges[s].deleted = []
    pendingChanges[s].modified = {}
  }
}

// === config_schema 数据视图 ===

/**
 * 获取 section 中所有字段的"当前值"（含已应用 + pending）
 * 返回 [{ name, type, default, isPending }]
 */
function getSectionFields(section) {
  const schema = selectedAgent.value?.config_schema || {}
  let current
  if (section === 'root') {
    current = {}
    for (const [k, v] of Object.entries(schema)) {
      if (k === 'state_fields' || k === 'context_fields') continue
      if (typeof v === 'object' && v && 'type' in v) current[k] = v
    }
  } else {
    current = schema[section] || {}
  }
  const result = []
  // 已有字段
  for (const [name, def] of Object.entries(current)) {
    const isPendingDel = pendingChanges[section].deleted.includes(name)
    if (isPendingDel) continue
    const isPendingMod = pendingChanges[section].modified[name]
    result.push({
      name,
      type: def.type || 'str',
      default: isPendingMod ? isPendingMod.default : def.default,
      isPending: !!isPendingMod,
      isNew: false,
    })
  }
  // 新增字段
  for (const [name, def] of Object.entries(pendingChanges[section].added)) {
    result.push({ name, ...def, isPending: true, isNew: true })
  }
  return result
}

const rootFields = computed(() => getSectionFields('root'))
const stateFields = computed(() => getSectionFields('state_fields'))
const contextFields = computed(() => getSectionFields('context_fields'))

// === 新增字段弹窗 ===

function openAddFieldDialog(section) {
  newField.section = section
  newField.source = 'agent_config'
  newField.fieldName = ''
  newField.type = 'str'
  newField.defaultValue = ''
  newFieldError.value = ''
  showAddFieldDialog.value = true
}

function applyTemplate(template) {
  newField.fieldName = template.field_name
  newField.type = template.type
  newField.defaultValue = template.default === null || template.default === undefined
    ? '' : String(template.default)
  if (typeof template.default === 'object' && template.default !== null) {
    newField.defaultValue = JSON.stringify(template.default)
  }
}

function changeFieldSource() {
  newField.fieldName = ''
  newField.type = 'str'
  newField.defaultValue = ''
}

async function confirmAddField() {
  newFieldError.value = ''
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(newField.fieldName)) {
    newFieldError.value = '字段名必须由字母 / 数字 / 下划线组成，且不能以数字开头'
    return
  }
  if (!SUPPORTED_TYPES.includes(newField.type)) {
    newFieldError.value = `不支持的类型: ${newField.type}`
    return
  }
  // 检查重复
  const existing = getSectionFields(newField.section)
  if (existing.some(f => f.name === newField.fieldName)) {
    newFieldError.value = `字段 '${newField.fieldName}' 已存在`
    return
  }
  // 解析默认值
  let defaultVal = newField.defaultValue
  if (newField.type === 'bool') {
    defaultVal = ['true', '1', 'yes'].includes(String(defaultVal).toLowerCase())
  } else if (newField.type === 'int') {
    defaultVal = parseInt(defaultVal, 10)
    if (Number.isNaN(defaultVal)) {
      newFieldError.value = 'int 类型默认值必须是整数'
      return
    }
  } else if (newField.type === 'float') {
    defaultVal = parseFloat(defaultVal)
    if (Number.isNaN(defaultVal)) {
      newFieldError.value = 'float 类型默认值必须是数字'
      return
    }
  } else if (newField.type === 'dict' || newField.type === 'list') {
    if (typeof defaultVal === 'string' && defaultVal.trim() !== '') {
      try {
        defaultVal = JSON.parse(defaultVal)
      } catch (e) {
        newFieldError.value = 'dict/list 类型默认值必须是合法 JSON'
        return
      }
    }
  }
  pendingChanges[newField.section].added[newField.fieldName] = {
    type: newField.type,
    default: defaultVal,
  }
  showAddFieldDialog.value = false
}

function removeField(section, name) {
  if (!confirm(`确定删除字段 '${name}'？`)) return
  // 移除 added
  if (pendingChanges[section].added[name]) {
    delete pendingChanges[section].added[name]
    return
  }
  // 移除 modified
  if (pendingChanges[section].modified[name]) {
    delete pendingChanges[section].modified[name]
  }
  // 标记 deleted
  if (!pendingChanges[section].deleted.includes(name)) {
    pendingChanges[section].deleted.push(name)
  }
}

// === 保存变更 ===

async function saveAllChanges() {
  if (!hasPendingChanges.value) return
  errorMessage.value = ''
  const errors = []
  try {
    // 增量更新策略：先删除，再修改，最后添加
    for (const section of ['root', 'state_fields', 'context_fields']) {
      const c = pendingChanges[section]
      for (const name of c.deleted) {
        try {
          await deleteAdminAgentConfigField(selectedAgentName.value, section, name)
        } catch (err) {
          errors.push(`删除 ${section}.${name} 失败: ${err.message}`)
          console.error(`[saveAllChanges] 删除 ${section}.${name} 失败`, err)
        }
      }
      for (const [name, def] of Object.entries(c.modified)) {
        try {
          // 2026-06-24 修复：使用 PUT 直接覆盖，避免"先删后加"导致的数据丢失
          await updateAdminAgentConfigField(selectedAgentName.value, section, name, def)
        } catch (err) {
          errors.push(`修改 ${section}.${name} 失败: ${err.message}`)
          console.error(`[saveAllChanges] 修改 ${section}.${name} 失败`, err)
        }
      }
      for (const [name, def] of Object.entries(c.added)) {
        try {
          await addAdminAgentConfigField(selectedAgentName.value, section, name, def)
        } catch (err) {
          errors.push(`添加 ${section}.${name} 失败: ${err.message}`)
          console.error(`[saveAllChanges] 添加 ${section}.${name} 失败`, err)
        }
      }
    }
    if (errors.length > 0) {
      errorMessage.value = errors.join('; ')
      return
    }
    // 重新加载
    await selectAgent(selectedAgentName.value)
  } catch (err) {
    errorMessage.value = err.message || '保存失败'
    console.error('[saveAllChanges] 未捕获异常', err)
  }
}

function discardChanges() {
  if (!confirm('放弃所有未保存的修改？')) return
  resetPendingChanges()
}

// === 启用 / 禁用 ===

async function toggleEnabled() {
  if (!selectedAgent.value) return
  const newEnabled = !selectedAgent.value.enabled
  try {
    const updated = await setAdminAgentEnabled(selectedAgentName.value, newEnabled)
    selectedAgent.value = { ...selectedAgent.value, ...updated }
    await loadAgentList()
  } catch (err) {
    errorMessage.value = err.message || '更新启用状态失败'
  }
}

// === 删除智能体 ===

function openDeleteAgentConfirm() {
  agentToDelete.value = selectedAgent.value
  showAgentDeleteConfirm.value = true
}

async function confirmDeleteAgent() {
  if (!agentToDelete.value) return
  try {
    await deleteAdminAgent(agentToDelete.value.name)
    showAgentDeleteConfirm.value = false
    agentToDelete.value = null
    selectedAgent.value = null
    selectedAgentName.value = ''
    await loadAgentList()
  } catch (err) {
    errorMessage.value = err.message || '删除智能体失败'
  }
}

// === 新增智能体弹窗 ===

function openCreateDialog() {
  createForm.name = ''
  createForm.display_name = ''
  createForm.description = ''
  createForm.agents_md_path = ''
  createForm.mcp_tags = ''
  createForm.enabled = true
  createForm.sort_order = 0
  createForm.configSchema = { state_fields: {}, context_fields: {} }
  createFormError.value = ''
  mdPathValid.value = false
  nameAvailable.value = false
  showCreateDialog.value = true
}

async function validateMdPath() {
  if (!createForm.agents_md_path) {
    mdPathValid.value = false
    return
  }
  mdPathValidating.value = true
  try {
    const res = await validateAgentMdPath(createForm.agents_md_path)
    mdPathValid.value = res.exists === true
  } catch (err) {
    mdPathValid.value = false
  } finally {
    mdPathValidating.value = false
  }
}

async function validateName() {
  if (!/^[a-z0-9_]{3,50}$/.test(createForm.name)) {
    nameAvailable.value = false
    return
  }
  nameValidating.value = true
  try {
    const res = await checkAgentNameUnique(createForm.name)
    nameAvailable.value = res.available === true
  } catch (err) {
    nameAvailable.value = false
  } finally {
    nameValidating.value = false
  }
}

async function confirmCreate() {
  createFormError.value = ''
  if (!/^[a-z0-9_]{3,50}$/.test(createForm.name)) {
    createFormError.value = 'name 必须由小写字母 / 数字 / 下划线组成，长度 3-50 字符'
    return
  }
  if (!createForm.display_name.trim()) {
    createFormError.value = '请输入显示名'
    return
  }
  if (!mdPathValid.value) {
    createFormError.value = 'AGENTS.md 路径无效或文件不存在'
    return
  }
  const payload = {
    name: createForm.name,
    display_name: createForm.display_name,
    description: createForm.description,
    agents_md_path: createForm.agents_md_path,
    enabled: createForm.enabled,
    sort_order: parseInt(createForm.sort_order, 10) || 0,
    mcp_tags: createForm.mcp_tags
      ? createForm.mcp_tags.split(',').map(s => s.trim()).filter(Boolean)
      : [],
    config_schema: createForm.configSchema,
  }
  try {
    const created = await createAdminAgent(payload)
    showCreateDialog.value = false
    await loadAgentList()
    selectAgent(created.name)
  } catch (err) {
    createFormError.value = err.message || '新增智能体失败'
  }
}

// === 生命周期 ===
onMounted(async () => {
  await loadFieldTemplates()
  await loadAgentList()
})
</script>

<template>
  <div class="agent-manager">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <h3 class="toolbar-title">智能体管理</h3>
      <div class="toolbar-actions">
        <button class="btn-primary" @click="openCreateDialog">新增智能体</button>
        <button class="btn-secondary" @click="loadAgentList">刷新列表</button>
      </div>
    </div>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <div class="agent-layout">
      <!-- 左侧栏：智能体列表 -->
      <aside class="agent-sidebar">
        <div v-if="isLoadingList" class="loading">加载中...</div>
        <div v-else-if="agentList.length === 0" class="empty">暂无智能体</div>
        <ul v-else class="agent-list">
          <li
            v-for="agent in agentList"
            :key="agent.name"
            class="agent-item"
            :class="{ active: selectedAgentName === agent.name }"
            @click="selectAgent(agent.name)"
          >
            <div class="agent-item-header">
              <span class="agent-display-name">{{ agent.display_name }}</span>
              <span v-if="!agent.enabled" class="badge-disabled">已禁用</span>
            </div>
            <div class="agent-item-meta">
              <span class="agent-name">{{ agent.name }}</span>
              <span class="agent-order">#{{ agent.sort_order || 0 }}</span>
            </div>
          </li>
        </ul>
      </aside>

      <!-- 右侧主区域 -->
      <main class="agent-main">
        <div v-if="!selectedAgent" class="empty-state">
          请选择左侧智能体查看详情，或点击「新增智能体」创建。
        </div>
        <div v-else-if="isLoadingDetail" class="loading">加载详情中...</div>
        <div v-else>
          <!-- 详情头部 -->
          <header class="agent-detail-header">
            <div>
              <h4 class="agent-title">{{ selectedAgent.display_name }}</h4>
              <p class="agent-subtitle">
                <code>{{ selectedAgent.name }}</code>
                <span class="separator">·</span>
                <span>{{ selectedAgent.description || '暂无描述' }}</span>
              </p>
            </div>
            <div class="header-actions">
              <label class="switch-label">
                <input type="checkbox" :checked="selectedAgent.enabled" @change="toggleEnabled" />
                <span>{{ selectedAgent.enabled ? '已启用' : '已禁用' }}</span>
              </label>
              <button class="btn-danger" @click="openDeleteAgentConfirm">删除智能体</button>
            </div>
          </header>

          <!-- 三组可编辑表格 -->
          <SectionEditor
            title="AgentConfig 字段"
            subtitle="覆盖 AgentConfig dataclass 的运行参数（temperature / max_tokens 等）"
            :fields="rootFields"
            :templates="fieldTemplates.root"
            source-label="AgentConfig"
            section="root"
            @add="openAddFieldDialog('root')"
            @remove="removeField"
          />
          <SectionEditor
            title="State 扩展字段"
            subtitle="state 字典的扩展字段（除基类保留字段外）"
            :fields="stateFields"
            :templates="fieldTemplates.state_fields"
            source-label="AgentState"
            section="state_fields"
            @add="openAddFieldDialog('state_fields')"
            @remove="removeField"
          />
          <SectionEditor
            title="Context 扩展字段"
            subtitle="context 字典的扩展字段（除基类保留字段外）"
            :fields="contextFields"
            :templates="fieldTemplates.context_fields"
            source-label="AgentContext"
            section="context_fields"
            @add="openAddFieldDialog('context_fields')"
            @remove="removeField"
          />

          <!-- 底部变更摘要 -->
          <div v-if="hasPendingChanges" class="changes-summary">
            <span>有未保存的修改</span>
            <div>
              <button class="btn-secondary" @click="discardChanges">放弃修改</button>
              <button class="btn-primary" @click="saveAllChanges">保存全部修改</button>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 新增字段弹窗 -->
    <div v-if="showAddFieldDialog" class="dialog-overlay" @click.self="showAddFieldDialog = false">
      <div class="dialog-card">
        <h4>新增字段</h4>
        <div class="form-group">
          <label>Section</label>
          <select v-model="newField.section" disabled>
            <option value="root">root (AgentConfig 字段)</option>
            <option value="state_fields">state_fields (State 扩展)</option>
            <option value="context_fields">context_fields (Context 扩展)</option>
          </select>
        </div>
        <div class="form-group">
          <label>覆盖来源</label>
          <select v-model="newField.source" @change="changeFieldSource">
            <option value="agent_config">
              {{ newField.section === 'root' ? 'AgentConfig 已有字段' : newField.section === 'state_fields' ? 'AgentState 已有字段' : 'AgentContext 已有字段' }}
            </option>
            <option value="custom">自定义</option>
          </select>
        </div>
        <div v-if="newField.source === 'agent_config'" class="form-group">
          <label>
            {{ newField.section === 'root' ? '选择 AgentConfig 字段' : newField.section === 'state_fields' ? '选择 AgentState 字段' : '选择 AgentContext 字段' }}
          </label>
          <select :value="newField.fieldName" @change="applyTemplate(templateByName[$event.target.value])">
            <option value="">-- 选择 --</option>
            <option v-for="t in fieldTemplates[newField.section]" :key="t.field_name" :value="t.field_name">
              {{ t.field_name }} ({{ t.type }})
            </option>
          </select>
        </div>
        <div class="form-group">
          <label>字段名</label>
          <input v-model="newField.fieldName" type="text" placeholder="例如：map_zoom" />
        </div>
        <div class="form-group">
          <label>类型</label>
          <select v-model="newField.type">
            <option v-for="t in SUPPORTED_TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>默认值</label>
          <input
            v-model="newField.defaultValue"
            type="text"
            :placeholder="newField.type === 'dict' || newField.type === 'list' ? 'JSON 字符串' : ''"
          />
        </div>
        <div v-if="newFieldError" class="error-message">{{ newFieldError }}</div>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showAddFieldDialog = false">取消</button>
          <button class="btn-primary" @click="confirmAddField">确认添加</button>
        </div>
      </div>
    </div>

    <!-- 新增智能体弹窗 -->
    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-card dialog-large">
        <h4>新增智能体</h4>
        <div class="form-group">
          <label>名称 (name) *</label>
          <input
            v-model="createForm.name"
            type="text"
            placeholder="小写字母 / 数字 / 下划线，3-50 字符"
            @blur="validateName"
          />
          <small v-if="createForm.name && !nameAvailable && !nameValidating" class="error-text">
            name 格式非法或已被占用
          </small>
        </div>
        <div class="form-group">
          <label>显示名 (display_name) *</label>
          <input v-model="createForm.display_name" type="text" placeholder="例如：地图智能体" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="createForm.description" rows="2" placeholder="智能体描述"></textarea>
        </div>
        <div class="form-group">
          <label>AGENTS.md 路径 *</label>
          <input
            v-model="createForm.agents_md_path"
            type="text"
            placeholder="例如：agents/new_agent/AGENTS.md"
            @blur="validateMdPath"
          />
          <small v-if="mdPathValidating" class="hint-text">校验中...</small>
          <small v-else-if="createForm.agents_md_path && !mdPathValid" class="error-text">
            文件不存在或路径无效
          </small>
        </div>
        <div class="form-group">
          <label>MCP 标签 (逗号分隔)</label>
          <input v-model="createForm.mcp_tags" type="text" placeholder="例如：map, audit" />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>启用</label>
            <input v-model="createForm.enabled" type="checkbox" />
          </div>
          <div class="form-group">
            <label>排序</label>
            <input v-model="createForm.sort_order" type="number" min="0" />
          </div>
        </div>
        <div v-if="createFormError" class="error-message">{{ createFormError }}</div>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showCreateDialog = false">取消</button>
          <button class="btn-primary" @click="confirmCreate">保存</button>
        </div>
      </div>
    </div>

    <!-- 删除智能体确认 -->
    <div v-if="showAgentDeleteConfirm" class="dialog-overlay" @click.self="showAgentDeleteConfirm = false">
      <div class="dialog-card">
        <h4>确认删除</h4>
        <p>确定删除智能体 <strong>{{ agentToDelete?.display_name }}</strong> 吗？</p>
        <p class="hint-text">此操作将级联删除其所有工具/技能绑定，但历史会话保留。</p>
        <div class="dialog-actions">
          <button class="btn-secondary" @click="showAgentDeleteConfirm = false">取消</button>
          <button class="btn-danger" @click="confirmDeleteAgent">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 嵌套的 SectionEditor 子组件（内联以减少文件数量）
import { defineComponent, h } from 'vue'

const SectionEditor = defineComponent({
  name: 'SectionEditor',
  props: {
    title: { type: String, required: true },
    subtitle: { type: String, default: '' },
    fields: { type: Array, required: true },
    templates: { type: Array, default: () => [] },
    section: { type: String, required: true },
    sourceLabel: { type: String, default: 'AgentConfig' },
  },
  emits: ['add', 'remove'],
  setup(props, { emit }) {
    return () => h('section', { class: 'section-editor' }, [
      h('header', { class: 'section-header' }, [
        h('div', null, [
          h('h4', { class: 'section-title' }, props.title),
          h('p', { class: 'section-subtitle' }, props.subtitle),
        ]),
        h('button', {
          class: 'btn-secondary btn-sm',
          onClick: () => emit('add'),
        }, '+ 添加字段'),
      ]),
      h('table', { class: 'fields-table' }, [
        h('thead', null, [
          h('tr', null, [
            h('th', null, '字段名'),
            h('th', null, '类型'),
            h('th', null, '默认值'),
            h('th', null, '来源'),
            h('th', null, '操作'),
          ]),
        ]),
        h('tbody', null,
          props.fields.length === 0
            ? [h('tr', null, [h('td', { colspan: 5, class: 'empty-row' }, '暂无字段')])]
            : props.fields.map(f =>
                h('tr', { key: f.name, class: { 'pending-row': f.isPending } }, [
                  h('td', null, [
                    h('code', null, f.name),
                    f.isNew ? h('span', { class: 'badge-new' }, '新增') : null,
                  ]),
                  h('td', null, f.type),
                  h('td', null, formatValue(f.default)),
                  h('td', null, f.isNew
                    ? h('span', { class: 'badge-custom' }, '自定义')
                    : props.templates.some(t => t.field_name === f.name)
                      ? h('span', { class: 'badge-agent-config' }, props.sourceLabel)
                      : h('span', { class: 'badge-custom' }, '自定义')
                  ),
                  h('td', null, [
                    h('button', {
                      class: 'btn-danger btn-sm',
                      onClick: () => emit('remove', props.section, f.name),
                    }, '删除'),
                  ]),
                ])
              )
        ),
      ]),
    ])
  },
})

function formatValue(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export default {
  components: { SectionEditor },
}
</script>

<style scoped>
.agent-manager {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px;
}
.toolbar-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
}

.error-banner {
  padding: 10px 14px;
  background-color: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
  border-radius: 4px;
  font-size: 13px;
}

.agent-layout {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.agent-sidebar {
  width: 260px;
  flex-shrink: 0;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  overflow-y: auto;
  background-color: var(--color-bg-secondary);
}

.agent-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.agent-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border-light);
  cursor: pointer;
  transition: background-color 0.15s;
}
.agent-item:hover {
  background-color: var(--color-bg-hover);
}
.agent-item.active {
  background-color: var(--color-accent-light);
  border-left: 3px solid var(--color-accent);
}
.agent-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}
.agent-display-name {
  font-weight: 500;
  font-size: 14px;
  color: var(--color-text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-item-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
}
.agent-name {
  font-family: monospace;
}
.badge-disabled {
  background-color: #fee2e2;
  color: #dc2626;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

.agent-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
}
.agent-title {
  margin: 0 0 4px;
  font-size: 18px;
}
.agent-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.agent-subtitle code {
  font-family: monospace;
  background-color: var(--color-bg-secondary);
  padding: 1px 6px;
  border-radius: 3px;
}
.separator {
  margin: 0 8px;
}
.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}
.switch-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}

.section-editor {
  margin-bottom: 24px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.section-subtitle {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
}

.fields-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}
.fields-table th,
.fields-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--color-border-light);
}
.fields-table th {
  background-color: var(--color-bg-secondary);
  font-weight: 600;
}
.fields-table td code {
  font-family: monospace;
  background-color: var(--color-bg-secondary);
  padding: 1px 4px;
  border-radius: 3px;
}
.pending-row {
  background-color: #fff7e6;
}
.empty-row {
  text-align: center;
  color: var(--color-text-muted);
  padding: 20px;
}
.badge-new {
  background-color: #dbeafe;
  color: #2563eb;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  margin-left: 4px;
}
.badge-agent-config,
.badge-custom {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
}
.badge-agent-config {
  background-color: #e0e7ff;
  color: #4338ca;
}
.badge-custom {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-muted);
}

.changes-summary {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background-color: #fff7e6;
  border: 1px solid #fbbf24;
  border-radius: 6px;
  margin-top: 16px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--color-text-muted);
  font-size: 14px;
  border: 1px dashed var(--color-border);
  border-radius: 6px;
}

.loading,
.empty {
  padding: 20px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
}

/* 按钮 */
.btn-primary,
.btn-secondary,
.btn-danger {
  font-family: inherit;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 4px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-primary {
  background-color: var(--color-accent);
  color: white;
}
.btn-primary:hover {
  background-color: var(--color-accent-hover);
}
.btn-secondary {
  background-color: var(--color-bg-secondary);
  color: var(--color-text-primary);
  border-color: var(--color-border);
}
.btn-secondary:hover {
  background-color: var(--color-bg-hover);
}
.btn-danger {
  background-color: #fee2e2;
  color: #dc2626;
}
.btn-danger:hover {
  background-color: #fecaca;
}
.btn-sm {
  padding: 3px 10px;
  font-size: 12px;
}

/* 弹窗 */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2200;
}
.dialog-card {
  background-color: var(--color-bg-primary);
  border-radius: 8px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 480px;
  max-width: calc(100vw - 32px);
  max-height: 90vh;
  padding: 20px 24px;
  overflow-y: auto;
}
.dialog-large {
  width: 600px;
}
.dialog-card h4 {
  margin: 0 0 16px;
  font-size: 16px;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.form-group {
  margin-bottom: 12px;
}
.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--color-text-primary);
}
.form-group input[type="text"],
.form-group input[type="number"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  font-family: inherit;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background-color: var(--color-bg-secondary);
  color: var(--color-text-primary);
}
.form-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.error-message {
  padding: 8px 12px;
  background-color: #fef2f2;
  color: #dc2626;
  border-radius: 4px;
  font-size: 13px;
  margin-bottom: 8px;
}
.error-text {
  color: #dc2626;
  font-size: 12px;
}
.hint-text {
  color: var(--color-text-muted);
  font-size: 12px;
}
</style>