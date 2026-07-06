<script setup>
import { reactive, onMounted, onBeforeUnmount, computed, ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'
import HumanApprovalBox from './components/HumanApprovalBox.vue'
import KnowledgePage from './components/KnowledgePage.vue'
import SubAgentDrawer from './components/SubAgentDrawer.vue'
import QueueStatusBanner from './components/QueueStatusBanner.vue'
// 2026-06-30 新增：项目弹窗
import ProjectDialog from './components/ProjectDialog.vue'
// 2026-07-01 新增：会话文件抽屉与文件预览弹窗
import SessionFileDrawer from './components/SessionFileDrawer.vue'
import FilePreviewModal from './components/FilePreviewModal.vue'
// 2026-07-02 新增：AI 回复点踩反馈弹窗
import DislikeDialog from './components/DislikeDialog.vue'
import {
  chatStream,
  createNewSession,
  logout as apiLogout,
  fetchSessionDetail,
  fetchSessionAttachments,
  fetchSessionMessages,
  validateToken,
  refreshToken,
  clearAuth,
  // 2026-06-30 新增：项目 API
  createProject,
  fetchProjectInfo,
  bindSessionToProject,
  unbindSessionFromProject,
  // 2026-07-01 新增：会话文件空间 API
  fetchSessionFileTree,
  previewSessionFile,
  // 2026-07-02 新增：消息反馈 API
  submitMessageFeedback,
  // 2026-07-06 新增：主动 abort API
  triggerAbort
} from './utils/api.js'
import { isThinkingBlock, tryParsePythonLiteral, extractTextFromBlock, processContentBlocks, parseMessageContent, processSSEEvent, createAiMessage, isSubAgentHistoryItem, convertSubAgentHistoryToAiSubAgent, isSubAgentTool } from './utils/sseParser.js'
import { redirectToLogin, tryRefreshOrRedirect } from './utils/auth.js'

// 2026-06-23 新增：当前激活的智能体名称（与后端 agents 表 name 字段一致）。
// 默认 null，未选择时由后端使用框架默认配置。
const agentName = ref(null)
// 2026-06-26 新增：当前激活的智能体展示名称（中文）
const agentDisplayName = ref('')
const currentPage = ref('agent')
const isLoggedIn = ref(false)
// 认证状态检查是否就绪；用于在 checkAuth 完成前显示 loading 占位，
// 避免因异步资源加载造成"页面内容闪烁两次"的视觉问题
const authReady = ref(false)
const currentUser = ref({ username: '', role: '', userId: null })
// 2026-07-01 新增：当前用户允许使用的智能体名称列表
const allowedAgents = ref([])

const messages = reactive([])
const sessionId = reactive({ value: '' })
const isStreaming = reactive({ value: false })
const sidebarRef = ref(null)
const currentAttachments = ref([])
const approvalMode = ref(false)
const approvalData = ref({ questions: [] })

// 2026-07-01 新增：当前会话标题（用于 ChatArea 顶部显示）
const sessionTitle = ref('')

// 2026-07-01 新增：会话文件抽屉状态
const sessionFileDrawerVisible = ref(false)
const sessionFileTree = ref(null)
const sessionFileDrawerLoading = ref(false)
const sessionFileDrawerError = ref('')

// 2026-07-01 新增：文件预览弹窗状态
const filePreviewOpen = ref(false)
const filePreviewData = ref({
  content: '',
  fileType: 'txt',
  fileName: '',
  loading: false,
  previewMode: 'text',
  fileUrl: ''
})

// 2026-06-30 新增：项目文件夹状态机
//   * currentProject: {id, name, uuid} | null
//   * null = 不使用文件夹（默认 / 旧会话）
const currentProject = ref(null)
const isProjectDialogOpen = ref(false)
const projectDialogMode = ref('create') // 'create' | 'pick'
const projects = ref([]) // pick 模式使用的项目列表缓存
const isProjectMutating = ref(false) // 防止项目切换过程中的并发请求

// 2026-06-15 新增：持有当前 SSE reader，供 InputBox 的 stop 事件调用 cancel() 立即中断 LLM
let currentStreamReader = null

// 2026-07-06 新增：60s 兜底 timer（防止后端工具卡死后锁永远不清）
// 启动：用户点停止 → triggerAbort → 60s timer
// 清理：SSE 白名单事件 / catch / finally / 切会话
// 到期：reader.cancel() + 追加 [工具执行超时] + 提示用户
let stopTimeoutId = null
const STOP_TIMEOUT_MS = 60 * 1000

// 2026-07-06 新增：中断待生效锁（工具/子智能体执行期间用户点击停止按钮后置 true）。
// 状态机：
//   - 置 true：handleStopMessage 入口（重复点击短路）
//   - 置 false（白名单）：SSE end / error / interrupt 事件；SSE 流自然走完（done=true）
//   - 置 false（兜底）：catch（异常）、finally（任何路径兜底）、newSession/handleSessionSwitch/handleApprovalCancel/handleStopMessage 入口前置
// 设计要点：白名单管"已知流走完"，兜底管"未知异常"，互不污染。
// 2026-07-06 修复：必须用 ref() 才能触发模板响应式更新，普通 let 变量 Vue 不会追踪。
const toolStopPending = ref(false)

/**
 * 统一清锁入口（2026-07-06 新增）。所有需要复位的路径都调用此函数，
 * 避免在多处直接赋值 toolStopPending.value = false 时遗漏或不一致。
 * 同时清理 60s 兜底 timer，避免 timer 仍生效导致后续会话异常。
 * @returns {void}
 */
function clearToolStopPending() {
  toolStopPending.value = false
  if (stopTimeoutId !== null) {
    clearTimeout(stopTimeoutId)
    stopTimeoutId = null
  }
}

/**
 * 启动 60s 兜底 timer（2026-07-06 新增）
 *
 * 场景：用户点停止 → triggerAbort 已发出，但后端工具卡在长 I/O（Docker exec 大文件
 * 解压、shell 等待等），abort_event 已 set 但 sandbox 还没感知，前端 SSE 流也没收到
 * 任何事件（不是断流，reader 仍开着）。60s 内若收到白名单事件，clearToolStopPending
 * 会清掉 timer；60s 到期后强制 reader.cancel() + 提示用户。
 *
 * @returns {void}
 */
function startStopTimeout() {
  if (stopTimeoutId !== null) {
    clearTimeout(stopTimeoutId)
  }
  stopTimeoutId = setTimeout(() => {
    stopTimeoutId = null
    // 60s 到期：仍未收到白名单事件，强制清锁 + reader.cancel + 提示
    console.warn('[App] 60s 兜底 timer 到期，强制取消 reader 并清锁')
    if (currentStreamReader) {
      try {
        currentStreamReader.cancel()
      } catch (err) {
        console.warn('[App] 60s 兜底 reader.cancel 异常（可忽略）:', err)
      }
    }
    // 追加超时提示到 AI 消息
    const aiMsg = messages[messages.length - 1]
    if (aiMsg && aiMsg.type === 'ai' && !aiMsg.text?.includes('[工具执行超时')) {
      aiMsg.text = (aiMsg.text || '') + '\n\n[工具执行超时，已强制停止]'
    }
    clearToolStopPending()
    isStreaming.value = false
  }, STOP_TIMEOUT_MS)
}

// 2026-06-14 改造：原 SandboxDrawer 已删除，沙箱数据统一由 SubAgentDrawer 展示
// 2026-06-13 新增：子智能体详情抽屉状态
const subAgentDrawerVisible = ref(false)
const currentSubAgent = ref(null)

// 2026-06-15 新增：排队状态机（SSE queue 事件 / HTTP 429 共同驱动）
// event: 'idle' | 'waiting' | 'ready'
const queueStatus = ref({
  event: 'idle',
  waitingCount: 0,
  activeCount: 0,
  maxConcurrency: 0,
  position: 0,
  timestamp: 0
})
const isQueueBannerVisible = computed(() => queueStatus.value.event === 'waiting')

// 2026-06-22 新增：重置 queueStatus 到初始 idle 状态，避免上一次请求的 ready/idle 残留影响下一次请求
function resetQueueStatus() {
  queueStatus.value = {
    event: 'idle',
    waitingCount: 0,
    activeCount: 0,
    maxConcurrency: 0,
    position: 0,
    timestamp: 0
  }
}

/**
 * 处理 SSE queue 事件：更新 queueStatus 响应式状态
 * @param {Object} data - { type: 'queue', event: 'waiting'|'ready', waiting_count, active_count, max_concurrency, position, timestamp }
 */
function handleQueueEvent(data) {
  if (!data || data.type !== 'queue') return
  queueStatus.value = {
    event: data.event || 'idle',
    waitingCount: Number(data.waiting_count) || 0,
    activeCount: Number(data.active_count) || 0,
    maxConcurrency: Number(data.max_concurrency) || 0,
    position: Number(data.position) || 0,
    timestamp: Number(data.timestamp) || 0
  }
}

/**
 * 处理 HTTP 429：从中提取排队信息并显示 banner（短时显示 3s 后自动淡出）
 * @param {Error} err - 包含 status/detail 的错误对象
 */
function handleQueueError(err) {
  if (!err || err.status !== 429 || !err.detail) return
  const errorTimestamp = Date.now() / 1000
  queueStatus.value = {
    event: 'waiting',
    waitingCount: Number(err.detail.waiting_count) || 1,
    activeCount: Number(err.detail.active_count) || 0,
    maxConcurrency: Number(err.detail.max_concurrency) || 0,
    position: 1,
    timestamp: errorTimestamp
  }
  // HTTP 模式拒绝时不等待，3s 后自动淡出 banner；
  // 仅当 banner 仍是本次 429 触发的（即 timestamp 未被新事件覆盖）时才淡出。
  // 2026-06-15 修复：原代码 `queueStatus.value.timestamp === queueStatus.value.timestamp`
  // 是恒真表达式（自我比较），无意义；改为捕获 errorTimestamp 闭包变量。
  setTimeout(() => {
    if (queueStatus.value.timestamp === errorTimestamp) {
      queueStatus.value = { ...queueStatus.value, event: 'idle' }
    }
  }, 3000)
}

/**
 * 新建任务锁，防止重复创建
 */
let isCreatingNewSession = false

const isEmptyState = computed(() => messages.length === 0)

// 2026-07-01 新增：项目文件夹可编辑性判定（用于锁定项目选择器）
// 派生自 isEmptyState + 历史加载失败标记：
//   * 新建会话（messages 空）→ true，可选择项目
//   * 已发送过消息或历史会话有消息 → false，锁定项目选择器
//   * 历史会话拉取失败 → false，默认锁定（保守策略，避免未知状态下误操作）
const historyLoadFailed = ref(false)
const canEditProject = computed(() => isEmptyState.value && !historyLoadFailed.value)

/**
 * 应用用户数据到当前状态
 * @param {Object} data - 包含 username 和 role
 */
function applyUserData(data) {
  const oldUsername = localStorage.getItem('username')
  if (oldUsername && oldUsername !== data.username) {
    localStorage.removeItem('session_id')
  }
  localStorage.setItem('user_role', data.role)
  localStorage.setItem('username', data.username)
  if (data.user_id) {
    localStorage.setItem('user_id', String(data.user_id))
  }
  currentUser.value = {
    username: data.username,
    role: data.role,
    userId: data.user_id || null
  }
  allowedAgents.value = data.allowed_agents || []
  isLoggedIn.value = true
}

/**
 * 检查本地存储的登录状态
 * 两段式验证：先 refreshToken（查服务端数据库，能实时感知 token 被删除/踢人），
 *            成功后再 validateToken 验证并应用用户数据。
 * 全部失败：调用 redirectToLogin() 携带当前 URL 作为 redirect 参数跳到 /login 入口，
 *          由 /login 上的 LoginView 接管（避免在本入口直接渲染 LoginView 造成"闪烁一次"）。
 *
 * 注意：失败路径**不**置 authReady.value = true；只有成功路径才置，
 *       让 redirectToLogin 触发的整页跳转（到 /login）期间不渲染任何额外内容。
 */
async function checkAuth() {
  const token = localStorage.getItem('auth_token')
  if (!token) {
    // 本地无 token：直接跳到 /login?redirect=/Agent/，由 /login 入口渲染 LoginView
    // 不设置 authReady.value = true，避免在跳转前渲染 LoginView 造成"占位→LoginView"切换
    redirectToLogin({ reason: 'checkAuth_no_token' })
    // 清掉残留 user_role/username 等本地信息，确保状态完全干净
    clearAuth()
    return
  }
  try {
    // 先尝试 refresh：refresh 会查服务端数据库，能实时感知 token 被删除/踢人
    const newToken = await refreshToken()
    localStorage.setItem('auth_token', newToken)
    const data = await validateToken()
    const savedUserId = localStorage.getItem('user_id')
    if (savedUserId && savedUserId !== 'null' && savedUserId !== 'undefined') {
      data.user_id = parseInt(savedUserId, 10)
    }
    applyUserData(data)
    // 已登录：标记为就绪，Vue 将渲染主应用
    authReady.value = true
  } catch {
    // refresh 或 validate 失败（典型场景：被 admin 强制下线后 refresh_token 已被服务端删除）
    // 清除本地 token，跳到 /login?redirect=/Agent/，由 /login 入口渲染 LoginView
    // 注意：失败路径**不**置 authReady.value = true，避免在跳转前渲染 LoginView
    clearAuth()
    redirectToLogin({ reason: 'checkAuth_refresh_failed' })
  }
}

// 兜底：若 checkAuth 在 5 秒内未完成，强制将 authReady 置为 true，
// 避免网络异常等极端情况下页面卡死在 loading 占位
// 2026-07-XX：原实现在模块顶层注册 setTimeout，全量 vitest 跑时（>400 个 mount(App, ...)）
// 偶发触发 5s 单测超时；改用模块级 ref 持有 timer id，组件 unmount 时清理。
let authReadyFallbackTimer = null


/**
 * 处理登出事件
 * 清除本地缓存并返回登录页
 */
async function handleLogout() {
  await apiLogout()
  isLoggedIn.value = false
  currentUser.value = { username: '', role: '', userId: null }
  localStorage.removeItem('user_id')
  localStorage.removeItem('session_id')
  localStorage.removeItem('knowledge_session_id')
  messages.splice(0, messages.length)
  sessionId.value = ''
  redirectToLogin({ reason: 'user_logout' })
}

/**
 * 处理用户名更新事件
 * @param {Object} data - 包含新用户名的数据
 */
function handleUsernameUpdated(data) {
  currentUser.value.username = data.username
  localStorage.setItem('username', data.username)
}

/**
 * 2026-07-01 新增：刷新当前会话标题
 * 从会话详情接口获取 title 并同步到 sessionTitle
 * @param {string} id - 会话 ID
 */
async function refreshSessionTitle(id) {
  if (!id) {
    sessionTitle.value = ''
    return
  }
  try {
    const detail = await fetchSessionDetail(id)
    sessionTitle.value = detail.title || '新对话'
  } catch (err) {
    console.warn('[App] 刷新会话标题失败:', err)
    sessionTitle.value = '新对话'
  }
}

/**
 * 2026-07-XX 新增：按需创建 session。
 * 仅在需要后端 session 的入口（首次发送 / 首次上传 / 首次斜杠命令）前调用；
 * 项目选择本身不触发 session 创建，只在首次需要后端时附带当前 projectId 一并绑定。
 * 内部使用 createNewSession 自带的 isCreatingSession / pendingSessionPromise 防重复锁，
 * 并发场景下不会触发多次 /api/session/create。
 * @param {number|null} projectId - 关联的项目 ID；None 表示不使用文件夹（默认）
 * @returns {Promise<string>} 当前有效的 session_id
 * @throws {Error} 创建会话失败时抛出错误（由调用方决定如何兜底）
 */
async function ensureSessionForFirstOp(projectId) {
  if (sessionId.value) return sessionId.value
  const newId = await createNewSession('session_id', projectId)
  sessionId.value = newId
  // 2026-07-XX 新增：同步新会话标题，避免 ChatArea 顶部空白 / 占位
  sessionTitle.value = '新对话'
  refreshSessionTitle(newId)
  if (sidebarRef.value) {
    sidebarRef.value.loadSessionList()
  }
  return newId
}

onMounted(async () => {
  // 仅做认证检查；不再自动建 session。
  // 2026-07-XX 改造：用户需求是"只有上传文件 / 单击发送时才建 session"，
  // 首次进入页面保持 sessionId 为空，避免空 session 写入 DB；
  // 侧边栏在首次交互前不显示任何"新对话"条目与高亮项。
  await checkAuth()
  // 2026-07-XX：5s 兜底 timer 改在 onMounted 中注册 + onBeforeUnmount 清理，
  // 避免全量 vitest 跑时（>400 mount）模块顶层 setTimeout 偶发触发 5s 单测超时。
  authReadyFallbackTimer = setTimeout(() => {
    if (!authReady.value) {
      authReady.value = true
    }
    authReadyFallbackTimer = null
  }, 5000)
})

// 2026-07-XX：组件卸载时清理兜底 timer，避免泄漏 + 防止跨测试污染。
onBeforeUnmount(() => {
  if (authReadyFallbackTimer) {
    clearTimeout(authReadyFallbackTimer)
    authReadyFallbackTimer = null
  }
})

async function newSession() {
  // 防止重复创建
  if (isCreatingNewSession) {
    console.log('[newSession] 正在重置中，跳过重复请求')
    return
  }

  // 2026-06-22 修复：新建会话前先取消当前 SSE 并复位 isStreaming，避免旧连接卡住状态
  if (currentStreamReader) {
    try {
      await currentStreamReader.cancel()
    } catch (err) {
      console.warn('[App] 新建会话 reader.cancel 异常（可忽略）:', err)
    }
    currentStreamReader = null
  }
  isStreaming.value = false
  // 2026-07-06 新增：入口前置清锁（避免脏状态延续到下一次会话）
  clearToolStopPending()
  resetQueueStatus()
  approvalMode.value = false

  isCreatingNewSession = true
  // 2026-07-XX 改造：点击"新建任务"改为纯前端重置，不再立刻调后端建 session；
  // session 的实际创建延后到 ensureSessionForFirstOp：首次发送 / 首次上传 / 首次斜杠命令时。
  console.log('[newSession] 重置前端页面状态（不建 session）')

  try {
    // 2026-07-XX：先清掉 sessionId 与 localStorage，避免下游 upload/chat 接口误用旧 session。
    // 此时并不重新创建 session，留待首次需要时由 ensureSessionForFirstOp 按需建。
    localStorage.removeItem('session_id')
    sessionId.value = ''
    messages.splice(0, messages.length)
    currentAttachments.value = []
    agentName.value = null
    agentDisplayName.value = ''

    // 2026-07-01 新增：新建会话时重置历史加载失败标记（保守锁定策略失效，新会话允许选择项目）
    historyLoadFailed.value = false

    // 关闭子智能体详情抽屉：避免上一个会话的 subagent 数据残留在 UI 上
    closeSubAgentDrawer()
    // 2026-07-01 新增：关闭上一个会话的文件抽屉，避免残留
    closeSessionFileDrawer()

    // 2026-07-XX：当前实现下"会话标题"无值（session 还没建），ChatArea 顶部自然走占位分支，
    // 此处显式置空保持语义清晰
    sessionTitle.value = ''
    console.log('[newSession] 前端态已清空，等待首次交互触发 ensureSessionForFirstOp')
  } finally {
    isCreatingNewSession = false
  }
}

/**
 * 2026-06-30 新增：项目工作下拉框事件处理
 * 2026-07-06 修正：项目是独立实体，选择/创建/解绑项目不再以 sessionId 为前提。
 *   - 无 session 时只更新前端 currentProject 状态；
 *   - 有 session 时才调用 bind/unbind 同步当前会话的项目关联。
 *
 * 注意：
 *   - 切项目会清空已选文件 + 已上传附件（跨项目隔离）
 *   - 当前会话已存在的附件由后端从旧 stored_path 读取，前端只更新 UI 状态
 */
async function handleProjectSelectNone() {
  if (isProjectMutating.value) return
  isProjectMutating.value = true
  try {
    // 2026-07-06 修复：项目是独立实体，无 session 时只更新前端状态，不强制创建 session
    if (sessionId.value) {
      await unbindSessionFromProject(sessionId.value)
    }
    currentProject.value = null
    currentAttachments.value = []
  } catch (err) {
    console.error('解除项目关联失败:', err)
    alert(`解除项目关联失败：${err.message}`)
  } finally {
    isProjectMutating.value = false
  }
}

async function handleProjectPick(project) {
  if (isProjectMutating.value) return
  isProjectMutating.value = true
  try {
    // 2026-07-06 修复：项目是独立实体，选择项目不依赖 sessionId；已有 session 时同步绑定
    if (sessionId.value) {
      await bindSessionToProject(sessionId.value, project.id)
    }
    currentProject.value = project
    currentAttachments.value = []
  } catch (err) {
    console.error('切换项目失败:', err)
    alert(`切换项目失败：${err.message}`)
  } finally {
    isProjectMutating.value = false
  }
}

async function handleProjectCreate({ name }) {
  if (isProjectMutating.value) return
  isProjectMutating.value = true
  try {
    // 2026-07-06 修复：项目是独立实体，创建项目不再使用 session_id 作为 uuid
    const result = await createProject(name)
    const project = result.project
    // 已有 session 时自动绑定到该项目；无 session 时仅更新前端状态
    if (sessionId.value) {
      await bindSessionToProject(sessionId.value, project.id)
    }
    currentProject.value = project
    currentAttachments.value = []
  } catch (err) {
    console.error('创建项目失败:', err)
    alert(`创建项目失败：${err.message}`)
  } finally {
    isProjectMutating.value = false
  }
}

function openCreateProjectDialog() {
  projectDialogMode.value = 'create'
  isProjectDialogOpen.value = true
}

async function openPickProjectDialog() {
  projectDialogMode.value = 'pick'
  isProjectDialogOpen.value = true
}

/**
 * 通过 session detail 恢复项目选择
 */
async function restoreProjectFromDetail(detail) {
  const projectId = detail.project_id
  if (projectId) {
    try {
      const data = await fetchProjectInfo(projectId)
      currentProject.value = data.project
    } catch (err) {
      console.warn('恢复项目选择失败:', err)
      currentProject.value = null
    }
  } else {
    currentProject.value = null
  }
}

function extractApprovalData(interruptArray) {
  if (!Array.isArray(interruptArray) || interruptArray.length === 0) {
    return { questions: [] }
  }
  const req = interruptArray[0]
  const payload = req.value ?? req
  const questions = payload.questions ?? []
  return { questions }
}

async function handleSendMessage(message, attachments = []) {
  if (!message.trim() && attachments.length === 0) return
  if (isStreaming.value) return

  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message,
    attachments
  }
  messages.push(userMsg)

  const aiMsg = reactive(createAiMessage())
  messages.push(aiMsg)

  // 2026-06-22 修复：发送前重置 queueStatus，避免上一次请求的 ready/idle 残留
  resetQueueStatus()
  let interrupted = false
  // 2026-06-15 改造：reader 提到模块级 currentStreamReader，供 stop 按钮跨函数访问
  currentStreamReader = null
  // 2026-07-06 新增：入口前置清锁（兜底层；正常路径下 toolStopPending 已是 false）
  clearToolStopPending()

  try {
    // 2026-07-01 新增：把当前会话绑定的项目 ID 通过 context_overrides.project_id 显式传入，
    // 与 sessions.project_id 隐式链路解耦；null 时由 chatStream 内部不写入该键，由 middleware 注入兜底。
    const projectIdForChat = currentProject.value ? currentProject.value.id : null

    // 2026-07-XX 新增：首次发送 / 无 session 时按需创建 session，
    // 复用 createNewSession 自带的防重复锁，并发场景下仅发一次 /api/session/create。
    await ensureSessionForFirstOp(projectIdForChat)

    const stream = await chatStream(sessionId.value, message, attachments, null, agentName.value, projectIdForChat)
    currentStreamReader = stream.getReader()
    // 拿到 SSE reader 后再置位 isStreaming，避免排队/握手阶段状态长期悬空无法复位
    isStreaming.value = true
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await currentStreamReader.read()
      if (done) {
        // 确保消息被标记为已结束
        if (!aiMsg.ended) {
          console.log('[App] Stream done, setting ended = true')
          aiMsg.ended = true
          aiMsg.isThinkingActive = false
        }
        // 2026-07-06 新增：流自然走完 → 复位 toolStopPending（白名单：done 等价 end）
        clearToolStopPending()
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
          // 2026-07-06 新增：白名单复位 toolStopPending（end/error/interrupt）
          // - end: 工具完成+流走完
          // - error: 错误收尾
          // - interrupt: HITL 进入审批（toolStopPending 已无意义，InputBox 不再渲染）
          if (data && (data.type === 'end' || data.type === 'error' || data.type === 'interrupt')) {
            clearToolStopPending()
          }
          // 2026-07-06 新增：识别 abort 真正生效的信号 — tools 节点完成 update
          // 后端 _stream_helper 在 LangGraph yield 包含 ToolMessage 的 tools 节点 update
          // 时就是 abort 真正生效的时刻：工具已主动 return ToolMessage，state 已配对。
          // data 格式：{ type: 'update', data: { 'tools': { 'messages': [ToolMessage, ...] } } }
          if (
            data && data.type === 'update' && data.data &&
            typeof data.data === 'object' &&
            data.data.tools &&
            Array.isArray(data.data.tools.messages) &&
            data.data.tools.messages.length > 0
          ) {
            // 工具节点完成 → 复位 lock（但不重置 isStreaming，等真正的 end 事件）
            clearToolStopPending()
          }
          // 2026-06-15 透传 onQueueEvent 回调（处理排队/衔接事件）
          processSSEEvent(data, aiMsg, { onQueueEvent: handleQueueEvent })
          console.log('[App] After processSSEEvent, downloadInfo:', JSON.stringify(aiMsg.downloadInfo))

          if (aiMsg.interrupt) {
            interrupted = true
            approvalMode.value = true
            approvalData.value = extractApprovalData(aiMsg.interrupt)
            // 2026-06-15 修复 HITL 卡死：主动 cancel reader 让 SSE 连接断开，
            // 配合后端 _stream_with_queue 在 yield interrupt 前调用 release_handle()，
            // 确保许可立即释放，避免 resume 请求卡在 FIFO 队列。
            try {
              await currentStreamReader.cancel()
            } catch (cancelErr) {
              console.warn('[App] reader.cancel 异常（可忽略）:', cancelErr)
            }
            break
          }
        } catch {}
      }
      if (interrupted) break
    }
  } catch (err) {
    console.error('聊天请求错误:', err)
    // 2026-07-06 新增：异常路径兜底复位（避免锁死）
    clearToolStopPending()
    // 2026-06-15 新增：HTTP 429 排队拒绝 → 显示 banner
    if (err && err.status === 429) {
      handleQueueError(err)
      aiMsg.ended = true
      // 2026-06-22 修复：429 错误路径必须复位 isStreaming，避免按钮永久卡死
      isStreaming.value = false
      currentStreamReader = null
      return
    }
    // 401/过期场景：先尝试 refresh_token；失败再跳登录页
    // 不再"看到'未登录'/'过期'字样就清登录态"，避免误踢
    const refreshed = await tryRefreshOrRedirect()
    if (!refreshed) {
      isStreaming.value = false
      currentStreamReader = null
      return
    }
    aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.ended = true
  } finally {
    // 2026-07-06 新增：finally 兜底复位（兜底层；正常路径已被白名单覆盖）
    clearToolStopPending()
    if (!interrupted) {
      isStreaming.value = false
    }
    currentStreamReader = null
  }
}

async function handleApprovalSubmit({ answers }) {
  // 2026-07-XX 防御性兜底：resume 必须在已有 session 的前提下进行，
  // 没有 session 直接退出（用户实际不会到这里，因为触达 HITL 必然经历了 handleSendMessage → 已建 session）。
  if (!sessionId.value) {
    console.warn('[App] handleApprovalSubmit 缺少 sessionId，跳过')
    approvalMode.value = false
    clearToolStopPending()
    return
  }

  approvalMode.value = false
  let interrupted = false

  const aiMsg = messages[messages.length - 1]
  if (!aiMsg || aiMsg.type !== 'ai') {
    isStreaming.value = false
    currentStreamReader = null
    // 2026-07-06 新增：异常路径兜底复位
    clearToolStopPending()
    return
  }

  // 清除上一次的中断状态，避免旧状态导致误触发
  aiMsg.interrupt = null

  const resumeData = { answers }
  // 2026-06-22 修复：resume 前重置 queueStatus
  resetQueueStatus()
  // 2026-06-15 改造：reader 提到模块级 currentStreamReader，供 stop 按钮跨函数访问
  currentStreamReader = null
  // 2026-07-06 新增：入口前置清锁
  clearToolStopPending()

  try {
    // 2026-07-01 新增：resume 时同样把当前项目 ID 显式带入，避免会话中断恢复后丢失项目上下文
    const projectIdForChat = currentProject.value ? currentProject.value.id : null
    const stream = await chatStream(sessionId.value, '', [], resumeData, agentName.value, projectIdForChat)
    currentStreamReader = stream.getReader()
    isStreaming.value = true
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await currentStreamReader.read()
      if (done) {
        if (!aiMsg.ended) {
          aiMsg.ended = true
          aiMsg.isThinkingActive = false
        }
        // 2026-07-06 新增：流自然走完 → 复位
        clearToolStopPending()
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
          // 2026-07-06 新增：白名单复位
          if (data && (data.type === 'end' || data.type === 'error' || data.type === 'interrupt')) {
            clearToolStopPending()
          }
          // 2026-07-06 新增：识别 abort 真正生效的信号 — tools 节点完成 update
          if (
            data && data.type === 'update' && data.data &&
            typeof data.data === 'object' &&
            data.data.tools &&
            Array.isArray(data.data.tools.messages) &&
            data.data.tools.messages.length > 0
          ) {
            clearToolStopPending()
          }
          // 2026-06-15 透传 onQueueEvent 回调（处理排队/衔接事件）
          processSSEEvent(data, aiMsg, { onQueueEvent: handleQueueEvent })

          if (aiMsg.interrupt) {
            interrupted = true
            approvalMode.value = true
            approvalData.value = extractApprovalData(aiMsg.interrupt)
            // 2026-06-15 修复 HITL 卡死：主动 cancel reader（详见 handleSendMessage 注释）
            try {
              await currentStreamReader.cancel()
            } catch (cancelErr) {
              console.warn('[App] resume reader.cancel 异常（可忽略）:', cancelErr)
            }
            break
          }
        } catch {}
      }
      if (interrupted) break
    }
  } catch (err) {
    console.error('Resume 请求错误:', err)
    // 2026-07-06 新增：异常路径兜底复位
    clearToolStopPending()
    // 2026-06-15 新增：HTTP 429 排队拒绝 → 显示 banner
    if (err && err.status === 429) {
      handleQueueError(err)
      aiMsg.ended = true
      // 2026-06-22 修复：429 错误路径必须复位 isStreaming，避免按钮永久卡死
      isStreaming.value = false
      currentStreamReader = null
      return
    }
    aiMsg.error = '恢复执行失败，请稍后重试。'
    aiMsg.ended = true
  } finally {
    // 2026-07-06 新增：finally 兜底复位
    clearToolStopPending()
    if (!interrupted) {
      isStreaming.value = false
    }
    currentStreamReader = null
  }
}

/**
 * 取消问答：退出 approval 模式并重置流状态
 * 2026-07-06 新增：入口前置清锁 toolStopPending（避免脏状态延续）
 */
function handleApprovalCancel() {
  approvalMode.value = false
  clearToolStopPending()
  isStreaming.value = false
  const aiMsg = messages[messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
  }
}

/**
 * 停止 LLM 生成（2026-06-15 新增；2026-07-06 重构）：用户点击停止按钮触发
 * 流程：
 * 1. 加锁 toolStopPending.value = true（重复点击短路，避免 user 重复触发）
 * 2. 调 triggerAbort(sessionId) 通知后端触发 abort_event
 *    - 后端 _stream_helper.py 不依赖 reader.cancel() 检测断开，而是依赖 abort_event
 *    - abort_event 触发后，sandbox 等工具下次 check 时主动构造 ToolMessage 返回
 *    - 走 stopped_by_user 分支：避免 orphan tool_calls（防止下次会话触发 2013 错误）
 * 3. 启动 60s 兜底 timer（防止后端工具卡死时锁永远不清）
 * 4. 标记最后一条 AI 消息 ended = true + 追加「中断中...」提示
 * 5. 不重置 isStreaming —— 按钮继续 stop-pending 模式，由 SSE 白名单事件
 *    （end/error/interrupt/tools 节点完成）触发清锁 + 60s 兜底 timer 兜底
 */
async function handleStopMessage() {
  if (!isStreaming.value) return
  // 2026-07-06 新增：重复点击短路（防止用户在等待工具完成时重复点击）
  if (toolStopPending.value) return

  // 1. 加锁（UI 由 InputBox 的 isStopPending 接收，立即变灰 + 旋转 badge）
  toolStopPending.value = true

  // 2. 通知后端触发 abort_event（不再是 reader.cancel！）
  //    后端会：
  //    - 工具下次 is_set() 检查时感知
  //    - 主动构造 ToolMessage 返回（stopped_by_user 分支）
  //    - LangGraph 正常推进 → yield tools update + end → SSE 自然关闭
  //    前端 reader 保持开启，正常接收所有后续 SSE 事件
  try {
    await triggerAbort(sessionId.value)
  } catch (err) {
    console.warn('[App] triggerAbort 调用失败（继续走 60s 兜底）:', err)
  }

  // 3. 启动 60s 兜底 timer
  startStopTimeout()

  // 4. 标记 AI 消息为「中断中」状态
  const aiMsg = messages[messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
    if (typeof aiMsg.text === 'string' && !aiMsg.text.includes('[中断中')) {
      aiMsg.text = (aiMsg.text || '') + '\n\n[中断中，等待工具完成...]'
    }
  }

  // 5. 不重置 isStreaming —— 由 SSE 流自然走完时复位
}

// 2026-06-13 新增：子智能体抽屉 open/close
// 2026-06-17 新增：再次点击同一 subagent 卡片时关闭抽屉（toggle 行为）；
// 点击不同 subagent 时仍切换抽屉内容。
// subagent 唯一标识使用 toolCallId（同一执行周期内稳定）
function openSubAgentDrawer(subAgent) {
  if (
    subAgentDrawerVisible.value &&
    currentSubAgent.value &&
    subAgent && subAgent.toolCallId &&
    currentSubAgent.value.toolCallId === subAgent.toolCallId
  ) {
    closeSubAgentDrawer()
    return
  }
  // 2026-06-14 改造：原 sandboxDrawerVisible 互斥逻辑已移除（SandboxDrawer 已删除）
  currentSubAgent.value = subAgent
  subAgentDrawerVisible.value = true
}

function closeSubAgentDrawer() {
  subAgentDrawerVisible.value = false
}

function handleTagSelect(tag, index) {
  console.log('选择技能标签:', tag.label)
}

function handleToolAction(action) {
  console.log('工具操作:', action)
}

/**
 * 处理 InputBox 触发的智能体切换事件
 * @param {string|Object|null} payload - 新激活的智能体信息。传对象时包含 name / display_name；传字符串时仅为 name；null 表示取消选择
 */
function handleAgentSwitched(payload) {
  const name = typeof payload === 'string' ? payload : payload?.name
  const displayName = typeof payload === 'string' ? '' : payload?.display_name
  if (agentName.value === name) return
  agentName.value = name || null
  agentDisplayName.value = displayName || ''
  console.log('[App] 智能体已切换为:', name, displayName)
}

function handleRegenerate(aiMessageId) {
  const aiIndex = messages.findIndex(m => m.id === aiMessageId)
  if (aiIndex === -1) return

  let userIndex = -1
  for (let i = aiIndex - 1; i >= 0; i--) {
    if (messages[i].type === 'user') {
      userIndex = i
      break
    }
  }
  if (userIndex === -1) return

  const userMsg = messages[userIndex]
  messages.splice(userIndex, aiIndex - userIndex + 1)
  handleSendMessage(userMsg.content, userMsg.attachments || [])
}

// 2026-07-04 新增：根据 AI 消息 id 回溯最近一条用户消息内容，用于反馈时填充 message_content
function findUserContentByAiMessageId(aiMessageId) {
  const aiIndex = messages.findIndex(m => m.id === aiMessageId)
  if (aiIndex === -1) return ''
  for (let i = aiIndex - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.type === 'user') {
      return typeof m.content === 'string' ? m.content : ''
    }
  }
  return ''
}

function handleLike(id) {
  const msg = messages.find(m => m.id === id)
  if (!msg) return
  submitMessageFeedback({
    session_id: sessionId.value,
    message_id: msg.id,
    feedback_type: 'like',
    message_content: findUserContentByAiMessageId(msg.id),
    ai_reply: msg.content || '',
    agent_name: agentName.value || ''
  })
    .then(() => showToast('感谢您的反馈', 'success'))
    .catch(err => showToast('反馈提交失败：' + (err.message || err), 'error'))
}

// 2026-07-02 新增：踩反馈弹窗状态机
const dislikeDialog = ref({
  visible: false,
  messageId: '',
  sessionId: '',
  messageContent: '',
  aiReply: '',
  agentName: ''
})

// 2026-07-02 新增：轻量 toast 工具（成功/失败提示）
const showToast = (message, type = 'info') => {
  // 优先使用项目已有 toast 工具；如无则降级为 console
  if (typeof window !== 'undefined' && window.__toast) {
    window.__toast(message, type)
    return
  }
  // 兜底：临时 alert（不阻塞主线程）
  // 注意：实际项目里通常有更友好的 toast 组件，这里保证有可见反馈即可
  // eslint-disable-next-line no-alert
  console.log(`[toast:${type}]`, message)
}

function handleDislike(id) {
  const msg = messages.find(m => m.id === id)
  if (!msg) return
  dislikeDialog.value = {
    visible: true,
    messageId: msg.id,
    sessionId: sessionId.value,
    messageContent: findUserContentByAiMessageId(msg.id),
    aiReply: msg.content || '',
    agentName: agentName.value || ''
  }
}

// 2026-07-02 新增：踩反馈成功提交后提示
function handleDislikeSubmitted(feedbackId) {
  showToast('感谢您的反馈，我们会持续改进', 'success')
}

function handleCopy(e) {
  console.log('复制消息:', e.messageId)
}

// 2026-07-01 新增：打开会话文件抽屉
async function handleOpenSessionFileDrawer() {
  // 已打开则关闭（toggle 行为）
  if (sessionFileDrawerVisible.value) {
    closeSessionFileDrawer()
    return
  }

  if (!sessionId.value) {
    sessionFileDrawerError.value = '当前无有效会话'
    sessionFileDrawerVisible.value = true
    return
  }

  sessionFileDrawerVisible.value = true
  sessionFileDrawerLoading.value = true
  sessionFileDrawerError.value = ''
  sessionFileTree.value = null

  try {
    const data = await fetchSessionFileTree(sessionId.value)
    sessionFileTree.value = data.tree || null
  } catch (err) {
    console.error('[App] 获取会话文件树失败:', err)
    sessionFileDrawerError.value = err.message || '获取会话文件树失败'
  } finally {
    sessionFileDrawerLoading.value = false
  }
}

// 2026-07-01 新增：关闭会话文件抽屉
function closeSessionFileDrawer() {
  sessionFileDrawerVisible.value = false
}

// 2026-07-01 新增：点击抽屉内文件时打开预览弹窗
async function handleSessionFileClick(file) {
  const storedPath = file?.stored_path || file?.path || ''
  if (!storedPath || !sessionId.value) return

  filePreviewOpen.value = true
  filePreviewData.value = {
    content: '',
    fileType: file?.file_type || file?.type || 'txt',
    fileName: file?.file_name || file?.name || '文件预览',
    loading: true,
    previewMode: 'text',
    fileUrl: ''
  }

  try {
    const data = await previewSessionFile(sessionId.value, storedPath)
    filePreviewData.value = {
      content: data.content || '',
      fileType: data.type || 'txt',
      fileName: data.file_name || file?.file_name || file?.name || '文件预览',
      loading: false,
      previewMode: data.preview_mode || 'text',
      fileUrl: data.file_url || ''
    }
  } catch (err) {
    console.error('[App] 预览文件失败:', err)
    filePreviewData.value = {
      ...filePreviewData.value,
      content: `预览文件失败：${err.message || '未知错误'}`,
      loading: false,
      previewMode: 'text'
    }
  }
}

// 2026-07-01 新增：关闭文件预览弹窗
function handleCloseFilePreview() {
  filePreviewOpen.value = false
}

function handlePageChange(page) {
  currentPage.value = page
}

/**
 * 切换到历史会话
 * 从后端获取会话详情和历史消息，还原对话内容和附件
 * @param {string} targetSessionId - 目标会话 ID
 */
async function handleSessionSwitch(targetSessionId) {
  if (targetSessionId === sessionId.value) return
  if (isStreaming.value) {
    // 2026-06-22 修复：切换会话时若还在生成中，先取消当前 SSE 并复位状态
    if (currentStreamReader) {
      try {
        await currentStreamReader.cancel()
      } catch (err) {
        console.warn('[App] 切换会话 reader.cancel 异常（可忽略）:', err)
      }
      currentStreamReader = null
    }
    isStreaming.value = false
    // 2026-07-06 新增：入口前置清锁（避免脏状态延续到下一次会话）
    clearToolStopPending()
    resetQueueStatus()
    approvalMode.value = false
  } else {
    // 2026-07-06 新增：非 isStreaming 场景下也清锁（防御性兜底）
    clearToolStopPending()
  }

  // 清空当前消息
  messages.splice(0, messages.length)
  currentAttachments.value = []

  // 2026-07-01 新增：进入新的切换会话前重置历史加载失败标记
  historyLoadFailed.value = false

  // 关闭子智能体详情抽屉：上一个会话的 subagent 详情不应在切换后仍残留
  // 与 newSession() 保持一致行为
  closeSubAgentDrawer()
  // 2026-07-01 新增：切换会话时关闭文件抽屉，避免上一个会话文件树残留
  closeSessionFileDrawer()

  // 切换到新会话
  sessionId.value = targetSessionId
  localStorage.setItem('session_id', targetSessionId)

  try {
    // 获取会话详情（含附件列表）
    const detail = await fetchSessionDetail(targetSessionId)

    // 2026-07-01 新增：同步当前会话标题
    sessionTitle.value = detail.title || '新对话'

    // 2026-06-26 新增：恢复会话绑定的智能体状态
    const boundAgentType = detail.agent_type
    const boundDisplayName = detail.agent_display_name
    if (boundAgentType && boundAgentType !== 'default') {
      agentName.value = boundAgentType
      agentDisplayName.value = boundDisplayName || boundAgentType
    } else {
      agentName.value = null
      agentDisplayName.value = ''
    }

    // 2026-06-30 新增：恢复会话绑定的项目状态
    await restoreProjectFromDetail(detail)

    // 还原附件列表
    if (detail.attachments && detail.attachments.length > 0) {
      currentAttachments.value = detail.attachments.map(a => ({
        filename: a.file_name,
        stored_path: a.stored_path,
        file_type: a.file_type,
        size: a.file_size,
        original_name: a.file_name
      }))
    }

    // 从 LangGraph Checkpoint 获取历史消息
    const history = await fetchSessionMessages(targetSessionId, 100)

    // 还原对话记录到 messages 数组
    if (history.messages && history.messages.length > 0) {
      // 2026-06-16 新增：后端现在会按时序插入 { type: "subagent", thread_id, tool, ... } 元素，
      // 用于反查恢复 sandbox / explore 等子智能体历史。
      // 策略：识别 subagent 元素后，将对应的 subAgent 挂到上一个 ai 消息的 subAgents 列表中，
      // 并在 MessageBubble 中按 SubAgentCard 渲染。老客户端 / 老代码不识别该 type，
      // 会落到 else 分支当成普通消息，但字段不破坏。
      let lastAiMsgRef = null
      for (const msg of history.messages) {
        // 从历史消息的 additional_kwargs 中提取附件信息
        const msgAttachments = msg.attachments || []

        if (msg.type === 'ai') {
          let text = ''
          let thinking = []
          let timeline = []
          let tools = []

          // 若后端已返回结构化字段，直接使用；否则用 sseParser 解析原始 content
          if (msg.timeline && Array.isArray(msg.timeline)) {
            timeline = msg.timeline
            thinking = msg.thinking || []
            text = msg.text || ''
            tools = msg.tools || []
          } else {
            const aiMsg = createAiMessage()
            parseMessageContent(msg.content, aiMsg, true)
            text = aiMsg.text
            thinking = aiMsg.thinking
            timeline = aiMsg.timeline
            tools = aiMsg.tools
          }

          // 2026-06-26 新增：后端 AIMessage 携带 tool_calls 时，为普通工具构造
          // 最小化事件注入 tools / timeline，使历史会话中 ToolCallCard 能渲染。
          // 子智能体工具跳过（它们已由 type:"subagent" 元素处理）。
          if (msg.tool_calls && Array.isArray(msg.tool_calls)) {
            for (const tc of msg.tool_calls) {
              if (isSubAgentTool(tc.name)) continue
              const toolCallId = tc.id || ''
              const toolName = tc.name || '工具调用'
              const event = {
                type: 'custom',
                data: {
                  type: 'tool_stop',
                  tool: toolName,
                  tool_call_id: toolCallId,
                  data: { status: 'success' }
                }
              }
              tools.push(event)
              timeline.push({ type: 'tool', content: event })
            }
          }

          const aiMsgObj = {
            id: msg.id || Date.now() + Math.random(),
            type: 'ai',
            content: msg.content,
            text,
            thinking,
            timeline,
            tools,
            subAgents: [],  // 2026-06-16 新增：历史恢复阶段 subagent 元素会追加到这
            attachments: msgAttachments.map(a => ({
              file_name: a.file_name || a.filename || '未知文件',
              stored_path: a.stored_path || '',
              file_type: a.file_type || '',
              file_size: a.file_size || a.size || 0,
              original_name: a.original_name || a.file_name || a.filename || '未知文件'
            })),
            ended: true
          }
          messages.push(aiMsgObj)
          lastAiMsgRef = aiMsgObj
        } else if (isSubAgentHistoryItem(msg)) {
          // 2026-06-16 新增：subagent 历史元素 → 转 subAgent 挂到上一个 AI 消息
          const sa = convertSubAgentHistoryToAiSubAgent(msg)
          if (sa && lastAiMsgRef) {
            if (!Array.isArray(lastAiMsgRef.subAgents)) {
              lastAiMsgRef.subAgents = []
            }
            // 防重：同一 toolCallId 不重复挂载
            if (!lastAiMsgRef.subAgents.some(s => s.toolCallId === sa.toolCallId)) {
              lastAiMsgRef.subAgents.push(sa)
            }
          }
          // 2026-06-16：subagent 元素不作为独立 message 推入 messages 数组
          // （它的渲染由 SubAgentCard 在 timeline.tool 块内完成，避免重复）
        } else {
          messages.push({
            id: msg.id || Date.now() + Math.random(),
            type: msg.type,
            content: msg.content,
            attachments: msgAttachments.map(a => ({
              file_name: a.file_name || a.filename || '未知文件',
              stored_path: a.stored_path || '',
              file_type: a.file_type || '',
              file_size: a.file_size || a.size || 0,
              original_name: a.original_name || a.file_name || a.filename || '未知文件'
            })),
            ended: true
          })
        }
      }
    } else if (detail.title && detail.title !== '新对话') {
      // 如果没有历史消息，显示切换提示
      messages.push({
        id: Date.now(),
        type: 'system',
        content: `已切换到会话：${detail.title}`
      })
    }
  } catch (err) {
    console.error('切换会话失败:', err)
    // 2026-07-01 新增：fetchSessionMessages 失败时按用户决策默认锁定项目选择器
    historyLoadFailed.value = true
    // 401/过期场景：先尝试 refresh_token；失败再跳登录页
    // 不再"看到'未登录'/'过期'字样就清登录态"，避免误踢
    await tryRefreshOrRedirect()
  }
}
</script>

<template>
  <!-- 认证状态检查中：显示 loading 占位，避免先渲染主应用再被 checkAuth 状态切换造成视觉闪烁 -->
  <div v-if="!authReady" class="auth-loading-screen">
    <div class="auth-loading-spinner"></div>
    <div class="auth-loading-text">正在验证登录状态...</div>
  </div>

  <!-- 已登录：显示主应用。
       未登录分支已移除：App.vue 不再渲染 LoginView / RegisterView；
       未登录时 checkAuth 会通过 redirectToLogin() 跳到 /login 入口，由 /login 渲染 LoginView。 -->
  <div v-else class="app-layout">
    <Sidebar
      ref="sidebarRef"
      :current-page="currentPage"
      :username="currentUser.username"
      :user-role="currentUser.role"
      :user-id="currentUser.userId"
      :current-session-id="sessionId.value"
      @new-chat="newSession"
      @page-change="handlePageChange"
      @logout="handleLogout"
      @username-updated="handleUsernameUpdated"
      @session-switch="handleSessionSwitch"
      @open-subagent-drawer="openSubAgentDrawer"
    />

    <main v-if="currentPage === 'agent'" class="content-area" :class="{ 'empty-layout': isEmptyState }">
      <ChatArea
        v-if="!isEmptyState"
        :messages="messages"
        :is-streaming="isStreaming.value"
        :session-name="sessionTitle"
        @regenerate="handleRegenerate"
        @like="handleLike"
        @dislike="handleDislike"
        @copy="handleCopy"
        @open-subagent-drawer="openSubAgentDrawer"
        @open-session-file-drawer="handleOpenSessionFileDrawer"
      />

      <div v-if="isEmptyState" class="welcome-title">Agent, 让你的工作更轻松</div>

      <!-- 2026-06-15 新增：动态排队提示横幅，挂在 ChatArea 与 HumanApprovalBox/InputBox 之间 -->
      <div class="queue-banner-wrapper">
        <QueueStatusBanner
          :queue-status="queueStatus"
          :is-visible="isQueueBannerVisible"
        />
      </div>

      <HumanApprovalBox
        v-if="approvalMode"
        :questions="approvalData.questions"
        @submit="handleApprovalSubmit"
        @cancel="handleApprovalCancel"
      />
      <template v-else>
        <InputBox
          :session-id="sessionId.value"
          :is-streaming="isStreaming.value"
          :is-stop-pending="toolStopPending.value"
          :bound-agent-name="agentName || ''"
          :bound-agent-display-name="agentDisplayName || ''"
          :current-project="currentProject"
          :project-locked="!canEditProject"
          :allowed-agents="allowedAgents"
          :ensure-session="ensureSessionForFirstOp"
          @send="handleSendMessage"
          @tool-action="handleToolAction"
          @new-chat="newSession"
          @stop="handleStopMessage"
          @agent-switched="handleAgentSwitched"
          @select-project="(p) => p === null ? handleProjectSelectNone() : handleProjectPick(p)"
          @create-project="openCreateProjectDialog"
          @pick-existing="openPickProjectDialog"
        />
      </template>
    </main>

    <!-- 2026-06-30 新增：项目弹窗（双模式：create / pick） -->
    <ProjectDialog
      v-model:visible="isProjectDialogOpen"
      :mode="projectDialogMode"
      :projects="projects"
      @created="handleProjectCreate"
      @picked="handleProjectPick"
    />

    <KnowledgePage
      v-if="currentPage === 'knowledge'"
      @new-chat="newSession"
      @page-change="handlePageChange"
      @open-subagent-drawer="openSubAgentDrawer"
    />

    <!--
      2026-06-14 改造：原 SandboxDrawer 已删除，沙箱执行详情统一由 SubAgentDrawer 展示。
      SubAgentDrawer 内部在 tool='sandbox' 时自动展示沙箱摘要 + 沙箱事件时间线。
    -->
    <SubAgentDrawer
      :visible="subAgentDrawerVisible"
      :sub-agent="currentSubAgent"
      @close="closeSubAgentDrawer"
    />

    <!--
      2026-07-01 新增：会话文件空间抽屉。
      Push Drawer 模式，与 SubAgentDrawer 同布局机制，放在 app-layout 内与 main 同级。
    -->
    <SessionFileDrawer
      v-if="currentPage === 'agent'"
      :visible="sessionFileDrawerVisible"
      :file-tree="sessionFileTree"
      :loading="sessionFileDrawerLoading"
      :error="sessionFileDrawerError"
      @close="closeSessionFileDrawer"
      @file-click="handleSessionFileClick"
    />

    <!-- 2026-07-01 新增：文件预览弹窗 -->
    <FilePreviewModal
      :is-open="filePreviewOpen"
      :content="filePreviewData.content"
      :file-type="filePreviewData.fileType"
      :file-name="filePreviewData.fileName"
      :loading="filePreviewData.loading"
      :preview-mode="filePreviewData.previewMode"
      :file-url="filePreviewData.fileUrl"
      @close="handleCloseFilePreview"
    />

    <!-- 2026-07-02 新增：AI 回复点踩反馈弹窗 -->
    <DislikeDialog
      v-model:visible="dislikeDialog.visible"
      :message-id="dislikeDialog.messageId"
      :session-id="dislikeDialog.sessionId"
      :message-content="dislikeDialog.messageContent"
      :ai-reply="dislikeDialog.aiReply"
      :agent-name="dislikeDialog.agentName"
      @submitted="handleDislikeSubmitted"
    />
  </div>
</template>

<style scoped>
/* 认证状态检查中的全屏 loading 占位
   用途：在 checkAuth 还未完成时显示，避免渲染分支切换造成视觉闪烁
   设计：与主应用色调保持一致，居中显示旋转动画和提示文字 */
.auth-loading-screen {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-base);
  background: linear-gradient(135deg, #EBF4FF 0%, #F0F7FF 40%, #FFFFFF 100%);
  z-index: 9999;
}

.auth-loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(30, 90, 168, 0.15);
  border-top-color: #1E5AA8;
  border-radius: 50%;
  animation: auth-loading-spin 0.8s linear infinite;
}

.auth-loading-text {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  letter-spacing: 0.5px;
}

@keyframes auth-loading-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.app-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  background-color: var(--color-bg-secondary);
  overflow: hidden;
}

.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}

.content-area.empty-layout {
  justify-content: center;
  align-items: center;
}

.content-area.empty-layout > * {
  width: 100%;
  max-width: 900px;
}

.welcome-title {
  font-size: 32px;
  font-weight: var(--font-weight-bold);
  /* 与登录页主色 #1E5AA8 保持一致 */
  color: #1E5AA8;
  margin-bottom: 32px;
  text-align: center;
}

/* 排队提示横幅 wrapper，与 InputBox 的 .input-box-container 横向边距对齐 */
.queue-banner-wrapper {
  padding: 0 40px;
}

/* empty-layout 下 content-area.empty-layout > * 已限制 max-width: 900px，
   若保留 padding 会导致横幅被二次收缩，故在此场景下移除 padding */
.content-area.empty-layout .queue-banner-wrapper {
  padding: 0;
}

</style>
