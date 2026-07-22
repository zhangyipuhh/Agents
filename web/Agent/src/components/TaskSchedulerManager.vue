<script setup>
/**
 * TaskSchedulerManager - 智能体定时任务管理组件（admin）
 *
 * 提供定时任务列表、任务表单、启停、立即运行和执行历史查看能力；
 * 以及「服务器扫描入库」Tab，在该 Tab 中按需拉取 DevOps 服务器脱敏列表并触发扫描。
 *
 * 安全设计：服务器列表只展示白名单字段（id / business_name / server_type / updated_at），
 * 绝不渲染 ip / port / username / password / blacklist / whitelist / 文件路径。
 * 扫描错误信息做脱敏处理：仅展示通用提示，不把后端 detail 透出到页面。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  fetchAdminAgentList,
  fetchTaskSchedules,
  createTaskSchedule,
  updateTaskSchedule,
  deleteTaskSchedule,
  setTaskScheduleEnabled,
  triggerTaskSchedule,
  fetchTaskRuns,
  fetchDevOpsServers,
  scanDevOpsServers,
  deleteDevOpsServer,
  fetchDevOpsServerDetail,  // 2026-07-22 新增：服务器详情（白名单 + 巡检脚本）
  fetchScripts,
  scanScripts,
  fetchEmailPolicies,
  fetchApiConfigTree,
} from '../utils/api.js'
import ApiConfigManager from './ApiConfigManager.vue'

const TAB_TASK = 'task'
const TAB_SCAN = 'scan'
const TAB_SCRIPT = 'script'
const TAB_API = 'api'

const TAB_LABELS = [
  { id: TAB_TASK, label: '编辑任务' },
  { id: TAB_SCAN, label: '服务器扫描入库' },
  { id: TAB_SCRIPT, label: '脚本扫描入库' },
  { id: TAB_API, label: 'API接口配置' },
]

const schedules = ref([])
const agents = ref([])
const runs = ref([])
const historySchedule = ref(null)
const isLoadingRuns = ref(false)
const historyErrorMessage = ref('')
const selectedSchedule = ref(null)
const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const isCreating = ref(false)
const contextJson = ref('{}')

// Tab 状态
const activeTab = ref(TAB_TASK)

// 服务器扫描状态
const devopsServers = ref([])
const isLoadingServers = ref(false)
const isScanning = ref(false)
const scanErrorMessage = ref('')
const listErrorMessage = ref('')
const scanSuccessMessage = ref('')
const scanSummary = ref(null)
const hasLoaded = ref(false)
// 删除状态：当前正在删除的行 id（防重复点击）
const isDeletingRowId = ref(null)

// 详情弹窗状态：白名单 / 巡检脚本
// 单 ref 同时持有 row 与 detail，避免多个 ref 同步问题
const whitelistDialog = ref({ open: false, row: null, detail: null, loading: false, error: '' })
const scriptDialog = ref({ open: false, row: null, detail: null, loading: false, error: '' })

/**
 * 打开白名单详情弹窗：
 * 1) ref 重置（保留 row 用于标题与取消重入）；
 * 2) 调 fetchDevOpsServerDetail 拉详情；
 * 3) 成功写入 detail；失败写入 error（脱敏文案）。
 * 同一时刻仅一个弹窗 open（互斥关闭另一个）。
 * @param {Object} row - 服务器列表行（脱敏 4 字段）
 * @returns {Promise<void>}
 */
async function openWhitelistDialog(row) {
  if (!row || row.id == null) return
  whitelistDialog.value = { open: true, row, detail: null, loading: true, error: '' }
  scriptDialog.value.open = false
  try {
    const detail = await fetchDevOpsServerDetail(row.id)
    whitelistDialog.value = { open: true, row, detail, loading: false, error: '' }
  } catch {
    whitelistDialog.value = {
      open: true, row, detail: null, loading: false,
      error: '白名单加载失败，请稍后重试',
    }
  }
}

/**
 * 打开巡检脚本详情弹窗（保留格式纯文本展示）。
 * @param {Object} row - 服务器列表行（脱敏 4 字段）
 * @returns {Promise<void>}
 */
async function openScriptDialog(row) {
  if (!row || row.id == null) return
  scriptDialog.value = { open: true, row, detail: null, loading: true, error: '' }
  whitelistDialog.value.open = false
  try {
    const detail = await fetchDevOpsServerDetail(row.id)
    scriptDialog.value = { open: true, row, detail, loading: false, error: '' }
  } catch {
    scriptDialog.value = {
      open: true, row, detail: null, loading: false,
      error: '脚本加载失败，请稍后重试',
    }
  }
}

/**
 * 关闭白名单弹窗。
 * @returns {void}
 */
function closeWhitelistDialog() {
  whitelistDialog.value = { ...whitelistDialog.value, open: false }
}

/**
 * 关闭脚本弹窗。
 * @returns {void}
 */
function closeScriptDialog() {
  scriptDialog.value = { ...scriptDialog.value, open: false }
}

// 脚本扫描状态
const scripts = ref([])
const isLoadingScripts = ref(false)
const isScanningScripts = ref(false)
const scriptError = ref('')
const scriptSuccess = ref('')
const scanScriptSummary = ref(null)
const hasLoadedScripts = ref(false)

// 脚本参数 schema-driven 状态：
// scriptParamValues：当前已添加、可编辑的受支持参数值（例如 { server_list: ['业务A'] }）。
// legacyScriptArgs：旧任务中未在 schema 中声明或当前 UI 暂不支持的参数键值；只做无损保留，不通过 UI 编辑。
// serverKeyword：服务器列表搜索词。
// apiKeyword：API 候选列表搜索词。
// 使用 ref({}) 而非 reactive({}) 是因为 Vue 3 在 reactive object 上动态添加 key 时，
// 由 hasOwnProperty 检查构成的 computed 依赖不会被自动追踪；ref 整体替换值时会强制触发依赖更新。
const scriptParamValues = ref({})
const legacyScriptArgs = ref({})
const serverKeyword = ref('')
const apiKeyword = ref('')

// API 接口配置节点状态（api_list 控件候选源），复用 GET /api/admin/api-configs/tree。
// apiNodes 白名单字段：id / parent_id / node_type / name / sort_order。
// hasLoadedApis / isLoadingApis / apiLoadPromise 复刻服务器缓存的契约。
const apiNodes = ref([])
const hasLoadedApis = ref(false)
const isLoadingApis = ref(false)
const apiListErrorMessage = ref('')
let apiLoadPromise = null
const API_NODE_WHITELIST = ['id', 'parent_id', 'node_type', 'name', 'sort_order'] // API节点白名单字段

// 邮件策略状态（仅 script 任务启用邮件通知时按需加载）
const emailPolicies = ref([])
const hasLoadedEmailPolicies = ref(false)
const isLoadingEmailPolicies = ref(false)

// 扫描结果只接受这 4 个数字；任何未知敏感字段都不会进入 DOM
const SUMMARY_FIELDS = ['scanned', 'inserted', 'updated', 'failed']

// 服务器字段白名单：仅显示这些键，绝不显示敏感字段
const SERVER_WHITELIST = ['id', 'business_name', 'server_type', 'updated_at']

// 脚本展示白名单字段：仅显示这些键，绝不显示 func 等内部对象。
// params_schema 由后端返回，驱动前端 schema-aware 参数 UI；前端只识别 x-control=server-multiselect 的参数。
const SCRIPT_PUBLIC_FIELDS = ['name', 'display_name', 'description', 'module_path', 'params_schema']
const SCRIPT_SUMMARY_FIELDS = ['scanned', 'registered', 'failed']

/**
 * 判断一个 schema 属性定义是否为前端受支持的「服务器列表多选」参数。
 * 仅当 key 精确等于 `server_list` 且所有 5 个 schema 约束均满足时返回 true：
 * type=array、items.type=string、x-control=server-multiselect、
 * x-source=devops-servers、x-value-field=business_name。
 * 把 key 纳入判定可避免「同形态、同 x-* 的影子 key（如 target_servers）」
 * 误识别为受支持控件。
 * @param {string} key - schema 属性名
 * @param {unknown} def - schema 中的单个属性定义
 * @returns {boolean} 是否为受支持的 server_list 参数
 */
function isServerListParamDefinition(key, def) {
  if (key !== 'server_list') return false
  if (!def || typeof def !== 'object') return false
  if (def.type !== 'array') return false
  const items = def.items
  if (!items || items.type !== 'string') return false
  return def['x-control'] === 'server-multiselect'
    && def['x-source'] === 'devops-servers'
    && def['x-value-field'] === 'business_name'
}

/**
 * 判断一个 schema 属性定义是否为前端受支持的「API 接口多选」参数。
 * 仅当 key 精确等于 `api_list` 且所有 5 个 schema 约束均满足时返回 true：
 * type=array、items.type=string、x-control=api-multiselect、
 * x-source=api-configs、x-value-field=id。
 * @param {string} key - schema 属性名
 * @param {unknown} def - schema 中的单个属性定义
 * @returns {boolean} 是否为受支持的 api_list 参数
 */
function isApiListParamDefinition(key, def) {
  if (key !== 'api_list') return false
  if (!def || typeof def !== 'object') return false
  if (def.type !== 'array') return false
  const items = def.items
  if (!items || items.type !== 'string') return false
  return def['x-control'] === 'api-multiselect'
    && def['x-source'] === 'api-configs'
    && def['x-value-field'] === 'id'
}

/**
 * 把任意值规整为「非空字符串、按首次出现顺序去重」的列表。
 * 供 server_list 与 api_list 等字符串数组参数共用：去掉非字符串 / null / 空串 /
 * 重复项，避免下游 `Set`、`Array.includes`、JSON 序列化出现 [object Object] /
 * null 等脏数据。
 * 不接受非数组输入（返回空数组），不复制原始数组（已构造新数组）。
 * @param {unknown} value - 原始输入（数组 / 其他类型）
 * @returns {string[]} 规范化后的字符串数组（保持首次出现顺序）
 */
function normalizeStringList(value) {
  if (!Array.isArray(value)) return []
  const out = []
  const seen = new Set()
  for (const item of value) {
    if (typeof item !== 'string' || !item) continue
    if (seen.has(item)) continue
    seen.add(item)
    out.push(item)
  }
  return out
}

/**
 * ``normalizeServerList`` 的兼容别名。
 * 历史测试与代码可能直接引用该名；保留以避免破坏调用方契约。
 */
const normalizeServerList = normalizeStringList

/**
 * 按 schema default 构造参数初值；非数组默认值被回退为对应默认值或 []。
 * @param {unknown} def - schema 属性定义
 * @returns {unknown} 适合作为 script_param 初值的副本
 */
function cloneParamDefault(def) {
  if (!def || typeof def !== 'object') return undefined
  if (Object.prototype.hasOwnProperty.call(def, 'default')) {
    const d = def.default
    if (Array.isArray(d)) return d.slice()
    try {
      return JSON.parse(JSON.stringify(d))
    } catch {
      return d
    }
  }
  if (def.type === 'array') return []
  if (def.type === 'object') return {}
  if (def.type === 'string') return ''
  if (def.type === 'number' || def.type === 'integer') return 0
  if (def.type === 'boolean') return false
  return undefined
}

const form = reactive({
  name: '',
  description: '',
  target_type: 'agent',
  agent_name: '',
  prompt: '',
  script_name: '',
  script_args: {},
  timezone: 'Asia/Shanghai',
  enabled: true,
  context_overrides: {},
  max_concurrent_runs: 1,
  notify_enabled: false,
  notify_policy_id: null,
})

// 预设调度模式类型（每天 / 每周 / 每月 / 每年 / 每隔 N 分钟 / 每隔 N 小时）
const SCHEDULE_TYPES = [
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'yearly', label: '每年' },
  { value: 'interval_minutes', label: '每隔 N 分钟' },
  { value: 'interval_hours', label: '每隔 N 小时' },
]

// 星期映射（cron 0-6，0=周日；APScheduler from_crontab 兼容 0-6）
const WEEKDAYS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
]

// 1-31 日选项
const MONTH_DAYS = Array.from({ length: 31 }, (_, i) => i + 1)
// 1-12 月选项
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
// 0-23 时选项
const HOURS = Array.from({ length: 24 }, (_, i) => i)
// 0-59 分选项
const MINUTES = Array.from({ length: 60 }, (_, i) => i)

// 友好调度配置（提交时由 buildCronExpression 转为 cron_expression）
// 字段统一用字符串存储，避免 v-model.number 在 <select> 上的兼容问题
const scheduleConfig = reactive({
  type: 'daily',            // daily | weekly | monthly | yearly | interval_minutes | interval_hours
  weekday: '1',             // 0-6（仅 weekly 用）
  month: '1',               // 1-12（仅 yearly 用）
  day: '1',                 // 1-31（monthly / yearly 用）
  hour: '9',                // 0-23
  minute: '0',              // 0-59
  interval: '15',           // 仅 interval_minutes / interval_hours 用（分钟 1-59，小时 1-23）
})

/**
 * 把结构化配置转为 5 段 cron 表达式。
 * @param {Object} cfg - scheduleConfig
 * @returns {string} cron 表达式，如 "0 9 * * *"
 */
function buildCronExpression(cfg) {
  const m = parseInt(cfg.minute, 10)
  const h = parseInt(cfg.hour, 10)
  const minute = Number.isNaN(m) ? 0 : m
  const hour = Number.isNaN(h) ? 0 : h
  switch (cfg.type) {
    case 'weekly': {
      const w = parseInt(cfg.weekday, 10)
      return `${minute} ${hour} * * ${Number.isNaN(w) ? 1 : w}`
    }
    case 'monthly': {
      const d = parseInt(cfg.day, 10)
      return `${minute} ${hour} ${Number.isNaN(d) ? 1 : d} * *`
    }
    case 'yearly': {
      const d = parseInt(cfg.day, 10)
      const mon = parseInt(cfg.month, 10)
      return `${minute} ${hour} ${Number.isNaN(d) ? 1 : d} ${Number.isNaN(mon) ? 1 : mon} *`
    }
    case 'interval_minutes': {
      const n = parseInt(cfg.interval, 10)
      const interval = Number.isNaN(n) || n < 1 || n > 59 ? 1 : n
      return `*/${interval} * * * *`
    }
    case 'interval_hours': {
      const n = parseInt(cfg.interval, 10)
      const interval = Number.isNaN(n) || n < 1 || n > 23 ? 1 : n
      return `0 */${interval} * * *`
    }
    case 'daily':
    default:
      return `${minute} ${hour} * * *`
  }
}

/**
 * 把 5 段 cron 表达式反向解析为结构化配置；无法识别时回退为 daily 09:00。
 * @param {string} cron - 5 段 crontab 表达式
 * @returns {Object} scheduleConfig 字段集（字符串值）
 */
function parseCronExpression(cron) {
  const fallback = { type: 'daily', weekday: '1', month: '1', day: '1', hour: '9', minute: '0', interval: '1' }
  const parts = String(cron || '').trim().split(/\s+/)
  if (parts.length !== 5) return fallback
  const [m, h, d, mon, w] = parts

  // 每隔 N 分钟：*/N * * * *
  if (/^\*\/\d+$/.test(m) && h === '*' && d === '*' && mon === '*' && w === '*') {
    return { type: 'interval_minutes', weekday: '1', month: '1', day: '1', hour: '9', minute: '0', interval: m.replace('*/', '') }
  }
  // 每隔 N 小时：0 */N * * *
  if (m === '0' && /^\*\/\d+$/.test(h) && d === '*' && mon === '*' && w === '*') {
    return { type: 'interval_hours', weekday: '1', month: '1', day: '1', hour: '9', minute: '0', interval: h.replace('*/', '') }
  }

  // 任何含 *,/,- 等复杂语法的字段都视为无法识别
  if ([m, h, d, mon, w].some((p) => /[^0-9]/.test(p) && p !== '*')) return fallback
  const minute = parseInt(m, 10)
  const hour = parseInt(h, 10)
  if (Number.isNaN(minute) || Number.isNaN(hour)) return fallback

  const dayIsAny = d === '*'
  const monIsAny = mon === '*'
  const wIsAny = w === '*'

  if (dayIsAny && monIsAny && wIsAny) {
    return { type: 'daily', weekday: '1', month: '1', day: '1', hour: String(hour), minute: String(minute), interval: '1' }
  }
  if (!dayIsAny && monIsAny && wIsAny) {
    return { type: 'monthly', weekday: '1', month: '1', day: d, hour: String(hour), minute: String(minute), interval: '1' }
  }
  if (dayIsAny && monIsAny && !wIsAny) {
    return { type: 'weekly', weekday: w, month: '1', day: '1', hour: String(hour), minute: String(minute), interval: '1' }
  }
  if (!dayIsAny && !monIsAny && wIsAny) {
    return { type: 'yearly', weekday: '1', month: mon, day: d, hour: String(hour), minute: String(minute), interval: '1' }
  }
  return fallback
}

const enabledAgents = computed(() => agents.value.filter((agent) => agent.enabled !== false))

/**
 * 当前所选脚本的注册信息（从 scripts 列表按 name 查找）。
 * @returns {Object|null} 含 params_schema 的脚本对象，未匹配为 null。
 */
const currentScript = computed(() => {
  const name = form.script_name
  if (!name) return null
  return scripts.value.find((s) => s && s.name === name) || null
})

/**
 * 读取当前 scriptParamValues 的内部引用（非副本）。
 * 注意：返回的是 `scriptParamValues.value` 本身，调用方若要修改应通过
 * `writeScriptParamValues` 或先 `{ ...obj }` 浅拷贝再写回，避免破坏 Vue 响应式跟踪。
 * @returns {Object} 当前参数值对象（内部引用）
 */
function readScriptParamValues() {
  return scriptParamValues.value || {}
}

/**
 * 当前脚本 params_schema 中所有受支持的参数定义。
 * 同时识别 server_list 与 api_list 两种受支持控件（新增控件需在此显式枚举）。
 * @returns {Array<{key: string, def: Object}>} 受支持参数定义数组。
 */
const supportedScriptParamDefinitions = computed(() => {
  const script = currentScript.value
  if (!script || !script.params_schema) return []
  const properties = script.params_schema.properties
  if (!properties || typeof properties !== 'object') return []
  const out = []
  for (const key of Object.keys(properties)) {
    const def = properties[key]
    if (isServerListParamDefinition(key, def) || isApiListParamDefinition(key, def)) {
      out.push({ key, def })
    }
  }
  return out
})

/**
 * 当前尚未添加、但可继续添加的参数（用于「添加参数」选择器）。
 * @returns {Array<{key: string, def: Object, label: string}>} 可添加参数列表。
 */
const availableScriptParams = computed(() => {
  const has = Object.prototype.hasOwnProperty
  const values = readScriptParamValues()
  return supportedScriptParamDefinitions.value
    .filter(({ key }) => !has.call(values, key))
    .map(({ key, def }) => ({
      key,
      def,
      label: def.title || key,
    }))
})

/**
 * 当前脚本参数区中已添加参数 key 的稳定列表。
 * @returns {string[]} 当前已添加参数 key（顺序与定义一致）。
 */
const addedScriptParamKeys = computed(() => {
  const has = Object.prototype.hasOwnProperty
  const values = readScriptParamValues()
  return supportedScriptParamDefinitions.value
    .map(({ key }) => key)
    .filter((key) => has.call(values, key))
})

/**
 * 按关键词过滤后的服务器候选列表（仅展示白名单字段后的 devopsServers）。
 * @returns {Array} 过滤后的服务器数组，每项均为 {id, business_name, server_type, updated_at}。
 */
const filteredDevopsServers = computed(() => {
  const kw = serverKeyword.value.trim().toLowerCase()
  const list = Array.isArray(devopsServers.value) ? devopsServers.value : []
  if (!kw) return list
  return list.filter((row) => {
    if (!row) return false
    const name = String(row.business_name || '').toLowerCase()
    const type = String(row.server_type || '').toLowerCase()
    return name.includes(kw) || type.includes(kw)
  })
})

/**
 * 当前已在 scriptParamValues.server_list 中、且仍能在 devopsServers 中匹配到的有效服务器。
 * 仅返回非空字符串业务名 + 仍存在的服务器 row。
 * @returns {Array<{row: Object, name: string}>} 有效服务器数组。
 */
const selectedValidServerListRows = computed(() => {
  const selected = readScriptParamValues().server_list
  if (!Array.isArray(selected)) return []
  const validNames = []
  for (const name of selected) {
    if (typeof name !== 'string' || !name) continue
    const row = devopsServers.value.find((r) => r && r.business_name === name)
    if (row) {
      validNames.push({ row, name })
    }
  }
  return validNames
})

/**
 * 当前已在 server_list 中、但 devopsServers 已不再提供的失效业务名（按顺序保留）。
 * @returns {string[]} 失效业务名列表。
 */
const selectedInvalidServerNames = computed(() => {
  const selected = readScriptParamValues().server_list
  if (!Array.isArray(selected)) return []
  return selected.filter((name) => {
    if (typeof name !== 'string' || !name) return false
    return !devopsServers.value.some((r) => r && r.business_name === name)
  })
})

/**
 * 已选服务器总数（有效 + 失效）。
 * @returns {number} 已选数量。
 */
const selectedServerCount = computed(() => {
  const selected = readScriptParamValues().server_list
  return Array.isArray(selected) ? selected.length : 0
})

/**
 * 清空脚本参数相关的状态（scriptParamValues / legacyScriptArgs / 搜索词）。
 * 切脚本 / 新建任务 / 切到 agent / 编辑不同任务前都应调用，避免跨脚本污染。
 */
function clearScriptParamState() {
  scriptParamValues.value = {}
  legacyScriptArgs.value = {}
  serverKeyword.value = ''
  apiKeyword.value = ''
}

/**
 * 写入当前已添加的参数（整体替换 ref.value 以便触发 computed 依赖）。
 * @param {Object} obj - 新的参数对象
 */
function writeScriptParamValues(obj) {
  scriptParamValues.value = obj || {}
}

/**
 * 编辑已有任务或 hydrate 回调：根据当前脚本 schema 把已存参数分配到 scriptParamValues。
 * - 已声明且受支持的参数（当前识别 server_list 与 api_list）→ 进入 scriptParamValues，
 *   经过 normalizeStringList 规范化（非空字符串 + 去重）；
 * - 其他键值（含 mode/content 等 schema 声明但 UI 暂不支持的参数，
 *   以及完全未在 schema 中的键）→ 进入 legacyScriptArgs 无损保留。
 * - 一旦检测到 server_list 按需触发 loadDevopsServers()；检测到 api_list
 *   按需触发 loadApiConfigTree()。两者复用各自 in-flight 请求，不重复 GET。
 * @param {string} scriptName - 脚本名（与 scripts.value 中 name 对应）
 * @param {Object} rawArgs - 后端存储的原始 script_args
 */
function hydrateScriptArgs(scriptName, rawArgs) {
  clearScriptParamState()
  const args = (rawArgs && typeof rawArgs === 'object') ? rawArgs : {}
  const script = scripts.value.find((s) => s && s.name === scriptName)
  const supportedDefs = script && script.params_schema && script.params_schema.properties
    ? script.params_schema.properties
    : null
  const legacy = {}
  const params = {}
  for (const key of Object.keys(args)) {
    const def = supportedDefs ? supportedDefs[key] : null
    const value = args[key]
    if (isServerListParamDefinition(key, def) || isApiListParamDefinition(key, def)) {
      params[key] = normalizeStringList(value)
    } else {
      // schema 未声明或 schema 声明但 UI 暂不支持的字段，均进入 legacy 无损保留
      legacy[key] = value
    }
  }
  writeScriptParamValues(params)
  legacyScriptArgs.value = legacy
  if (Object.prototype.hasOwnProperty.call(params, 'server_list') && !hasLoaded.value) {
    loadDevopsServers()
  }
  if (Object.prototype.hasOwnProperty.call(params, 'api_list') && !hasLoadedApis.value) {
    loadApiConfigTree()
  }
}

/**
 * 新增一个受支持参数：按 schema default 初始化数组值，并在首次添加 server_list
 * / api_list 时按需加载对应候选列表。
 * 仅支持当前识别函数（isServerListParamDefinition / isApiListParamDefinition）
 * 白名单内的 key；初值均经 normalizeStringList 规范化，避免 default 中混入
 * 非字符串 / 重复项。
 * @param {string} key - 参数键名（必须已在 supportedScriptParamDefinitions 中）
 */
function addScriptParam(key) {
  if (!key) return
  const defRecord = supportedScriptParamDefinitions.value.find((d) => d.key === key)
  if (!defRecord) return
  const current = { ...readScriptParamValues() }
  if (Object.prototype.hasOwnProperty.call(current, key)) return
  const fallback = cloneParamDefault(defRecord.def) ?? []
  current[key] = (key === 'server_list' || key === 'api_list')
    ? normalizeStringList(fallback)
    : fallback
  writeScriptParamValues(current)
  if (key === 'server_list' && !hasLoaded.value) {
    loadDevopsServers()
  } else if (key === 'api_list' && !hasLoadedApis.value) {
    loadApiConfigTree()
  }
}

/**
 * 移除一个已添加参数：同时从 scriptParamValues 删除键，确保提交 payload 不再包含该参数。
 * @param {string} key - 参数键名
 */
function removeScriptParam(key) {
  if (!key) return
  const current = { ...readScriptParamValues() }
  if (Object.prototype.hasOwnProperty.call(current, key)) {
    delete current[key]
    writeScriptParamValues(current)
  }
}

/**
 * 把 legacyScriptArgs 与 scriptParamValues 合并为最终提交 payload。
 * - server_list / api_list 在合并时统一经 normalizeStringList 规范化
 *   （非空字符串 + 去重），即便上游 hydrate / add / set / toggle 路径漏掉
 *   过滤，仍能在提交边界兜底。
 * - 其他数组值统一复制为新数组，避免外部修改响应式源对象。
 * - legacyScriptArgs 的内容保持原样：非白名单参数的未知数组透传，不污染。
 * @returns {Object} 合并后的 script_args 对象
 */
function buildScriptArgs() {
  const out = {}
  for (const [k, v] of Object.entries(legacyScriptArgs.value || {})) {
    out[k] = Array.isArray(v) ? v.slice() : v
  }
  const values = readScriptParamValues()
  for (const key of Object.keys(values)) {
    const v = values[key]
    if (key === 'server_list' || key === 'api_list') {
      out[key] = normalizeStringList(v)
    } else if (Array.isArray(v)) {
      out[key] = v.slice()
    } else {
      out[key] = v
    }
  }
  return out
}

/**
 * 脚本选择变更处理：切换脚本时同步清空旧脚本参数与 form.script_args，
 * 避免把上一个脚本的 server_list 等带过来，也避免 UI（scriptParamValues）
 * 与原始 form.script_args 出现双重状态歧义。
 * 切换同时使 fillForm 旧 hydrate 回调失效（递增 fillVersion），
 * 避免上一个脚本的 hydrate 在 loadScripts 完成时反扑。
 * 在 fillForm 编辑已有任务时不会调用本函数（由 fillForm 直接 hydrate）。
 */
function onScriptNameChange() {
  bumpFillVersion()
  clearScriptParamState()
  form.script_args = {}
}

/**
 * 把 server_list 替换为给定数组（触发 ref 重写），同时经 normalizeServerList 规范化。
 * @param {Array<string>} list - 新服务器列表
 */
function setServerList(list) {
  const values = { ...readScriptParamValues() }
  values.server_list = normalizeServerList(list)
  writeScriptParamValues(values)
}

/**
 * 全选当前过滤结果中、且仍出现在已选 server_list 中的服务器之外的所有候选。
 * 即「全选」只作用于当前过滤后的候选。
 * 候选 business_name 不是非空字符串的行由 maskServers 提前过滤掉，循环里再次防御。
 */
function selectAllVisibleServers() {
  const current = normalizeServerList(readScriptParamValues().server_list)
  const set = new Set(current)
  for (const row of filteredDevopsServers.value) {
    if (!row || typeof row.business_name !== 'string' || !row.business_name) continue
    if (set.has(row.business_name)) continue
    current.push(row.business_name)
    set.add(row.business_name)
  }
  setServerList(current)
}

/**
 * 清空当前已选服务器（包括失效项）。
 */
function clearAllSelectedServers() {
  setServerList([])
}

/**
 * 单个服务器 checkbox 切换。
 * business_name 不是非空字符串的候选 row 直接拒绝（防御 maskServers 漏过滤）。
 * @param {Object} row - 候选服务器对象（含 business_name）
 * @param {boolean} checked - 勾选状态
 */
function toggleServerSelection(row, checked) {
  if (!row || typeof row.business_name !== 'string' || !row.business_name) return
  const current = normalizeServerList(readScriptParamValues().server_list)
  const set = new Set(current)
  if (checked) {
    if (!set.has(row.business_name)) {
      current.push(row.business_name)
    }
  } else {
    const next = current.filter((n) => n !== row.business_name)
    setServerList(next)
    return
  }
  setServerList(current)
}

/**
 * 按业务名从 server_list 中移除（用于 chip 上的移除按钮）。
 * name 不是非空字符串时直接返回（防御空 chip / 非法 name）。
 * @param {string} name - 已选服务器的业务名
 */
function removeSelectedServerByName(name) {
  if (typeof name !== 'string' || !name) return
  const current = normalizeServerList(readScriptParamValues().server_list)
  const next = current.filter((n) => n !== name)
  setServerList(next)
}

/**
 * 检查某业务名是否已在 server_list 中。
 * @param {string} name - 业务名
 * @returns {boolean} 是否已选
 */
function isServerSelected(name) {
  if (!name) return false
  const list = readScriptParamValues().server_list
  return Array.isArray(list) && list.includes(name)
}

/**
 * 脱敏后的服务器列表：仅保留白名单字段 + id 非空 + business_name 为非空字符串，
 * 避免 ip/password 等敏感值流入 UI，并阻止后端把 null / 空串 / 非字符串
 * business_name 的"幽灵行"作为候选进入 UI（toggleServerSelection /
 * selectedValidServerListRows 等虽再防御，但白名单边界直接过滤更稳）。
 * @param {Array} rows - 后端原始返回数组
 * @returns {Array} 仅含白名单字段的合法候选对象数组
 */
function maskServers(rows) {
  if (!Array.isArray(rows)) return []
  return rows
    .map((row) => {
      const safe = {}
      for (const key of SERVER_WHITELIST) {
        if (row && Object.prototype.hasOwnProperty.call(row, key)) {
          safe[key] = row[key]
        }
      }
      // 即使后端返回了多余字段，spread 也被刻意不使用，确保 UI 永不会触达
      return safe
    })
    .filter((row) => {
      if (!row || row.id === undefined || row.id === null) return false
      // business_name 必须是字符串且非空，否则视为幽灵行从候选中剔除
      return typeof row.business_name === 'string' && row.business_name.length > 0
    })
}

/**
 * 脱敏后的 API 配置节点列表：仅保留白名单字段 + id 有限 + node_type 与 name 合法。
 * api_list 控件只需 (id, parent_id, node_type, name) 这 4 个字段来：
 *   * 过滤 node_type==='api' 作为候选；
 *   * 沿 parent_id 链拼父路径用于展示；
 *   * id 字符串化后作为唯一标识。
 * 节点层级可能存在多层文件夹；候选按 id 升序避免 parent 在 child 之后被选中。
 * @param {Array} rows - 后端 /api/admin/api-configs/tree 返回的原始节点
 * @returns {Array} 脱敏后的节点数组（仅含白名单字段 + 合法行）
 */
function maskApiNodes(rows) {
  if (!Array.isArray(rows)) return []
  return rows
    .map((row) => {
      if (!row || typeof row !== 'object') return null
      const safe = {}
      for (const key of API_NODE_WHITELIST) {
        if (Object.prototype.hasOwnProperty.call(row, key)) {
          safe[key] = row[key]
        }
      }
      const id = Number(safe.id)
      if (!Number.isFinite(id) || id <= 0) return null
      if (safe.node_type !== 'folder' && safe.node_type !== 'api') return null
      if (typeof safe.name !== 'string' || !safe.name) return null
      safe.id = id
      safe.parent_id = safe.parent_id == null ? null : Number(safe.parent_id)
      safe.sort_order = Number(safe.sort_order) || 0
      return safe
    })
    .filter((row) => row !== null)
}

/**
 * 加载并脱敏 API 配置节点树，供 api_list 控件候选列表使用。
 * 与 ``loadDevopsServers`` 同语义：hasLoadedApis 短路复用，in-flight Promise
 * 复用，force 时先 await 旧请求再发起新请求；失败时统一脱敏文案，不外泄后端
 * detail；强制刷新失败且有缓存时保留旧候选，否则清空。
 * @param {Object} [opts] - 选项
 * @param {boolean} [opts.force=false] - 强制刷新
 * @returns {Promise<void>}
 */
async function loadApiConfigTree(opts = {}) {
  const force = opts && opts.force === true
  if (!force && hasLoadedApis.value) return
  if (!force && apiLoadPromise) return apiLoadPromise
  if (force && apiLoadPromise) {
    try { await apiLoadPromise } catch { /* 旧失败已被原 caller 记录 */ }
  }
  const promise = (async () => {
    isLoadingApis.value = true
    apiListErrorMessage.value = ''
    try {
      const payload = await fetchApiConfigTree()
      const rows = payload && Array.isArray(payload.nodes) ? payload.nodes : []
      apiNodes.value = maskApiNodes(rows)
      hasLoadedApis.value = true
    } catch {
      apiListErrorMessage.value = '接口列表加载失败'
      const hasCached = force && Array.isArray(apiNodes.value) && apiNodes.value.length > 0
      if (!hasCached) {
        apiNodes.value = []
        hasLoadedApis.value = false
      }
    } finally {
      isLoadingApis.value = false
    }
  })()
  const tracked = promise.finally(() => {
    if (apiLoadPromise === tracked) apiLoadPromise = null
  })
  apiLoadPromise = tracked
  return tracked
}

/**
 * 把 ``apiNodes`` 中的 api 节点规整为带有父路径的候选数组。
 * 父路径沿 ``parent_id`` 链向上拼文件夹名（不含 api 节点自身）；若有祖先缺失则
 * 截断到已找到的层级；hops 上限防御环状数据（最多遍历 ``apiNodes.length`` 次）。
 * @returns {Array<{id: number, name: string, path: string}>} 候选数组
 */
const apiCandidates = computed(() => {
  const nodes = Array.isArray(apiNodes.value) ? apiNodes.value : []
  const byId = new Map()
  for (const node of nodes) {
    if (node && Number.isFinite(node.id)) byId.set(node.id, node)
  }
  const out = []
  const limit = byId.size + 1
  for (const node of nodes) {
    if (!node || node.node_type !== 'api') continue
    const segments = []
    let cursor = node.parent_id
    let hops = 0
    while (cursor != null && hops < limit) {
      const parent = byId.get(cursor)
      if (!parent) break
      segments.push(parent.name)
      cursor = parent.parent_id
      hops += 1
    }
    segments.reverse()
    out.push({ id: node.id, name: node.name, path: segments.join('/') })
  }
  out.sort((a, b) => a.id - b.id)
  return out
})

/**
 * 按关键词过滤后的 API 候选列表（对 name + path 做大小写不敏感包含匹配）。
 * @returns {Array<{id: number, name: string, path: string}>}
 */
const filteredApiCandidates = computed(() => {
  const kw = apiKeyword.value.trim().toLowerCase()
  const list = apiCandidates.value
  if (!kw) return list
  return list.filter((row) => {
    if (!row) return false
    return (
      String(row.name || '').toLowerCase().includes(kw)
      || String(row.path || '').toLowerCase().includes(kw)
    )
  })
})

/**
 * 当前已在 scriptParamValues.api_list 中、且仍能在 apiCandidates 匹配到的接口。
 * 元素为 ``{row, id}``，``id`` 为字符串形式以与 schema / payload 对齐。
 * @returns {Array<{row: Object, id: string}>}
 */
const selectedValidApiRows = computed(() => {
  const selected = readScriptParamValues().api_list
  if (!Array.isArray(selected)) return []
  const out = []
  for (const raw of selected) {
    if (typeof raw !== 'string' || !raw) continue
    const idNum = Number(raw)
    if (!Number.isFinite(idNum)) continue
    const row = apiCandidates.value.find((r) => r && r.id === idNum)
    if (row) out.push({ row, id: raw })
  }
  return out
})

/**
 * 当前已在 api_list 中、但 apiCandidates 已不再提供的失效 id 列表（按顺序保留）。
 * @returns {string[]}
 */
const selectedInvalidApiIds = computed(() => {
  const selected = readScriptParamValues().api_list
  if (!Array.isArray(selected)) return []
  return selected.filter((raw) => {
    if (typeof raw !== 'string' || !raw) return false
    const idNum = Number(raw)
    if (!Number.isFinite(idNum)) return false
    return !apiCandidates.value.some((r) => r && r.id === idNum)
  })
})

/**
 * 已选 API 总数（有效 + 失效）。
 * @returns {number}
 */
const selectedApiCount = computed(() => {
  const selected = readScriptParamValues().api_list
  return Array.isArray(selected) ? selected.length : 0
})

/**
 * 把 api_list 替换为给定数组（经 ``normalizeStringList`` 规范化）。
 * @param {Array<string>} list - 新 id 列表
 */
function setApiList(list) {
  const values = { ...readScriptParamValues() }
  values.api_list = normalizeStringList(list)
  writeScriptParamValues(values)
}

/**
 * 全选当前过滤结果中、且不在已选 api_list 中的接口。
 */
function selectAllVisibleApis() {
  const current = normalizeStringList(readScriptParamValues().api_list)
  const set = new Set(current)
  for (const row of filteredApiCandidates.value) {
    if (!row || !Number.isFinite(row.id)) continue
    const sid = String(row.id)
    if (set.has(sid)) continue
    current.push(sid)
    set.add(sid)
  }
  setApiList(current)
}

/**
 * 清空当前已选 api_list。
 */
function clearAllSelectedApis() {
  setApiList([])
}

/**
 * 单个 API checkbox 切换。
 * @param {{id: number}} row - 候选对象
 * @param {boolean} checked - 勾选状态
 */
function toggleApiSelection(row, checked) {
  if (!row || !Number.isFinite(row.id)) return
  const sid = String(row.id)
  const current = normalizeStringList(readScriptParamValues().api_list)
  const set = new Set(current)
  if (checked) {
    if (!set.has(sid)) current.push(sid)
  } else {
    setApiList(current.filter((x) => x !== sid))
    return
  }
  setApiList(current)
}

/**
 * 按 id（字符串形式）从 api_list 中移除。
 * @param {string} id - 已选 id 字符串
 */
function removeSelectedApiById(id) {
  if (typeof id !== 'string' || !id) return
  const current = normalizeStringList(readScriptParamValues().api_list)
  setApiList(current.filter((x) => x !== id))
}

/**
 * 检查某 id 是否已在 api_list 中。
 * @param {string|number} id
 * @returns {boolean}
 */
function isApiSelected(id) {
  if (id === null || id === undefined) return false
  const sid = String(id)
  const list = readScriptParamValues().api_list
  return Array.isArray(list) && list.includes(sid)
}

/**
 * 初始化数据。
 * 任务列表 + 智能体列表 + 脚本列表三者并行加载；脚本列表复用 loadScripts 的
 * 共享 in-flight Promise 与失败重试机制（不再用 fetchScripts().catch(()=>[])
 * 把失败错误吞掉再伪装成 hasLoadedScripts=true），保持与切到 script Tab 时
 * 加载路径的一致性。脚本加载失败不会 reject（loadScripts 内部已吞错并保持
 * hasLoadedScripts=false 允许重试），因此不会阻断任务列表加载。
 * @returns {Promise<void>} 无返回值
 */
async function loadInitialData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    // 三路并行：task / agent 失败会被外层 catch 接住；
    // loadScripts 内部已吞错不会 reject，等同于「失败不阻断任务列表加载」
    const [taskRows, agentRows] = await Promise.all([
      fetchTaskSchedules(),
      fetchAdminAgentList(),
      loadScripts(),
    ])
    schedules.value = taskRows || []
    agents.value = agentRows || []
    if (schedules.value.length > 0) {
      await selectSchedule(schedules.value[0])
    } else {
      startCreate()
    }
  } catch (error) {
    errorMessage.value = error.message || '加载定时任务失败'
  } finally {
    isLoading.value = false
  }
}

/**
 * 选中已有任务并加载执行历史。
 * fillForm 现在可能是 async（脚本列表尚未加载时需要等 loadScripts 完成才能 hydrate），
 * 因此这里必须 await fillForm，避免后续的 runs 加载在 hydrate 之前跑完导致 UI 闪旧值。
 * @param {Object} schedule - 定时任务记录
 * @returns {Promise<void>} 无返回值
 */
async function selectSchedule(schedule) {
  selectedSchedule.value = schedule
  closeHistory()
  isCreating.value = false
  await fillForm(schedule)
  await loadRuns(schedule.id)
}

/**
 * 打开指定任务的执行历史弹窗。
 * @param {Object} schedule - 定时任务记录
 * @returns {Promise<void>} 无返回值
 */
async function openHistory(schedule) {
  if (!schedule || !schedule.id) return
  historySchedule.value = schedule
  runs.value = []
  historyErrorMessage.value = ''
  await loadRuns(schedule.id)
}

/**
 * 关闭执行历史弹窗并清理临时数据。
 * @returns {void} 无返回值
 */
function closeHistory() {
  historySchedule.value = null
  runs.value = []
  historyErrorMessage.value = ''
}

/**
 * 响应弹窗 Escape 关闭事件。
 * @param {KeyboardEvent} event - 键盘事件
 * @returns {void} 无返回值
 */
function handleHistoryKeydown(event) {
  if (event.key === 'Escape' && historySchedule.value) {
    closeHistory()
  }
}

/**
 * 加载执行历史。
 * @param {number} scheduleId - 定时任务 ID
 * @returns {Promise<void>} 无返回值
 */
async function loadRuns(scheduleId) {
  if (!scheduleId) {
    runs.value = []
    return
  }
  isLoadingRuns.value = true
  historyErrorMessage.value = ''
  try {
    runs.value = await fetchTaskRuns(scheduleId, 50)
  } catch (error) {
    runs.value = []
    historyErrorMessage.value = error.message || '加载执行历史失败'
  } finally {
    isLoadingRuns.value = false
  }
}

/**
 * 切换 Tab。切到扫描 Tab 时按需加载服务器列表，并仅保留白名单字段。
 * 切到脚本 Tab 时按需加载脚本列表。
 * 切回任务 Tab 时不再触发任何 devops / scripts 请求。
 * 第一次加载完成后置 ``hasLoaded=true`` / ``hasLoadedScripts=true``，之后切回再进入不再重复 GET。
 * @param {string} tabId - TAB_TASK / TAB_SCAN / TAB_SCRIPT / TAB_API
 * @returns {Promise<void>} 无返回值
 */
async function switchTab(tabId) {
  if (activeTab.value === tabId) return
  activeTab.value = tabId
  if (tabId === TAB_SCAN && !hasLoaded.value) {
    await loadDevopsServers()
  }
  if (tabId === TAB_SCRIPT && !hasLoadedScripts.value) {
    await loadScripts()
  }
}

// DevOps 服务器列表的共享 in-flight Promise：避免并发调用触发多次 GET。
// 当普通加载与按需扫描刷新请求同时存在时，后者会 await 该 Promise 后再发起新请求。
let devopsLoadPromise = null

// fillForm 单调递增版本号：startCreate / onTargetTypeChange / onScriptNameChange
// 与下一次 fillForm 入口都会自增 1；loadScripts 完成后的 hydrate 回调捕获调用时
// 的快照版本，仅当当前版本仍等于快照且目标类型仍为 script / script_name 未变时
// 才执行 hydrate，避免旧回调用上一个任务的 script_args 覆盖新表单。
let fillVersion = 0
function bumpFillVersion() {
  fillVersion += 1
}

/**
 * 加载并脱敏 DevOps 服务器列表。
 * - 普通调用：已成功加载过（hasLoaded=true）或已有 pending 请求时直接复用，不重复 GET。
 * - 失败时保持 hasLoaded=false 并允许下次重试（不固化缓存）。
 * - { force: true }：跳过 hasLoaded 缓存短路；若此时已有 pending 请求，
 *   先 await 等待旧请求结束（避免旧响应覆盖新响应），再发起一次全新 GET。
 * - 错误一律走通用脱敏文案「服务器列表加载失败」，不外泄后端 detail；
 *   无论是否首次加载或强制刷新，只要失败就设置 listErrorMessage。
 * - 失败时仅在 force 且存在非空缓存时保留 devopsServers 与加载状态；
 *   其余失败均清空列表并显式设置 hasLoaded=false，包括普通失败时旧状态异常为 true 的情况。
 * @param {Object} [opts] - 选项
 * @param {boolean} [opts.force=false] - 强制刷新，跳过已加载短路
 * @returns {Promise<void>} 无返回值
 */
async function loadDevopsServers(opts = {}) {
  const force = opts && opts.force === true
  if (!force && hasLoaded.value) return
  if (!force && devopsLoadPromise) return devopsLoadPromise
  if (force && devopsLoadPromise) {
    // 扫描刷新遇到 pending：串行等待旧请求完成，再发起新请求
    try {
      await devopsLoadPromise
    } catch {
      // 旧请求失败已被原 caller 记录，吞掉后继续 force
    }
  }
  const promise = (async () => {
    isLoadingServers.value = true
    listErrorMessage.value = ''
    try {
      const rows = await fetchDevOpsServers()
      devopsServers.value = maskServers(rows)
      hasLoaded.value = true
    } catch {
      // 统一使用脱敏文案；仅强制刷新且存在缓存时保留旧候选与加载状态
      listErrorMessage.value = '服务器列表加载失败'
      const hasCachedServers = force && Array.isArray(devopsServers.value) && devopsServers.value.length > 0
      if (!hasCachedServers) {
        devopsServers.value = []
        hasLoaded.value = false
      }
    } finally {
      isLoadingServers.value = false
    }
  })()
  const tracked = promise.finally(() => {
    if (devopsLoadPromise === tracked) {
      devopsLoadPromise = null
    }
  })
  devopsLoadPromise = tracked
  return tracked
}

/**
 * 把后端返回的统计对象严格白名单复制为 4 个整数。
 * 避免 ``scanSummary.value = summary`` 直接暴露后端可能附带的敏感字段。
 * @param {unknown} raw - 后端 /scan 响应
 * @returns {{scanned: number, inserted: number, updated: number, failed: number}}
 */
function sanitizeSummary(raw) {
  const out = { scanned: 0, inserted: 0, updated: 0, failed: 0 }
  if (!raw || typeof raw !== 'object') return out
  for (const key of SUMMARY_FIELDS) {
    const value = Number(raw[key])
    out[key] = Number.isFinite(value) ? value : 0
  }
  return out
}

/**
 * 触发服务器扫描。带防重复提交：scanning 过程中再次点击会被忽略。
 * 扫描成功后用 force 强制刷新列表；任何错误使用脱敏提示。
 * @returns {Promise<void>} 无返回值
 */
async function triggerServerScan() {
  if (isScanning.value) return
  isScanning.value = true
  scanErrorMessage.value = ''
  scanSuccessMessage.value = ''
  scanSummary.value = null
  try {
    const summary = await scanDevOpsServers()
    scanSummary.value = sanitizeSummary(summary)
    scanSuccessMessage.value = '扫描完成'
    // 扫描成功后显式 force 刷新：绕过 hasLoaded 短路，
    // 若此时已有 pending 加载会先串行等待，避免旧响应覆盖新数据
    await loadDevopsServers({ force: true })
  } catch {
    scanErrorMessage.value = '扫描失败，请稍后重试'
  } finally {
    isScanning.value = false
  }
}

/**
 * 删除按钮的二次确认与异步调用：
 *   1. window.confirm 弹出用户确认；
 *   2. 通过后调用 api.deleteDevOpsServer(row.id)；
 *   3. 成功：从 devopsServers.value 中按 id 移除该行（无需全表刷新）；
 *   4. 失败：使用脱敏文案（与扫描失败一致），不回显后端 detail。
 * 任何删除失败都保持原列表状态，不清理旧 row。
 * @param {Object} row - 服务器行（含 id / business_name / server_type / updated_at）
 * @returns {Promise<void>} 无返回值
 */
async function confirmDeleteServer(row) {
  if (!row || row.id === undefined || row.id === null) return
  // 防重复点击：同一行删除中再次点击会被忽略
  if (isDeletingRowId.value === row.id) return
  const ok = window.confirm(`确认删除服务器「${row.business_name}」？此操作不可撤销。`)
  if (!ok) return
  isDeletingRowId.value = row.id
  listErrorMessage.value = ''
  try {
    await deleteDevOpsServer(row.id)
    // 成功：从本地列表移除该行（无需全表刷新）
    devopsServers.value = devopsServers.value.filter(
      (item) => item && item.id !== row.id
    )
    scanSuccessMessage.value = `服务器「${row.business_name}」已删除`
  } catch {
    // 通用脱敏文案，不回显后端 detail（避免泄漏服务器名 / IP 等）
    listErrorMessage.value = '删除服务器失败，请稍后重试'
  } finally {
    isDeletingRowId.value = null
  }
}

// 脚本列表的共享 in-flight Promise：避免 loadInitialData 与切到 script Tab
// 等并发调用触发多次 GET。失败时不固化 hasLoadedScripts=true，允许下次重试。
let scriptsLoadPromise = null

/**
 * 加载已注册脚本列表（白名单字段过滤）。
 * 仅保留 SCRIPT_PUBLIC_FIELDS 中的字段，绝不渲染 func 等内部对象。
 * - 普通调用：已成功加载过（hasLoadedScripts=true）或已有 pending 请求时直接复用，不重复 GET。
 * - { force: true }：跳过 hasLoadedScripts 缓存短路；若此时已有 pending 请求，
 *   先 await 等待旧请求完成（避免旧响应覆盖新响应），再发起一次全新 GET。
 * - 失败时保持 hasLoadedScripts=false，允许下次重试；不再把失败错误吞掉伪装成空数组。
 * - 脚本加载失败不阻断任务列表加载（loadInitialData 会 catch 该 Promise 的 reject）。
 * @param {Object} [opts] - 选项
 * @param {boolean} [opts.force=false] - 强制刷新，跳过已加载短路
 * @returns {Promise<void>} 无返回值
 */
async function loadScripts(opts = {}) {
  const force = opts && opts.force === true
  if (!force && hasLoadedScripts.value) return
  if (!force && scriptsLoadPromise) return scriptsLoadPromise
  if (force && scriptsLoadPromise) {
    // 扫描刷新遇到 pending：串行等待旧请求完成，再发起新请求，避免旧响应覆盖新数据
    try {
      await scriptsLoadPromise
    } catch {
      // 旧请求失败已被原 caller 记录，吞掉后继续 force
    }
  }
  const promise = (async () => {
    isLoadingScripts.value = true
    scriptError.value = ''
    try {
      const raw = await fetchScripts()
      scripts.value = (raw || []).map((item) => {
        const safe = {}
        for (const key of SCRIPT_PUBLIC_FIELDS) {
          if (item && Object.prototype.hasOwnProperty.call(item, key)) {
            safe[key] = item[key]
          }
        }
        return safe
      }).filter((item) => item && item.name)
      hasLoadedScripts.value = true
    } catch {
      scriptError.value = '脚本列表加载失败'
      scripts.value = []
      // 失败保持 hasLoadedScripts=false，不固化缓存，允许下次重试
    } finally {
      isLoadingScripts.value = false
    }
  })()
  const tracked = promise.finally(() => {
    if (scriptsLoadPromise === tracked) {
      scriptsLoadPromise = null
    }
  })
  scriptsLoadPromise = tracked
  return tracked
}

/**
 * 触发脚本目录扫描，成功后刷新列表。
 * 带防重复提交：scanning 过程中再次点击会被忽略。
 * @returns {Promise<void>} 无返回值
 */
async function triggerScriptScan() {
  if (isScanningScripts.value) return
  isScanningScripts.value = true
  scriptError.value = ''
  scriptSuccess.value = ''
  scanScriptSummary.value = null
  try {
    const raw = await scanScripts()
    const summary = { scanned: 0, registered: 0, failed: 0 }
    for (const key of SCRIPT_SUMMARY_FIELDS) {
      const v = Number(raw[key])
      summary[key] = Number.isFinite(v) ? v : 0
    }
    scanScriptSummary.value = summary
    scriptSuccess.value = `扫描完成：扫描 ${summary.scanned} 个文件，注册 ${summary.registered} 个脚本，失败 ${summary.failed} 个`
    // 扫描成功后用 force 强制刷新：绕过 hasLoadedScripts 短路，
    // 若此时已有 pending 加载会先串行等待，避免旧响应覆盖新数据
    await loadScripts({ force: true })
  } catch {
    scriptError.value = '扫描失败，请稍后重试'
  } finally {
    isScanningScripts.value = false
  }
}

/**
 * 目标类型切换时清理无关字段并按需加载脚本列表。
 * 切到 agent 时清空 script_name/script_args；切到 script 时清空 agent_name/prompt。
 * 切换同时使 fillForm 旧 hydrate 回调失效（递增 fillVersion），
 * 避免旧 fillForm 在 loadScripts 完成后用旧 schedule 数据覆盖新表单。
 */
function onTargetTypeChange() {
  bumpFillVersion()
  if (form.target_type === 'agent') {
    form.script_name = ''
    form.script_args = {}
    clearScriptParamState()
    // agent 任务不发送邮件通知，重置字段
    form.notify_enabled = false
    form.notify_policy_id = null
  } else {
    form.agent_name = ''
    form.prompt = ''
    if (!hasLoadedScripts.value) {
      loadScripts()
    }
  }
}

/**
 * 加载邮件策略列表（仅 script 任务启用邮件通知时按需调用）。
 * 使用白名单字段，避免注入 recipients 数组等额外字段到 UI。
 * @returns {Promise<void>} 无返回值
 */
async function loadEmailPolicies() {
  if (hasLoadedEmailPolicies.value || isLoadingEmailPolicies.value) return
  isLoadingEmailPolicies.value = true
  try {
    const rows = await fetchEmailPolicies()
    emailPolicies.value = (rows || []).map((item) => ({
      id: item.id,
      name: item.name || `策略 ${item.id}`,
      recipient_count: Array.isArray(item.recipient_user_ids)
        ? item.recipient_user_ids.length
        : 0,
    }))
    hasLoadedEmailPolicies.value = true
  } catch {
    emailPolicies.value = []
  } finally {
    isLoadingEmailPolicies.value = false
  }
}

/**
 * 切换 notify_enabled 时按需加载策略列表，并把 notify_policy_id 切换到合法值。
 * @param {boolean} value - 新开关值
 */
function onNotifyEnabledChange(value) {
  if (value && !hasLoadedEmailPolicies.value) {
    loadEmailPolicies()
  }
  if (!value) {
    // 关闭时清空已选策略
    form.notify_policy_id = null
  } else if (
    form.notify_policy_id != null
    && !emailPolicies.value.some((p) => p.id === form.notify_policy_id)
  ) {
    // 策略列表已加载但当前值不在其中，重置
    form.notify_policy_id = null
  }
}

/**
 * 将任务记录填充到表单。
 * 加载是 async：脚本列表尚未就绪时，需 await loadScripts() 完成再 hydrate
 * scriptParamValues（hydrate 需要 script.params_schema 才能识别 server_list）。
 * 为防止旧回调覆盖新任务：每次进入 fillForm 自增 fillVersion；脚本列表加载
 * 完成的 hydrate 回调捕获调用时的 (version, scriptName) 快照，仅当当前版本
 * 仍等于快照、目标类型仍为 script 且 script_name 未变化时才执行 hydrate。
 * @param {Object} schedule - 定时任务记录
 * @returns {Promise<void>} 无返回值
 */
function fillForm(schedule) {
  // 本次 fillForm 的版本快照 + 同步字段写入必须在最前完成，避免 hydrate 完成时
  // 看到 form.script_name 已被并发 fillForm 改写
  const myVersion = ++fillVersion
  const snapshotScriptName = schedule.script_name || ''
  const snapshotScriptArgs = schedule.script_args || {}
  form.name = schedule.name || ''
  form.description = schedule.description || ''
  form.target_type = schedule.target_type || 'agent'
  form.agent_name = schedule.agent_name || enabledAgents.value[0]?.name || ''
  form.prompt = schedule.prompt || ''
  form.script_name = snapshotScriptName
  form.script_args = snapshotScriptArgs
  Object.assign(scheduleConfig, parseCronExpression(schedule.cron_expression))
  form.timezone = schedule.timezone || 'Asia/Shanghai'
  form.enabled = schedule.enabled !== false
  form.context_overrides = schedule.context_overrides || {}
  form.max_concurrent_runs = schedule.max_concurrent_runs || 1
  form.notify_enabled = schedule.notify_enabled === true
  form.notify_policy_id = schedule.notify_policy_id || null
  contextJson.value = JSON.stringify(form.context_overrides, null, 2)
  // 根据当前脚本 schema 把已存参数分配到 scriptParamValues 或 legacyScriptArgs
  if (form.target_type === 'script') {
    if (!hasLoadedScripts.value && scripts.value.length === 0) {
      // 等待脚本列表加载完成后 hydrate；hydrate 前再校验版本 + 目标 + script_name
      return loadScripts().then(() => {
        if (myVersion !== fillVersion) return
        if (form.target_type !== 'script') return
        if (form.script_name !== snapshotScriptName) return
        hydrateScriptArgs(snapshotScriptName, snapshotScriptArgs)
      })
    }
    hydrateScriptArgs(snapshotScriptName, snapshotScriptArgs)
  } else {
    clearScriptParamState()
  }
  // 切换到 script 时按需加载邮件策略
  if (form.target_type === 'script' && form.notify_enabled) {
    loadEmailPolicies()
  }
  return Promise.resolve()
}

/**
 * 开始创建新任务。
 * 同时使 fillForm 旧 hydrate 回调失效（递增 fillVersion），
 * 避免上一个编辑任务的 hydrate 在 loadScripts 完成时反扑到新任务表单。
 */
function startCreate() {
  bumpFillVersion()
  selectedSchedule.value = null
  closeHistory()
  isCreating.value = true
  runs.value = []
  form.name = ''
  form.description = ''
  form.target_type = 'agent'
  form.agent_name = enabledAgents.value[0]?.name || ''
  form.prompt = ''
  form.script_name = ''
  form.script_args = {}
  Object.assign(scheduleConfig, {
    type: 'daily',
    weekday: '1',
    month: '1',
    day: '1',
    hour: '9',
    minute: '0',
    interval: '15',
  })
  form.timezone = 'Asia/Shanghai'
  form.enabled = true
  form.context_overrides = {}
  form.max_concurrent_runs = 1
  form.notify_enabled = false
  form.notify_policy_id = null
  contextJson.value = '{}'
  clearScriptParamState()
  errorMessage.value = ''
  successMessage.value = ''
}

/**
 * 构造提交 payload。根据 target_type 分支构造：
 * agent 任务包含 agent_name/prompt；script 任务包含 script_name/script_args。
 * context_overrides 来自 contextJson 文本框，需 JSON.parse；script_args 不再走
 * JSON.parse（已切到 schema-driven 参数面板，由 buildScriptArgs 直接合并）。
 * @returns {Object} 后端请求体
 * @throws {Error} 任务名称为空或 context_overrides JSON 非法时抛出
 */
function buildPayload() {
  // 前端防御性校验：任务名称为空时直接拦截，避免触发后端 422。
  const trimmedName = form.name.trim()
  if (!trimmedName) {
    throw new Error('任务名称不能为空')
  }
  let contextOverrides = {}
  try {
    contextOverrides = contextJson.value.trim() ? JSON.parse(contextJson.value) : {}
  } catch {
    throw new Error('上下文 JSON 格式不正确')
  }
  const payload = {
    name: trimmedName,
    description: form.description.trim(),
    target_type: form.target_type,
    cron_expression: buildCronExpression(scheduleConfig).trim(),
    timezone: form.timezone.trim() || 'Asia/Shanghai',
    enabled: form.enabled,
    context_overrides: contextOverrides,
    max_concurrent_runs: Number(form.max_concurrent_runs) || 1,
  }
  if (form.target_type === 'agent') {
    payload.agent_name = form.agent_name
    payload.prompt = form.prompt.trim()
  } else {
    payload.script_name = form.script_name
    payload.script_args = buildScriptArgs()
    payload.notify_enabled = !!form.notify_enabled
    payload.notify_policy_id = form.notify_enabled
      ? (form.notify_policy_id || null)
      : null
  }
  return payload
}

/**
 * 保存任务。
 * @returns {Promise<void>} 无返回值
 */
async function saveTask() {
  isSaving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const payload = buildPayload()
    if (isCreating.value) {
      const created = await createTaskSchedule(payload)
      successMessage.value = '任务已创建'
      await loadInitialData()
      const match = schedules.value.find((item) => item.id === created.id)
      if (match) await selectSchedule(match)
    } else if (selectedSchedule.value) {
      const updated = await updateTaskSchedule(selectedSchedule.value.id, payload)
      successMessage.value = '任务已保存'
      await refreshSchedules(updated.id)
    }
  } catch (error) {
    // 优先取 err.detail（Pydantic 422 数组已由 api.js 解析）；
    // 兜底用 error.message，避免在 error 非 Error 对象时显示 [object Object]。
    const detail = error && error.detail
    if (Array.isArray(detail)) {
      errorMessage.value = detail
        .map((d) => `${(d.loc || []).slice(1).join('.') || '字段'}: ${d.msg}`)
        .join('；')
    } else {
      errorMessage.value = (error && error.message) || '保存任务失败'
    }
  } finally {
    isSaving.value = false
  }
}

/**
 * 刷新任务列表并保持选中项。
 * @param {number} selectedId - 选中任务 ID
 * @returns {Promise<void>} 无返回值
 */
async function refreshSchedules(selectedId = selectedSchedule.value?.id) {
  schedules.value = await fetchTaskSchedules()
  const next = schedules.value.find((item) => item.id === selectedId) || schedules.value[0]
  if (next) await selectSchedule(next)
}

/**
 * 启用或停用当前任务。
 * @returns {Promise<void>} 无返回值
 */
async function toggleTask() {
  if (!selectedSchedule.value) return
  errorMessage.value = ''
  try {
    const updated = await setTaskScheduleEnabled(selectedSchedule.value.id, !selectedSchedule.value.enabled)
    successMessage.value = updated.enabled ? '任务已启用' : '任务已停用'
    await refreshSchedules(updated.id)
  } catch (error) {
    errorMessage.value = error.message || '更新启用状态失败'
  }
}

/**
 * 立即运行当前任务。
 * @returns {Promise<void>} 无返回值
 */
async function runNow() {
  if (!selectedSchedule.value) return
  errorMessage.value = ''
  try {
    await triggerTaskSchedule(selectedSchedule.value.id)
    successMessage.value = '任务已提交运行'
    if (historySchedule.value?.id === selectedSchedule.value.id) {
      await loadRuns(selectedSchedule.value.id)
    }
  } catch (error) {
    errorMessage.value = error.message || '立即运行失败'
  }
}

/**
 * 删除当前任务。
 * @returns {Promise<void>} 无返回值
 */
async function removeTask() {
  if (!selectedSchedule.value) return
  if (!window.confirm(`确认删除任务「${selectedSchedule.value.name}」？`)) return
  errorMessage.value = ''
  try {
    await deleteTaskSchedule(selectedSchedule.value.id)
    successMessage.value = '任务已删除'
    await refreshSchedules(null)
    if (!schedules.value.length) startCreate()
  } catch (error) {
    errorMessage.value = error.message || '删除任务失败'
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleHistoryKeydown)
  loadInitialData()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleHistoryKeydown)
})
</script>

<template>
  <section class="task-scheduler-manager">
    <aside class="task-sidebar">
      <div class="panel-header">
        <div>
          <h3>定时任务</h3>
          <p>按计划触发已配置智能体</p>
        </div>
        <button class="primary-btn" type="button" @click="startCreate">新增任务</button>
      </div>

      <div v-if="isLoading" class="empty-state">正在加载...</div>
      <div v-else-if="!schedules.length" class="empty-state">暂无定时任务</div>
      <article
        v-for="schedule in schedules"
        :key="schedule.id"
        class="task-item"
        :class="{ active: selectedSchedule && selectedSchedule.id === schedule.id }"
        @click="selectSchedule(schedule)"
      >
        <button
          class="task-select-btn"
          type="button"
          @click.stop="selectSchedule(schedule)"
        >
          <span class="task-name">{{ schedule.name }}</span>
          <span class="task-agent">
            <span class="badge" :class="schedule.target_type === 'script' ? 'badge-script' : 'badge-agent'">
              {{ schedule.target_type === 'script' ? '脚本' : '智能体' }}
            </span>
            {{ schedule.target_type === 'script' ? schedule.script_name : schedule.agent_name }}
          </span>
          <span class="task-cron">{{ schedule.cron_expression }}</span>
          <span class="task-status" :class="schedule.enabled ? 'enabled' : 'disabled'">
            {{ schedule.enabled ? '已启用' : '已停用' }}
          </span>
        </button>
        <button
          class="task-history-btn"
          type="button"
          aria-label="查看执行历史"
          title="查看执行历史"
          aria-haspopup="dialog"
          :aria-busy="isLoadingRuns && historySchedule?.id === schedule.id ? 'true' : 'false'"
          :disabled="isLoadingRuns && historySchedule?.id === schedule.id"
          @click.stop="openHistory(schedule)"
        >
          <svg class="task-history-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M12 7v5l3.5 2.1M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5" />
          </svg>
        </button>
      </article>
    </aside>

    <main class="task-detail">
      <div
        class="tablist"
        role="tablist"
        aria-label="定时任务管理"
        data-testid="tablist"
      >
        <button
          v-for="tab in TAB_LABELS"
          :key="tab.id"
          type="button"
          role="tab"
          :id="`tab-${tab.id}`"
          :aria-controls="`panel-${tab.id}`"
          :aria-selected="activeTab === tab.id ? 'true' : 'false'"
          :tabindex="activeTab === tab.id ? 0 : -1"
          :class="['tab', { active: activeTab === tab.id }]"
          :data-testid="`tab-${tab.id}`"
          @click="switchTab(tab.id)"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- 任务 Tab —— 使用 v-if 互斥挂载：
           form / scriptParamValues / devopsServers 都保存在 setup() 内的 ref / reactive 中，
           与 panel 是否挂载无关：切回任务 Tab 时 panel 重新挂载，computed 会基于现有状态
           重建 UI，无需把隐藏表单常驻 DOM。
      -->
      <section
        v-if="activeTab === TAB_TASK"
        :id="`panel-${TAB_TASK}`"
        role="tabpanel"
        aria-labelledby="tab-task"
        data-testid="panel-task"
      >
        <div v-if="errorMessage" class="alert error">{{ errorMessage }}</div>
        <div v-if="successMessage" class="alert success">{{ successMessage }}</div>

        <header class="detail-header">
          <div>
            <h3>{{ isCreating ? '新增定时任务' : '编辑定时任务' }}</h3>
            <p>每次触发都会创建新的会话记录，停机期间错过的触发不会补跑。</p>
          </div>
          <div class="actions" v-if="isCreating || selectedSchedule">
            <button
              class="primary-btn"
              type="submit"
              form="task-scheduler-form"
              :disabled="isSaving"
              data-testid="schedule-save-btn"
            >
              {{ isSaving ? '保存中...' : '保存任务' }}
            </button>
            <template v-if="!isCreating && selectedSchedule">
              <button type="button" class="secondary-btn" @click="toggleTask">
                {{ selectedSchedule.enabled ? '停用任务' : '启用任务' }}
              </button>
              <button type="button" class="secondary-btn" @click="runNow">立即运行</button>
              <button type="button" class="danger-btn" @click="removeTask">删除任务</button>
            </template>
          </div>
        </header>

        <form id="task-scheduler-form" class="task-form" @submit.prevent="saveTask">
          <label class="form-field">
            <span>任务名称 *</span>
            <input v-model="form.name" type="text" placeholder="例如：每日巡检" />
          </label>
          <label class="form-field">
            <span>目标类型 *</span>
            <select v-model="form.target_type" data-testid="schedule-target-type" @change="onTargetTypeChange">
              <option value="agent">智能体</option>
              <option value="script">脚本</option>
            </select>
          </label>
          <label v-if="form.target_type === 'agent'" class="form-field">
            <span>目标智能体 *</span>
            <select v-model="form.agent_name" data-testid="schedule-agent">
              <option v-for="agent in enabledAgents" :key="agent.name" :value="agent.name">
                {{ agent.display_name || agent.name }}（{{ agent.name }}）
              </option>
            </select>
          </label>
          <label v-else class="form-field">
            <span>目标脚本 *</span>
            <select
              v-model="form.script_name"
              data-testid="schedule-script"
              :disabled="isLoadingScripts"
              @change="onScriptNameChange"
            >
              <option value="" disabled>{{ isLoadingScripts ? '加载中...' : '请选择脚本' }}</option>
              <option v-for="script in scripts" :key="script.name" :value="script.name">
                {{ script.display_name || script.name }}（{{ script.name }}）
              </option>
            </select>
          </label>
          <label class="form-field">
            <span>执行频率 *</span>
            <select v-model="scheduleConfig.type" data-testid="schedule-type">
              <option v-for="t in SCHEDULE_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </label>
          <label v-if="scheduleConfig.type === 'interval_minutes'" class="form-field">
            <span>间隔（分钟）*</span>
            <input
              v-model="scheduleConfig.interval"
              data-testid="schedule-interval"
              type="number"
              min="1"
              max="59"
              placeholder="1-59"
            />
          </label>
          <label v-if="scheduleConfig.type === 'interval_hours'" class="form-field">
            <span>间隔（小时）*</span>
            <input
              v-model="scheduleConfig.interval"
              data-testid="schedule-interval"
              type="number"
              min="1"
              max="23"
              placeholder="1-23"
            />
          </label>
          <label v-if="scheduleConfig.type === 'weekly'" class="form-field">
            <span>星期几 *</span>
            <select v-model="scheduleConfig.weekday" data-testid="schedule-weekday">
              <option v-for="w in WEEKDAYS" :key="w.value" :value="w.value">{{ w.label }}</option>
            </select>
          </label>
          <label v-if="scheduleConfig.type === 'monthly'" class="form-field">
            <span>几号 *</span>
            <select v-model="scheduleConfig.day" data-testid="schedule-day">
              <option v-for="d in MONTH_DAYS" :key="d" :value="d">{{ d }} 日</option>
            </select>
          </label>
          <template v-if="scheduleConfig.type === 'yearly'">
            <label class="form-field">
              <span>月份 *</span>
              <select v-model="scheduleConfig.month" data-testid="schedule-month">
                <option v-for="mo in MONTHS" :key="mo" :value="mo">{{ mo }} 月</option>
              </select>
            </label>
            <label class="form-field">
              <span>日期 *</span>
              <select v-model="scheduleConfig.day" data-testid="schedule-day">
                <option v-for="d in MONTH_DAYS" :key="d" :value="d">{{ d }} 日</option>
              </select>
            </label>
          </template>
          <!-- interval 模式下 cron 表达式忽略 hour/minute，不展示「执行时间」字段 -->
          <label
            v-if="scheduleConfig.type !== 'interval_minutes' && scheduleConfig.type !== 'interval_hours'"
            class="form-field"
          >
            <span>执行时间 *</span>
            <div class="time-input" data-testid="schedule-time">
              <select v-model="scheduleConfig.hour" data-testid="schedule-hour">
                <option v-for="h in HOURS" :key="h" :value="h">{{ String(h).padStart(2, '0') }}</option>
              </select>
              <span class="time-sep">:</span>
              <select v-model="scheduleConfig.minute" data-testid="schedule-minute">
                <option v-for="mi in MINUTES" :key="mi" :value="mi">{{ String(mi).padStart(2, '0') }}</option>
              </select>
            </div>
          </label>
          <label class="form-field">
            <span>时区</span>
            <input v-model="form.timezone" type="text" placeholder="Asia/Shanghai" />
          </label>
          <label v-if="form.target_type === 'agent'" class="form-field full">
            <span>任务提示词 *</span>
            <textarea v-model="form.prompt" rows="5" placeholder="描述定时触发时需要智能体完成的任务"></textarea>
          </label>
          <!-- 脚本任务：参数化容器（testid 沿用 schedule-script-args），由 params_schema 驱动 -->
          <div v-else class="form-field full script-params" data-testid="schedule-script-args" role="group" aria-label="脚本参数">
            <span class="script-params__title">脚本参数</span>
            <p class="script-params__hint">只能由当前脚本 params_schema 声明，受支持参数以「添加参数」按钮添加，未支持的旧参数自动保留。</p>

            <!-- 已添加参数列表 -->
            <div
              v-if="addedScriptParamKeys.length"
              class="script-param-list"
              aria-label="已添加脚本参数"
            >
              <div
                v-for="paramKey in addedScriptParamKeys"
                :key="paramKey"
                class="script-param-item"
                :data-testid="`schedule-param-${paramKey}`"
              >
                <!-- 当前唯一受支持的控件就是 server_list；不再渲染通用占位分支。 -->
                <template v-if="paramKey === 'server_list'">
                  <!-- server_list 多选控件 -->
                  <section class="server-list-panel" data-testid="schedule-param-server-list" :aria-label="`参数 ${paramKey}`">
                    <header class="script-param-item__head">
                      <div>
                        <strong>{{ supportedScriptParamDefinitions.find((d) => d.key === paramKey)?.def.title || paramKey }}</strong>
                        <span class="script-param-item__key">{{ paramKey }}</span>
                      </div>
                      <button
                        type="button"
                        class="link-btn"
                        :data-testid="`schedule-remove-param-${paramKey}`"
                        :aria-label="`移除参数 ${paramKey}`"
                        @click="removeScriptParam(paramKey)"
                      >
                        移除参数
                      </button>
                    </header>
                    <p
                      v-if="supportedScriptParamDefinitions.find((d) => d.key === paramKey)?.def.description"
                      class="script-param-item__desc"
                    >
                      {{ supportedScriptParamDefinitions.find((d) => d.key === paramKey).def.description }}
                    </p>

                    <!-- 工具栏：搜索 / 全选 / 清空 / 计数 -->
                    <div class="server-list-panel__toolbar">
                      <input
                        v-model="serverKeyword"
                        type="search"
                        class="server-search"
                        placeholder="搜索业务名或系统类型..."
                        aria-label="搜索服务器"
                        data-testid="schedule-server-search"
                      />
                      <div class="server-list-panel__actions">
                        <button
                          type="button"
                          class="link-btn"
                          :disabled="!filteredDevopsServers.length"
                          aria-label="全选当前过滤服务器"
                          @click="selectAllVisibleServers"
                        >
                          全选
                        </button>
                        <span class="divider" aria-hidden="true"></span>
                        <button
                          type="button"
                          class="link-btn"
                          :disabled="selectedServerCount === 0"
                          aria-label="清空已选服务器"
                          @click="clearAllSelectedServers"
                        >
                          清空
                        </button>
                      </div>
                      <span
                        class="server-counter"
                        :class="{ active: selectedServerCount > 0 }"
                        aria-label="已选服务器计数"
                      >
                        已选 <strong>{{ selectedServerCount }}</strong> /
                        {{ filteredDevopsServers.length }}
                      </span>
                    </div>

                    <!-- 状态链不包含候选列表，force 刷新失败时错误与缓存候选可同时展示 -->
                    <div
                      v-if="isLoadingServers && !hasLoaded"
                      class="empty-state"
                      data-testid="schedule-server-list-loading"
                    >
                      正在加载服务器列表...
                    </div>
                    <div
                      v-else-if="listErrorMessage && !isLoadingServers"
                      class="alert error"
                      role="alert"
                      data-testid="schedule-server-list-error"
                    >
                      <span>{{ listErrorMessage }}</span>
                      <button
                        type="button"
                        class="link-btn"
                        :data-testid="'schedule-server-list-retry'"
                        aria-label="重新加载服务器"
                        @click="loadDevopsServers({ force: true })"
                      >
                        重新加载服务器
                      </button>
                    </div>
                    <div
                      v-else-if="hasLoaded && !devopsServers.length"
                      class="empty-state"
                      data-testid="schedule-server-list-empty"
                    >
                      暂无已扫描入库的服务器，请先在「服务器扫描入库」中扫描。
                    </div>

                    <!-- 多选列表独立于状态链，允许与缓存刷新错误同时展示 -->
                    <ul
                      v-if="filteredDevopsServers.length"
                      class="server-options"
                      role="listbox"
                      aria-multiselectable="true"
                      :aria-label="`已扫描服务器候选列表`"
                      data-testid="schedule-server-options"
                    >
                      <li
                        v-for="row in filteredDevopsServers"
                        :key="row.id"
                        class="server-option"
                        :class="{ selected: isServerSelected(row.business_name) }"
                      >
                        <label class="server-option__label">
                          <input
                            type="checkbox"
                            :checked="isServerSelected(row.business_name)"
                            :data-testid="`schedule-server-option-${row.id}`"
                            @change="toggleServerSelection(row, $event.target.checked)"
                          />
                          <span class="server-option__main">{{ row.business_name }}</span>
                          <span class="server-option__meta">{{ row.server_type }}</span>
                        </label>
                      </li>
                    </ul>
                    <div
                      v-if="!filteredDevopsServers.length && serverKeyword.trim() && devopsServers.length"
                      class="empty-state"
                      data-testid="schedule-server-list-no-match"
                    >
                      没有匹配「{{ serverKeyword }}」的服务器
                    </div>

                    <!-- 已选 / 失效 chips -->
                    <div
                      v-if="selectedValidServerListRows.length || selectedInvalidServerNames.length"
                      class="selected-server-chips"
                      aria-label="已选服务器列表"
                      data-testid="schedule-selected-server-list"
                    >
                      <span
                        v-for="entry in selectedValidServerListRows"
                        :key="`valid-${entry.row.id}-${entry.name}`"
                        class="chip selected-server-chip"
                        :data-testid="`schedule-selected-server-chip-${entry.name}`"
                      >
                        <span>{{ entry.name }}</span>
                        <button
                          type="button"
                          class="chip-remove"
                          :aria-label="`移除已选服务器 ${entry.name}`"
                          @click="removeSelectedServerByName(entry.name)"
                        >
                          ×
                        </button>
                      </span>
                      <span
                        v-for="name in selectedInvalidServerNames"
                        :key="`invalid-${name}`"
                        class="chip selected-server-chip invalid"
                        data-testid="schedule-selected-server-invalid-chip"
                      >
                        <span class="invalid-name">{{ name }}</span>
                        <span class="invalid-tag" aria-label="已失效">已失效</span>
                        <button
                          type="button"
                          class="chip-remove"
                          :aria-label="`移除已选服务器 ${name}`"
                          @click="removeSelectedServerByName(name)"
                        >
                          ×
                        </button>
                      </span>
                    </div>
                  </section>
                </template>
                <template v-else-if="paramKey === 'api_list'">
                  <!-- api_list 多选控件（系统级标准参数：候选来自「API接口配置」树） -->
                  <section class="server-list-panel api-list-panel" data-testid="schedule-param-api-list" :aria-label="`参数 ${paramKey}`">
                    <header class="script-param-item__head">
                      <div>
                        <strong>{{ supportedScriptParamDefinitions.find((d) => d.key === paramKey)?.def.title || paramKey }}</strong>
                        <span class="script-param-item__key">{{ paramKey }}</span>
                      </div>
                      <button
                        type="button"
                        class="link-btn"
                        :data-testid="`schedule-remove-param-${paramKey}`"
                        :aria-label="`移除参数 ${paramKey}`"
                        @click="removeScriptParam(paramKey)"
                      >
                        移除参数
                      </button>
                    </header>
                    <p
                      v-if="supportedScriptParamDefinitions.find((d) => d.key === paramKey)?.def.description"
                      class="script-param-item__desc"
                    >
                      {{ supportedScriptParamDefinitions.find((d) => d.key === paramKey).def.description }}
                    </p>

                    <div class="server-list-panel__toolbar">
                      <input
                        v-model="apiKeyword"
                        type="search"
                        class="server-search"
                        placeholder="搜索接口名或路径..."
                        aria-label="搜索接口"
                        data-testid="schedule-api-search"
                      />
                      <div class="server-list-panel__actions">
                        <button
                          type="button"
                          class="link-btn"
                          :disabled="!filteredApiCandidates.length"
                          aria-label="全选当前过滤接口"
                          @click="selectAllVisibleApis"
                        >
                          全选
                        </button>
                        <span class="divider" aria-hidden="true"></span>
                        <button
                          type="button"
                          class="link-btn"
                          :disabled="selectedApiCount === 0"
                          aria-label="清空已选接口"
                          @click="clearAllSelectedApis"
                        >
                          清空
                        </button>
                      </div>
                      <span
                        class="server-counter"
                        :class="{ active: selectedApiCount > 0 }"
                        aria-label="已选接口计数"
                      >
                        已选 <strong>{{ selectedApiCount }}</strong> /
                        {{ filteredApiCandidates.length }}
                      </span>
                    </div>

                    <div
                      v-if="isLoadingApis && !hasLoadedApis"
                      class="empty-state"
                      data-testid="schedule-api-list-loading"
                    >
                      正在加载接口列表...
                    </div>
                    <div
                      v-else-if="apiListErrorMessage && !isLoadingApis"
                      class="alert error"
                      role="alert"
                      data-testid="schedule-api-list-error"
                    >
                      <span>{{ apiListErrorMessage }}</span>
                      <button
                        type="button"
                        class="link-btn"
                        :data-testid="'schedule-api-list-retry'"
                        aria-label="重新加载接口"
                        @click="loadApiConfigTree({ force: true })"
                      >
                        重新加载接口
                      </button>
                    </div>
                    <div
                      v-else-if="hasLoadedApis && !apiCandidates.length"
                      class="empty-state"
                      data-testid="schedule-api-list-empty"
                    >
                      暂无已配置的接口，请先在「API接口配置」中创建。
                    </div>

                    <ul
                      v-if="filteredApiCandidates.length"
                      class="server-options"
                      role="listbox"
                      aria-multiselectable="true"
                      aria-label="已配置 API 接口候选列表"
                      data-testid="schedule-api-options"
                    >
                      <li
                        v-for="row in filteredApiCandidates"
                        :key="row.id"
                        class="server-option"
                        :class="{ selected: isApiSelected(row.id) }"
                      >
                        <label class="server-option__label">
                          <input
                            type="checkbox"
                            :checked="isApiSelected(row.id)"
                            :data-testid="`schedule-api-option-${row.id}`"
                            @change="toggleApiSelection(row, $event.target.checked)"
                          />
                          <span class="server-option__main">{{ row.name }}</span>
                          <span class="server-option__meta">{{ row.path || '根目录' }}</span>
                        </label>
                      </li>
                    </ul>
                    <div
                      v-if="!filteredApiCandidates.length && apiKeyword.trim() && apiCandidates.length"
                      class="empty-state"
                      data-testid="schedule-api-list-no-match"
                    >
                      没有匹配「{{ apiKeyword }}」的接口
                    </div>

                    <div
                      v-if="selectedValidApiRows.length || selectedInvalidApiIds.length"
                      class="selected-server-chips"
                      aria-label="已选接口列表"
                      data-testid="schedule-selected-api-list"
                    >
                      <span
                        v-for="entry in selectedValidApiRows"
                        :key="`valid-${entry.row.id}-${entry.id}`"
                        class="chip selected-server-chip"
                        :data-testid="`schedule-selected-api-chip-${entry.row.id}`"
                      >
                        <span>{{ entry.row.name }}</span>
                        <button
                          type="button"
                          class="chip-remove"
                          :aria-label="`移除已选接口 ${entry.row.name}`"
                          @click="removeSelectedApiById(entry.id)"
                        >
                          ×
                        </button>
                      </span>
                      <span
                        v-for="rawId in selectedInvalidApiIds"
                        :key="`invalid-${rawId}`"
                        class="chip selected-server-chip invalid"
                        data-testid="schedule-selected-api-invalid-chip"
                      >
                        <span class="invalid-name">{{ rawId }}</span>
                        <span class="invalid-tag" aria-label="已失效">已失效</span>
                        <button
                          type="button"
                          class="chip-remove"
                          :aria-label="`移除已选接口 ${rawId}`"
                          @click="removeSelectedApiById(rawId)"
                        >
                          ×
                        </button>
                      </span>
                    </div>
                  </section>
                </template>
                <!--
                  注意：故意不提供 v-else 分支。当前 supportedScriptParamDefinitions
                  显式枚举 server_list 与 api_list 两种控件；任何被识别进入
                  addedScriptParamKeys 的 key 必然命中上面 v-if / v-else-if 分支并
                  渲染对应控件。若未来新增受支持控件，必须同步在识别函数中显式
                  枚举并在模板中加入对应分支。
                -->
              </div>
            </div>

            <!-- 添加参数下拉：始终保持 DOM 存在（testid 已添加参数下拉），仅在可用项为空时显示提示 -->
            <div
              v-if="supportedScriptParamDefinitions.length"
              class="add-script-param"
            >
              <label class="add-script-param__label">
                <span>添加参数</span>
                <span
                  v-if="!availableScriptParams.length"
                  id="schedule-add-script-param-empty-hint"
                  class="add-script-param__hint"
                  data-testid="schedule-add-script-param-empty"
                >
                  已添加当前脚本所有受支持参数。
                </span>
                <select
                  class="add-script-param__select"
                  data-testid="schedule-add-script-param"
                  :value="''"
                  aria-label="添加脚本参数"
                  aria-describedby="schedule-add-script-param-empty-hint"
                  :disabled="!availableScriptParams.length"
                  @change="addScriptParam($event.target.value); $event.target.value = ''"
                >
                  <option value="" disabled selected>请选择要添加的参数</option>
                  <option v-for="p in availableScriptParams" :key="p.key" :value="p.key">
                    {{ p.label }}
                  </option>
                </select>
              </label>
            </div>
            <div v-else-if="!currentScript" class="empty-state">
              请先选择脚本以加载参数定义。
            </div>
          </div>
          <!-- 脚本任务专属：邮件通知启用状态与策略选择，同处两列容器 -->
          <div v-if="form.target_type === 'script'" class="notify-fields">
            <label class="form-field">
              <span>启用邮件通知</span>
              <select
                v-model="form.notify_enabled"
                data-testid="schedule-notify-enabled"
                @change="onNotifyEnabledChange(form.notify_enabled)"
              >
                <option :value="false">不启用</option>
                <option :value="true">启用</option>
              </select>
            </label>
            <label v-if="form.notify_enabled" class="form-field">
              <span>邮件策略 *</span>
              <select
                v-model="form.notify_policy_id"
                data-testid="schedule-notify-policy"
                :disabled="isLoadingEmailPolicies"
              >
                <option :value="null" disabled>
                  {{ isLoadingEmailPolicies ? '加载中…' : '请选择策略' }}
                </option>
                <option v-for="p in emailPolicies" :key="p.id" :value="p.id">
                  {{ p.name }}（{{ p.recipient_count }} 个收件人）
                </option>
              </select>
            </label>
          </div>
          <label class="form-field full">
            <span>描述</span>
            <input v-model="form.description" type="text" placeholder="可选：说明该任务的用途" />
          </label>
          <label v-if="form.target_type === 'agent'" class="form-field full">
            <span>context_overrides JSON</span>
            <textarea v-model="contextJson" rows="4" placeholder='{}'></textarea>
          </label>
          <label class="inline-field">
            <input v-model="form.enabled" type="checkbox" />
            <span>保存后启用任务</span>
          </label>
        </form>
      </section>

      <!-- 服务器扫描 Tab —— v-else-if 互斥挂载，理由同任务 Tab -->
      <section
        v-else-if="activeTab === TAB_SCAN"
        :id="`panel-${TAB_SCAN}`"
        role="tabpanel"
        aria-labelledby="tab-scan"
        data-testid="panel-scan"
      >
        <header class="detail-header">
          <div>
            <h3>服务器扫描入库</h3>
            <p>仅展示脱敏字段（业务名 / 类型 / 更新时间），敏感信息不会显示在前端。</p>
          </div>
          <div class="actions">
            <button
              type="button"
              class="primary-btn"
              data-testid="scan-servers-btn"
              :disabled="isScanning"
              :aria-busy="isScanning ? 'true' : 'false'"
              @click="triggerServerScan"
            >
              <span v-if="isScanning" data-testid="scan-loading">扫描中...</span>
              <span v-else>立即扫描</span>
            </button>
          </div>
        </header>

        <div
          v-if="scanErrorMessage"
          class="alert error"
          role="alert"
          data-testid="scan-error"
        >
          {{ scanErrorMessage }}
        </div>
        <div
          v-if="listErrorMessage"
          class="alert error"
          role="alert"
          data-testid="list-error"
        >
          {{ listErrorMessage }}
        </div>
        <div
          v-if="scanSuccessMessage"
          class="alert success"
          data-testid="scan-status"
        >
          {{ scanSuccessMessage }}
        </div>

        <div
          v-if="scanSummary"
          class="alert info summary"
          data-testid="scan-summary"
        >
          <span data-testid="summary-scanned">扫描 {{ scanSummary.scanned }}</span>
          <span data-testid="summary-inserted">新增 {{ scanSummary.inserted }}</span>
          <span data-testid="summary-updated">更新 {{ scanSummary.updated }}</span>
          <span data-testid="summary-failed">失败 {{ scanSummary.failed }}</span>
        </div>

        <div v-if="isLoadingServers" class="empty-state" data-testid="scan-loading-list">
          正在加载服务器列表...
        </div>

        <div
          v-else-if="!devopsServers.length"
          class="empty-state"
          data-testid="scan-empty"
        >
          暂无可入库的服务器
        </div>

        <table
          v-else
          class="server-table"
          data-testid="server-table"
          aria-label="DevOps 服务器列表（脱敏）"
        >
          <thead>
            <tr>
              <th scope="col">业务名</th>
              <th scope="col">系统类型</th>
              <th scope="col">最近同步</th>
              <th scope="col">白名单</th>
              <th scope="col">巡检脚本</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in devopsServers"
              :key="row.id"
              :data-testid="`server-row-${row.id}`"
            >
              <td>{{ row.business_name }}</td>
              <td>{{ row.server_type }}</td>
              <td>{{ row.updated_at }}</td>
              <td class="server-action-cell">
                <button
                  type="button"
                  class="server-detail-btn"
                  :data-testid="`server-whitelist-btn-${row.id}`"
                  :aria-label="`查看 ${row.business_name} 的白名单命令`"
                  @click="openWhitelistDialog(row)"
                >
                  查看白名单
                </button>
              </td>
              <td class="server-action-cell">
                <button
                  type="button"
                  class="server-detail-btn"
                  :data-testid="`server-script-btn-${row.id}`"
                  :aria-label="`查看 ${row.business_name} 的巡检脚本`"
                  @click="openScriptDialog(row)"
                >
                  查看脚本
                </button>
              </td>
              <td class="server-action-cell">
                <button
                  type="button"
                  class="server-delete-btn"
                  :data-testid="`server-delete-btn-${row.id}`"
                  :disabled="isDeletingRowId === row.id"
                  :aria-label="`删除服务器 ${row.business_name}`"
                  @click="confirmDeleteServer(row)"
                >
                  <span v-if="isDeletingRowId === row.id">删除中...</span>
                  <span v-else>删除</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 脚本扫描 Tab —— v-else-if 互斥挂载，理由同任务 Tab -->
      <section
        v-else-if="activeTab === TAB_SCRIPT"
        :id="`panel-${TAB_SCRIPT}`"
        role="tabpanel"
        aria-labelledby="tab-script"
        data-testid="panel-script"
      >
        <header class="detail-header">
          <div>
            <h3>脚本扫描入库</h3>
            <p>扫描 app/scripts/ 目录下所有 .py 文件，通过 @register_script 装饰器注册到全局 registry。</p>
          </div>
          <div class="actions">
            <button
              type="button"
              class="primary-btn"
              data-testid="scan-scripts-btn"
              :disabled="isScanningScripts"
              :aria-busy="isScanningScripts ? 'true' : 'false'"
              @click="triggerScriptScan"
            >
              <span v-if="isScanningScripts" data-testid="scan-scripts-loading">扫描中...</span>
              <span v-else>立即扫描</span>
            </button>
          </div>
        </header>

        <div v-if="scriptError" class="alert error" role="alert" data-testid="scan-scripts-error">
          {{ scriptError }}
        </div>
        <div v-if="scriptSuccess" class="alert success" data-testid="scan-scripts-status">
          {{ scriptSuccess }}
        </div>
        <div
          v-if="scanScriptSummary"
          class="alert info summary"
          data-testid="scan-scripts-summary"
        >
          <span data-testid="script-summary-scanned">扫描 {{ scanScriptSummary.scanned }}</span>
          <span data-testid="script-summary-registered">注册 {{ scanScriptSummary.registered }}</span>
          <span data-testid="script-summary-failed">失败 {{ scanScriptSummary.failed }}</span>
        </div>

        <div v-if="isLoadingScripts" class="empty-state" data-testid="scan-scripts-loading-list">
          正在加载脚本列表...
        </div>
        <div v-else-if="!scripts.length" class="empty-state" data-testid="scan-scripts-empty">
          暂无已注册脚本，点击「立即扫描」加载。
        </div>
        <table v-else class="data-table" data-testid="script-table">
          <thead>
            <tr>
              <th scope="col">脚本名</th>
              <th scope="col">显示名</th>
              <th scope="col">描述</th>
              <th scope="col">模块路径</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in scripts"
              :key="s.name"
              :data-testid="`script-row-${s.name}`"
            >
              <td>{{ s.name }}</td>
              <td>{{ s.display_name }}</td>
              <td>{{ s.description }}</td>
              <td>{{ s.module_path }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- API 接口配置 Tab —— v-else-if 互斥挂载，理由同任务 Tab -->
      <section
        v-else-if="activeTab === TAB_API"
        :id="`panel-${TAB_API}`"
        role="tabpanel"
        aria-labelledby="tab-api"
        data-testid="panel-api"
        class="task-panel-api"
      >
        <ApiConfigManager />
      </section>
    </main>
  </section>

  <Teleport to="body">
    <Transition name="task-history-fade">
      <div
        v-if="historySchedule"
        class="task-history-overlay"
        @click.self.stop="closeHistory"
      >
        <div
          class="task-history-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="task-history-dialog-title"
          @click.stop
        >
          <header class="task-history-dialog-header">
            <h3 id="task-history-dialog-title">执行历史 - {{ historySchedule.name }}</h3>
            <button
              class="task-history-close"
              type="button"
              aria-label="关闭执行历史"
              @click="closeHistory"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                <path d="M15 5 5 15M5 5l10 10" />
              </svg>
            </button>
          </header>
          <div class="task-history-dialog-body" aria-live="polite">
            <section class="run-history">
              <div v-if="isLoadingRuns" class="empty-state">正在加载执行历史...</div>
              <div v-else-if="historyErrorMessage" class="alert error" data-testid="task-history-error">
                {{ historyErrorMessage }}
              </div>
              <div v-else-if="!runs.length" class="empty-state">暂无执行记录</div>
              <div v-else v-for="run in runs" :key="run.id" class="run-item">
                <div class="run-main">
                  <strong>{{ run.status }}</strong>
                  <span>{{ run.trigger_type }}</span>
                  <span>{{ run.created_at || run.started_at }}</span>
                </div>
                <p v-if="run.output_text">{{ run.output_text }}</p>
                <p v-if="run.error_message" class="run-error">{{ run.error_message }}</p>
              </div>
            </section>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 白名单弹窗（2026-07-22 新增） -->
  <Teleport to="body">
    <Transition name="task-history-fade">
      <div
        v-if="whitelistDialog.open"
        class="task-history-overlay"
        data-testid="whitelist-dialog"
        @click.self.stop="closeWhitelistDialog"
      >
        <div
          class="task-history-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="whitelist-dialog-title"
          @click.stop
        >
          <header class="task-history-dialog-header">
            <h3 id="whitelist-dialog-title">
              白名单 - {{ whitelistDialog.row?.business_name || '' }}
            </h3>
            <button
              class="task-history-close"
              type="button"
              aria-label="关闭白名单"
              data-testid="whitelist-dialog-close"
              @click="closeWhitelistDialog"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                <path d="M15 5 5 15M5 5l10 10" />
              </svg>
            </button>
          </header>
          <div class="task-history-dialog-body">
            <div v-if="whitelistDialog.loading" class="empty-state" data-testid="whitelist-dialog-loading">
              正在加载白名单...
            </div>
            <div v-else-if="whitelistDialog.error" class="alert error" data-testid="whitelist-dialog-error">
              {{ whitelistDialog.error }}
            </div>
            <div
              v-else-if="!whitelistDialog.detail?.whitelist?.length"
              class="empty-state"
              data-testid="whitelist-dialog-empty"
            >
              暂无白名单命令
            </div>
            <table
              v-else
              class="whitelist-table"
              data-testid="whitelist-table"
            >
              <thead>
                <tr>
                  <th scope="col" style="width: 64px">序号</th>
                  <th scope="col">命令</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(cmd, idx) in whitelistDialog.detail.whitelist"
                  :key="`${whitelistDialog.row.id}-${idx}`"
                  :data-testid="`whitelist-row-${idx}`"
                >
                  <td>{{ idx + 1 }}</td>
                  <td><code class="whitelist-cmd">{{ cmd }}</code></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 巡检脚本弹窗（2026-07-22 新增） -->
  <Teleport to="body">
    <Transition name="task-history-fade">
      <div
        v-if="scriptDialog.open"
        class="task-history-overlay"
        data-testid="script-dialog"
        @click.self.stop="closeScriptDialog"
      >
        <div
          class="task-history-dialog task-history-dialog-wide"
          role="dialog"
          aria-modal="true"
          aria-labelledby="script-dialog-title"
          @click.stop
        >
          <header class="task-history-dialog-header">
            <h3 id="script-dialog-title">
              巡检脚本 - {{ scriptDialog.row?.business_name || '' }}
              <small
                v-if="scriptDialog.detail?.inspection_parser"
                class="script-parser-tag"
                data-testid="script-parser-tag"
              >
                解析器: {{ scriptDialog.detail.inspection_parser }}
              </small>
            </h3>
            <button
              class="task-history-close"
              type="button"
              aria-label="关闭巡检脚本"
              data-testid="script-dialog-close"
              @click="closeScriptDialog"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                <path d="M15 5 5 15M5 5l10 10" />
              </svg>
            </button>
          </header>
          <div class="task-history-dialog-body">
            <div v-if="scriptDialog.loading" class="empty-state" data-testid="script-dialog-loading">
              正在加载脚本...
            </div>
            <div v-else-if="scriptDialog.error" class="alert error" data-testid="script-dialog-error">
              {{ scriptDialog.error }}
            </div>
            <div
              v-else-if="!scriptDialog.detail?.inspection_script"
              class="empty-state"
              data-testid="script-dialog-empty"
            >
              未配置巡检脚本
            </div>
            <pre
              v-else
              class="script-content"
              data-testid="script-content"
              :aria-label="`${scriptDialog.row?.business_name || ''} 巡检脚本原文`"
            >{{ scriptDialog.detail.inspection_script }}</pre>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.task-scheduler-manager {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 20px;
  min-height: 0;    /* 允许父级 flex 收缩时不破坏滚动约束 */
  min-height: 560px; /* 兜底下限：dialog 视口很小时仍保留最小高度 */
  flex: 1;          /* 沿父级 flex 高度链占满，确保 aside/main 撑到 .dialog-content 可视高度 */
}

.task-sidebar,
.task-detail {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 18px;
  height: 100%;
  min-height: 0;
}

/* 卡片高度被高度链固定后，任务列表超高时在卡片内部滚动，避免溢出卡片边界 */
.task-sidebar {
  overflow-y: auto;
}

.task-detail {
  display: flex;
  flex-direction: column;
}

/* 业务面板（编辑任务 / 服务器扫描 / 脚本扫描）：
   .task-detail 高度被高度链固定，面板必须收缩并在内部滚动，
   否则长表单内容会溢出卡片边界（API 面板由子组件自滚动，见下） */
.task-detail > section[role="tabpanel"]:not(.task-panel-api) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.task-detail > .task-panel-api {
  display: flex;
  flex: 1;
  min-height: 0;
  /* 子组件（ApiConfigManager）已负责内部滚动，这里裁剪防止内容外溢 */
  overflow: hidden;
}

.panel-header,
.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.panel-header h3,
.detail-header h3 {
  margin: 0;
  color: #111827;
  font-size: 18px;
}

.panel-header p,
.detail-header p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.task-item {
  position: relative;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 12px;
  margin-bottom: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}

.task-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.task-select-btn {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  padding: 0 36px 0 0;
  border: 0;
  color: inherit;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.task-select-btn:focus-visible,
.task-history-btn:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.task-history-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid #d1d5db;
  border-radius: 7px;
  color: #4b5563;
  background: #ffffff;
  cursor: pointer;
}

.task-history-btn:hover {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
}

.task-history-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.task-history-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.task-name {
  color: #111827;
  font-weight: 600;
}

.task-agent,
.task-cron {
  color: #4b5563;
  font-size: 12px;
}

.task-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}

.task-status.enabled {
  color: #047857;
  background: #d1fae5;
}

.task-status.disabled {
  color: #6b7280;
  background: #f3f4f6;
}

.task-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-field,
.inline-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #374151;
  font-size: 13px;
}

.inline-field {
  flex-direction: row;
  align-items: center;
  gap: 4px;
  justify-self: start;
}

.inline-field input[type="checkbox"] {
  width: auto;
  flex: 0 0 auto;
  margin: 0;
}

.inline-field span {
  white-space: nowrap;
}

.form-field.full,
.notify-fields {
  grid-column: 1 / -1;
}

.notify-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 14px;
  color: #111827;
  background: #ffffff;
}

textarea {
  resize: vertical;
}

input[type="number"] {
  width: auto;
  min-width: 80px;
}

.time-input {
  display: flex;
  align-items: center;
  gap: 6px;
}

.time-input select {
  width: auto;
  min-width: 70px;
}

.time-sep {
  color: #374151;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.primary-btn,
.secondary-btn,
.danger-btn {
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-weight: 600;
}

.primary-btn {
  color: #ffffff;
  background: #2563eb;
}

.primary-btn:disabled,
.primary-btn[disabled] {
  background: #93c5fd;
  cursor: not-allowed;
}

.secondary-btn {
  color: #1f2937;
  background: #e5e7eb;
}

.danger-btn {
  color: #ffffff;
  background: #dc2626;
}

.alert {
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
}

.alert.error {
  color: #991b1b;
  background: #fee2e2;
}

.alert.success {
  color: #065f46;
  background: #d1fae5;
}

.alert.info {
  color: #1e3a8a;
  background: #dbeafe;
}

.alert.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  color: #1e40af;
  background: #eff6ff;
}

.empty-state {
  color: #6b7280;
  padding: 16px;
  text-align: center;
}

.task-history-overlay {
  position: fixed;
  inset: 0;
  z-index: 2200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(4px);
}

.task-history-dialog {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 800px;
  max-width: 90vw;
  max-height: 80vh;
  overflow: hidden;
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.task-history-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.task-history-dialog-header h3 {
  margin: 0;
  color: #111827;
  font-size: 18px;
}

.task-history-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  color: #6b7280;
  background: transparent;
  cursor: pointer;
}

.task-history-close:hover {
  color: #111827;
  background: #f3f4f6;
}

.task-history-close:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.task-history-close:active {
  transform: scale(0.96);
}

.task-history-close svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.task-history-dialog-body {
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
}

.task-history-dialog-body .run-history {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.task-history-dialog-body .run-history .empty-state {
  padding: 24px 16px;
}

.task-history-dialog-body .run-item {
  background: #f9fafb;
}

.task-history-fade-enter-active,
.task-history-fade-leave-active {
  transition: opacity 0.2s ease;
}

.task-history-fade-enter-active .task-history-dialog,
.task-history-fade-leave-active .task-history-dialog {
  transition: transform 0.2s ease;
}

.task-history-fade-enter-from,
.task-history-fade-leave-to {
  opacity: 0;
}

.task-history-fade-enter-from .task-history-dialog,
.task-history-fade-leave-to .task-history-dialog {
  transform: scale(0.96);
}

.run-history {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.run-history h4 {
  margin: 0 0 12px;
  color: #111827;
  font-size: 14px;
}

.run-history .empty-state {
  padding: 10px 0;
}

.run-history .alert {
  margin-bottom: 0;
}

.run-item {
  min-width: 0;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: #ffffff;
}

.run-main {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #374151;
  font-size: 13px;
}

.run-item p {
  margin: 6px 0 0;
  color: #374151;
  overflow-wrap: anywhere;
}

.run-error {
  color: #b91c1c !important;
}

.tablist {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 18px;
  flex-shrink: 0; /* flex 列容器内不被压缩，保证 tab 栏始终完整可见 */
}

.tab {
  background: transparent;
  border: 0;
  padding: 10px 14px;
  border-radius: 8px 8px 0 0;
  color: #4b5563;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
}

.tab.active {
  color: #2563eb;
  border-bottom: 2px solid #2563eb;
  background: #eff6ff;
}

.tab:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.server-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
}

.server-table th,
.server-table td {
  border-bottom: 1px solid #e5e7eb;
  padding: 10px 12px;
  text-align: left;
  font-size: 13px;
  color: #111827;
}

.server-table th {
  background: #f9fafb;
  color: #374151;
  font-weight: 600;
}

.server-action-cell {
  text-align: right;
  white-space: nowrap;
}

.server-delete-btn {
  border: 1px solid #dc2626;
  background: #ffffff;
  color: #dc2626;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.server-delete-btn:hover:not(:disabled) {
  background: #fee2e2;
  border-color: #b91c1c;
  color: #b91c1c;
}

.server-delete-btn:disabled {
  opacity: 0.6;
  cursor: wait;
  background: #f3f4f6;
  color: #6b7280;
  border-color: #d1d5db;
}

/* 详情列按钮（白名单 / 巡检脚本）—— 与删除按钮风格统一，按需复用 */
.server-detail-btn {
  border: 1px solid #2563eb;
  background: #ffffff;
  color: #2563eb;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.server-detail-btn:hover {
  background: #dbeafe;
  border-color: #1d4ed8;
  color: #1d4ed8;
}

/* 宽弹窗（脚本） */
.task-history-dialog-wide {
  max-width: 960px;
  width: min(960px, 92vw);
}

/* 白名单命令表格 */
.whitelist-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: #111827;
}

.whitelist-table th,
.whitelist-table td {
  border-bottom: 1px solid #e5e7eb;
  padding: 8px 12px;
  text-align: left;
}

.whitelist-table th {
  background: #f9fafb;
  color: #374151;
  font-weight: 600;
}

.whitelist-cmd {
  font-family: 'Menlo', 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: #1f2937;
  word-break: break-all;
}

/* 巡检脚本原文：保留换行/缩进/等宽字体 */
.script-content {
  margin: 0;
  padding: 16px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  font-family: 'Menlo', 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre;        /* 保留所有空白与换行 */
  overflow: auto;
  max-height: 60vh;        /* 弹窗内可滚动，避免过长撑爆视口 */
  tab-size: 4;
}

.script-parser-tag {
  margin-left: 12px;
  padding: 2px 8px;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  margin-right: 4px;
  font-weight: 600;
}

.badge-agent {
  background: #dbeafe;
  color: #1e40af;
}

.badge-script {
  background: #f3e5f5;
  color: #7b1fa2;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
}

.data-table th,
.data-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
  font-size: 13px;
  color: #111827;
}

.data-table th {
  background: #f9fafb;
  color: #374151;
  font-weight: 600;
}

@media (max-width: 900px) {
  .task-scheduler-manager {
    grid-template-columns: 1fr;
  }
  .notify-fields {
    grid-template-columns: 1fr;
  }
  .tablist {
    flex-wrap: wrap;
  }
  .script-param-list {
    grid-template-columns: 1fr;
  }
  .server-list-panel__toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .server-options {
    grid-template-columns: 1fr;
  }
  .selected-server-chips .chip {
    max-width: 100%;
  }
}

/* ===== 脚本参数 schema-driven 面板样式 ===== */
.script-params {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.script-params__title {
  font-weight: 600;
  color: #111827;
  font-size: 14px;
}

.script-params__hint {
  margin: 0;
  color: #6b7280;
  font-size: 12px;
}

.script-param-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.script-param-item {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
}

.script-param-item__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.script-param-item__head strong {
  color: #111827;
  margin-right: 8px;
}

.script-param-item__key {
  color: #6b7280;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.script-param-item__desc {
  margin: 4px 0 10px;
  color: #4b5563;
  font-size: 12px;
}

.server-list-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.server-list-panel__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.server-search {
  flex: 1 1 200px;
  min-width: 160px;
  height: 32px;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 13px;
  background: #ffffff;
  color: #111827;
}

.server-search:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.server-list-panel__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.link-btn {
  background: none;
  border: 0;
  color: #2563eb;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
}

.link-btn:hover:not(:disabled) {
  text-decoration: underline;
  background: #eff6ff;
}

.link-btn:disabled {
  color: #9ca3af;
  cursor: not-allowed;
  text-decoration: none;
}

.divider {
  width: 1px;
  height: 14px;
  background: #e5e7eb;
}

.server-counter {
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
  padding: 4px 10px;
  background: #f3f4f6;
  border-radius: 999px;
}

.server-counter.active {
  color: #1e3a8a;
  background: #dbeafe;
  font-weight: 600;
}

.server-options {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px;
}

.server-option {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
}

.server-option.selected {
  border-color: #2563eb;
  background: #eff6ff;
}

.server-option__label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 13px;
  color: #111827;
}

.server-option__label input[type='checkbox'] {
  width: auto;
  margin: 0;
  flex: 0 0 auto;
}

.server-option__main {
  flex: 1 1 auto;
  font-weight: 500;
  word-break: break-all;
}

.server-option__meta {
  color: #6b7280;
  font-size: 12px;
  flex: 0 0 auto;
}

.selected-server-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px dashed #e5e7eb;
}

.selected-server-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: #eff6ff;
  color: #1e40af;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  font-size: 12px;
  max-width: 100%;
}

.selected-server-chip.invalid {
  background: #fef2f2;
  color: #991b1b;
  border-color: #fecaca;
}

.selected-server-chip.invalid .invalid-tag {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 999px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
}

.selected-server-chip .chip-remove {
  background: none;
  border: 0;
  color: inherit;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}

.add-script-param {
  display: flex;
  align-items: center;
  gap: 8px;
}

.add-script-param__label {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  width: 100%;
}

.add-script-param__select {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 14px;
  color: #111827;
  background: #ffffff;
}

.add-script-param__hint {
  color: #6b7280;
  font-size: 12px;
}
</style>
