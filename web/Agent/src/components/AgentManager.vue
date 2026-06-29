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
  updateAdminAgent,
  updateAdminAgentConfigSchema,
  addAdminAgentConfigField,
  updateAdminAgentConfigField,
  deleteAdminAgentConfigField,
  fetchAgentConfigFieldTemplates,
  validateAgentMdPath,
  checkAgentNameUnique,
  listTools,
  getAgentToolBindings,
  updateAgentToolBindings,
  listMcpServers,
  listMcpMethods,
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

// === Tab 切换状态 ===
const activeTab = ref('basic') // 'basic'（基本信息） | 'config'（配置字段） | 'tools'（工具绑定）

// === 基本信息编辑状态 ===
const basicForm = reactive({
  display_name: '',
  description: '',
})
const basicSaving = ref(false)
const basicSavedTip = ref('')

// === 工具绑定相关状态 ===
const builtinTools = ref([])              // 内置工具列表（listTools 返回）
const mcpServersWithMethods = ref([])     // MCP 服务器列表（含 methods，由 listMcpServers + listMcpMethods 组装）
const agentToolBindings = ref([])         // 当前 agent 已保存的工具绑定（getAgentToolBindings 返回）
const isLoadingTools = ref(false)         // 工具绑定 Tab 加载状态
const toolBindingsError = ref('')         // 工具绑定 Tab 错误信息
const toolBindingsSavedTip = ref('')      // 工具绑定保存成功提示
const localSelectedBindings = ref({})     // 本地勾选状态：key = `${tool_type}:${tool_name}` -> true
const toolsInitialized = ref(false)       // 工具列表（builtin + mcp）是否已加载（全局缓存，避免每次切换 agent 重复拉取）

// === 工具绑定：分组折叠状态 ===
const expandedToolGroups = ref(new Set()) // 已展开的工具分类集合

/**
 * 切换工具分组的展开/折叠状态
 * @param {string} category - 分类名称
 */
function toggleToolGroup(category) {
  const next = new Set(expandedToolGroups.value)
  if (next.has(category)) {
    next.delete(category)
  } else {
    next.add(category)
  }
  expandedToolGroups.value = next
}

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
  // 切换 agent 时重置工具绑定本地状态
  agentToolBindings.value = []
  localSelectedBindings.value = {}
  toolBindingsError.value = ''
  toolBindingsSavedTip.value = ''
  // 记录切换前是否在工具绑定 Tab，用于决定是否需要重新加载绑定
  const wasOnToolsTab = activeTab.value === 'tools'
  try {
    selectedAgent.value = await fetchAdminAgentConfig(name)
    // 若当前停留在工具绑定 Tab，切换 agent 后立即重新加载该 agent 的绑定
    if (wasOnToolsTab) {
      await loadAgentBindings()
    }
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

async function toggleAgentEnabled(agent) {
  if (!agent) return
  const newEnabled = !agent.enabled
  try {
    const updated = await setAdminAgentEnabled(agent.name, newEnabled)
    agent.enabled = updated.enabled
    await loadAgentList()
  } catch (err) {
    errorMessage.value = err.message || '更新启用状态失败'
  }
}

// === 删除智能体 ===

function openDeleteAgent(agent) {
  agentToDelete.value = agent
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

// === 工具绑定：computed ===

/**
 * 判断指定工具是否在本地勾选集合中
 * @param {string} toolType - 工具类型（builtin / mcp）
 * @param {string} toolName - 工具名称
 * @returns {boolean} 是否勾选
 */
function isToolSelected(toolType, toolName) {
  return !!localSelectedBindings.value[`${toolType}:${toolName}`]
}

/**
 * 按分类分组展示所有可用工具（内置 + MCP）
 * - 内置工具分类 = tools.category
 * - MCP 工具分类 = mcp_server.display_name
 * @returns {Array<{category: string, tools: Array}>} 分组后的工具列表
 */
const groupedTools = computed(() => {
  const groups = {}
  const order = []

  // 内置工具按 category 分组
  for (const tool of builtinTools.value) {
    const category = tool.category || '未分类'
    if (!groups[category]) {
      groups[category] = []
      order.push(category)
    }
    // 内置工具展示名 = "文件名.函数名"（如 "BaseTools.get_current_time"），
    // 绑定时仍传函数名（与后端 tools.name 一致）。
    const fileBase = (tool.file_path || '').split(/[/\\]/).pop() || ''
    const fileBaseNoExt = fileBase.replace(/\.py$/i, '')
    const showName = fileBaseNoExt
      ? `${fileBaseNoExt}.${tool.name}`
      : (tool.display_name || tool.name)
    groups[category].push({
      tool_name: tool.name,
      tool_type: 'builtin',
      display_name: showName,
      description: tool.description || '',
      sourceEnabled: tool.enabled,
    })
  }

  // MCP 工具按 server display_name 分组
  for (const server of mcpServersWithMethods.value) {
    const category = server.display_name || server.name
    if (!groups[category]) {
      groups[category] = []
      order.push(category)
    }
    for (const method of server.methods || []) {
      // MCP 工具 binding 用 "server.method" 复合名（避免跨 server 命名冲突）。
      // 展示时为可读性，用 "server.method" 完整形式。
      const compositeName = `${server.name}.${method.method_name}`
      groups[category].push({
        tool_name: compositeName,
        tool_type: 'mcp',
        display_name: compositeName,
        description: method.description || '',
        sourceEnabled: method.enabled,
      })
    }
  }

  return order.map(category => ({ category, tools: groups[category] }))
})

/**
 * 当前勾选的工具绑定数量
 */
const selectedBindingsCount = computed(() => {
  return Object.keys(localSelectedBindings.value).length
})

/**
 * 工具绑定是否有未保存的修改（对比本地勾选与服务端已保存的绑定）
 * @returns {boolean} 是否存在差异
 */
const hasBindingChanges = computed(() => {
  const savedSet = new Set()
  for (const b of agentToolBindings.value) {
    if (b.enabled) savedSet.add(`${b.tool_type}:${b.tool_name}`)
  }
  const localSet = new Set(Object.keys(localSelectedBindings.value))
  if (savedSet.size !== localSet.size) return true
  for (const k of localSet) {
    if (!savedSet.has(k)) return true
  }
  return false
})

// === 工具绑定：加载与保存 ===

/**
 * 加载所有可用工具列表（内置 + MCP），全局缓存只加载一次
 * 内置工具调用 listTools；MCP 工具先调 listMcpServers 再对每个 server 调 listMcpMethods
 * @returns {Promise<void>} 无返回值；失败时设置 toolBindingsError
 */
async function loadAllTools() {
  if (toolsInitialized.value) return
  toolBindingsError.value = ''
  try {
    // 并行加载内置工具 + MCP 服务器列表
    const [tools, servers] = await Promise.all([
      listTools(),
      listMcpServers(),
    ])
    builtinTools.value = Array.isArray(tools) ? tools : []

    // 对每个 MCP server 加载其方法列表（任一 server 失败不影响其他）
    const serversWithMethods = await Promise.all(
      (Array.isArray(servers) ? servers : []).map(async (server) => {
        try {
          const methods = await listMcpMethods(server.name)
          return { ...server, methods: Array.isArray(methods) ? methods : [] }
        } catch (err) {
          console.error(`加载 MCP 服务器 ${server.name} 方法列表失败:`, err)
          return { ...server, methods: [] }
        }
      })
    )
    mcpServersWithMethods.value = serversWithMethods
    toolsInitialized.value = true
  } catch (err) {
    toolBindingsError.value = err.message || '加载工具列表失败'
  }
}

/**
 * 加载当前选中 agent 的工具绑定，并同步本地勾选状态
 * @returns {Promise<void>} 无返回值；失败时设置 toolBindingsError
 */
async function loadAgentBindings() {
  if (!selectedAgentName.value) return
  toolBindingsError.value = ''
  try {
    const data = await getAgentToolBindings(selectedAgentName.value)
    const bindings = data.tool_bindings || []
    agentToolBindings.value = bindings
    // 同步本地勾选状态：仅 enabled=true 的工具被勾选
    const selected = {}
    for (const b of bindings) {
      if (b.enabled) {
        selected[`${b.tool_type}:${b.tool_name}`] = true
      }
    }
    localSelectedBindings.value = selected
  } catch (err) {
    toolBindingsError.value = err.message || '加载工具绑定失败'
    agentToolBindings.value = []
    localSelectedBindings.value = {}
  }
}

/**
 * 切换到工具绑定 Tab 时触发加载（工具列表 + 当前 agent 绑定）
 * @returns {Promise<void>} 无返回值
 */
async function onSwitchToToolsTab() {
  isLoadingTools.value = true
  try {
    await loadAllTools()
    await loadAgentBindings()
  } finally {
    isLoadingTools.value = false
  }
}

/**
 * 保存智能体基本信息（display_name / description）
 * @returns {Promise<void>} 无返回值
 */
async function saveBasicInfo() {
  if (!selectedAgentName.value) return
  basicSaving.value = true
  errorMessage.value = ''
  basicSavedTip.value = ''
  try {
    await updateAdminAgent(selectedAgentName.value, {
      display_name: basicForm.display_name.trim(),
      description: basicForm.description.trim(),
    })
    basicSavedTip.value = '基本信息保存成功'
    setTimeout(() => { basicSavedTip.value = '' }, 3000)
    // 同步刷新列表和当前详情
    await loadAgentList()
    await selectAgent(selectedAgentName.value)
  } catch (err) {
    errorMessage.value = err.message || '保存基本信息失败'
  } finally {
    basicSaving.value = false
  }
}

/**
 * 切换 Tab；切到工具绑定 Tab 时按需加载工具数据
 * @param {string} tab - 目标 Tab 名称（basic / config / tools）
 * @returns {Promise<void>} 无返回值
 */
async function switchTab(tab) {
  if (activeTab.value === tab) return
  activeTab.value = tab
  if (tab === 'tools' && selectedAgentName.value) {
    await onSwitchToToolsTab()
  }
}

/**
 * 切换单个工具的勾选状态
 * @param {string} toolType - 工具类型（builtin / mcp）
 * @param {string} toolName - 工具名称
 */
function toggleToolSelection(toolType, toolName) {
  const key = `${toolType}:${toolName}`
  if (localSelectedBindings.value[key]) {
    const next = { ...localSelectedBindings.value }
    delete next[key]
    localSelectedBindings.value = next
  } else {
    localSelectedBindings.value = { ...localSelectedBindings.value, [key]: true }
  }
}

/**
 * 保存工具绑定到后端
 * 构造 bindings 数组（仅勾选的工具，sort_order 按分组顺序生成），
 * 调用 updateAgentToolBindings；成功后重新加载绑定状态并显示提示
 * @returns {Promise<void>} 无返回值；失败时设置 toolBindingsError
 */
async function saveToolBindings() {
  if (!selectedAgentName.value) return
  toolBindingsError.value = ''
  toolBindingsSavedTip.value = ''
  // 构造 bindings：所有勾选的工具，sort_order 按分组顺序生成
  const bindings = []
  let sortOrder = 0
  for (const group of groupedTools.value) {
    for (const tool of group.tools) {
      if (isToolSelected(tool.tool_type, tool.tool_name)) {
        bindings.push({
          tool_name: tool.tool_name,
          tool_type: tool.tool_type,
          enabled: true,
          sort_order: sortOrder++,
        })
      }
    }
  }
  try {
    await updateAgentToolBindings(selectedAgentName.value, bindings)
    // 保存成功后重新加载绑定状态，保持本地与服务端一致
    await loadAgentBindings()
    toolBindingsSavedTip.value = '工具绑定保存成功'
    // 3 秒后自动清除提示
    setTimeout(() => { toolBindingsSavedTip.value = '' }, 3000)
  } catch (err) {
    toolBindingsError.value = err.message || '保存工具绑定失败'
  }
}

// === 监听 selectedAgent 变化，同步基本信息表单 ===
watch(
  () => selectedAgent.value,
  (agent) => {
    if (agent) {
      basicForm.display_name = agent.display_name || ''
      basicForm.description = agent.description || ''
    } else {
      basicForm.display_name = ''
      basicForm.description = ''
    }
  },
  { immediate: true }
)

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
            <div class="header-actions">
              <label class="switch-label">
                <input type="checkbox" :checked="agent.enabled" @change.stop="toggleAgentEnabled(agent)" />
                <span>{{ agent.enabled ? '已启用' : '已禁用' }}</span>
              </label>
              <button class="btn-danger btn-sm" @click.stop="openDeleteAgent(agent)">删除智能体</button>
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
          </header>

          <!-- Tab 导航栏 -->
          <nav class="tab-nav">
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'basic' }"
              @click="switchTab('basic')"
            >
              <span class="tab-icon">&#128196;</span>
              <span>基本信息</span>
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'config' }"
              @click="switchTab('config')"
            >
              <span class="tab-icon">&#9881;</span>
              <span>配置字段</span>
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'tools' }"
              @click="switchTab('tools')"
            >
              <span class="tab-icon">&#129522;</span>
              <span>工具绑定</span>
            </button>
          </nav>

          <!-- 基本信息 Tab -->
          <div v-if="activeTab === 'basic'" class="tab-content">
            <div v-if="basicSavedTip" class="success-banner">{{ basicSavedTip }}</div>
            <section class="section-editor">
              <header class="section-header">
                <div class="section-title-wrap">
                  <h4 class="section-title">
                    <span class="section-accent-bar"></span>
                    基本信息
                  </h4>
                  <p class="section-subtitle">编辑智能体的显示名称和描述</p>
                </div>
              </header>
              <div class="form-group">
                <label>显示名称 (display_name) *</label>
                <input
                  v-model="basicForm.display_name"
                  type="text"
                  placeholder="例如：地图智能体"
                />
              </div>
              <div class="form-group">
                <label>描述</label>
                <textarea
                  v-model="basicForm.description"
                  rows="3"
                  placeholder="智能体描述"
                ></textarea>
              </div>
              <div class="basic-form-actions">
                <button
                  class="btn-primary"
                  :disabled="basicSaving"
                  @click="saveBasicInfo"
                >
                  {{ basicSaving ? '保存中...' : '保存修改' }}
                </button>
              </div>
            </section>
          </div><!-- /基本信息 Tab -->

          <!-- 配置字段 Tab -->
          <div v-if="activeTab === 'config'" class="tab-content">
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
            <span class="changes-summary-text">&#9888; 有未保存的修改</span>
            <div>
              <button class="btn-secondary" @click="discardChanges">放弃修改</button>
              <button class="btn-primary" @click="saveAllChanges">保存全部修改</button>
            </div>
          </div>
          </div><!-- /配置字段 Tab -->

          <!-- 工具绑定 Tab -->
          <div v-if="activeTab === 'tools'" class="tab-content">
            <!-- 错误提示 -->
            <div v-if="toolBindingsError" class="error-banner">{{ toolBindingsError }}</div>
            <!-- 保存成功提示 -->
            <div v-if="toolBindingsSavedTip" class="success-banner">{{ toolBindingsSavedTip }}</div>

            <div v-if="isLoadingTools" class="loading">加载工具列表中...</div>
            <div v-else>
              <!-- 工具绑定说明 + 保存按钮 -->
              <div class="tools-toolbar">
                <div class="tools-summary">
                  已勾选 <strong>{{ selectedBindingsCount }}</strong> 个工具
                  <span v-if="hasBindingChanges" class="badge-pending">有未保存的修改</span>
                </div>
                <div class="tools-actions">
                  <button
                    class="btn-primary"
                    :disabled="!hasBindingChanges"
                    @click="saveToolBindings"
                  >
                    保存工具绑定
                  </button>
                </div>
              </div>

              <!-- 按分类分组展示所有可用工具 -->
              <div v-if="groupedTools.length === 0" class="empty-state">
                暂无可用工具
              </div>
              <div v-else class="tools-groups">
                <section
                  v-for="group in groupedTools"
                  :key="group.category"
                  class="tool-group"
                >
                  <div
                    class="tool-group-header"
                    @click="toggleToolGroup(group.category)"
                  >
                    <span
                      class="tool-group-arrow"
                      :class="{ expanded: expandedToolGroups.has(group.category) }"
                    >▶</span>
                    <h5 class="tool-group-title">{{ group.category }}</h5>
                    <span class="tool-group-count">{{ group.tools.length }}</span>
                  </div>
                  <ul v-show="expandedToolGroups.has(group.category)" class="tool-list">
                    <li
                      v-for="tool in group.tools"
                      :key="`${tool.tool_type}:${tool.tool_name}`"
                      class="tool-item"
                    >
                      <label class="tool-checkbox">
                        <input
                          type="checkbox"
                          :checked="isToolSelected(tool.tool_type, tool.tool_name)"
                          @change="toggleToolSelection(tool.tool_type, tool.tool_name)"
                        />
                        <span class="tool-name">{{ tool.display_name }}</span>
                        <span class="tool-type-badge" :class="tool.tool_type">
                          {{ tool.tool_type === 'builtin' ? '内置' : 'MCP' }}
                        </span>
                        <span v-if="!tool.sourceEnabled" class="tool-disabled-hint">
                          （来源已禁用）
                        </span>
                      </label>
                      <p v-if="tool.description" class="tool-desc">{{ tool.description }}</p>
                    </li>
                  </ul>
                </section>
              </div>

              <!-- 底部保存按钮（与顶部一致，方便长列表操作） -->
              <div v-if="hasBindingChanges" class="changes-summary">
                <span>工具绑定有未保存的修改</span>
                <div>
                  <button class="btn-primary" @click="saveToolBindings">保存工具绑定</button>
                </div>
              </div>
            </div>
          </div><!-- /工具绑定 Tab -->
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
            placeholder="小写字母 / 下划线（数字可选），3-50 字符"
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
// SectionEditor 已抽到独立 .vue 文件（src/components/SectionEditor.vue）
// 用模板写法保证 <style scoped> 自动生效（原 h() render function 不会自动加 data-v-xxx）
import SectionEditor from './SectionEditor.vue'

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
  display: flex;
  flex-direction: column;
  gap: 6px;
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
.agent-item .header-actions {
  justify-content: space-between;
  gap: 8px;
  margin-top: 2px;
}
.agent-item .header-actions .switch-label {
  font-size: 12px;
}
.switch-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}

/* section-editor / section-header / fields-table / badge-* 等样式已迁移到
   src/components/SectionEditor.vue（独立 .vue 文件，<style scoped> 自动生效） */

.changes-summary {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  background-color: #fff7e6;
  border: 1px solid #fbbf24;
  border-left: 4px solid #f59e0b;
  border-radius: var(--radius-md);
  margin-top: 16px;
  box-shadow: var(--shadow-lg);
}
.changes-summary-text {
  font-weight: 500;
  color: #92400e;
  font-size: 14px;
}

/* Tab 导航栏 */
.tab-nav {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 20px;
  padding: 0 4px;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  font-size: 13px;
  font-family: inherit;
  background-color: transparent;
  color: var(--color-text-secondary);
  border: none;
  border-bottom: 3px solid transparent;
  border-radius: 8px 8px 0 0;
  cursor: pointer;
  transition: all 0.2s ease;
}
.tab-btn:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-hover);
}
.tab-btn.active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
  font-weight: 600;
  background-color: var(--color-accent-light);
}
.tab-icon {
  font-size: 14px;
  line-height: 1;
}
.tab-content {
  min-height: 200px;
}

/* 基本信息 Tab */
.basic-form-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

/* 工具绑定 Tab */
.success-banner {
  padding: 10px 14px;
  background-color: #ecfdf5;
  color: #059669;
  border: 1px solid #a7f3d0;
  border-radius: 4px;
  font-size: 13px;
  margin-bottom: 12px;
}
.tools-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  margin-bottom: 16px;
}
.tools-summary {
  font-size: 13px;
  color: var(--color-text-secondary);
}
.tools-summary strong {
  color: var(--color-accent);
  font-size: 14px;
}
.badge-pending {
  margin-left: 8px;
  background-color: #fef3c7;
  color: #d97706;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}
.tools-actions {
  display: flex;
  gap: 8px;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tools-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.tool-group {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  overflow: hidden;
}
.tool-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s;
  background-color: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
}
.tool-group-header:hover {
  background-color: var(--color-bg-hover);
}
.tool-group-arrow {
  font-size: 10px;
  color: var(--color-text-muted);
  transition: transform 0.2s;
  display: inline-block;
}
.tool-group-arrow.expanded {
  transform: rotate(90deg);
}
.tool-group-title {
  margin: 0;
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.tool-group-count {
  font-size: 11px;
  color: var(--color-text-muted);
  background-color: var(--color-bg-active);
  padding: 1px 6px;
  border-radius: 999px;
}
.tool-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tool-item {
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border-light);
}
.tool-item:last-child {
  border-bottom: none;
}
.tool-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
}
.tool-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}
.tool-name {
  font-weight: 500;
  color: var(--color-text-primary);
}
.tool-type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.tool-type-badge.builtin {
  background-color: #e0e7ff;
  color: #4338ca;
}
.tool-type-badge.mcp {
  background-color: #dbeafe;
  color: #1d4ed8;
}
.tool-disabled-hint {
  color: var(--color-text-muted);
  font-size: 11px;
}
.tool-desc {
  margin: 4px 0 0 24px;
  font-size: 12px;
  color: var(--color-text-muted);
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