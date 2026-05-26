<script setup>
import { reactive, onMounted, computed, ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'
import KnowledgePage from './components/KnowledgePage.vue'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'
import { chatStream, ensureAuth, createNewSession, logout as apiLogout } from './utils/api.js'
import { isThinkingBlock, tryParsePythonLiteral, extractTextFromBlock, processContentBlocks, parseMessageContent, processSSEEvent, createAiMessage } from './utils/sseParser.js'

const currentPage = ref('agent')
const authView = ref('login') // 'login' | 'register'
const isLoggedIn = ref(false)
const currentUser = ref({ username: '', role: '', userId: null })

const messages = reactive([])
const sessionId = reactive({ value: '' })
const isStreaming = reactive({ value: false })

const isEmptyState = computed(() => messages.length === 0)

/**
 * 检查本地存储的登录状态
 * 从 localStorage 读取 token 和用户信息，判断是否已登录
 */
function checkAuth() {
  const token = localStorage.getItem('auth_token')
  const username = localStorage.getItem('username')
  const role = localStorage.getItem('user_role')

  if (token && username) {
    isLoggedIn.value = true
    currentUser.value = {
      username,
      role: role || 'user',
      userId: null // userId 不存储在 localStorage 中，需要时从后端获取
    }
  } else {
    isLoggedIn.value = false
  }
}

/**
 * 处理登录成功事件
 * @param {Object} data - 登录结果数据，包含 token、role、username
 */
function handleLoginSuccess(data) {
  localStorage.setItem('auth_token', data.token)
  localStorage.setItem('user_role', data.role)
  localStorage.setItem('username', data.username)
  isLoggedIn.value = true
  currentUser.value = {
    username: data.username,
    role: data.role,
    userId: null
  }
}

/**
 * 处理登出事件
 * 清除本地缓存并返回登录页
 */
async function handleLogout() {
  await apiLogout()
  isLoggedIn.value = false
  currentUser.value = { username: '', role: '', userId: null }
  messages.splice(0, messages.length)
  sessionId.value = ''
  authView.value = 'login'
}

/**
 * 处理用户名更新事件
 * @param {Object} data - 包含新用户名的数据
 */
function handleUsernameUpdated(data) {
  currentUser.value.username = data.username
  localStorage.setItem('username', data.username)
}

onMounted(async () => {
  // 检查登录状态
  checkAuth()

  if (isLoggedIn.value) {
    try {
      const newId = await createNewSession()
      sessionId.value = newId
    } catch (err) {
      console.error('初始化会话失败:', err)
      // 如果是认证错误，跳转到登录页
      if (err.message.includes('未登录') || err.message.includes('过期')) {
        isLoggedIn.value = false
      }
    }
  }
})

async function newSession() {
  // 先清除旧的 session_id，确保新建任务时一定会重新生成
  localStorage.removeItem('session_id')
  sessionId.value = ''
  messages.splice(0, messages.length)

  try {
    const newId = await createNewSession()
    sessionId.value = newId
  } catch (err) {
    console.error('新建会话失败:', err)
    if (err.message.includes('未登录') || err.message.includes('过期')) {
      isLoggedIn.value = false
    }
  }
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
        } catch {}
      }
    }
  } catch (err) {
    console.error('聊天请求错误:', err)
    if (err.message.includes('未登录') || err.message.includes('过期')) {
      isLoggedIn.value = false
      return
    }
    aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.ended = true
  } finally {
    isStreaming.value = false
  }
}

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
</script>

<template>
  <!-- 未登录：显示登录/注册页面 -->
  <LoginView
    v-if="!isLoggedIn && authView === 'login'"
    @login-success="handleLoginSuccess"
    @switch-to-register="authView = 'register'"
  />
  <RegisterView
    v-else-if="!isLoggedIn && authView === 'register'"
    @switch-to-login="authView = 'login'"
  />

  <!-- 已登录：显示主应用 -->
  <div v-else class="app-layout">
    <Sidebar
      :current-page="currentPage"
      :username="currentUser.username"
      :user-role="currentUser.role"
      @new-chat="newSession"
      @page-change="handlePageChange"
      @logout="handleLogout"
      @username-updated="handleUsernameUpdated"
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
      />

      <div v-if="isEmptyState" class="welcome-title">Agent, 让你的工作更轻松</div>

      <InputBox
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
  </div>
</template>

<style scoped>
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
  color: rgb(79, 70, 229);
  margin-bottom: 32px;
  text-align: center;
}
</style>
