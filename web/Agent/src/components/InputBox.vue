<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { uploadFileInChunks, formatFileSize, getFileExtension, refreshToken, fetchAgentList, deleteAttachments, fetchUploadConfig } from '../utils/api.js'
import ProjectDropdown from './ProjectDropdown.vue'
// 2026-07-14 新增：子智能体快选条组件（常驻在 InputBox 下方）
import SubAgentSuggestionStrip from './SubAgentSuggestionStrip.vue'
import { handleCommand, COMMAND_REGISTRY } from '../utils/commandRegistry.js'
// 2026-07-26 新增：触发器注册表（按字符触发的引用面板；未来加 `@` / `$` 等只需注册条目）
import { TRIGGER_REGISTRY, searchTriggerByChar, buildOverridesFor } from '../utils/triggerRegistry.js'
// 2026-07-26 新增：通用触发面板组件（搜索 + 平铺 + 键盘导航）
import TriggerPanel from './TriggerPanel.vue'

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

const inputValue = ref('')
const textareaRef = ref(null)
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
const showAgentDropdown = ref(false)
const activeAgentIndex = ref(-1)
const agentDropdownRef = ref(null)

// 2026-07-26 新增：触发器状态机（以单字符触发的引用面板，与 "/" 智能体下拉平级）。
// 设计为可扩展：未来加 "@知识库" / "$变量" 等只需在 TRIGGER_REGISTRY 追加条目，
// InputBox 本组件零改动。
//
// selectedTriggers: { [triggerId]: Array<item> } —— 已选中项（以 trigger.id 为键）
// activeTriggerId: 当前打开面板的 trigger id（null = 未打开）
// triggerPanelSearch: 面板搜索词（绑定到 TriggerPanel 输入框）
// activeTriggerIndex: TriggerPanel 当前高亮行索引
// triggerItemsCache: { [triggerId]: Array<item> } —— 各 trigger 数据缓存
// triggerItemsLoading: { [triggerId]: boolean }
// triggerItemsError: { [triggerId]: string }
const selectedTriggers = ref({})
const activeTriggerId = ref(null)
const triggerPanelSearch = ref('')
const activeTriggerIndex = ref(0)
const triggerItemsCache = ref({})
const triggerItemsLoading = ref({})
const triggerItemsError = ref({})

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
 * 平铺的已选 trigger 项（含 trigger id 信息，供 chips 渲染与 buildOverrides 使用）
 * @returns {Array<{trigger: Object, item: Object, key: any}>}
 */
const selectedTriggerChips = computed(() => {
  const result = []
  for (const trigger of TRIGGER_REGISTRY) {
    const items = selectedTriggers.value[trigger.id] || []
    for (const item of items) {
      result.push({
        trigger,
        item,
        key: trigger.itemKey(item),
      })
    }
  }
  return result
})

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

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    const newHeight = Math.max(80, Math.min(textarea.scrollHeight, 200))
    textarea.style.height = newHeight + 'px'
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

/**
 * 2026-07-26 新增：检测光标处的触发字符 + 激活对应面板
 *
 * 词边界规则：触发字符位于行首或前一个字符为空白，避免 C# / 注释符误触发。
 *
 * @param {string} text - 当前 textarea 完整文本
 * @param {number} caret - 当前光标位置（基于 event.target.selectionStart）
 * @returns {Object|undefined} { trigger, query, charIdx } 或 undefined
 */
function detectTriggerAtCaret(text, caret) {
  const c = text.charAt(caret - 1)
  if (!c || !searchTriggerByChar(c)) return undefined
  // 词边界：行首或前一个字符为空格/换行/标点
  const prev = text.charAt(caret - 2)
  if (prev && !/\s/.test(prev)) return undefined
  const trigger = searchTriggerByChar(c)
  const query = text.slice(caret)
  return { trigger, query, charIdx: caret - 1 }
}

/**
 * 2026-07-26 新增：从选中 trigger 项列表移除指定 key 的项
 * @param {string} triggerId - trigger id
 * @param {any} key - 唯一键（trigger.itemKey(item)）
 */
function removeTriggerItem(triggerId, key) {
  const def = TRIGGER_REGISTRY.find((t) => t.id === triggerId)
  if (!def) return
  const list = selectedTriggers.value[triggerId] || []
  selectedTriggers.value = {
    ...selectedTriggers.value,
    [triggerId]: list.filter((item) => def.itemKey(item) !== key),
  }
}

/**
 * 2026-07-26 新增：面板选中项（去重）回调
 * @param {Object|null} item - TriggerPanel 选中项；null 表示 Esc 取消
 */
function onTriggerPanelSelect(item) {
  const def = activeTriggerDef.value
  if (!def) {
    activeTriggerId.value = null
    return
  }
  if (item) {
    const list = selectedTriggers.value[def.id] || []
    const exists = list.some((i) => def.itemKey(i) === def.itemKey(item))
    if (!exists) {
      selectedTriggers.value = {
        ...selectedTriggers.value,
        [def.id]: [...list, item],
      }
    }
    // 选中后关闭面板并清空触发字符串（保留 # 让用户继续添加/不删除）
    activeTriggerId.value = null
    triggerPanelSearch.value = ''
    // 从输入框移除触发字符串及其后的搜索词
    const text = inputValue.value
    const caret = textareaRef.value?.selectionStart ?? text.length
    const detected = detectTriggerAtCaret(text, caret)
    if (detected) {
      const next = text.slice(0, detected.charIdx) + text.slice(caret)
      inputValue.value = next
      nextTick(() => {
        if (textareaRef.value) {
          textareaRef.value.selectionStart = detected.charIdx
          textareaRef.value.selectionEnd = detected.charIdx
          autoResize()
        }
      })
    }
    return
  }
  // null = Esc / 外部取消：关闭面板同时清掉触发字符串
  const text = inputValue.value
  const caret = textareaRef.value?.selectionStart ?? text.length
  const detected = detectTriggerAtCaret(text, caret)
  if (detected) {
    const next = text.slice(0, detected.charIdx) + text.slice(caret)
    inputValue.value = next
    nextTick(() => {
      if (textareaRef.value) {
        textareaRef.value.selectionStart = detected.charIdx
        textareaRef.value.selectionEnd = detected.charIdx
      }
    })
  }
  activeTriggerId.value = null
  triggerPanelSearch.value = ''
}

/**
 * 2026-07-26 新增：处理工具栏 trigger 按钮点击 —— 在光标处插入字符 + 聚焦
 * （与键入同路径：触发 input 事件走 handleInput 统一检测）
 * @param {string} char - trigger 字符
 */
function onTriggerButtonClick(char) {
  const textarea = textareaRef.value
  if (!textarea) return
  const start = textarea.selectionStart ?? inputValue.value.length
  const end = textarea.selectionEnd ?? inputValue.value.length
  const before = inputValue.value.slice(0, start)
  const after = inputValue.value.slice(end)
  // 确保插入位置前是词边界
  const needsSpace = before.length > 0 && !/\s/.test(before.charAt(before.length - 1))
  const insert = (needsSpace ? ' ' : '') + char
  inputValue.value = before + insert + after
  const newCaret = (before + insert).length
  nextTick(() => {
    textarea.focus()
    textarea.selectionStart = newCaret
    textarea.selectionEnd = newCaret
    // 手动派发 input 事件走 handleInput 统一逻辑
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

/**
 * 2026-07-26 新增：监听 sessionId 变化，会话切换 / 新建会话时清空所有 trigger 选择
 */
watch(
  () => props.sessionId,
  () => {
    selectedTriggers.value = {}
    activeTriggerId.value = null
    triggerPanelSearch.value = ''
  }
)

const handleInput = (event) => {
  inputValue.value = event.target.value
  autoResize()
  // 若当前 session 已绑定非 default 智能体，禁止唤起 /command 下拉菜单
  if (props.boundAgentName && props.boundAgentName !== 'default') {
    showAgentDropdown.value = false
    activeAgentIndex.value = -1
    activeTriggerId.value = null
    return
  }
  // 仅输入 "/" 时加载智能体列表并显示下拉菜单
  const trimmed = inputValue.value.trim()
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
  // 2026-07-26 新增：trigger 字符检测（与 "/" 智能体下拉平级）
  const caret = event.target.selectionStart ?? inputValue.value.length
  const detected = detectTriggerAtCaret(inputValue.value, caret)
  if (detected) {
    if (activeTriggerId.value !== detected.trigger.id) {
      activeTriggerId.value = detected.trigger.id
      activeTriggerIndex.value = 0
      loadTriggerItems(detected.trigger.id)
    }
    triggerPanelSearch.value = detected.query
  } else if (activeTriggerId.value) {
    // 触发字符被删掉或失去词边界 → 关闭面板
    activeTriggerId.value = null
    triggerPanelSearch.value = ''
  }
}

/**
 * 选中智能体（从下拉菜单）
 * @param {Object} agent - 智能体对象
 */
function selectAgent(agent) {
  selectedAgent.value = agent
  inputValue.value = ''
  showAgentDropdown.value = false
  activeAgentIndex.value = -1
  nextTick(() => {
    autoResize()
    textareaRef.value?.focus()
  })
}

/**
 * 移除已选中的智能体
 */
function removeSelectedAgent() {
  selectedAgent.value = null
  emit('agent-switched', null)
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

const handleKeydown = (event) => {
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
    inputValue.value = ''
    // 2026-07-26 新增：命令执行后也清空 trigger 选择（命令结果作为新消息发出）
    selectedTriggers.value = {}
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

  // 2026-07-26 新增：把已选 trigger 项经 buildOverrides 转成 context_overrides 片段，
  // 作为第 3 个 emit 参数（extras）传给 App.vue → chatStream。
  const extras = {}
  for (const trigger of TRIGGER_REGISTRY) {
    const items = selectedTriggers.value[trigger.id] || []
    Object.assign(extras, buildOverridesFor(trigger.id, items))
  }

  emit('send', text, uploadedFiles, extras)

  inputValue.value = ''
  selectedFiles.value = []
  selectedAgent.value = null
  // 2026-07-26 新增：清空所有 trigger 选择（per-message 携带，发送后即清空）
  selectedTriggers.value = {}

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

          <!-- 2026-07-26 新增：trigger 引用 chips（与 selected-agent-tag 平级，可移除）。
               由 TRIGGER_REGISTRY 驱动渲染；每条 chip 显示 trigger.char 前缀 + item.chipLabel。 -->
          <div
            v-for="chip in selectedTriggerChips"
            :key="`${chip.trigger.id}:${chip.key}`"
            class="selected-trigger-chip"
            :data-testid="`selected-trigger-chip-${chip.trigger.id}-${chip.key}`"
          >
            <span class="trigger-char">{{ chip.trigger.char }}</span>
            <span class="trigger-chip-label">{{ chip.trigger.chipLabel(chip.item) }}</span>
            <button
              class="trigger-chip-remove-btn"
              :title="`移除 ${chip.trigger.chipLabel(chip.item)}`"
              @click="removeTriggerItem(chip.trigger.id, chip.key)"
            >×</button>
          </div>

          <textarea
            ref="textareaRef"
            v-model="inputValue"
            class="text-input"
            :placeholder="selectedAgent ? '请输入消息，按「Enter」发送' : (boundAgentName ? `当前智能体：${boundAgentDisplayName || boundAgentName}` : '输入 / 快速使用智能体')"
            rows="3"
            @input="handleInput"
            @keydown="handleKeydown"
            @focus="handleFocus"
            @blur="handleBlur"
          ></textarea>
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
  height: 80px;
  min-height: 80px;
  max-height: 200px;
  padding: 8px 0;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: transparent;
  resize: none;
  overflow-y: auto;

  &::placeholder {
    color: var(--color-text-muted);
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

  &:focus {
    outline: none;
    box-shadow: none;
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

/* 2026-07-26 新增：trigger 引用 chips（与 selected-agent-tag 平级，可移除） */
.selected-trigger-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  margin-top: 4px;
  flex-shrink: 0;
}

.trigger-char {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
  color: var(--color-accent);
}

.trigger-chip-label {
  line-height: 1.4;
}

.trigger-chip-remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  margin-left: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  font-size: 16px;
  line-height: 1;
  transition: var(--transition-colors);

  &:hover {
    background-color: rgba(0, 0, 0, 0.08);
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
