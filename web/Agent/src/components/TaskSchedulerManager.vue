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
import { computed, onMounted, reactive, ref } from 'vue'
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
  fetchScripts,
  scanScripts,
  fetchEmailPolicies,
} from '../utils/api.js'

const TAB_TASK = 'task'
const TAB_SCAN = 'scan'
const TAB_SCRIPT = 'script'

const TAB_LABELS = [
  { id: TAB_TASK, label: '编辑任务' },
  { id: TAB_SCAN, label: '服务器扫描入库' },
  { id: TAB_SCRIPT, label: '脚本扫描入库' },
]

const schedules = ref([])
const agents = ref([])
const runs = ref([])
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

// 脚本扫描状态
const scripts = ref([])
const isLoadingScripts = ref(false)
const isScanningScripts = ref(false)
const scriptError = ref('')
const scriptSuccess = ref('')
const scanScriptSummary = ref(null)
const hasLoadedScripts = ref(false)
const scriptArgsJson = ref('{}')

// 邮件策略状态（仅 script 任务启用邮件通知时按需加载）
const emailPolicies = ref([])
const hasLoadedEmailPolicies = ref(false)
const isLoadingEmailPolicies = ref(false)

// 扫描结果只接受这 4 个数字；任何未知敏感字段都不会进入 DOM
const SUMMARY_FIELDS = ['scanned', 'inserted', 'updated', 'failed']

// 服务器字段白名单：仅显示这些键，绝不显示敏感字段
const SERVER_WHITELIST = ['id', 'business_name', 'server_type', 'updated_at']

// 脚本展示白名单字段：仅显示这些键，绝不显示 func 等内部对象
const SCRIPT_PUBLIC_FIELDS = ['name', 'display_name', 'description', 'module_path']
const SCRIPT_SUMMARY_FIELDS = ['scanned', 'registered', 'failed']

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
 * 脱敏后的服务器列表：仅保留白名单字段，避免 ip/password 等敏感值流入 UI。
 * @param {Array} rows - 后端原始返回数组
 * @returns {Array} 仅含白名单字段的对象数组
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
    .filter((row) => row && row.id !== undefined && row.id !== null)
}

/**
 * 初始化数据。
 * @returns {Promise<void>} 无返回值
 */
async function loadInitialData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [taskRows, agentRows] = await Promise.all([
      fetchTaskSchedules(),
      fetchAdminAgentList(),
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
 * @param {Object} schedule - 定时任务记录
 * @returns {Promise<void>} 无返回值
 */
async function selectSchedule(schedule) {
  selectedSchedule.value = schedule
  isCreating.value = false
  fillForm(schedule)
  await loadRuns(schedule.id)
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
  try {
    runs.value = await fetchTaskRuns(scheduleId, 50)
  } catch (error) {
    errorMessage.value = error.message || '加载执行历史失败'
  }
}

/**
 * 切换 Tab。切到扫描 Tab 时按需加载服务器列表，并仅保留白名单字段。
 * 切到脚本 Tab 时按需加载脚本列表。
 * 切回任务 Tab 时不再触发任何 devops / scripts 请求。
 * 第一次加载完成后置 ``hasLoaded=true`` / ``hasLoadedScripts=true``，之后切回再进入不再重复 GET。
 * @param {string} tabId - TAB_TASK / TAB_SCAN / TAB_SCRIPT
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

/**
 * 加载并脱敏 DevOps 服务器列表。
 * @returns {Promise<void>} 无返回值
 */
async function loadDevopsServers() {
  isLoadingServers.value = true
  listErrorMessage.value = ''
  try {
    const rows = await fetchDevOpsServers()
    devopsServers.value = maskServers(rows)
    hasLoaded.value = true
  } catch {
    listErrorMessage.value = '服务器列表加载失败'
    devopsServers.value = []
  } finally {
    isLoadingServers.value = false
  }
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
 * 扫描成功后刷新列表；任何错误使用脱敏提示。
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
    // 扫描成功后主动刷新服务器列表
    await loadDevopsServers()
  } catch {
    scanErrorMessage.value = '扫描失败，请稍后重试'
  } finally {
    isScanning.value = false
  }
}

/**
 * 加载已注册脚本列表（白名单字段过滤）。
 * 仅保留 SCRIPT_PUBLIC_FIELDS 中的字段，绝不渲染 func 等内部对象。
 * @returns {Promise<void>} 无返回值
 */
async function loadScripts() {
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
  } finally {
    isLoadingScripts.value = false
  }
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
    await loadScripts()
  } catch {
    scriptError.value = '扫描失败，请稍后重试'
  } finally {
    isScanningScripts.value = false
  }
}

/**
 * 目标类型切换时清理无关字段并按需加载脚本列表。
 * 切到 agent 时清空 script_name/script_args；切到 script 时清空 agent_name/prompt。
 */
function onTargetTypeChange() {
  if (form.target_type === 'agent') {
    form.script_name = ''
    form.script_args = {}
    scriptArgsJson.value = '{}'
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
 * @param {Object} schedule - 定时任务记录
 */
function fillForm(schedule) {
  form.name = schedule.name || ''
  form.description = schedule.description || ''
  form.target_type = schedule.target_type || 'agent'
  form.agent_name = schedule.agent_name || enabledAgents.value[0]?.name || ''
  form.prompt = schedule.prompt || ''
  form.script_name = schedule.script_name || ''
  form.script_args = schedule.script_args || {}
  Object.assign(scheduleConfig, parseCronExpression(schedule.cron_expression))
  form.timezone = schedule.timezone || 'Asia/Shanghai'
  form.enabled = schedule.enabled !== false
  form.context_overrides = schedule.context_overrides || {}
  form.max_concurrent_runs = schedule.max_concurrent_runs || 1
  form.notify_enabled = schedule.notify_enabled === true
  form.notify_policy_id = schedule.notify_policy_id || null
  contextJson.value = JSON.stringify(form.context_overrides, null, 2)
  scriptArgsJson.value = JSON.stringify(form.script_args, null, 2)
  // 切换到 script 时按需加载邮件策略
  if (form.target_type === 'script' && form.notify_enabled) {
    loadEmailPolicies()
  }
}

/**
 * 开始创建新任务。
 */
function startCreate() {
  selectedSchedule.value = null
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
  scriptArgsJson.value = '{}'
  errorMessage.value = ''
  successMessage.value = ''
}

/**
 * 构造提交 payload。根据 target_type 分支构造：
 * agent 任务包含 agent_name/prompt；script 任务包含 script_name/script_args。
 * @returns {Object} 后端请求体
 * @throws {Error} context_overrides 或 script_args JSON 非法时抛出
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
    let scriptArgs = {}
    try {
      scriptArgs = scriptArgsJson.value.trim() ? JSON.parse(scriptArgsJson.value) : {}
    } catch {
      throw new Error('脚本参数 JSON 格式不正确')
    }
    payload.script_name = form.script_name
    payload.script_args = scriptArgs
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
    await loadRuns(selectedSchedule.value.id)
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

onMounted(loadInitialData)
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
      <button
        v-for="schedule in schedules"
        :key="schedule.id"
        class="task-item"
        :class="{ active: selectedSchedule && selectedSchedule.id === schedule.id }"
        type="button"
        @click="selectSchedule(schedule)"
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

      <!-- 任务 Tab -->
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
          <div class="actions" v-if="!isCreating && selectedSchedule">
            <button type="button" class="secondary-btn" @click="toggleTask">
              {{ selectedSchedule.enabled ? '停用任务' : '启用任务' }}
            </button>
            <button type="button" class="secondary-btn" @click="runNow">立即运行</button>
            <button type="button" class="danger-btn" @click="removeTask">删除任务</button>
          </div>
        </header>

        <form class="task-form" @submit.prevent="saveTask">
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
            <select v-model="form.script_name" data-testid="schedule-script" :disabled="isLoadingScripts">
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
          <label v-else class="form-field full">
            <span>脚本参数 (JSON)</span>
            <textarea v-model="scriptArgsJson" rows="4" data-testid="schedule-script-args" placeholder='{"greeting":"Hello"}'></textarea>
          </label>
          <!-- 脚本任务专属：邮件通知开关与策略选择 -->
          <template v-if="form.target_type === 'script'">
            <label class="form-field full">
              <span>脚本执行完成后自动发送邮件</span>
              <label class="inline-field">
                <input
                  v-model="form.notify_enabled"
                  type="checkbox"
                  data-testid="schedule-notify-enabled"
                  @change="onNotifyEnabledChange($event.target.checked)"
                />
                <span>启用邮件通知（脚本返回值将作为邮件正文，附件路径取自脚本返回值第二项）</span>
              </label>
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
          </template>
          <label class="form-field full">
            <span>描述</span>
            <input v-model="form.description" type="text" placeholder="可选：说明该任务的用途" />
          </label>
          <label class="form-field full">
            <span>context_overrides JSON</span>
            <textarea v-model="contextJson" rows="4" placeholder='{}'></textarea>
          </label>
          <label class="inline-field">
            <input v-model="form.enabled" type="checkbox" />
            <span>保存后启用任务</span>
          </label>
          <div class="form-actions">
            <button class="primary-btn" type="submit" :disabled="isSaving">
              {{ isSaving ? '保存中...' : '保存任务' }}
            </button>
          </div>
        </form>

        <section class="run-history" v-if="!isCreating">
          <h4>执行历史</h4>
          <div v-if="!runs.length" class="empty-state">暂无执行记录</div>
          <div v-for="run in runs" :key="run.id" class="run-item">
            <div class="run-main">
              <strong>{{ run.status }}</strong>
              <span>{{ run.trigger_type }}</span>
              <span>{{ run.created_at || run.started_at }}</span>
            </div>
            <p v-if="run.output_text">{{ run.output_text }}</p>
            <p v-if="run.error_message" class="run-error">{{ run.error_message }}</p>
          </div>
        </section>
      </section>

      <!-- 服务器扫描 Tab -->
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
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 脚本扫描 Tab -->
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
    </main>
  </section>
</template>

<style scoped>
.task-scheduler-manager {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 20px;
  min-height: 560px;
}

.task-sidebar,
.task-detail {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 18px;
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
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  padding: 12px;
  margin-bottom: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
}

.task-item.active {
  border-color: #2563eb;
  background: #eff6ff;
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

.inline-field span {
  white-space: nowrap;
}

.form-field.full,
.form-actions {
  grid-column: 1 / -1;
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

.actions,
.form-actions {
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

.run-history {
  margin-top: 22px;
}

.run-history h4 {
  margin: 0 0 12px;
  color: #111827;
}

.run-item {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: #f9fafb;
}

.run-main {
  display: flex;
  gap: 12px;
  color: #374151;
  font-size: 13px;
}

.run-item p {
  margin: 6px 0 0;
  color: #374151;
}

.run-error {
  color: #b91c1c !important;
}

.tablist {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 18px;
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
  .tablist {
    flex-wrap: wrap;
  }
}
</style>
