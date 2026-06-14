<script setup>
import { reactive, onMounted, computed, ref, watch } from 'vue'
import Sidebar from './components/Sidebar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'
import HumanApprovalBox from './components/HumanApprovalBox.vue'
import KnowledgePage from './components/KnowledgePage.vue'
import SandboxDrawer from './components/SandboxDrawer.vue'
import SubAgentDrawer from './components/SubAgentDrawer.vue'
import { chatStream, createNewSession, logout as apiLogout, fetchSessionDetail, fetchSessionAttachments, fetchSessionMessages, validateToken, refreshToken, clearAuth } from './utils/api.js'
import { isThinkingBlock, tryParsePythonLiteral, extractTextFromBlock, processContentBlocks, parseMessageContent, processSSEEvent, createAiMessage } from './utils/sseParser.js'
import { redirectToLogin, tryRefreshOrRedirect } from './utils/auth.js'

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

// 沙盒详情面板状态
const sandboxDrawerVisible = ref(false)
const currentSandboxEvents = ref([])
const currentSandboxSummary = ref(null)
const currentSandboxStatus = ref('running')

// 2026-06-13 新增：子智能体详情抽屉状态（与 sandbox 抽屉互斥同开）
const subAgentDrawerVisible = ref(false)
const currentSubAgent = ref(null)

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

  isCreatingNewSession = true
  console.log('[newSession] 开始创建新会话')

  try {
    // 先清除旧的 session_id，确保新建任务时一定会重新生成
    localStorage.removeItem('session_id')
    sessionId.value = ''
    messages.splice(0, messages.length)
    currentAttachments.value = []

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

  isStreaming.value = true
  let interrupted = false

  try {
    const stream = await chatStream(sessionId.value, message, attachments)
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
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
          processSSEEvent(data, aiMsg)
          console.log('[App] After processSSEEvent, downloadInfo:', JSON.stringify(aiMsg.downloadInfo))

          if (aiMsg.interrupt) {
            interrupted = true
            approvalMode.value = true
            approvalData.value = extractApprovalData(aiMsg.interrupt)
            break
          }
        } catch {}
      }
      if (interrupted) break
    }
  } catch (err) {
    console.error('聊天请求错误:', err)
    // 401/过期场景：先尝试 refresh_token；失败再跳登录页
    // 不再"看到'未登录'/'过期'字样就清登录态"，避免误踢
    const refreshed = await tryRefreshOrRedirect()
    if (!refreshed) {
      return
    }
    aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.ended = true
  } finally {
    if (!interrupted) {
      isStreaming.value = false
    }
  }
}

async function handleApprovalSubmit({ answers }) {
  approvalMode.value = false
  let interrupted = false

  const aiMsg = messages[messages.length - 1]
  if (!aiMsg || aiMsg.type !== 'ai') {
    isStreaming.value = false
    return
  }

  // 清除上一次的中断状态，避免旧状态导致误触发
  aiMsg.interrupt = null

  const resumeData = { answers }

  try {
    const stream = await chatStream(sessionId.value, '', [], resumeData)
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
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
          processSSEEvent(data, aiMsg)

          if (aiMsg.interrupt) {
            interrupted = true
            approvalMode.value = true
            approvalData.value = extractApprovalData(aiMsg.interrupt)
            break
          }
        } catch {}
      }
      if (interrupted) break
    }
  } catch (err) {
    console.error('Resume 请求错误:', err)
    aiMsg.error = '恢复执行失败，请稍后重试。'
    aiMsg.ended = true
  } finally {
    if (!interrupted) {
      isStreaming.value = false
    }
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

function openSandboxDrawer(sandboxData) {
  // 互斥：打开沙箱抽屉时关闭子智能体抽屉
  subAgentDrawerVisible.value = false
  currentSandboxEvents.value = sandboxData.events || []
  currentSandboxSummary.value = sandboxData.summary || null
  currentSandboxStatus.value = sandboxData.status || 'running'
  sandboxDrawerVisible.value = true
}

function closeSandboxDrawer() {
  sandboxDrawerVisible.value = false
}

// 2026-06-13 新增：子智能体抽屉 open/close
function openSubAgentDrawer(subAgent) {
  // 互斥：打开子智能体抽屉时关闭沙箱抽屉
  sandboxDrawerVisible.value = false
  currentSubAgent.value = subAgent
  subAgentDrawerVisible.value = true
}

function closeSubAgentDrawer() {
  subAgentDrawerVisible.value = false
}

// 监听当前消息的沙盒状态，执行完成后自动关闭
watch(() => {
  const lastMsg = messages[messages.length - 1]
  return lastMsg && lastMsg.type === 'ai' ? lastMsg.sandboxExecution : null
}, (newVal) => {
  if (newVal && newVal.status !== 'running' && sandboxDrawerVisible.value) {
    // 延迟 2 秒后自动关闭，让用户看到完成状态
    setTimeout(() => {
      if (newVal.status !== 'running') {
        sandboxDrawerVisible.value = false
      }
    }, 2000)
  }
})

function handleTagSelect(tag, index) {
  console.log('选择技能标签:', tag.label)
}

function handleToolAction(action) {
  console.log('工具操作:', action)
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
  if (isStreaming.value) return

  // 清空当前消息
  messages.splice(0, messages.length)
  currentAttachments.value = []

  // 切换到新会话
  sessionId.value = targetSessionId
  localStorage.setItem('session_id', targetSessionId)

  try {
    // 获取会话详情（含附件列表）
    const detail = await fetchSessionDetail(targetSessionId)

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

          messages.push({
            id: msg.id || Date.now() + Math.random(),
            type: 'ai',
            content: msg.content,
            text,
            thinking,
            timeline,
            tools,
            attachments: msgAttachments.map(a => ({
              file_name: a.file_name || a.filename || '未知文件',
              stored_path: a.stored_path || '',
              file_type: a.file_type || '',
              file_size: a.file_size || a.size || 0,
              original_name: a.original_name || a.file_name || a.filename || '未知文件'
            })),
            ended: true
          })
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
        @open-sandbox-drawer="openSandboxDrawer"
        @open-subagent-drawer="openSubAgentDrawer"
      />

      <div v-if="isEmptyState" class="welcome-title">Agent, 让你的工作更轻松</div>

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
        @send="handleSendMessage"
        @tool-action="handleToolAction"
        @new-chat="newSession"
      />
    </main>

    <KnowledgePage
      v-if="currentPage === 'knowledge'"
      @new-chat="newSession"
      @page-change="handlePageChange"
    />

    <!-- 沙盒详情面板 -->
    <SandboxDrawer
      :visible="sandboxDrawerVisible"
      :events="currentSandboxEvents"
      :summary="currentSandboxSummary"
      :status="currentSandboxStatus"
      @close="closeSandboxDrawer"
    />

    <!-- 2026-06-13 新增：子智能体详情抽屉（与 SandboxDrawer 互斥同开，组件/样式完全独立） -->
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
</style>
