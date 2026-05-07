<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { fetchKnowledgeFiles, fetchFilePreview, createNewSession, chatStream } from './utils/api.js'
import { createAiMessage, processSSEEvent } from './utils/sseParser.js'
import FileList from './components/FileList.vue'
import FilePreview from './components/FilePreview.vue'
import MessageBubble from './components/MessageBubble.vue'

const isPreviewOpen = ref(false)
const previewContent = ref('')
const previewLoading = ref(false)
const previewFileType = ref('')
const previewFileName = ref('')
const files = ref([])
const folders = ref([])
const filesLoading = ref(false)
const currentSessionId = ref('')
const isStreaming = ref(false)
const isSidebarCollapsed = ref(false)

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

// 聊天相关
const messages = ref([])
const inputValue = ref('')
const textareaRef = ref(null)
const isFocused = ref(false)
const isDragging = ref(false)
const chatContainer = ref(null)
const showScrollButton = ref(false)
const unreadCount = ref(0)

// 页面状态
const showChat = ref(false)

onMounted(async () => {
  filesLoading.value = true
  try {
    const result = await fetchKnowledgeFiles()
    files.value = result.files || []
    folders.value = result.folders || []
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

  // 创建新会话
  try {
    const newId = await createNewSession()
    currentSessionId.value = newId
  } catch (err) {
    console.error('创建会话失败:', err)
  }
})

async function handleFileClick(file) {
  isPreviewOpen.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewFileType.value = file.type || 'txt'
  previewFileName.value = file.name || ''
  try {
    const result = await fetchFilePreview(file.path || file.name)
    previewContent.value = result.content || result.preview || ''
  } catch (err) {
    previewContent.value = '预览加载失败: ' + err.message
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  isPreviewOpen.value = false
  previewContent.value = ''
}

function handleNewChat() {
  messages.value = []
  inputValue.value = ''
  showChat.value = false
  nextTick(() => autoResize())
  try {
    createNewSession().then(newId => {
      currentSessionId.value = newId
    })
  } catch (err) {
    console.error('新建会话失败:', err)
  }
}

// 聊天功能
const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    const newHeight = Math.max(80, Math.min(textarea.scrollHeight, 200))
    textarea.style.height = newHeight + 'px'
  }
}

const handleInput = (event) => {
  inputValue.value = event.target.value
  autoResize()
}

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

const handleSend = async () => {
  const message = inputValue.value.trim()
  if (!message || isStreaming.value) return

  // 切换到聊天视图
  showChat.value = true

  // 添加用户消息
  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message
  }
  messages.value.push(userMsg)

  inputValue.value = ''
  nextTick(() => autoResize())

  // 添加AI消息
  const aiMsg = ref(createAiMessage())
  messages.value.push(aiMsg.value)

  isStreaming.value = true
  nextTick(() => scrollToBottom())

  try {
    const stream = await chatStream(currentSessionId.value, message)
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
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
    }
  } catch (err) {
    aiMsg.value.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.value.ended = true
  } finally {
    isStreaming.value = false
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

function uploadFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.onchange = (e) => {
    const selectedFiles = Array.from(e.target.files)
    console.log('选择文件:', selectedFiles)
    alert(`选择了 ${selectedFiles.length} 个文件：\n${selectedFiles.map(f => f.name).join('\n')}`)
  }
  input.click()
}

function handleToolAction(action) {
  console.log('Tool action:', action)
}
</script>

<template>
  <div class="knowledge-app">
    <!-- 左侧：文件列表 -->
    <aside class="file-sidebar" :class="{ collapsed: isSidebarCollapsed }">
      <div class="sidebar-header">
        <h2 class="sidebar-title" v-show="!isSidebarCollapsed">知识库文件</h2>
        <button class="sidebar-collapse-btn" @click="toggleSidebar" :title="isSidebarCollapsed ? '展开' : '折叠'">
          <svg class="collapse-icon" :class="{ collapsed: isSidebarCollapsed }" viewBox="0 0 20 20" fill="currentColor">
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
          <div class="input-wrapper">
            <div
              class="input-main"
              :class="{ focused: isFocused, dragging: isDragging }"
            >
              <textarea
                ref="textareaRef"
                v-model="inputValue"
                class="text-input"
                placeholder="请输入你的需求，按「Enter」发送"
                rows="3"
                @input="handleInput"
                @keydown="handleKeydown"
                @focus="isFocused = true"
                @blur="isFocused = false"
              ></textarea>

              <div class="bottom-row">
                <div class="toolbar">
                  <button
                    class="tool-btn"
                    title="附件"
                    @click="uploadFile"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                      <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd"/>
                    </svg>
                  </button>

                  <button
                    class="tool-btn text-btn"
                    title="技能"
                    @click="handleToolAction('skills')"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/>
                    </svg>
                    <span>技能</span>
                  </button>

                  <button
                    class="tool-btn"
                    title="设置"
                    @click="handleToolAction('settings')"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                      <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
                    </svg>
                  </button>
                </div>

                <button
                  class="send-btn"
                  :class="{ disabled: !inputValue.trim() || isStreaming }"
                  :disabled="!inputValue.trim() || isStreaming"
                  @click="handleSend"
                  title="发送消息"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" class="send-icon">
                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
          <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
        </div>
      </div>

      <!-- 聊天状态：显示消息列表 + 底部输入框 -->
      <template v-else>
        <div class="chat-header">
          <span class="chat-title">知识库问答</span>
          <button class="new-chat-btn" @click="handleNewChat" title="新建任务">
            <svg viewBox="0 0 20 20" fill="currentColor" class="btn-icon">
              <path d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"/>
            </svg>
            <span class="btn-text">新建任务</span>
          </button>
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
            />
          </div>
        </div>

        <div class="chat-input-section">
          <div class="input-wrapper">
            <div
              class="input-main"
              :class="{ focused: isFocused, dragging: isDragging }"
            >
              <textarea
                ref="textareaRef"
                v-model="inputValue"
                class="text-input"
                placeholder="请输入你的需求，按「Enter」发送"
                rows="3"
                @input="handleInput"
                @keydown="handleKeydown"
                @focus="isFocused = true"
                @blur="isFocused = false"
              ></textarea>

              <div class="bottom-row">
                <div class="toolbar">
                  <button
                    class="tool-btn"
                    title="附件"
                    @click="uploadFile"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                      <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd"/>
                    </svg>
                  </button>

                  <button
                    class="tool-btn text-btn"
                    title="技能"
                    @click="handleToolAction('skills')"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/>
                    </svg>
                    <span>技能</span>
                  </button>

                  <button
                    class="tool-btn"
                    title="设置"
                    @click="handleToolAction('settings')"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                      <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
                    </svg>
                  </button>
                </div>

                <button
                  class="send-btn"
                  :class="{ disabled: !inputValue.trim() || isStreaming }"
                  :disabled="!inputValue.trim() || isStreaming"
                  @click="handleSend"
                  title="发送消息"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" class="send-icon">
                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
          <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
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
      padding: 16px 8px;
    }
  }
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
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

/* 输入框容器 */
.input-box-container {
  width: 100%;
  max-width: 800px;
  padding: 0 20px;
}

.input-wrapper {
  width: 100%;
}

.input-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  background-color: var(--color-bg-primary);
  border: 2px solid var(--color-accent);
  border-radius: 16px;
  transition: all 0.25s ease;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), 0 2px 6px rgba(0, 0, 0, 0.1);
}

.input-main:hover:not(.focused):not(.dragging) {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2), 0 4px 10px rgba(0, 0, 0, 0.15);
}

.input-main.focused {
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3), 0 4px 10px rgba(99, 102, 241, 0.2), 0 0 0 4px rgba(99, 102, 241, 0.15);
}

.text-input {
  width: 100%;
  min-height: 80px;
  max-height: 200px;
  padding: 8px 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-primary);
  background-color: transparent;
  border: none;
  resize: none;
  overflow-y: auto;
  font-family: inherit;
}

.text-input::placeholder {
  color: var(--color-text-muted);
}

.text-input:focus {
  outline: none;
}

.bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
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
  padding: 8px 12px;
  background-color: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
  font-size: 14px;
}

.tool-btn:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.tool-btn.text-btn {
  font-weight: 500;
}

.tool-icon {
  width: 18px;
  height: 18px;
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
  flex-shrink: 0;
}

.send-btn:hover:not(.disabled) {
  background-color: var(--color-accent-hover);
  transform: scale(1.08);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.send-btn.disabled {
  background-color: var(--color-border);
  cursor: not-allowed;
  opacity: 0.6;
}

.send-icon {
  width: 18px;
  height: 18px;
}

.disclaimer {
  text-align: center;
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 12px;
  line-height: 1.4;
}

/* 聊天模式样式 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background-color: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.chat-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.new-chat-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background-color: var(--color-accent);
  color: white;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;
  border: none;
}

.new-chat-btn:hover {
  background-color: var(--color-accent-hover);
}

.btn-text {
  line-height: 1;
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

.chat-input-section {
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

.chat-input-section .input-wrapper {
  max-width: 900px;
  margin: 0 auto;
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
