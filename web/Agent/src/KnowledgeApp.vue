<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { fetchKnowledgeFiles, fetchFilePreview, createNewSession, knowledgeChatStream, validateToken, refreshToken } from './utils/api.js'
import { createAiMessage, processSSEEvent } from './utils/sseParser.js'
import { redirectToLogin } from './utils/auth.js'
import FileList from './components/FileList.vue'
import FilePreview from './components/FilePreview.vue'
import MessageBubble from './components/MessageBubble.vue'
import ProfileInputBox from './components/ProfileInputBox.vue'
import HumanApprovalBox from './components/HumanApprovalBox.vue'
import QueueStatusBanner from './components/QueueStatusBanner.vue'
// 2026-06-15 新增：复用主聊天页的 SubAgentDrawer，独立 SPA 路径需自持渲染
import SubAgentDrawer from './components/SubAgentDrawer.vue'

const isPreviewOpen = ref(false)
const previewContent = ref('')
const previewLoading = ref(false)
const previewFileType = ref('')
const previewFileName = ref('')
const previewMode = ref('text')
const previewFileUrl = ref('')
const files = ref([])
const folders = ref([])
const filesLoading = ref(false)
const currentSessionId = ref('')
const isStreaming = ref(false)
const approvalMode = ref(false)
const approvalData = ref({ questions: [] })
const isSidebarCollapsed = ref(false)
const isCollapseBtnHovered = ref(false)

// 2026-06-15 新增：排队状态机（与 App.vue 同结构）
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

function handleQueueError(err) {
  if (!err || err.status !== 429 || !err.detail) return
  const ts = Date.now() / 1000
  queueStatus.value = {
    event: 'waiting',
    waitingCount: Number(err.detail.waiting_count) || 1,
    activeCount: Number(err.detail.active_count) || 0,
    maxConcurrency: Number(err.detail.max_concurrency) || 0,
    position: 1,
    timestamp: ts
  }
  setTimeout(() => {
    if (queueStatus.value.timestamp === ts) {
      queueStatus.value = { ...queueStatus.value, event: 'idle' }
    }
  }, 3000)
}

/**
 * 新建任务锁，防止重复创建
 */
let isCreatingNewSession = false

// 2026-06-15 新增：持有当前 SSE reader，供 ProfileInputBox 的 stop 事件调用 cancel() 立即中断 LLM
let currentStreamReader = null

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

// 聊天相关
const messages = ref([])
const chatContainer = ref(null)
const showScrollButton = ref(false)
const unreadCount = ref(0)

// 页面状态
const showChat = ref(false)

// 2026-06-15 新增：子智能体详情抽屉状态（独立 SPA，需自持；与 App.vue 同模式）
const subAgentDrawerVisible = ref(false)
const currentSubAgent = ref(null)

onMounted(async () => {
  // 验证 token 有效性，失效则尝试静默刷新
  // 全部失败：调用 redirectToLogin() 携带当前 /Agent/knowledge.html 作为 redirect，
  // 登录成功后回到原页面（避免被强制跳到 /Agent/）。
  try {
    await validateToken()
  } catch {
    try {
      const newToken = await refreshToken()
      localStorage.setItem('auth_token', newToken)
    } catch {
      redirectToLogin({ reason: 'knowledge_validate_failed' })
      return
    }
  }

  // 优先复用本地已有的 knowledge_session_id，避免每次挂载都新建会话
  const existingSessionId = localStorage.getItem('knowledge_session_id')
  if (existingSessionId && existingSessionId !== 'undefined') {
    currentSessionId.value = existingSessionId
  } else {
    // 首次进入知识库，自动创建新会话，确保后续请求携带 X-Session-ID
    try {
      const newId = await createNewSession('knowledge_session_id')
      currentSessionId.value = newId
      console.log('[KnowledgeApp] 初始化知识库会话:', newId)
    } catch (err) {
      console.error('知识库初始化会话失败:', err)
    }
  }

  // 加载文件列表
  filesLoading.value = true
  try {
    const result = await fetchKnowledgeFiles()
    if (Array.isArray(result)) {
      files.value = result.filter(f => f.type !== 'folder')
      folders.value = result.filter(f => f.type === 'folder')
    } else {
      files.value = result.files || []
      folders.value = result.folders || []
    }
  } catch (err) {
    console.error('加载文件失败:', err)
    // 使用模拟数据作为后备
    folders.value = [
      {
        name: '文档资料',
        path: '/docs',
        children: [
          { name: '项目说明.md', size: 1024, date: '2024-01-15', keywords: ['项目', '文档'] },
          { name: '需求分析.pdf', size: 2048000, date: '2024-01-14', keywords: ['需求'] },
        ]
      },
      {
        name: '代码文件',
        path: '/code',
        children: [
          { name: 'main.py', size: 5120, date: '2024-01-13', keywords: ['Python', '主程序'] },
          { name: 'utils.js', size: 3072, date: '2024-01-12', keywords: ['工具'] },
        ]
      }
    ]
    files.value = [
      { name: 'README.md', size: 2048, date: '2024-01-10', summary: '项目说明文档', keywords: ['说明'] },
      { name: 'config.json', size: 512, date: '2024-01-09', keywords: ['配置'] },
    ]
  } finally {
    filesLoading.value = false
  }
})

async function handleFileClick(file) {
  isPreviewOpen.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewFileType.value = file.type || 'txt'
  previewFileName.value = file.name || ''
  previewMode.value = 'text'
  previewFileUrl.value = ''
  try {
    const result = await fetchFilePreview(file.path || file.name)
    previewContent.value = result.content || ''
    previewMode.value = result.preview_mode || 'text'
    previewFileUrl.value = result.file_url || ''
  } catch (err) {
    previewContent.value = '预览加载失败: ' + err.message
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  isPreviewOpen.value = false
  previewContent.value = ''
  previewMode.value = 'text'
  previewFileUrl.value = ''
}

async function handleNewChat() {
  // 防止重复创建
  if (isCreatingNewSession) {
    console.log('[handleNewChat] 正在创建中，跳过重复请求')
    return
  }

  isCreatingNewSession = true
  console.log('[handleNewChat] 开始创建新会话')

  messages.value = []
  showChat.value = false

  try {
    const newId = await createNewSession('knowledge_session_id')
    currentSessionId.value = newId
    console.log('[handleNewChat] 新会话创建成功:', newId)
  } catch (err) {
    console.error('新建会话失败:', err)
  } finally {
    isCreatingNewSession = false
  }
}

const scrollToBottom = (behavior = 'smooth') => {
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior
    })
    unreadCount.value = 0
  }
}

const handleScroll = () => {
  if (!chatContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  if (isStreaming.value) {
    showScrollButton.value = false
    return
  }
  showScrollButton.value = distanceFromBottom > 150
  if (distanceFromBottom < 50) {
    unreadCount.value = 0
  }
}

function handleToolAction(action) {
  console.log('Tool action:', action)
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

/**
 * 启动知识库 SSE 流式聊天。
 *
 * 2026-06-16 重构：原实现使用 `.then().then().catch().finally()` 链式 + 嵌套 `read()` 递归，
 * 外层 `.finally(() => { currentStreamReader = null })` 会在 `read()` 同步启动后立即执行
 * （微任务阶段），导致下次 `read()` 递归访问 `currentStreamReader.read()` 时已为 null，
 * 抛 TypeError 被 catch 块捕获，最终输出「不好意思，刚刚出了点小故障」固定文案。
 *
 * 现改为 `async/await + while(true) + try/catch/finally` 模式：
 *   - `try` 块完整走完（while break / 自然结束 / catch 后）才执行 finally
 *   - `finally` 中清理 `currentStreamReader` 与重置 `isStreaming`
 *   - 与 App.vue / KnowledgeChat.handleSend 保持一致，避免类似竞态复发
 *
 * @param {string} message - 用户消息文本
 * @param {Array} uploadedFiles - 已上传文件列表
 * @param {import('vue').Ref<Object>} aiMsg - AI 消息 ref（ref.value 为消息对象）
 * @param {Object|null} resumeData - HITL 中断恢复数据，{ answers: string[][] }
 * @returns {Promise<void>}
 */
async function startChatStream(message, uploadedFiles, aiMsg, resumeData = null) {
  let interrupted = false
  currentStreamReader = null
  try {
    const stream = await knowledgeChatStream(currentSessionId.value, message, uploadedFiles, resumeData)
    currentStreamReader = stream.getReader()
    // 2026-06-22 修复：拿到 reader 后再置位 isStreaming，避免排队/握手阶段状态长期悬空无法复位
    isStreaming.value = true
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await currentStreamReader.read()
      if (done) {
        if (aiMsg.value && !aiMsg.value.ended) {
          aiMsg.value.ended = true
          aiMsg.value.isThinkingActive = false
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
          processSSEEvent(data, aiMsg.value, { onQueueEvent: handleQueueEvent })

          if (aiMsg.value.interrupt) {
            interrupted = true
            approvalMode.value = true
            approvalData.value = extractApprovalData(aiMsg.value.interrupt)
            try {
              await currentStreamReader.cancel()
            } catch (cancelErr) {
              console.warn('[KnowledgeApp] reader.cancel 异常（可忽略）:', cancelErr)
            }
            break
          }
        } catch (parseErr) {
          // 单个事件解析失败不影响后续事件，继续处理
          console.warn('[KnowledgeApp] SSE 事件解析异常（可忽略）:', parseErr)
        }
      }

      if (interrupted) {
        break
      }

      nextTick(() => scrollToBottom())
    }
  } catch (err) {
    if (err && err.status === 429) {
      handleQueueError(err)
      aiMsg.value.ended = true
      // 2026-06-22 修复：429 错误路径必须复位 isStreaming，避免按钮永久卡死
      isStreaming.value = false
      currentStreamReader = null
      return
    }
    if (interrupted) {
      return
    }
    aiMsg.value.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.value.ended = true
  } finally {
    if (!interrupted) {
      isStreaming.value = false
    }
    currentStreamReader = null
  }
}

async function handleProfileSend(message, uploadedFiles) {
  if (!message || isStreaming.value) return

  showChat.value = true

  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message,
    attachments: uploadedFiles
  }
  messages.value.push(userMsg)

  const aiMsg = ref(createAiMessage())
  messages.value.push(aiMsg.value)

  // 2026-06-22 修复：发送前重置 queueStatus
  resetQueueStatus()
  // isStreaming 由 startChatStream 在拿到 reader 后置位
  nextTick(() => scrollToBottom())

  await startChatStream(message, uploadedFiles, aiMsg)
}

async function handleApprovalSubmit({ answers }) {
  approvalMode.value = false

  const aiMsg = messages.value[messages.value.length - 1]
  if (!aiMsg || aiMsg.type !== 'ai') {
    isStreaming.value = false
    currentStreamReader = null
    return
  }

  const resumeData = { answers }

  // 清除上一次的中断状态，避免旧状态导致误触发（与 App.vue 保持一致）
  aiMsg.interrupt = null

  const aiMsgRef = ref(aiMsg)
  await startChatStream('', [], aiMsgRef, resumeData)
}

/**
 * 取消问答：退出 approval 模式并重置流状态
 */
function handleApprovalCancel() {
  approvalMode.value = false
  isStreaming.value = false
  const aiMsg = messages.value[messages.value.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
  }
}

/**
 * 停止 LLM 生成（2026-06-15 新增）：用户点击停止按钮触发
 * 与 App.vue 的 handleStopMessage 行为一致：
 * 1. 调用 currentStreamReader.cancel() 断开 SSE 连接
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
      console.warn('[KnowledgeApp] stop reader.cancel 异常（可忽略）:', err)
    }
    currentStreamReader = null
  }

  // 2. 标记 AI 消息已停止
  const aiMsg = messages.value[messages.value.length - 1]
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

// 2026-06-15 新增：子智能体详情抽屉 open / close（独立 SPA 自持；与 App.vue 同款签名）
// 2026-06-17 新增 toggle 行为：再次点击同一 subagent 卡片时关闭抽屉，点击不同卡片时切换抽屉内容
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
  currentSubAgent.value = subAgent
  subAgentDrawerVisible.value = true
}

function closeSubAgentDrawer() {
  subAgentDrawerVisible.value = false
}
</script>

<template>
  <div class="knowledge-app">
    <!-- 左侧：文件列表 -->
    <aside class="file-sidebar" :class="{ collapsed: isSidebarCollapsed }">
      <div class="sidebar-header">
        <svg v-show="!isSidebarCollapsed" class="sidebar-folder-icon" viewBox="0 0 20 20" fill="currentColor">
          <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
        </svg>
        <button class="sidebar-collapse-btn" @click="toggleSidebar" :title="isSidebarCollapsed ? '展开' : '折叠'" @mouseenter="isCollapseBtnHovered = true" @mouseleave="isCollapseBtnHovered = false">
          <svg v-if="isSidebarCollapsed && !isCollapseBtnHovered" class="collapse-icon folder-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
          </svg>
          <svg v-else class="collapse-icon" :class="{ collapsed: isSidebarCollapsed }" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd"/>
          </svg>
        </button>
      </div>
      <div v-show="!isSidebarCollapsed" class="sidebar-body">
        <FileList 
          :files="files" 
          :folders="folders" 
          :loading="filesLoading" 
          @file-click="handleFileClick" 
        />
      </div>
    </aside>

    <!-- 中间：主内容区 -->
    <main class="main-content" :class="{ 'chat-mode': showChat }">
      <!-- 初始化状态：居中输入框 -->
      <div v-if="!showChat" class="welcome-section">
        <h2 class="welcome-title">Agent, 让你的工作更轻松</h2>
        <div class="input-box-container">
          <!-- 2026-06-15 新增：排队提示 banner（聊天面板下方、输入框上方） -->
          <QueueStatusBanner
            :queue-status="queueStatus"
            :is-visible="isQueueBannerVisible"
          />
          <HumanApprovalBox
            v-if="approvalMode"
            :questions="approvalData.questions"
            @submit="handleApprovalSubmit"
            @cancel="handleApprovalCancel"
          />
          <ProfileInputBox
            v-else
            :session-id="currentSessionId"
            :is-streaming="isStreaming"
            @send="handleProfileSend"
            @tool-action="handleToolAction"
            @new-chat="handleNewChat"
            @stop="handleStopMessage"
          />
        </div>
      </div>

      <!-- 聊天状态：显示消息列表 + 底部输入框 -->
      <template v-else>
        <div class="chat-header">
          <span class="chat-title">知识库问答</span>
        </div>

        <div class="chat-body" ref="chatContainer" @scroll="handleScroll">
          <div class="messages-container">
            <MessageBubble
              v-for="message in messages"
              :key="message.id"
              :type="message.type"
              :content="message.content"
              :attachments="message.attachments"
              :timeline="message.timeline"
              :thinking="message.thinking"
              :tools="message.tools"
              :text="message.text"
              :ended="message.ended"
              :error="message.error"
              :message-id="message.id"
              :is-thinking-active="message.isThinkingActive"
              :download-info="message.downloadInfo"
              :sub-agents="message.subAgents"
              @open-subagent-drawer="openSubAgentDrawer"
            />
          </div>
        </div>

        <div class="chat-input-area">
          <!-- 2026-06-15 新增：排队提示 banner（聊天面板下方、输入框上方） -->
          <QueueStatusBanner
            :queue-status="queueStatus"
            :is-visible="isQueueBannerVisible"
          />
          <transition name="fade">
            <button
              v-show="showScrollButton"
              type="button"
              class="input-scroll-btn"
              @click="scrollToBottom('smooth')"
              :title="unreadCount > 0 ? `有 ${unreadCount} 条新消息` : '滚动到底部'"
            >
              <svg viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
              <span v-if="unreadCount > 0" class="input-scroll-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
            </button>
          </transition>
          <HumanApprovalBox
            v-if="approvalMode"
            :questions="approvalData.questions"
            @submit="handleApprovalSubmit"
            @cancel="handleApprovalCancel"
          />
          <ProfileInputBox
            v-else
            :session-id="currentSessionId"
            :is-streaming="isStreaming"
            @send="handleProfileSend"
            @tool-action="handleToolAction"
            @new-chat="handleNewChat"
            @stop="handleStopMessage"
          />
        </div>
      </template>
    </main>

    <!-- 右侧文件预览 -->
    <FilePreview
      :isOpen="isPreviewOpen"
      :content="previewContent"
      :fileType="previewFileType"
      :fileName="previewFileName"
      :loading="previewLoading"
      :previewMode="previewMode"
      :fileUrl="previewFileUrl"
      @close="closePreview"
    />

    <!--
      2026-06-15 新增：子智能体详情抽屉（独立 SPA，自持渲染；与 App.vue 顶层抽屉同款组件）
      KnowledgeApp 不在 App.vue 渲染树内，无法复用 App.vue 的抽屉，需自行持有状态 + 渲染
    -->
    <SubAgentDrawer
      :visible="subAgentDrawerVisible"
      :sub-agent="currentSubAgent"
      @close="closeSubAgentDrawer"
    />
  </div>
</template>

<style scoped>
.knowledge-app {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}

/* 左侧文件栏 */
.file-sidebar {
  width: 260px;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-primary);
  border-right: 1px solid var(--color-border);
  flex-shrink: 0;
  transition: width 0.3s ease, min-width 0.3s ease;

  &.collapsed {
    width: 50px;
    min-width: 50px;

    .sidebar-header {
      justify-content: center;
      padding: 8px;
    }
  }
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* 2026-06-15 调整：保持 padding: 8px 12px，配合 32px 折叠按钮（box-sizing: border-box 含 1px border）
     自然高度 = 8 + 32 + 8 = 48px，与 .chat-header / .drawer-header 一致 */
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  /* 2026-06-15 新增：兜底 min-height，保证折叠态（padding 8px）也不矮于 48px */
  min-height: 48px;
  box-sizing: border-box;
}

.sidebar-folder-icon {
  width: 20px;
  height: 20px;
  color: #F59E0B;
}

.sidebar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background-color: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}

.sidebar-btn:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.sidebar-collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  /* 2026-06-15 调整：28→32px + box-sizing: border-box，与 SubAgentDrawer .close-btn 尺寸对齐，
     保证 1px border 包含在 32px 内，避免 sidebar-header 实际高度超出 min-height: 48px */
  width: 32px;
  height: 32px;
  box-sizing: border-box;
  background-color: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid var(--color-border);
  flex-shrink: 0;
}

.sidebar-collapse-btn:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
  border-color: var(--color-text-muted);
}

.collapse-icon {
  width: 16px;
  height: 16px;
  transition: transform 0.3s ease;
  transform: rotate(0deg);
}

.collapse-icon.collapsed {
  transform: rotate(180deg);
}

.collapse-icon.folder-icon {
  color: #F59E0B;
  transform: rotate(0deg);
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.sidebar-body::-webkit-scrollbar {
  width: 4px;
}

.sidebar-body::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-body::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: 9999px;
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  min-width: 0;
}

.main-content.chat-mode {
  background-color: var(--color-bg-secondary);
}

/* 欢迎区域 - 居中布局 */
.welcome-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background-color: var(--color-bg-secondary);
}

.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--color-accent);
  margin-bottom: 40px;
  text-align: center;
}

.input-box-container {
  width: 100%;
  max-width: 900px;
  padding: 0 20px;
}

/* 聊天模式样式 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* 2026-06-15 调整：padding 设为 10/24，配合内部 22px 文本行高 */
  padding: 10px 24px;
  background-color: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  /* 2026-06-15 新增：与 .sidebar-header / .drawer-header 三处统一 48px，
     避免聊天模式切换时头部高度跳动 */
  min-height: 48px;
  box-sizing: border-box;
}

.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px 40px;
  background-color: var(--color-bg-secondary);
}

.messages-container {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 滚动条样式 */
.chat-body::-webkit-scrollbar {
  width: 6px;
}

.chat-body::-webkit-scrollbar-track {
  background: transparent;
}

.chat-body::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: 9999px;
}

.chat-body::-webkit-scrollbar-thumb:hover {
  background-color: var(--color-text-muted);
}

.chat-input-area {
  position: relative;
  padding: 0;
  background-color: rgb(249, 250, 251);
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.input-scroll-btn {
  position: absolute;
  top: -18px;
  left: 50%;
  transform: translateX(-50%);
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  box-shadow: var(--shadow-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  z-index: 10;
}

.input-scroll-btn:hover {
  background-color: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
  transform: translateX(-50%) translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.input-scroll-btn:active {
  transform: translateX(-50%) scale(0.95);
}

.input-scroll-btn svg {
  width: 18px;
  height: 18px;
}

.input-scroll-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background-color: #EF4444;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(239, 68, 68, 0.3);
}

.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px) scale(0.9);
}
</style>
