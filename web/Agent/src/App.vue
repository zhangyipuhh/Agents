<script setup>
import { reactive, onMounted, computed, ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'
import HumanApprovalBox from './components/HumanApprovalBox.vue'
import KnowledgePage from './components/KnowledgePage.vue'
import SubAgentDrawer from './components/SubAgentDrawer.vue'
import QueueStatusBanner from './components/QueueStatusBanner.vue'
import { chatStream, createNewSession, logout as apiLogout, fetchSessionDetail, fetchSessionAttachments, fetchSessionMessages, validateToken, refreshToken, clearAuth } from './utils/api.js'
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

const messages = reactive([])
const sessionId = reactive({ value: '' })
const isStreaming = reactive({ value: false })
const sidebarRef = ref(null)
const currentAttachments = ref([])
const approvalMode = ref(false)
const approvalData = ref({ questions: [] })

// 2026-06-15 新增：持有当前 SSE reader，供 InputBox 的 stop 事件调用 cancel() 立即中断 LLM
let currentStreamReader = null

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
setTimeout(() => {
  if (!authReady.value) {
    authReady.value = true
  }
}, 5000)

/**
 * 处理登出事件
 * 清除本地缓存并返回登录页
 */
async function handleLogout() {
  await apiLogout()
  isLoggedIn.value = false
  currentUser.value = { username: '', role: '', userId: null }
  localStorage.removeItem('user_id')
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
 * 确保当前用户有一个有效的会话
 * 如果本地没有 session_id，则自动创建新会话并刷新侧边栏列表
 */
async function ensureSession() {
  const existingSessionId = localStorage.getItem('session_id')
  if (existingSessionId && existingSessionId !== 'undefined') {
    sessionId.value = existingSessionId
    return
  }

  try {
    const newId = await createNewSession()
    sessionId.value = newId
    if (sidebarRef.value) {
      sidebarRef.value.loadSessionList()
    }
  } catch (err) {
    console.error('自动创建会话失败:', err)
  }
}

onMounted(async () => {
  await checkAuth()

  if (isLoggedIn.value) {
    await ensureSession()
  }
})

async function newSession() {
  // 防止重复创建
  if (isCreatingNewSession) {
    console.log('[newSession] 正在创建中，跳过重复请求')
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
  resetQueueStatus()
  approvalMode.value = false

  isCreatingNewSession = true
  console.log('[newSession] 开始创建新会话')

  try {
    // 先清除旧的 session_id，确保新建任务时一定会重新生成
    localStorage.removeItem('session_id')
    sessionId.value = ''
    messages.splice(0, messages.length)
    currentAttachments.value = []
    agentName.value = null
    agentDisplayName.value = ''

    // 关闭子智能体详情抽屉：避免上一个会话的 subagent 数据残留在 UI 上
    // 复用已有的 closeSubAgentDrawer()（会同步将 subAgentDrawerVisible 置 false，无需另清 currentSubAgent）
    closeSubAgentDrawer()

    const newId = await createNewSession()
    sessionId.value = newId
    console.log('[newSession] 新会话创建成功:', newId)

    // 刷新侧边栏会话列表
    if (sidebarRef.value) {
      sidebarRef.value.loadSessionList()
    }
  } catch (err) {
    console.error('新建会话失败:', err)
    // API 报错时先尝试 refresh_token；失败再跳登录页（带 redirect）
    // 注意：不再"看到'未登录'/'过期'字样就清登录态"，避免误踢
    await tryRefreshOrRedirect()
  } finally {
    isCreatingNewSession = false
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

  try {
    const stream = await chatStream(sessionId.value, message, attachments, null, agentName.value)
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
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
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
    if (!interrupted) {
      isStreaming.value = false
    }
    currentStreamReader = null
  }
}

async function handleApprovalSubmit({ answers }) {
  approvalMode.value = false
  let interrupted = false

  const aiMsg = messages[messages.length - 1]
  if (!aiMsg || aiMsg.type !== 'ai') {
    isStreaming.value = false
    currentStreamReader = null
    return
  }

  // 清除上一次的中断状态，避免旧状态导致误触发
  aiMsg.interrupt = null

  const resumeData = { answers }
  // 2026-06-22 修复：resume 前重置 queueStatus
  resetQueueStatus()
  // 2026-06-15 改造：reader 提到模块级 currentStreamReader，供 stop 按钮跨函数访问
  currentStreamReader = null

  try {
    const stream = await chatStream(sessionId.value, '', [], resumeData, agentName.value)
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
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
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
    if (!interrupted) {
      isStreaming.value = false
    }
    currentStreamReader = null
  }
}

/**
 * 取消问答：退出 approval 模式并重置流状态
 */
function handleApprovalCancel() {
  approvalMode.value = false
  isStreaming.value = false
  const aiMsg = messages[messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
  }
}

/**
 * 停止 LLM 生成（2026-06-15 新增）：用户点击停止按钮触发
 * 流程：
 * 1. 调用 currentStreamReader.cancel() 断开 SSE 连接
 *    - 后端 map_router.py 的 is_disconnected() 检测会立即生效，LangGraph 跳出循环
 * 2. 标记最后一条 AI 消息 ended = true + 追加"已停止"提示
 * 3. 重置 isStreaming
 */
async function handleStopMessage() {
  if (!isStreaming.value) return

  // 1. 取消 SSE reader
  if (currentStreamReader) {
    try {
      await currentStreamReader.cancel()
    } catch (err) {
      console.warn('[App] stop reader.cancel 异常（可忽略）:', err)
    }
    currentStreamReader = null
  }

  // 2. 标记 AI 消息已停止
  const aiMsg = messages[messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
    if (typeof aiMsg.text === 'string' && !aiMsg.text.includes('[生成已被用户中止]')) {
      aiMsg.text = (aiMsg.text || '') + '\n\n[生成已被用户中止]'
    }
  }

  // 3. 重置流式状态
  isStreaming.value = false
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

function handleLike(id) {
  console.log('点赞消息:', id)
}

function handleDislike(id) {
  console.log('点踩消息:', id)
}

function handleCopy(e) {
  console.log('复制消息:', e.messageId)
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
    resetQueueStatus()
    approvalMode.value = false
  }

  // 清空当前消息
  messages.splice(0, messages.length)
  currentAttachments.value = []

  // 关闭子智能体详情抽屉：上一个会话的 subagent 详情不应在切换后仍残留
  // 与 newSession() 保持一致行为
  closeSubAgentDrawer()

  // 切换到新会话
  sessionId.value = targetSessionId
  localStorage.setItem('session_id', targetSessionId)

  try {
    // 获取会话详情（含附件列表）
    const detail = await fetchSessionDetail(targetSessionId)

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
    />

    <main v-if="currentPage === 'agent'" class="content-area" :class="{ 'empty-layout': isEmptyState }">
      <SkillTags v-if="!isEmptyState" @tag-select="handleTagSelect" />

      <ChatArea
        v-if="!isEmptyState"
        :messages="messages"
        :is-streaming="isStreaming.value"
        @regenerate="handleRegenerate"
        @like="handleLike"
        @dislike="handleDislike"
        @copy="handleCopy"
        @open-subagent-drawer="openSubAgentDrawer"
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
      <InputBox
        v-else
        :session-id="sessionId.value"
        :is-streaming="isStreaming.value"
        :bound-agent-name="agentName || ''"
        :bound-agent-display-name="agentDisplayName || ''"
        @send="handleSendMessage"
        @tool-action="handleToolAction"
        @new-chat="newSession"
        @stop="handleStopMessage"
        @agent-switched="handleAgentSwitched"
      />
    </main>

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
