<script setup>
import { ref, computed, nextTick, onMounted, watch, getCurrentInstance } from 'vue'
import { uploadFileInChunks, formatFileSize, getFileExtension, refreshToken, fetchAgentList, deleteAttachments, fetchUploadConfig } from '../utils/api.js'
import ProjectDropdown from './ProjectDropdown.vue'
// 2026-07-14 新增：子智能体快选条组件（常驻在 InputBox 下方）
import SubAgentSuggestionStrip from './SubAgentSuggestionStrip.vue'
import { handleCommand, COMMAND_REGISTRY } from '../utils/commandRegistry.js'
// 2026-07-26 新增：触发器注册表（按字符触发的引用面板；未来加 `@` / `$` 等只需注册条目）
import { TRIGGER_REGISTRY, searchTriggerByChar, buildOverridesFor } from '../utils/triggerRegistry.js'
// 2026-07-26 新增：通用触发面板组件（搜索 + 平铺 + 键盘导航）
import TriggerPanel from './TriggerPanel.vue'
// 2026-07-27 新增：contenteditable 编辑器 DOM 工具（序列化服务器 mention、定位光标、替换触发串）
import {
  serializeEditor,
  getTextBeforeCaret,
  replaceTriggerRangeWithServerChip,
  setCaretAfter,
} from '../utils/inputEditor.js'

const SUPPORTED_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'json']
// 2026-07-13 修改：原硬编码 50MB 改为由后端 /api/core/upload-config 动态下发，默认 3MB
const DEFAULT_MAX_FILE_SIZE_MB = 3
const maxFileSizeBytes = ref(DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024)

const props = defineProps({
  sessionId: {
    type: String,
    default: ''
  },
  isStreaming: {
    type: Boolean,
    default: false
  },
  boundAgentName: {
    type: String,
    default: ''
  },
  boundAgentDisplayName: {
    type: String,
    default: ''
  },
  // 2026-06-30 新增：当前会话关联的项目
  currentProject: {
    type: Object,
    default: null
  },
  // 2026-07-01 新增：项目是否锁定（已发送过消息或历史会话时为 true）
  projectLocked: {
    type: Boolean,
    default: false
  },
  // 2026-07-01 新增：当前用户允许使用的智能体名称列表
  allowedAgents: {
    type: Array,
    default: () => []
  },
  // 2026-07-24 新增：当前用户是否为 admin 角色。
  // 用途：admin 走全量智能体（绕过 allowedAgents 过滤，配合 _compute_allowed_agents 服务端旁路）。
  // 普通用户按 allowedAgents 过滤，受 user_agent_acl ACL 控制。
  isAdmin: {
    type: Boolean,
    default: false
  },
  // 2026-07-06 新增：停止按钮是否处于「中断待生效」状态。
  // 当用户在工具/子智能体执行期间点击停止按钮后置 true，
  // 期间按钮保持 stop-mode 样式 + 右上角旋转 badge + disabled 拦截重复点击，
  // 直到后端完成 tools 节点（toolStopPending 由父组件 App.vue/KnowledgeApp.vue 维护）。
  isStopPending: {
    type: Boolean,
    default: false
  },
  // 2026-07-XX 新增：父组件注入的"确保 session 存在"异步回调。
  // InputBox 不直接 import createNewSession（保持与 KnowledgeApp 等宿主解耦），
  // 在 startUpload() 首调上传前调用，避免文件落到后端 middleware 的 'default' 公共目录。
  // 类型签名：接受 projectId（number|null）并返回 Promise<string>（新 session_id）。
  ensureSession: {
    type: Function,
    default: null
  }
})

// 2026-07-27 改造：输入区由 textarea 切换为 contenteditable，正文可与原子服务器 Chip 混排。
// inputValue 改为只读派生，从 editorRef 序列化得到，避免双向数据流与 DOM 状态脱节。
const inputValue = ref('')
const editorRef = ref(null)
const editorSnapshotsBySession = ref({})
const fileInputRef = ref(null)
const isFocused = ref(false)
const isDragging = ref(false)
const isRefreshingToken = ref(false)
// 命令执行中标记：防止命令执行期间用户重复点击发送按钮导致重复触发
const isExecutingCommand = ref(false)
// 发送时上传文件标记：防止上传期间重复点击发送
const isUploading = ref(false)
const selectedFiles = ref([])

// 2026-06-24 新增：智能体快速选择相关状态
const agentList = ref([])
const isLoadingAgents = ref(false)
const selectedAgent = ref(null)

// 2026-07-29 新增：输入框 placeholder 文案统一在此生成。
// 三档分支：已选智能体 / 已绑定智能体 / 空载；空载场景末尾追加 "# 快捷添加引用" 提示
// 让用户在不点击工具栏按钮的情况下也能感知 "#" 可触发服务器引用面板。
// 未来若新增触发字符（如 @知识库），只需在此处追加提示文案。
const inputPlaceholder = computed(() => {
  if (selectedAgent.value) return '请输入消息，按「Enter」发送'
  if (props.boundAgentName) {
    return `当前智能体：${props.boundAgentDisplayName || props.boundAgentName}`
  }
  return '输入 / 快速使用智能体 · 输入 # 快捷添加引用'
})
const showAgentDropdown = ref(false)
const activeAgentIndex = ref(-1)
const agentDropdownRef = ref(null)

// 2026-07-26 新增：触发器状态机（以单字符触发的引用面板，与 "/" 智能体下拉平级）。
// 设计为可扩展：未来加 "@知识库" / "$变量" 等只需在 TRIGGER_REGISTRY 追加条目，
// InputBox 本组件零改动。
//
// triggerSelectionsBySession: { [sessionId]: { [triggerId]: Array<item> } }
// 按会话持久化 trigger 选择，切换/新建 session 时自动隔离。
// selectedTriggers: 当前 session 的已选中项（以 trigger.id 为键）
// activeTriggerId: 当前打开面板的 trigger id（null = 未打开）
// triggerPanelSearch: 面板搜索词（绑定到 TriggerPanel 输入框）
// activeTriggerIndex: TriggerPanel 当前高亮行索引
// triggerItemsCache: { [triggerId]: Array<item> } —— 各 trigger 数据缓存
// triggerItemsLoading: { [triggerId]: boolean }
// triggerItemsError: { [triggerId]: string }
const triggerSelectionsBySession = ref({})
const activeTriggerId = ref(null)
const triggerPanelSearch = ref('')
const activeTriggerIndex = ref(0)
const triggerItemsCache = ref({})
const triggerItemsLoading = ref({})
const triggerItemsError = ref({})
const triggerRange = ref(null)

/**
 * 当前 sessionId（空字符串兜底为 _default，避免 key 为空）
 * @returns {string}
 */
const currentTriggerSessionId = computed(() => props.sessionId || '_default')

/**
 * 当前 session 的 trigger 选择对象
 * @returns {Object} { [triggerId]: Array<item> }
 */
const selectedTriggers = computed(() =>
  triggerSelectionsBySession.value[currentTriggerSessionId.value] || {}
)

/**
 * 设置当前 session 的 trigger 选择对象
 * @param {Object|Function} next - 新值或接收旧值的函数
 */
function setCurrentSessionTriggers(next) {
  const sid = currentTriggerSessionId.value
  const prev = triggerSelectionsBySession.value[sid] || {}
  triggerSelectionsBySession.value = {
    ...triggerSelectionsBySession.value,
    [sid]: typeof next === 'function' ? next(prev) : next,
  }
}

/**
 * 当前激活 trigger 的注册条目（计算属性）
 * @returns {Object|undefined} activeTriggerId 对应的 TRIGGER_REGISTRY 条目；无激活时 undefined
 */
const activeTriggerDef = computed(() =>
  activeTriggerId.value ? TRIGGER_REGISTRY.find((t) => t.id === activeTriggerId.value) : undefined
)

/**
 * 当前激活 trigger 的候选列表（已加载）
 * @returns {Array} 候选项数组；无激活时返回空数组
 */
const activeTriggerItems = computed(() => {
  const id = activeTriggerId.value
  if (!id) return []
  return triggerItemsCache.value[id] || []
})

/**
 * 当前激活 trigger 的加载状态
 * @returns {boolean} 是否正在加载
 */
const activeTriggerLoading = computed(() =>
  activeTriggerId.value ? !!triggerItemsLoading.value[activeTriggerId.value] : false
)

/**
 * 当前激活 trigger 的错误状态
 * @returns {string} 错误文本；无错误返回空串
 */
const activeTriggerError = computed(() =>
  activeTriggerId.value ? triggerItemsError.value[activeTriggerId.value] || '' : ''
)

/**
 * 当前激活 trigger 的搜索键集合
 * @returns {Array<string>} 搜索字段名
 */
const activeTriggerSearchKeys = computed(() => activeTriggerDef.value?.searchKeys || [])

/**
 * 当前激活 trigger 的 getItemKey 函数（用于列表渲染 key）
 * @returns {Function} 取 item 唯一键的函数
 */
const activeTriggerGetItemKey = computed(() => activeTriggerDef.value?.itemKey || ((item) => item))

/**
 * 当前激活 trigger 的 getItemLabel 函数
 * @returns {Function} 取 item 显示文本的函数
 */
const activeTriggerGetItemLabel = computed(() => activeTriggerDef.value?.chipLabel || ((item) => String(item)))

/**
 * TriggerPanel 的副标签函数（显示 server_type 等附加信息）
 * @returns {Function} 取 item 副标签的函数；无则返回空函数
 */
const activeTriggerGetItemSubLabel = computed(() => {
  const def = activeTriggerDef.value
  if (!def) return () => ''
  if (def.id === 'server') {
    return (item) => item?.server_type ? `[${item.server_type}]` : ''
  }
  return () => ''
})

/**
 * 2026-07-27 改造：上方集中 chip 渲染区已移除，触发器选择只通过编辑器 DOM 维护。
 * 保留 selectedTriggers（按 session 隔离）以兼容非服务器类 trigger 的 buildOverrides 调用。
 */

const canSend = computed(() => {
  if (props.isStreaming) return false
  // 2026-07-06 新增：中断待生效期间禁用发送按钮，避免用户在等待工具完成时
  // 重复点击导致状态混乱或产生孤儿 tool_calls（2013 错误根因）。
  if (props.isStopPending) return false
  if (isRefreshingToken.value) return false
  if (isExecutingCommand.value) return false
  // 2026-07-07 新增：发送时上传文件期间禁用发送按钮，避免重复触发上传与发送流程
  if (isUploading.value) return false
  const hasText = inputValue.value.trim().length > 0
  return hasText
})

// 2026-07-07 新增：是否存在已选中的文件（含待上传、上传中、已上传、失败）。
// 用于向上游同步项目选择器锁定状态：只要用户已选择文件，即使尚未发送，
// 也应禁止切换项目，避免文件在发送时被挂接到错误的 projectId。
const hasSelectedFiles = computed(() => selectedFiles.value.length > 0)

/**
 * 是否为命令输入（以 / 开头，且未通过下拉菜单选中智能体）
 * @returns {boolean} 当前输入是否为斜杠命令
 */
const isCommand = computed(() => {
  if (props.boundAgentName && props.boundAgentName !== 'default') return false
  const trimmed = inputValue.value.trim()
  return trimmed.startsWith('/') && !selectedAgent.value
})

/**
 * 解析当前命令输入
 * 复用单一解析逻辑，避免 commandHint 与 handleSend 中重复解析命令字符串。
 * @returns {{cmd: string, args: string[]} | null} 命令对象（含命令名与参数数组）；非命令输入返回 null
 */
const parsedCommand = computed(() => {
  if (!isCommand.value) return null
  const parts = inputValue.value.trim().slice(1).split(/\s+/)
  return { cmd: parts[0], args: parts.slice(1) }
})

/**
 * 命令提示文本
 * 根据输入内容匹配 COMMAND_REGISTRY 中的命令定义，返回描述与用法提示。
 * @returns {string} 命令提示文本；非命令输入或仅输入 "/" 时返回空字符串
 */
const commandHint = computed(() => {
  const parsed = parsedCommand.value
  if (!parsed) return ''
  // 仅输入 "/" 时不显示命令提示，由下拉菜单替代
  if (parsed.cmd === '') return ''
  const reg = COMMAND_REGISTRY.find((r) => r.name === parsed.cmd)
  return reg ? `命令：${reg.description}（用法：${reg.usage}）` : `未知命令：/${parsed.cmd}`
})

/**
 * 同步 inputValue 为编辑器当前 DOM 的纯文本。
 * 用于 canSend / 命令分支 / 触发检测等读取文本的派生逻辑。
 */
function syncEditorState() {
  const { text } = serializeEditor(editorRef.value)
  inputValue.value = text
}

const autoResize = () => {
  const editor = editorRef.value
  if (editor) {
    editor.style.height = 'auto'
    const newHeight = Math.max(80, Math.min(editor.scrollHeight, 200))
    editor.style.height = newHeight + 'px'
  }
}

/**
 * 加载可用智能体列表（供下拉菜单使用）
 */
async function loadAgents() {
  if (agentList.value.length > 0 || isLoadingAgents.value) return
  isLoadingAgents.value = true
  try {
    const agents = await fetchAgentList()
    agentList.value = agents || []
  } catch (err) {
    console.error('加载智能体列表失败:', err)
    agentList.value = []
  } finally {
    isLoadingAgents.value = false
  }
}

// 页面加载时自动获取智能体列表，确保用户输入 "/" 时列表已就绪
onMounted(() => {
  loadAgents()
  // 2026-07-13 新增：拉取后端下发的最大文件大小（失败时保留默认 3MB）
  fetchUploadConfig()
    .then((cfg) => {
      const mb = Number(cfg?.max_file_size_mb)
      if (mb && mb > 0) {
        maxFileSizeBytes.value = mb * 1024 * 1024
      }
    })
    .catch((err) => {
      console.warn('[InputBox] 获取上传配置失败，使用默认 3MB：', err)
    })
})

/**
 * 过滤后的智能体列表（当输入 "/" 后，可继续输入字符进行过滤）
 * 2026-07-24 改造：按角色分流
 * - admin：全量智能体（绕过 allowedAgents 过滤）
 * - 普通用户：按 allowedAgents（来自后端 user_agent_acl）过滤
 */
const filteredAgents = computed(() => {
  // admin 走全量；普通用户按 allowedAgents 过滤
  const sourceNames = props.isAdmin
    ? agentList.value.map((a) => a.name)
    : (props.allowedAgents || [])
  if (!sourceNames.length) return []
  const allowedSet = new Set(sourceNames)
  const allowedOnly = agentList.value.filter((a) => allowedSet.has(a.name))

  const trimmed = inputValue.value.trim()
  if (trimmed === '/') return allowedOnly
  if (!trimmed.startsWith('/')) return []
  const query = trimmed.slice(1).toLowerCase()
  return allowedOnly.filter(
    (a) =>
      a.name.toLowerCase().includes(query) ||
      (a.display_name && a.display_name.toLowerCase().includes(query))
  )
})

// 2026-07-14 新增：常驻子智能体快选条所需的智能体列表。
// 与 filteredAgents 不同，它不依赖 trim 后的输入字符，
// 仅受 allowedAgents 与 agentList 加载状态约束。
// 父组件 ProjectDropdown 同级，在 !projectLocked 时挂载 SubAgentSuggestionStrip 消费。
// 2026-07-24 改造：admin 走全量。
const suggestionAgents = computed(() => {
  const sourceNames = props.isAdmin
    ? agentList.value.map((a) => a.name)
    : (props.allowedAgents || [])
  if (!sourceNames.length) return []
  const allowedSet = new Set(sourceNames)
  return agentList.value.filter((a) => allowedSet.has(a.name))
})

/**
 * 2026-07-26 新增：加载指定 trigger 的候选列表（含缓存）
 *
 * @param {string} triggerId - 注册 id
 * @returns {Promise<void>}
 */
async function loadTriggerItems(triggerId) {
  const def = TRIGGER_REGISTRY.find((t) => t.id === triggerId)
  if (!def) return
  if (triggerItemsCache.value[triggerId]) return
  if (triggerItemsLoading.value[triggerId]) return
  triggerItemsLoading.value = { ...triggerItemsLoading.value, [triggerId]: true }
  triggerItemsError.value = { ...triggerItemsError.value, [triggerId]: '' }
  try {
    const items = await def.fetchItems()
    triggerItemsCache.value = { ...triggerItemsCache.value, [triggerId]: items || [] }
  } catch (err) {
    console.error(`[InputBox] 加载 trigger[${triggerId}] 候选项失败:`, err)
    triggerItemsError.value = {
      ...triggerItemsError.value,
      [triggerId]: err?.message || '加载失败',
    }
  } finally {
    triggerItemsLoading.value = { ...triggerItemsLoading.value, [triggerId]: false }
  }
}

function detectEditorTriggerAtCaret() {
  const root = editorRef.value
  const selection = window.getSelection()
  const before = getTextBeforeCaret(root, selection)
  if (!before) return undefined
  const node = before.range.startContainer
  if (node.nodeType !== Node.TEXT_NODE) return undefined
  const prefix = node.textContent.slice(0, before.range.startOffset)
  const charIdx = prefix.lastIndexOf('#')
  if (charIdx < 0) return undefined
  const prev = prefix.charAt(charIdx - 1)
  if (prev && !/\s/.test(prev)) return undefined
  const trigger = searchTriggerByChar('#')
  if (!trigger) return undefined
  // 搜索词边界：到第一个空白为止，避免用户在搜索串后又输入其他字符时把空白一并吞掉。
  const query = prefix.slice(charIdx + 1).replace(/\s+$/, '')
  const range = document.createRange()
  range.setStart(node, charIdx)
  range.setEnd(node, charIdx + 1 + query.length)
  return { trigger, query, range }
}

/**
 * 2026-07-27 改造：行内 chip 通过 removeInlineChip 直接操作 DOM；不再需要独立 removeTriggerItem。
 * 保留函数便于兼容旧的 selectedTriggerChips 调用点（已删除模板引用）。
 */
function removeTriggerItem(triggerId, key) {
  const def = TRIGGER_REGISTRY.find((t) => t.id === triggerId)
  if (!def) return
  setCurrentSessionTriggers((prev) => {
    const list = prev[triggerId] || []
    return {
      ...prev,
      [triggerId]: list.filter((item) => def.itemKey(item) !== key),
    }
  })
}

/**
 * 当前组件 SFC scoped CSS 的 scopeId（形如 data-v-xxxxxxxx）。
 * 通过 document.createElement 直接创建的子节点不会自动带 scopeId，
 * 会导致 scoped 选择器全部不匹配；这里在节点创建时显式注入。
 */
const chipScopeId = (() => {
  const scopeId = getCurrentInstance()?.vnode?.scopeId
  return scopeId || ''
})()

function createServerChip(item) {
  const chip = document.createElement('span')
  chip.className = 'selected-trigger-chip inline-trigger-chip'
  chip.contentEditable = 'false'
  chip.dataset.triggerId = 'server'
  chip.dataset.businessName = item?.business_name || ''
  chip.dataset.serverType = item?.server_type || ''
  chip.setAttribute('data-testid', `inline-trigger-chip-server-${item?.business_name || ''}`)
  // 注入 scoped CSS scopeId，让 .inline-trigger-chip 等样式命中 DOM 创建的节点
  if (chipScopeId) chip.setAttribute(chipScopeId, '')

  const char = document.createElement('span')
  char.className = 'trigger-char'
  char.textContent = '#'
  const label = document.createElement('span')
  label.className = 'trigger-chip-label'
  label.textContent = item?.business_name || ''
  const removeButton = document.createElement('button')
  removeButton.className = 'trigger-chip-remove-btn'
  removeButton.type = 'button'
  removeButton.title = `移除 ${item?.business_name || ''}`
  removeButton.textContent = '×'
  // 同样的 scopeId 注入，避免 chip 内部子元素无法命中样式
  if (chipScopeId) {
    char.setAttribute(chipScopeId, '')
    label.setAttribute(chipScopeId, '')
    removeButton.setAttribute(chipScopeId, '')
  }
  removeButton.addEventListener('mousedown', (event) => event.preventDefault())
  removeButton.addEventListener('click', (event) => {
    event.preventDefault()
    event.stopPropagation()
    removeInlineChip(chip)
  })
  chip.append(char, label, removeButton)
  return chip
}

/**
 * 删除正文中的服务器 Chip，并同步输入状态。
 * @param {HTMLElement} chip - 要删除的服务器 Chip
 * @returns {void}
 */
function removeInlineChip(chip) {
  const parent = chip?.parentNode
  if (!parent) return
  const offset = Array.prototype.indexOf.call(parent.childNodes, chip)
  parent.removeChild(chip)
  const range = document.createRange()
  range.setStart(parent, Math.max(0, offset))
  range.collapse(true)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)
  syncEditorState()
  editorRef.value?.focus()
}

function onTriggerPanelSelect(item) {
  const def = activeTriggerDef.value
  const root = editorRef.value
  if (!def || !root) {
    activeTriggerId.value = null
    return
  }
  if (item && def.id === 'server' && triggerRange.value) {
    replaceTriggerRangeWithServerChip({
      root,
      range: triggerRange.value,
      charIndex: triggerRange.value.startOffset,
      server: item,
      createChip: createServerChip,
    })
    syncEditorState()
  } else if (!item && triggerRange.value) {
    const range = triggerRange.value
    range.deleteContents()
    setCaretAfter(range.startContainer)
    syncEditorState()
  }
  triggerRange.value = null
  activeTriggerId.value = null
  triggerPanelSearch.value = ''
  nextTick(() => {
    editorRef.value?.focus()
    autoResize()
  })
}

/**
 * 在当前选区插入触发字符并重新触发面板检测。
 * @param {string} char - 触发字符
 * @returns {void}
 */
function onTriggerButtonClick(char) {
  const root = editorRef.value
  if (!root) return
  const selection = window.getSelection()
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null
  const targetRange = range && root.contains(range.startContainer) ? range.cloneRange() : document.createRange()
  if (!range || !root.contains(range.startContainer)) {
    targetRange.selectNodeContents(root)
    targetRange.collapse(false)
  }
  const beforeText = targetRange.startContainer.nodeType === Node.TEXT_NODE
    ? targetRange.startContainer.textContent.slice(0, targetRange.startOffset)
    : ''
  const needsSpace = beforeText && !/\s/.test(beforeText.slice(-1))
  targetRange.deleteContents()
  const textNode = document.createTextNode((needsSpace ? ' ' : '') + char)
  targetRange.insertNode(textNode)
  const caretRange = document.createRange()
  caretRange.setStart(textNode, textNode.textContent.length)
  caretRange.collapse(true)
  selection.removeAllRanges()
  selection.addRange(caretRange)
  root.focus()
  root.dispatchEvent(new Event('input', { bubbles: true }))
}


/**
 * 2026-07-27 改造：监听 sessionId 变化时，按 session 隔离触发器选择并保存 / 恢复编辑器快照。
 * 新 session 无记录时初始化为空对象与空快照；切回旧 session 时恢复其编辑器 DOM。
 */
function snapshotEditorForSession(sid) {
  const root = editorRef.value
  if (!root) return
  editorSnapshotsBySession.value = {
    ...editorSnapshotsBySession.value,
    [sid || '_default']: root.innerHTML,
  }
}

function restoreEditorForSession(sid) {
  const root = editorRef.value
  if (!root) return
  const snapshot = editorSnapshotsBySession.value[sid]
  const html = typeof snapshot === 'string' ? snapshot : ''
  // 只允许恢复由本组件生成的白名单 DOM；过滤任意 HTML 输入以防 XSS。
  root.innerHTML = sanitizeEditorHtml(html)
  triggerRange.value = null
  activeTriggerId.value = null
  triggerPanelSearch.value = ''
  syncEditorState()
  nextTick(() => autoResize())
}

function sanitizeEditorHtml(html) {
  if (!html) return ''
  const template = document.createElement('template')
  template.innerHTML = html
  const allowedTags = new Set(['SPAN', 'BR', 'BUTTON'])
  const allowedAttrs = new Set([
    'data-trigger-id', 'data-business-name', 'data-server-type',
    'data-mention-class', 'class', 'title', 'contenteditable'
  ])
  // 危险属性黑名单:event handler / 表单行为 / srcdoc
  const dangerousAttrs = /^(on\w+|formaction|srcdoc|action)$/i
  // 危险 URL 协议(用于 href/src)
  const dangerousUrl = /^\s*(javascript|data|vbscript|file):/i

  const walk = (node) => {
    const children = Array.from(node.childNodes)
    for (const child of children) {
      if (child.nodeType === Node.TEXT_NODE) continue
      if (child.nodeType !== Node.ELEMENT_NODE) {
        child.remove()
        continue
      }
      const tag = child.tagName
      const isServerChip = tag === 'SPAN' && child.dataset?.triggerId === 'server'
      const isAllowed = allowedTags.has(tag) || isServerChip
      if (!isAllowed) {
        // 不在白名单：剥掉外壳，保留其内部文本
        const fragment = document.createDocumentFragment()
        while (child.firstChild) fragment.appendChild(child.firstChild)
        child.replaceWith(fragment)
        continue
      }
      // 2026-08-07 新增：过滤属性,防 onerror 等事件处理器 / javascript: URL 复活
      for (const attr of Array.from(child.attributes)) {
        if (dangerousAttrs.test(attr.name)) {
          child.removeAttribute(attr.name)
          continue
        }
        if ((attr.name === 'href' || attr.name === 'src') && dangerousUrl.test(attr.value)) {
          child.removeAttribute(attr.name)
          continue
        }
        if (!allowedAttrs.has(attr.name)) {
          child.removeAttribute(attr.name)
        }
      }
      walk(child)
    }
  }
  walk(template.content)
  return template.innerHTML
}

watch(
  () => props.sessionId,
  (newSid, oldSid) => {
    const oldSidKey = oldSid || '_default'
    const sid = newSid || '_default'

    // 2026-07-28 修复：session 切换时清空"待发送的本地态"，
    // 避免前一会话的 selectedAgent / selectedFiles / 下拉菜单残留到新会话输入框，
    // 导致与新会话的 boundAgent 标签同时出现（重复智能体标签）。
    // immediate 阶段 sid === oldSidKey（都为空），不会触发误清空。
    if (sid !== oldSidKey) {
      selectedAgent.value = null
      selectedFiles.value = []
      showAgentDropdown.value = false
      activeAgentIndex.value = -1
      isExecutingCommand.value = false
    }

    snapshotEditorForSession(oldSidKey)
    if (!triggerSelectionsBySession.value[sid]) {
      triggerSelectionsBySession.value = {
        ...triggerSelectionsBySession.value,
        [sid]: {},
      }
    }
    if (sid !== oldSidKey && !(sid in editorSnapshotsBySession.value)) {
      editorSnapshotsBySession.value = {
        ...editorSnapshotsBySession.value,
        [sid]: '',
      }
    }
    // 保持既有的“切回原 session 恢复 chips”语义：
    // - 旧 session 有快照时加载快照；
    // - 旧 session 无快照时（新 session，从未编辑过）保持当前 DOM 不变（即清空）。
    const snapshot = editorSnapshotsBySession.value[sid]
    if (typeof snapshot === 'string') {
      restoreEditorForSession(sid)
    } else {
      // 第一次进入该 session，无快照：保留 watch immediate 阶段已恢复的空 DOM 即可。
      restoreEditorForSession(sid)
    }
  },
  { immediate: true }
)

const handleInput = () => {
  syncEditorState()
  autoResize()

  const trimmed = inputValue.value.trim()

  // 若当前 session 已绑定非 default 智能体，禁止唤起 /command 下拉菜单，
  // 但不应阻止 # 等 trigger 面板的正常触发。
  if (props.boundAgentName && props.boundAgentName !== 'default') {
    showAgentDropdown.value = false
    activeAgentIndex.value = -1
  } else {
    // 仅输入 "/" 时加载智能体列表并显示下拉菜单
    if (trimmed === '/') {
      showAgentDropdown.value = true
      activeAgentIndex.value = -1
      loadAgents()
    } else if (!trimmed.startsWith('/')) {
      showAgentDropdown.value = false
      activeAgentIndex.value = -1
    } else {
      // 输入 "/xxx" 时继续显示下拉菜单（过滤模式）
      showAgentDropdown.value = true
      activeAgentIndex.value = -1
    }
  }

  // 2026-07-27 改造：trigger 字符检测改为基于 contenteditable DOM 与 Selection；
  // 检测到触发串时保存 Range（用于 onTriggerPanelSelect 替换原位）。
  const detected = detectEditorTriggerAtCaret()
  if (detected) {
    triggerRange.value = detected.range
    if (activeTriggerId.value !== detected.trigger.id) {
      activeTriggerId.value = detected.trigger.id
      activeTriggerIndex.value = 0
      loadTriggerItems(detected.trigger.id)
    }
    triggerPanelSearch.value = detected.query
  } else {
    triggerRange.value = null
    if (activeTriggerId.value) {
      // 触发字符被删掉或失去词边界 → 关闭面板
      activeTriggerId.value = null
      triggerPanelSearch.value = ''
    }
  }
}

/**
 * 粘贴处理：仅接受纯文本，避免破坏受控 Chip DOM 与引入 XSS。
 * @param {ClipboardEvent} event - 原生粘贴事件
 */
/**
 * 删除紧邻光标的服务器 Chip。仅处理光标紧贴 Chip 的方向，返回 true 表示已处理。
 */
function handleAdjacentChipDelete(event, root) {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return false
  const range = selection.getRangeAt(0)
  if (!range.collapsed || !root.contains(range.startContainer)) return false
  const node = range.startContainer
  const offset = range.startOffset
  const isBackspace = event.key === 'Backspace'

  // 2026-07-27 修复：先按光标在文本节点内的 offset 判定是否真的"贴边"，
  // 避免在 chip 之后的文本节点中删字时误删 chip。
  // - Backspace：offset===0 时前一个兄弟可能是 chip；offset>0 时光标前是文本字符，不拦截。
  // - Delete    ：offset===textLength 时后一个兄弟可能是 chip；offset<textLength 时不拦截。
  if (node.nodeType === Node.TEXT_NODE) {
    const textLen = (node.textContent || '').length
    if (isBackspace && offset > 0) return false
    if (!isBackspace && offset < textLen) return false
  } else if (node.nodeType !== Node.ELEMENT_NODE) {
    return false
  }

  // 找到光标所在容器的 children
  let container = node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode
  if (!container) return false
  const ownerRoot = container.nodeType === Node.ELEMENT_NODE ? container : root
  const children = ownerRoot.childNodes
  let edgeIndex = -1
  if (node.nodeType === Node.TEXT_NODE) {
    for (let i = 0; i < children.length; i++) {
      if (children[i] === node || children[i].contains?.(node)) {
        edgeIndex = i
        break
      }
    }
  } else {
    // 光标直接定位在 element 级 children[i]，offset 即索引
    edgeIndex = offset
  }
  if (edgeIndex < 0) return false
  const targetIndex = isBackspace ? edgeIndex - 1 : edgeIndex + 1
  const target = children[targetIndex]
  if (!target || target.nodeType !== Node.ELEMENT_NODE || target.dataset?.triggerId !== 'server') {
    return false
  }
  // 仅当"贴边 + 邻接兄弟是 chip"时整块删除 chip
  event.preventDefault()
  ownerRoot.removeChild(target)
  // 删除 chip 后光标定位于原 chip 所在位置（ownerRoot.childNodes 中的 targetIndex）。
  // 不论 Backspace/Delete，光标位置都是「原 chip 占的槽位」，原 chip 之后的兄弟自然前移。
  const newRange = document.createRange()
  newRange.setStart(ownerRoot, Math.max(0, Math.min(targetIndex, ownerRoot.childNodes.length)))
  newRange.collapse(true)
  selection.removeAllRanges()
  selection.addRange(newRange)
  syncEditorState()
  return true
}

function handleEditorPaste(event) {
  event.preventDefault()
  // 2026-08-07 改造：仅取纯文本(text/plain),不解析 text/html,
  // 避免复制富文本时携带 onerror / javascript: 等危险属性。
  // 使用现代 Selection + Range API 实现,不再使用已被废弃的 document.execCommand('insertText')。
  const text = (event.clipboardData || window.clipboardData)?.getData?.('text/plain') || ''
  if (!text) return
  const root = editorRef.value
  if (!root) return
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer)) return
  // 把 \n 转为 <br>，其余字符作为文本节点插入
  const parts = text.split('\n')
  range.deleteContents()
  const fragment = document.createDocumentFragment()
  parts.forEach((part, index) => {
    if (part) fragment.appendChild(document.createTextNode(part))
    if (index < parts.length - 1) fragment.appendChild(document.createElement('br'))
  })
  range.insertNode(fragment)
  // 把光标移动到插入末尾
  const newRange = document.createRange()
  const lastNode = fragment.lastChild
  if (lastNode && lastNode.nodeType === Node.TEXT_NODE) {
    newRange.setStart(lastNode, lastNode.textContent.length)
  } else {
    newRange.setStartAfter(lastNode || range.endContainer)
  }
  newRange.collapse(true)
  selection.removeAllRanges()
  selection.addRange(newRange)
  syncEditorState()
  autoResize()
}

/**
 * 选中智能体（从下拉菜单）
 * @param {Object} agent - 智能体对象
 */
function selectAgent(agent) {
  selectedAgent.value = agent
  if (editorRef.value) editorRef.value.replaceChildren()
  inputValue.value = ''
  showAgentDropdown.value = false
  activeAgentIndex.value = -1
  nextTick(() => {
    autoResize()
    editorRef.value?.focus()
  })
}

/**
 * 移除已选中的智能体
 */
function removeSelectedAgent() {
  selectedAgent.value = null
  emit('agent-switched', null)
  nextTick(() => {
    editorRef.value?.focus()
  })
}

const handleKeydown = (event) => {
  // 2026-07-27 改造：Backspace/Delete 紧邻行内服务器 Chip 时整块删除，
  // 避免光标进入 Chip 内部把原子节点拆散。
  if (event.key === 'Backspace' || event.key === 'Delete') {
    const root = editorRef.value
    if (root && handleAdjacentChipDelete(event, root)) {
      return
    }
  }
  // 2026-07-26 新增：trigger 面板打开时由 TriggerPanel 自身处理键盘（input 内联），
  // 这里只需拦截 Enter 防止穿透触发 handleSend。
  if (activeTriggerId.value) {
    if (event.key === 'Enter' && !event.shiftKey) {
      // TriggerPanel 内联 onKeydown 已处理 Enter → selectItem；不调 handleSend
      return
    }
  }
  // 下拉菜单打开时，支持键盘导航
  if (showAgentDropdown.value && filteredAgents.value.length > 0) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      activeAgentIndex.value = (activeAgentIndex.value + 1) % filteredAgents.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      activeAgentIndex.value =
        (activeAgentIndex.value - 1 + filteredAgents.value.length) % filteredAgents.value.length
      return
    }
    if (event.key === 'Enter' && !event.shiftKey && activeAgentIndex.value >= 0) {
      event.preventDefault()
      selectAgent(filteredAgents.value[activeAgentIndex.value])
      return
    }
    if (event.key === 'Escape') {
      showAgentDropdown.value = false
      activeAgentIndex.value = -1
      return
    }
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

/**
 * 执行斜杠命令
 * 在命令执行期间设置 isExecutingCommand 锁，防止用户重复点击发送；
 * 命令结果通过 send 事件作为系统消息显示，switchAgent 信号通过 agent-switched 事件传递。
 * @param {string} text - 已 trim 的输入文本（以 / 开头）
 * @returns {Promise<void>}
 * @throws {Error} 命令执行失败时通过 emit('send', '命令执行失败：...') 兜底处理，不向上抛出
 */
const executeCommand = async (text) => {
  const parsed = parsedCommand.value
  if (!parsed) return
  const { cmd, args } = parsed
  isExecutingCommand.value = true
  try {
    const result = await handleCommand(cmd, args)
    if (result.switchAgent) {
      // 2026-06-26 改造：若 result.switchAgent 是字符串，包装为对象以兼容 App.vue
      const payload = typeof result.switchAgent === 'string'
        ? { name: result.switchAgent, display_name: result.switchAgent }
        : result.switchAgent
      emit('agent-switched', payload)
    }
    // 命令结果作为系统消息显示（通过 send 事件传递）
    emit('send', result.text, [])
  } catch (err) {
    emit('send', `命令执行失败：${err.message}`, [])
  } finally {
    isExecutingCommand.value = false
    if (editorRef.value) editorRef.value.replaceChildren()
    inputValue.value = ''
    // 2026-07-26 新增：命令执行后也清空当前 session 的 trigger 选择（命令结果作为新消息发出）
    setCurrentSessionTriggers({})
    nextTick(() => {
      autoResize()
    })
  }
}

const handleSend = async () => {
  if (!canSend.value) return

  const text = inputValue.value.trim()
  // 2026-07-07 修正：必须有文本才能发送，禁止纯附件发送。
  if (!text) return

  // 命令检测：以 / 开头视为命令，不走普通发送流程
  if (text.startsWith('/')) {
    await executeCommand(text)
    return
  }

  isRefreshingToken.value = true
  try {
    await refreshToken()
  } catch (err) {
    alert('获取认证信息失败，请稍后重试')
    isRefreshingToken.value = false
    return
  }
  isRefreshingToken.value = false

  // 2026-07-07 改造：上传文件移到发送时统一处理。
  // 仅当存在待上传文件时，才需要在 InputBox 内先创建 session 并挂接 projectId；
  // 纯文本发送仍由 App.vue 负责 session 创建，保持与历史行为一致。
  const pendingFiles = selectedFiles.value.filter(f => f.status === 'pending')
  if (pendingFiles.length > 0) {
    isUploading.value = true
    try {
      const projectIdForUpload = props.currentProject ? props.currentProject.id : null
      if (typeof props.ensureSession === 'function') {
        await props.ensureSession(projectIdForUpload)
      } else {
        throw new Error('会话初始化失败：未提供 ensureSession 回调')
      }

      await Promise.all(pendingFiles.map(f => startUpload(f)))

      const failedFiles = selectedFiles.value.filter(f => f.status === 'error')
      if (failedFiles.length > 0) {
        throw new Error(`以下文件上传失败：${failedFiles.map(f => f.name).join(', ')}`)
      }
    } catch (err) {
      alert(err?.message || '发送失败，请重试')
      isUploading.value = false
      return
    }
  }

  const uploadedFiles = selectedFiles.value
    .filter(f => f.status === 'success')
    .map(f => ({
      file_name: f.uploadResult.filename,
      stored_path: f.uploadResult.stored_path,
      file_type: f.uploadResult.file_type,
      original_name: f.name,
      file_size: f.size
    }))

  // 2026-06-24 新增：若通过下拉菜单选中了智能体，先切换智能体再发送消息
  // 2026-06-26 改造：emit 对象包含 display_name，供 App.vue 同步展示名称
  if (selectedAgent.value) {
    emit('agent-switched', {
      name: selectedAgent.value.name,
      display_name: selectedAgent.value.display_name || selectedAgent.value.name
    })
  }

  // 2026-07-27 改造：发送时直接从编辑器 DOM 序列化。
  // - 文本按 DOM 顺序保留用户输入，服务器 mention 按行内 Chip 位置序列化为内部标记，
  //   不再统一追加到消息最前面。
  // - extras 基于正文中实际存在的服务器 Chip 派生并去重，与后端 DYNAMIC_NODE_REGISTRY 镜像。
  const { text: serializedText, referencedServers } = serializeEditor(editorRef.value)
  const trimmedText = serializedText.trim()
  if (!trimmedText) return
  const extras = {}
  for (const trigger of TRIGGER_REGISTRY) {
    if (trigger.id === 'server') {
      Object.assign(extras, buildOverridesFor('server', referencedServers.map((s) => ({
        business_name: s.name,
        server_type: s.server_type,
      }))))
    } else {
      const items = selectedTriggers.value[trigger.id] || []
      Object.assign(extras, buildOverridesFor(trigger.id, items))
    }
  }

  emit('send', trimmedText, uploadedFiles, extras)

  if (editorRef.value) editorRef.value.replaceChildren()
  inputValue.value = ''
  selectedFiles.value = []
  selectedAgent.value = null
  // 2026-07-26 调整：每轮发送后清空 trigger 选择，避免服务器引用长期驻留输入框，
  // 下轮提问需重新选择。
  setCurrentSessionTriggers({})

  nextTick(() => {
    autoResize()
  })
  isUploading.value = false
}

/**
 * 发送/停止按钮统一点击处理（2026-07-06 新增）。
 *
 * 三态分支：
 *   1. isStopPending=true → 直接返回（按钮 disabled + 灰态 + 旋转 badge，
 *      但保留 click 拦截作为防御性，避免键盘 Enter 等绕过 disabled 的场景）
 *   2. isStreaming=true    → emit('stop')，由父组件 App.vue::handleStopMessage 加锁
 *   3. 其余情况             → handleSend() 走原有发送逻辑
 *
 * 替代原先模板里的内联三元表达式：原表达式在 isStreaming 与 isStopPending 同时
 * 为 true 时会出现「按钮看起来是 stop-mode 但点击会被外层 disabled 拦截」的歧义，
 * 统一收敛到函数里更清晰，也方便测试断言。
 *
 * @returns {void}
 */
const handleSendBtnClick = () => {
  if (props.isStopPending) return
  if (props.isStreaming) {
    emit('stop')
    return
  }
  handleSend()
}

const handleFocus = () => {
  isFocused.value = true
}

const handleBlur = () => {
  isFocused.value = false
  // 延迟关闭下拉菜单，确保点击菜单项的 mousedown 能先触发
  setTimeout(() => {
    showAgentDropdown.value = false
    activeAgentIndex.value = -1
  }, 200)
}

const handleAttachmentClick = () => {
  fileInputRef.value?.click()
}

const handleFileSelect = (event) => {
  const files = Array.from(event.target.files || [])
  addFiles(files)
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

const addFiles = (files) => {
  let hasValidFileAdded = false
  for (const file of files) {
    const ext = getFileExtension(file.name)
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      const fileItem = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`,
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        extension: ext,
        status: 'error',
        progress: 0,
        uploadResult: null,
        errorMsg: `不支持的文件类型: .${ext}，仅支持 ${SUPPORTED_EXTENSIONS.map(e => '.' + e).join(', ')}`,
        cancelFn: null
      }
      selectedFiles.value.push(fileItem)
      continue
    }
    if (file.size > maxFileSizeBytes.value) {
      const fileItem = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`,
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        extension: ext,
        status: 'error',
        progress: 0,
        uploadResult: null,
        errorMsg: `文件大小超过限制（最大 ${formatFileSize(maxFileSizeBytes.value)}）`,
        cancelFn: null
      }
      selectedFiles.value.push(fileItem)
      continue
    }
    const fileItem = {
      id: `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`,
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      extension: ext,
      status: 'pending',
      progress: 0,
      uploadResult: null,
      errorMsg: '',
      cancelFn: null
    }
    selectedFiles.value.push(fileItem)
    hasValidFileAdded = true
  }
  // 2026-07-07 新增：只要有待上传文件被选中，即锁定项目选择器，
  // 防止用户切项目后再发送，导致文件被挂接到错误 projectId。
  if (hasValidFileAdded) {
    emit('project-lock-change', true)
  }
}

const startUpload = (fileItem) => {
  fileItem.status = 'uploading'
  fileItem.progress = 0
  fileItem.errorMsg = ''
  return runChunkUpload(fileItem)
}

/**
 * 实际执行分片上传逻辑（2026-07-XX 抽离）：
 * startUpload() 在确保 session 存在后调用此函数，避免嵌套太多层使逻辑不清。
 * @param {Object} fileItem - selectedFiles 中的文件项
 * @returns {void}
 */
function runChunkUpload(fileItem) {
  return uploadFileInChunks(
    fileItem.file,
    (progress) => {
      const item = selectedFiles.value.find(f => f.id === fileItem.id)
      if (item) item.progress = progress
    },
    (cancelFn) => {
      const item = selectedFiles.value.find(f => f.id === fileItem.id)
      if (item) item.cancelFn = cancelFn
    }
  ).then(result => {
    const item = selectedFiles.value.find(f => f.id === fileItem.id)
    if (item) {
      item.status = 'success'
      item.progress = 100
      item.uploadResult = result.files?.[0] || result
    }
  }).catch(err => {
    const item = selectedFiles.value.find(f => f.id === fileItem.id)
    if (item) {
      if (err.message === '上传已取消') {
        const idx = selectedFiles.value.findIndex(f => f.id === fileItem.id)
        if (idx !== -1) selectedFiles.value.splice(idx, 1)
      } else {
        item.status = 'error'
        item.errorMsg = err.message
      }
    }
  })
}

const removeFile = async (fileItem) => {
  if (fileItem.status === 'uploading' && fileItem.cancelFn) {
    fileItem.cancelFn()
  }

  // 已上传成功的文件需要先删除服务器上的真实文件
  if (fileItem.status === 'success' && fileItem.uploadResult?.stored_path) {
    try {
      await deleteAttachments([fileItem.uploadResult.stored_path])
    } catch (err) {
      console.error('删除附件失败:', err)
      alert(`删除附件失败: ${err.message}`)
      return
    }
  }

  const idx = selectedFiles.value.findIndex(f => f.id === fileItem.id)
  if (idx !== -1) selectedFiles.value.splice(idx, 1)

  // 2026-07-07 修正：当已选文件全部移除后解除项目选择器锁定。
  // 由于项目锁定时机已提前到"文件被选中"时，此处只需在列表为空时解锁。
  if (!hasSelectedFiles.value) {
    emit('project-lock-change', false)
  }
}

const retryUpload = (fileItem) => {
  if (!SUPPORTED_EXTENSIONS.includes(fileItem.extension)) {
    return
  }
  if (fileItem.size > maxFileSizeBytes.value) {
    return
  }
  fileItem.status = 'pending'
  fileItem.errorMsg = ''
  startUpload(fileItem)
}

const handleDragOver = (event) => {
  event.preventDefault()
  isDragging.value = true
}

const handleDragLeave = (event) => {
  event.preventDefault()
  isDragging.value = false
}

const handleDrop = (event) => {
  event.preventDefault()
  isDragging.value = false
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length > 0) {
    addFiles(files)
  }
}

const handleToolAction = (action) => {
  emit('tool-action', action)
}

const getFileIconColor = (ext) => {
  const colorMap = {
    pdf: '#EF4444',
    doc: '#3B82F6', docx: '#3B82F6',
    xls: '#10B981', xlsx: '#10B981', csv: '#10B981',
    jpg: '#8B5CF6', jpeg: '#8B5CF6', png: '#8B5CF6', gif: '#8B5CF6', svg: '#8B5CF6', webp: '#8B5CF6',
    txt: '#6B7280', md: '#6B7280',
    ppt: '#F59E0B', pptx: '#F59E0B',
    zip: '#6B7280', rar: '#6B7280', '7z': '#6B7280',
  }
  return colorMap[ext] || '#9CA3AF'
}

const emit = defineEmits([
  'send',
  'tool-action',
  'stop',
  'agent-switched',
  'project-changed',
  'select-project',
  'create-project',
  'pick-existing',
  // 2026-07-06 新增：向上游报告项目选择器应否锁定
  'project-lock-change'
])
</script>

<template>
  <div class="input-box-container">
    <div class="input-wrapper">
      <div
        class="input-main"
        :class="{ focused: isFocused, dragging: isDragging }"
        @dragover="handleDragOver"
        @dragleave="handleDragLeave"
        @drop="handleDrop"
      >
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.txt,.md,.csv,.json"
          style="display: none"
          @change="handleFileSelect"
        />

        <div v-if="selectedFiles.length > 0" class="file-tags-container">
          <div
            v-for="fileItem in selectedFiles"
            :key="fileItem.id"
            class="file-tag"
            :class="[fileItem.status]"
          >
            <svg
              class="file-type-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
              :style="{ color: getFileIconColor(fileItem.extension) }"
            >
              <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>

            <div class="file-info">
              <span class="file-name" :title="fileItem.name">{{ fileItem.name }}</span>
              <span class="file-size">{{ formatFileSize(fileItem.size) }}</span>
            </div>

            <div v-if="fileItem.status === 'uploading'" class="progress-area">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: fileItem.progress + '%' }"></div>
              </div>
              <span class="progress-text">{{ fileItem.progress }}%</span>
            </div>

            <svg
              v-if="fileItem.status === 'success'"
              class="status-icon success-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
            </svg>

            <svg
              v-if="fileItem.status === 'error' && SUPPORTED_EXTENSIONS.includes(fileItem.extension) && fileItem.size <= maxFileSizeBytes"
              class="status-icon error-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
              @click="retryUpload(fileItem)"
              title="点击重试"
            >
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>

            <svg
              v-if="fileItem.status === 'error' && (!SUPPORTED_EXTENSIONS.includes(fileItem.extension) || fileItem.size > maxFileSizeBytes)"
              class="status-icon error-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
              :title="fileItem.errorMsg"
            >
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>

            <span v-if="fileItem.status === 'error' && fileItem.errorMsg" class="error-msg" :title="fileItem.errorMsg">{{ fileItem.errorMsg }}</span>

            <button class="remove-btn" @click="removeFile(fileItem)" :title="fileItem.status === 'uploading' ? '取消上传' : '移除文件'">
              <svg viewBox="0 0 20 20" fill="currentColor" class="remove-icon">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- 2026-06-24 新增：智能体下拉菜单 -->
        <div
          v-if="showAgentDropdown && isCommand && inputValue.trim() === '/'"
          ref="agentDropdownRef"
          class="agent-dropdown"
        >
          <div v-if="isLoadingAgents" class="agent-dropdown-loading">加载中...</div>
          <div v-else-if="filteredAgents.length === 0" class="agent-dropdown-empty">暂无可用智能体</div>
          <div
            v-for="(agent, index) in filteredAgents"
            :key="agent.name"
            class="agent-dropdown-item"
            :class="{ active: activeAgentIndex === index }"
            @mousedown.prevent="selectAgent(agent)"
            @mouseenter="activeAgentIndex = index"
          >
            <div class="agent-dropdown-name">{{ agent.display_name || agent.name }}</div>
          </div>
        </div>

        <!-- 2026-07-26 新增：trigger 触发面板（与 agent-dropdown 平级）。
             当用户在 textarea 中输入触发字符（如 #）时显示，
             由通用 TriggerPanel 组件渲染（搜索 + 列表 + 键盘导航）。
             data-testid 用于测试断言。 -->
        <TriggerPanel
          v-if="activeTriggerId"
          :trigger-id="activeTriggerId"
          :items="activeTriggerItems"
          :search-keys="activeTriggerSearchKeys"
          :active-index="activeTriggerIndex"
          :loading="activeTriggerLoading"
          :error="activeTriggerError"
          empty-hint="暂无可引用项"
          :search-placeholder="`搜索 ${activeTriggerDef?.title || ''}...`"
          :get-item-key="activeTriggerGetItemKey"
          :get-item-label="activeTriggerGetItemLabel"
          :get-item-sub-label="activeTriggerGetItemSubLabel"
          @select="onTriggerPanelSelect"
          @update:active-index="(v) => (activeTriggerIndex = v)"
        />

        <!-- 新增：输入区域包裹层，将标签与 textarea 并排 -->
        <div class="text-input-area">
          <!-- 2026-06-24 新增：已选智能体标签（可移除） -->
          <div v-if="selectedAgent" class="selected-agent-tag">
            <span class="agent-slash">/</span>
            <span class="agent-name">{{ selectedAgent.display_name || selectedAgent.name }}</span>
            <button class="agent-remove-btn" @click="removeSelectedAgent" title="移除">
              <svg viewBox="0 0 20 20" fill="currentColor" class="agent-remove-icon">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>

          <!-- 2026-06-26 新增：会话已绑定智能体标签（不可移除） -->
          <div v-if="boundAgentName && boundAgentName !== 'default'" class="selected-agent-tag bound-agent-tag">
            <span class="agent-slash">/</span>
            <span class="agent-name">{{ boundAgentDisplayName || boundAgentName }}</span>
          </div>

          <!-- 2026-07-27 改造：服务器引用以行内原子 Chip 形式直接渲染在输入正文中，
               与文本混排；不再使用 textarea 也不在文本框上方集中展示 chip。
               chip 由 onTriggerPanelSelect 通过 createServerChip 写入 DOM。 -->
          <div
            ref="editorRef"
            class="text-input message-editor"
            data-testid="input-editor"
            role="textbox"
            aria-multiline="true"
            :data-placeholder="inputPlaceholder"
            contenteditable="true"
            spellcheck="false"
            @input="handleInput"
            @keydown="handleKeydown"
            @focus="handleFocus"
            @blur="handleBlur"
            @paste="handleEditorPaste"
          ></div>
        </div>

        <div v-if="isCommand && inputValue.trim() !== '/'" class="command-hint">
          {{ commandHint }}
        </div>

        <div class="bottom-row">
          <div class="toolbar">
            <button
              class="tool-btn"
              title="附件"
              @click="handleAttachmentClick"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd"/>
              </svg>
            </button>
            <!-- 2026-07-26 新增：trigger 按钮由 TRIGGER_REGISTRY 驱动渲染；
                 未来新增触发类型只需注册条目，按钮自动出现。
                 点击 = 在光标处插入字符 + 聚焦（与键入同路径走 handleInput）。 -->
            <button
              v-for="trigger in TRIGGER_REGISTRY"
              :key="trigger.id"
              class="tool-btn trigger-tool-btn"
              :title="trigger.title"
              :disabled="props.isStreaming"
              :data-testid="`trigger-btn-${trigger.id}`"
              @click="onTriggerButtonClick(trigger.char)"
            >
              <span class="tool-char">{{ trigger.char }}</span>
            </button>
          </div>

          <button
            class="send-btn"
            :class="{
              'send-mode': !isStreaming && !isStopPending,
              'stop-mode': isStreaming && !isStopPending,
              'stop-pending-mode': isStopPending,
              'disabled': !canSend && !isStreaming && !isStopPending
            }"
            :disabled="!canSend && !isStreaming && !isStopPending"
            :title="isStopPending
              ? '中断中，等待工具完成...'
              : (isStreaming ? '停止生成' : '发送消息')"
            @click="handleSendBtnClick"
          >
            <!-- 发送模式：纸飞机图标 -->
            <svg v-if="!isStreaming && !isStopPending" viewBox="0 0 20 20" fill="currentColor" class="send-icon">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
            </svg>
            <!-- 2026-07-06 新增：中断待生效模式：旋转圆环图标 -->
            <svg v-else-if="isStopPending" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="stop-pending-inner-icon">
              <circle cx="10" cy="10" r="6" stroke-dasharray="20 8" />
            </svg>
            <!-- 停止模式：实心方块图标 -->
            <svg v-else viewBox="0 0 20 20" fill="currentColor" class="stop-icon">
              <rect x="5" y="5" width="10" height="10" rx="1.5" />
            </svg>
            <!-- 2026-07-06 新增：中断待生效右上角旋转 badge，传达"等待工具完成"语义 -->
            <span v-if="isStopPending" class="stop-pending-badge" aria-label="中断中"></span>
          </button>
        </div>
      </div>

      <!-- 2026-07-01 调整：项目下拉框置于 .input-main 外部，
           作为独立浅灰卡片紧跟主卡下方，与主卡形成「主卡 + 次卡」分层结构。 -->
      <div v-if="!projectLocked" class="project-dropdown-slot">
        <ProjectDropdown
          :current-project="currentProject"
          :disabled="isStreaming"
          :locked="projectLocked"
          @select-project="$emit('select-project', $event)"
          @create-project="$emit('create-project')"
          @pick-existing="$emit('pick-existing')"
        />
      </div>

      <!-- 2026-07-14 新增：常驻子智能体快选条。
           仅在 !projectLocked（未发送 / 非历史会话 / 未选待上传文件）时显示。
           选中胶囊 → 复用现有 selectAgent() 路径，把智能体以 /xx 形式注入 InputBox。 -->
      <SubAgentSuggestionStrip
        v-if="!projectLocked"
        :agents="suggestionAgents"
        :disabled="isStreaming"
        @select="selectAgent"
      />
    </div>

    <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
  </div>
</template>

<style scoped>
.input-box-container {
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
  contain: layout style paint;
}

/* 2026-07-01 样式微调：.input-wrapper 保持为透明容器（仅约束宽度与居中），
   视觉外壳由 .input-main 独立承担。 */
.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

/* 2026-07-01 样式微调：.input-main 保留 2px 实色蓝边框与厚重阴影，
   与下方的项目卡形成「主卡 + 独立次卡」的视觉层级。 */
.input-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--color-accent);
  border-radius: var(--radius-lg);
  transition: var(--transition-colors), var(--transition-shadow), border-color 0.25s ease;
  position: relative;
  max-width: 900px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);

  &:hover:not(.focused):not(.dragging) {
    box-shadow: 0 10px 32px rgba(0, 0, 0, 0.16), 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  &.focused {
    box-shadow: 0 10px 32px rgba(99, 102, 241, 0.25), 0 4px 12px rgba(99, 102, 241, 0.15), 0 0 0 4px rgba(99, 102, 241, 0.12);
  }

  &.dragging {
    box-shadow: 0 10px 32px rgba(99, 102, 241, 0.3), 0 4px 12px rgba(99, 102, 241, 0.2), 0 0 0 4px rgba(99, 102, 241, 0.18);
    background-color: var(--color-accent-light);
  }
}

.file-tags-container {
  display: flex;
  flex-direction: row;
  gap: 8px;
  padding: 4px 0;
  overflow-x: auto;
  overflow-y: hidden;
  flex-shrink: 0;

  &::-webkit-scrollbar {
    height: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);
  }

  scrollbar-width: thin;
  scrollbar-color: var(--color-border) transparent;
}

.file-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  min-width: 0;
  transition: var(--transition-colors), border-color 0.2s ease;
  position: relative;

  &.uploading {
    border-color: var(--color-accent);
  }

  &.success {
    border-color: var(--color-success);
  }

  &.error {
    border-color: var(--color-error);
  }
}

.file-type-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.file-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.file-name {
  font-size: 12px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.file-size {
  font-size: 11px;
  color: var(--color-text-muted);
  line-height: 1.2;
}

.progress-area {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 60px;
}

.progress-bar {
  width: 40px;
  height: 3px;
  background-color: var(--color-bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: var(--color-accent);
  border-radius: 2px;
  transition: width 0.2s ease;
}

.progress-text {
  font-size: 11px;
  color: var(--color-accent);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  min-width: 28px;
}

.status-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;

  &.success-icon {
    color: var(--color-success);
  }

  &.error-icon {
    color: var(--color-error);
    cursor: pointer;

    &:hover {
      opacity: 0.8;
    }
  }
}

.error-msg {
  font-size: 10px;
  color: var(--color-error);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

.remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  transition: var(--transition-colors);

  &:hover {
    color: var(--color-error);
    background-color: var(--color-bg-hover);
  }
}

.remove-icon {
  width: 12px;
  height: 12px;
}

.bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 10px;
  background-color: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background-color: var(--color-bg-hover);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover {
    color: var(--color-text-primary);

    &::before {
      opacity: 1;
    }
  }

  &:active:not(:disabled) {
    transform: scale(0.95);
  }

  > * {
    position: relative;
    z-index: 1;
  }

  &.text-btn {
    font-size: var(--font-size-sm);
    font-weight: var(--font-weight-medium);
    padding: 6px 12px;
  }
}

.tool-icon {
  width: 18px;
  height: 18px;
}

.text-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: transparent;
  outline: none;
}

/* 2026-07-27 改造：输入区由 textarea 切换为 contenteditable，保留行高与滚动规则。 */
.message-editor {
  min-height: 80px;
  max-height: 200px;
  padding: 8px 0;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  caret-color: var(--color-accent);

  &:empty::before {
    content: attr(data-placeholder);
    color: var(--color-text-muted);
    pointer-events: none;
  }

  &:focus {
    outline: none;
    box-shadow: none;
  }

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);
  }
}

/* 命令提示样式：以 / 开头输入时显示命令说明 */
.command-hint {
  padding: 6px 8px;
  font-size: var(--font-size-sm);
  color: var(--color-accent);
  background-color: var(--color-accent-light);
  border-radius: var(--radius-sm);
  margin-top: 4px;
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 50%;
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  flex-shrink: 0;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover:not(.disabled) {
    background-color: var(--color-accent-hover);
    transform: scale(1.08);
    box-shadow:
      0 4px 12px rgba(99, 102, 241, 0.3),
      0 2px 4px rgba(99, 102, 241, 0.2);

    &::before {
      opacity: 1;
    }
  }

  &:active:not(.disabled) {
    transform: scale(0.95);
  }

  &.disabled {
    background-color: var(--color-border);
    cursor: not-allowed;
    opacity: var(--opacity-disabled);

    &:hover {
      box-shadow: none;
      transform: none;
    }
  }
}

.send-icon {
  width: 16px;
  height: 16px;
}

/* 2026-06-15 新增：停止模式样式（与发送按钮同色系，通过缩放+阴影脉冲传达「生成中」状态） */
.send-btn.stop-mode {
  background-color: var(--color-accent);  /* 与发送模式同色 */
  cursor: pointer;
  animation: stopPulse 1.2s ease-in-out infinite;
}

.send-btn.stop-mode:hover {
  background-color: var(--color-accent-hover);  /* 与发送模式 hover 同色 */
  transform: scale(1.08);
  box-shadow:
    0 4px 12px rgba(99, 102, 241, 0.3),  /* 与发送模式 hover 同色阴影 */
    0 2px 4px rgba(99, 102, 241, 0.2);
}

.send-btn.stop-mode::before {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%);
}

.stop-icon {
  width: 14px;
  height: 14px;
  color: white;
}

/* 缩放+阴影脉冲动画：背景色不变，仅缩放与阴影扩散传达「生成中」语义 */
@keyframes stopPulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3),
                0 2px 4px rgba(99, 102, 241, 0.2),
                0 0 0 0 rgba(99, 102, 241, 0.4);
  }
  50% {
    transform: scale(1.06);
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3),
                0 2px 4px rgba(99, 102, 241, 0.2),
                0 0 0 8px rgba(99, 102, 241, 0);
  }
}

/* 2026-07-06 新增：中断待生效模式（isStopPending=true 时）
   用户已点击停止按钮，正在等待后端 tools 节点完成 ToolMessage 后真正断开。
   设计要点：
   - 背景色变灰（禁用感），但保留 stop-mode 同色 accent 作为底色，避免与 disabled 完全一致
   - hover 不变（cursor: not-allowed 传达不可交互）
   - 内嵌旋转圆环图标 + 右上角橙色旋转 badge，双重视觉反馈 */
.send-btn.stop-pending-mode {
  background-color: var(--color-text-muted);
  cursor: not-allowed;
  opacity: 0.7;
}

.send-btn.stop-pending-mode:hover {
  background-color: var(--color-text-muted);
  transform: none;
  box-shadow: none;
}

.send-btn.stop-pending-mode::before {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, transparent 100%);
}

.stop-pending-inner-icon {
  width: 16px;
  height: 16px;
  color: white;
  animation: stopPendingSpin 0.9s linear infinite;
}

.stop-pending-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f59e0b;          /* 橙色：与 .stopped_by_user 徽章同色，传达"中断等待中" */
  border: 2px solid var(--color-bg-secondary);
  box-sizing: content-box;
  animation: stopPendingSpin 0.9s linear infinite;
  pointer-events: none;
}

@keyframes stopPendingSpin {
  to {
    transform: rotate(360deg);
  }
}

.disclaimer {
  text-align: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: 12px 0 0;
  line-height: 1.4;
  letter-spacing: 0.01em;
  transition: var(--transition-opacity);

  &:hover {
    color: var(--color-text-secondary);
  }
}

/* 新增：输入区域包裹层，标签与 textarea 并排 */
.text-input-area {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

/* 2026-06-24 新增：已选智能体标签 */
.selected-agent-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background-color: var(--color-accent-light);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  margin-top: 4px;
  flex-shrink: 0;
}

.agent-slash {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
}

.agent-name {
  line-height: 1.4;
}

.agent-remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  margin-left: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-accent);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors);

  &:hover {
    background-color: rgba(99, 102, 241, 0.15);
  }
}

.agent-remove-icon {
  width: 12px;
  height: 12px;
}

/* 2026-06-26 新增：已绑定智能体标签（不可移除） */
.bound-agent-tag {
  background-color: var(--color-bg-tertiary);
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

/* 2026-07-27 改造：trigger 引用 chip 既作为独立标签（已不再使用）
   也作为行内原子 chip 显示在输入框正文中。行内样式由 .inline-trigger-chip 修饰。 */
.selected-trigger-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
  user-select: none;
  transition: var(--transition-colors), box-shadow 0.15s ease;
}

/* 行内原子 chip：与正文文本基线对齐、与文本水平间距 2px、避免被空格截断 */
.selected-trigger-chip.inline-trigger-chip {
  margin: 0 2px;
  padding: 1px 4px 1px 6px;
  vertical-align: baseline;
  white-space: nowrap;
  background-color: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.35);
  color: var(--color-accent);
  line-height: 1.6;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);

  &:hover {
    background-color: rgba(99, 102, 241, 0.14);
    border-color: rgba(99, 102, 241, 0.55);
  }
}

/* `#` 前缀：单独胶囊化、加底色，让 chip 与纯文本区分明显 */
.trigger-char {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: var(--font-weight-bold);
  color: #ffffff;
  background-color: var(--color-accent);
  border-radius: var(--radius-full);
  line-height: 1;
}

.trigger-chip-label {
  line-height: 1.4;
}

.trigger-chip-remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 2px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  color: rgba(15, 23, 42, 0.45);
  border-radius: var(--radius-full);
  font-size: 14px;
  line-height: 1;
  transition: var(--transition-colors);

  &:hover {
    background-color: rgba(239, 68, 68, 0.12);
    color: #b91c1c;
  }
}

/* 2026-07-26 新增：trigger 按钮工具栏样式（registry 驱动，未来多按钮自动适应） */
.trigger-tool-btn {
  font-size: 14px;
  font-weight: var(--font-weight-bold);
}

.tool-char {
  font-size: 14px;
  font-weight: var(--font-weight-bold);
  color: var(--color-text-secondary);
}

/* 2026-06-24 新增：智能体下拉菜单 */
.agent-dropdown {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 240px;
  overflow-y: auto;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);
  margin-bottom: 8px;
  padding: 6px;
  z-index: 10;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-border);
    border-radius: var(--radius-full);
  }
}

.agent-dropdown-loading,
.agent-dropdown-empty {
  padding: 12px 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  text-align: center;
}

.agent-dropdown-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover,
  &.active {
    background-color: var(--color-accent-light);
  }
}

.agent-dropdown-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: 1.4;
}

/* 2026-07-01 样式微调：项目下拉框作为独立浅灰卡片置于 .input-main 外部下方，
   8px 间距，无阴影无边框，圆角与主卡风格一致，
   与上方主卡形成「主卡 + 次卡」视觉层级。 */
.project-dropdown-slot {
  margin-top: 8px;
  display: flex;
  justify-content: flex-start;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  box-shadow: none;
  border: none;
}
</style>
