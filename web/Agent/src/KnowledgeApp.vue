<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { fetchKnowledgeFiles, fetchFilePreview, createNewSession, knowledgeChatStream } from './utils/api.js'
import { createAiMessage, processSSEEvent } from './utils/sseParser.js'
import FileList from './components/FileList.vue'
import FilePreview from './components/FilePreview.vue'
import MessageBubble from './components/MessageBubble.vue'
import ProfileInputBox from './components/ProfileInputBox.vue'

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
const isSidebarCollapsed = ref(false)
const isCollapseBtnHovered = ref(false)

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

onMounted(async () => {
  // 1. 先创建会话，确保认证信息已准备好
  try {
    const newId = await createNewSession()
    currentSessionId.value = newId
  } catch (err) {
    console.error('创建会话失败:', err)
  }

  // 2. 然后加载文件列表
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

function handleNewChat() {
  messages.value = []
  showChat.value = false
  try {
    createNewSession().then(newId => {
      currentSessionId.value = newId
    })
  } catch (err) {
    console.error('新建会话失败:', err)
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

function handleProfileSend(message, uploadedFiles) {
  if (!message || isStreaming.value) return

  // 切换到聊天视图
  showChat.value = true

  // 添加用户消息
  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message,
    attachments: uploadedFiles
  }
  messages.value.push(userMsg)

  // 添加AI消息
  const aiMsg = ref(createAiMessage())
  messages.value.push(aiMsg.value)

  isStreaming.value = true
  nextTick(() => scrollToBottom())

  knowledgeChatStream(currentSessionId.value, message)
    .then(stream => {
      const reader = stream.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) {
            isStreaming.value = false
            return
          }
          buffer += decoder.decode(value, { stream: true })
          const events = buffer.split('\n\n')
          buffer = events.pop()
          for (const event of events) {
            if (!event.startsWith('data: ')) continue
            try {
              const data = JSON.parse(event.slice(6))
              processSSEEvent(data, aiMsg.value)
            } catch {}
          }
          nextTick(() => scrollToBottom())
          read()
        }).catch(err => {
          aiMsg.value.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
          aiMsg.value.ended = true
          isStreaming.value = false
        })
      }
      read()
    })
    .catch(err => {
      aiMsg.value.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
      aiMsg.value.ended = true
      isStreaming.value = false
    })
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
          <ProfileInputBox
            :session-id="currentSessionId"
            :is-streaming="isStreaming"
            @send="handleProfileSend"
            @tool-action="handleToolAction"
            @new-chat="handleNewChat"
          />
        </div>
      </div>

      <!-- 聊天状态：显示消息列表 + 底部输入框 -->
      <template v-else>
        <div class="chat-header">
          <span class="chat-title">知识库问答</span>
        </div>

        <div class="chat-body" ref="chatContainer">
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
            />
          </div>
        </div>

        <ProfileInputBox
          :session-id="currentSessionId"
          :is-streaming="isStreaming"
          @send="handleProfileSend"
          @tool-action="handleToolAction"
          @new-chat="handleNewChat"
        />
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
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  height: 40px;
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
  width: 28px;
  height: 28px;
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
  padding: 8px 24px;
  background-color: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  height: 40px;
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
</style>
