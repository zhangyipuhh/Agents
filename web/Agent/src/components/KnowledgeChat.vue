<script setup>
import { ref, reactive, nextTick, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import { knowledgeChatStream, refreshToken, uploadFileInChunks, formatFileSize, getFileExtension } from '../utils/api.js'
import { createAiMessage, processSSEEvent } from '../utils/sseParser.js'
import MessageBubble from './MessageBubble.vue'
import QueueStatusBanner from './QueueStatusBanner.vue'

const SUPPORTED_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'json']
const MAX_FILE_SIZE = 50 * 1024 * 1024

const props = defineProps({
  sessionId: {
    type: String,
    default: ''
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

// 2026-06-15 新增：open-subagent-drawer emit 透传，触发父组件（KnowledgePage / App.vue）打开子智能体详情抽屉
const emit = defineEmits(['new-chat', 'send', 'open-subagent-drawer'])

const messages = reactive([])
const inputValue = ref('')
const textareaRef = ref(null)
const fileInputRef = ref(null)
const isFocused = ref(false)
const isDragging = ref(false)
const isRefreshingToken = ref(false)
const selectedFiles = ref([])
const chatContainer = ref(null)
const internalStreaming = ref(false)
const showScrollButton = ref(false)
const showScrollToTopButton = ref(false)
const unreadCount = ref(0)

// 人工回路状态
const approvalMode = ref(false)
const approvalData = ref({ questions: [] })

// 2026-06-15 新增：排队状态机（独立使用 KnowledgeChat 时也具备提示能力）
const queueStatus = ref({
  event: 'idle',
  waitingCount: 0,
  activeCount: 0,
  maxConcurrency: 0,
  position: 0,
  timestamp: 0
})
const isQueueBannerVisible = computed(() => queueStatus.value.event === 'waiting')

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

const isCurrentlyStreaming = computed(() => props.isStreaming || internalStreaming.value)

const canSend = computed(() => {
  // 2026-06-15 修改：isCurrentlyStreaming=true 时不禁用按钮（停止按钮必须可点）
  // 按钮可点性统一在模板的 :disabled 中通过 !canSend && !isCurrentlyStreaming 管控
  if (isRefreshingToken.value) return false
  const hasText = inputValue.value.trim().length > 0
  const hasUploadedFiles = selectedFiles.value.some(f => f.status === 'success')
  return hasText || hasUploadedFiles
})

// 2026-06-15 新增：持有当前 SSE reader，供停止按钮调用 cancel()
let currentReader = null

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
  if (!canSend.value) return

  const message = inputValue.value.trim()
  const uploadedFiles = selectedFiles.value
    .filter(f => f.status === 'success')
    .map(f => ({
      filename: f.uploadResult.filename,
      stored_path: f.uploadResult.stored_path,
      file_type: f.uploadResult.file_type,
      original_name: f.name,
      size: f.size
    }))

  if (!message && uploadedFiles.length === 0) return

  isRefreshingToken.value = true
  try {
    await refreshToken()
  } catch (err) {
    alert('获取认证信息失败，请稍后重试')
    isRefreshingToken.value = false
    return
  }
  isRefreshingToken.value = false

  emit('send', message, uploadedFiles)

  inputValue.value = ''
  selectedFiles.value = []
  nextTick(() => autoResize())

  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message,
    attachments: uploadedFiles
  }
  messages.push(userMsg)

  const aiMsg = reactive(createAiMessage())
  messages.push(aiMsg)

  internalStreaming.value = true

  nextTick(() => scrollToBottom())

  currentReader = null

  try {
    const stream = await knowledgeChatStream(props.sessionId, message)
    currentReader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let interrupted = false

    while (true) {
      const { done, value } = await currentReader.read()
      if (done) {
        // 确保消息被标记为已结束
        if (!aiMsg.ended) {
          console.log('[KnowledgeChat] Stream done, setting ended = true')
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
          // 2026-06-15 透传 onQueueEvent 回调
          processSSEEvent(data, aiMsg, { onQueueEvent: handleQueueEvent })
          // 2026-06-15 HITL interrupt 主动 cancel reader（与 App.vue 同逻辑）
          if (aiMsg.interrupt) {
            interrupted = true
            approvalMode.value = true
            approvalData.value = extractApprovalData(aiMsg.interrupt)
            try {
              await currentReader.cancel()
            } catch (cancelErr) {
              console.warn('[KnowledgeChat] reader.cancel 异常（可忽略）:', cancelErr)
            }
            break
          }
        } catch {}
      }
      if (interrupted) break
      nextTick(() => scrollToBottom())
    }
  } catch (err) {
    // 2026-06-15 新增：HTTP 429 排队拒绝 → 显示 banner
    if (err && err.status === 429) {
      handleQueueError(err)
      aiMsg.ended = true
      return
    }
    aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
    aiMsg.ended = true
  } finally {
    internalStreaming.value = false
    currentReader = null
  }
}

const handleNewChat = async () => {
  // 不在这里创建会话，只发射事件让父组件处理
  // 避免父子组件重复创建会话
  messages.splice(0, messages.length)
  selectedFiles.value = []
  inputValue.value = ''
  nextTick(() => autoResize())
  emit('new-chat')
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

function handleApprovalSubmit({ answers }) {
  approvalMode.value = false

  const aiMsg = messages[messages.length - 1]
  if (!aiMsg || aiMsg.type !== 'ai') {
    internalStreaming.value = false
    return
  }

  // 清除上一次的中断状态，避免旧状态导致误触发
  aiMsg.interrupt = null

  const resumeData = { answers }

  internalStreaming.value = true

  currentReader = null

  const readStream = async () => {
    try {
      const stream = await knowledgeChatStream(props.sessionId, '', [], resumeData)
      currentReader = stream.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let interrupted = false

      while (true) {
        const { done, value } = await currentReader.read()
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
            processSSEEvent(data, aiMsg, { onQueueEvent: handleQueueEvent })

            if (aiMsg.interrupt) {
              interrupted = true
              approvalMode.value = true
              approvalData.value = extractApprovalData(aiMsg.interrupt)
              try {
                await currentReader.cancel()
              } catch (cancelErr) {
                console.warn('[KnowledgeChat] resume reader.cancel 异常（可忽略）:', cancelErr)
              }
              break
            }
          } catch (parseErr) {
            // 2026-06-16 新增：单个事件解析失败不影响后续事件，记录日志便于排查
            console.warn('[KnowledgeChat] resume SSE 事件解析异常（可忽略）:', parseErr)
          }
        }
        if (interrupted) break
        nextTick(() => scrollToBottom())
      }
    } catch (err) {
      if (err && err.status === 429) {
        handleQueueError(err)
        aiMsg.ended = true
        return
      }
      aiMsg.error = '恢复执行失败，请稍后重试。'
      aiMsg.ended = true
    } finally {
      if (!approvalMode.value) {
        internalStreaming.value = false
      }
      currentReader = null
    }
  }

  readStream()
}

/**
 * 取消问答：退出 approval 模式并重置流状态
 */
function handleApprovalCancel() {
  approvalMode.value = false
  internalStreaming.value = false
  const aiMsg = messages[messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
  }
}

/**
 * 停止生成（2026-06-15 新增）：用户点击停止按钮触发
 * 与 App.vue / KnowledgeApp.vue 的 handleStopMessage 行为一致：
 * 1. 调用 currentReader.cancel() 断开 SSE 连接
 * 2. 标记最后一条 AI 消息 ended = true + 追加"已停止"提示
 * 3. 重置 internalStreaming
 */
async function handleStop() {
  if (!isCurrentlyStreaming.value) return

  // 取消 SSE reader
  if (currentReader) {
    try {
      await currentReader.cancel()
    } catch (err) {
      console.warn('[KnowledgeChat] stop reader.cancel 异常（可忽略）:', err)
    }
    currentReader = null
  }

  // 标记最后一条 AI 消息为已停止
  const aiMsg = messages[messages.length - 1]
  if (aiMsg && aiMsg.type === 'ai') {
    aiMsg.ended = true
    aiMsg.isThinkingActive = false
    if (typeof aiMsg.text === 'string' && !aiMsg.text.includes('[生成已被用户中止]')) {
      aiMsg.text = (aiMsg.text || '') + '\n\n[生成已被用户中止]'
    }
  }

  internalStreaming.value = false
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

const scrollToTop = (behavior = 'smooth') => {
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: 0,
      behavior
    })
  }
}

const handleScroll = () => {
  if (!chatContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  if (isCurrentlyStreaming.value) {
    showScrollButton.value = false
    return
  }
  // 当内容可滚动且不在底部时显示按钮
  const isScrollable = scrollHeight > clientHeight
  showScrollButton.value = isScrollable && distanceFromBottom > 20
  if (distanceFromBottom < 50) {
    unreadCount.value = 0
  }
  // 当距离顶部超过 200px 时显示"滚动到顶部"按钮
  showScrollToTopButton.value = scrollTop > 200
}

watch(() => messages.length, (newLength, oldLength) => {
  if (!chatContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = chatContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  if (distanceFromBottom > 150 && newLength > oldLength) {
    unreadCount.value += 1
    showScrollButton.value = true
  } else {
    nextTick(() => scrollToBottom())
  }
})

watch(() => messages, () => {
  if (isCurrentlyStreaming.value) {
    nextTick(() => scrollToBottom())
  }
}, { deep: true })

onMounted(() => {
  setTimeout(() => scrollToBottom('auto'), 0)
  if (chatContainer.value) {
    chatContainer.value.addEventListener('scroll', handleScroll)
  }
})

onBeforeUnmount(() => {
  if (chatContainer.value) {
    chatContainer.value.removeEventListener('scroll', handleScroll)
  }
})

// 文件上传相关方法
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
    if (file.size > MAX_FILE_SIZE) {
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
        errorMsg: `文件大小超过限制（最大 ${formatFileSize(MAX_FILE_SIZE)}）`,
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
    startUpload(fileItem)
  }
}

const startUpload = (fileItem) => {
  fileItem.status = 'uploading'
  fileItem.progress = 0
  fileItem.errorMsg = ''

  uploadFileInChunks(
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

const removeFile = (fileItem) => {
  if (fileItem.status === 'uploading' && fileItem.cancelFn) {
    fileItem.cancelFn()
  }
  const idx = selectedFiles.value.findIndex(f => f.id === fileItem.id)
  if (idx !== -1) selectedFiles.value.splice(idx, 1)
}

const retryUpload = (fileItem) => {
  if (!SUPPORTED_EXTENSIONS.includes(fileItem.extension)) {
    return
  }
  if (fileItem.size > MAX_FILE_SIZE) {
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
  console.log('Tool action:', action)
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
</script>

<template>
  <div class="knowledge-chat">
    <div class="chat-header">
      <span class="chat-title">知识库问答</span>
    </div>

    <div class="chat-body" ref="chatContainer">
      <div class="messages-container">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="32" cy="32" r="30" stroke="var(--color-border)" stroke-width="2"/>
              <path d="M32 20v24M20 32h24" stroke="var(--color-text-muted)" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
          </div>
          <h3 class="empty-title">向知识库提问</h3>
          <p class="empty-description">输入问题，获取基于知识库的精准回答</p>
        </div>

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
          @open-subagent-drawer="(sa) => emit('open-subagent-drawer', sa)"
        />
      </div>

    </div>

    <div class="chat-input-area">
          <!-- 2026-06-15 新增：排队提示 banner（聊天面板下方、输入框上方） -->
          <QueueStatusBanner
            :queue-status="queueStatus"
            :is-visible="isQueueBannerVisible"
          />

          <!-- 输入框上方滚动按钮 -->
          <transition name="fade">
            <button
              v-show="true"
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
                v-if="fileItem.status === 'error' && SUPPORTED_EXTENSIONS.includes(fileItem.extension) && fileItem.size <= MAX_FILE_SIZE"
                class="status-icon error-icon"
                viewBox="0 0 20 20"
                fill="currentColor"
                @click="retryUpload(fileItem)"
                title="点击重试"
              >
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
              </svg>

              <svg
                v-if="fileItem.status === 'error' && (!SUPPORTED_EXTENSIONS.includes(fileItem.extension) || fileItem.size > MAX_FILE_SIZE)"
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

          <textarea
            ref="textareaRef"
            v-model="inputValue"
            class="text-input"
            placeholder="输入问题，按 Enter 发送"
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
                @click="handleAttachmentClick"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                  <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd"/>
                </svg>
              </button>
            </div>

            <button
              class="send-btn"
              :class="{
                'send-mode': !isCurrentlyStreaming,
                'stop-mode': isCurrentlyStreaming,
                'disabled': !canSend && !isCurrentlyStreaming
              }"
              :disabled="!canSend && !isCurrentlyStreaming"
              :title="isCurrentlyStreaming ? '停止生成' : '发送消息'"
              @click="isCurrentlyStreaming ? handleStop() : handleSend()"
            >
              <!-- 发送模式：纸飞机图标 -->
              <svg v-if="!isCurrentlyStreaming" viewBox="0 0 20 20" fill="currentColor" class="send-icon">
                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
              </svg>
              <!-- 停止模式：实心方块图标 -->
              <svg v-else viewBox="0 0 20 20" fill="currentColor" class="stop-icon">
                <rect x="5" y="5" width="10" height="10" rx="1.5" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
    </div>
  </div>
</template>

<style scoped>
.knowledge-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background-color: var(--color-bg-primary);
  border-left: 1px solid var(--color-border);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  height: 40px;
  box-sizing: border-box;
}

.chat-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px 40px;
  position: relative;

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

  scrollbar-width: thin;
  scrollbar-color: var(--color-border) transparent;
}

.messages-container {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  flex: 1;
  animation: fadeInUp 0.5s ease-out;
}

.empty-icon {
  width: 64px;
  height: 64px;
  margin-bottom: 20px;
  opacity: 0.5;

  svg {
    width: 100%;
    height: 100%;
  }
}

.empty-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 8px;
}

.empty-description {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  line-height: var(--line-height-normal);
  max-width: 280px;
  margin: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.9);
}

/* 输入区域样式 - 采用 InputBox.vue 的 main 逻辑 */
.chat-input-area {
  position: relative;
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

/* 输入框上方滚动按钮 */
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

/* 未读消息徽章 */
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

.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

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
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), 0 2px 6px rgba(0, 0, 0, 0.1);

  &:hover:not(.focused):not(.dragging) {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2), 0 4px 10px rgba(0, 0, 0, 0.15);
  }

  &.focused {
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3), 0 4px 10px rgba(99, 102, 241, 0.2), 0 0 0 4px rgba(99, 102, 241, 0.15);
  }

  &.dragging {
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35), 0 4px 10px rgba(99, 102, 241, 0.25), 0 0 0 4px rgba(99, 102, 241, 0.2);
    background-color: var(--color-accent-light);
  }
}

/* 文件标签样式 */
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

.text-input {
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

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
