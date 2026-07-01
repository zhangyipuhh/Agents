<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { uploadFileInChunks, formatFileSize, getFileExtension, refreshToken, fetchAgentList } from '../utils/api.js'
import ProjectDropdown from './ProjectDropdown.vue'
import { handleCommand, COMMAND_REGISTRY } from '../utils/commandRegistry.js'

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
  },
  boundAgentName: {
    type: String,
    default: ''
  },
  boundAgentDisplayName: {
    type: String,
    default: ''
  },
  // 2026-06-30 新增：当前会话关联的项目
  currentProject: {
    type: Object,
    default: null
  }
})

const inputValue = ref('')
const textareaRef = ref(null)
const fileInputRef = ref(null)
const isFocused = ref(false)
const isDragging = ref(false)
const isRefreshingToken = ref(false)
// 命令执行中标记：防止命令执行期间用户重复点击发送按钮导致重复触发
const isExecutingCommand = ref(false)
const selectedFiles = ref([])

// 2026-06-24 新增：智能体快速选择相关状态
const agentList = ref([])
const isLoadingAgents = ref(false)
const selectedAgent = ref(null)
const showAgentDropdown = ref(false)
const activeAgentIndex = ref(-1)
const agentDropdownRef = ref(null)

const canSend = computed(() => {
  if (props.isStreaming) return false
  if (isRefreshingToken.value) return false
  if (isExecutingCommand.value) return false
  const hasText = inputValue.value.trim().length > 0
  const hasUploadedFiles = selectedFiles.value.some(f => f.status === 'success')
  return hasText || hasUploadedFiles
})

/**
 * 是否为命令输入（以 / 开头，且未通过下拉菜单选中智能体）
 * @returns {boolean} 当前输入是否为斜杠命令
 */
const isCommand = computed(() => {
  if (props.boundAgentName && props.boundAgentName !== 'default') return false
  const trimmed = inputValue.value.trim()
  return trimmed.startsWith('/') && !selectedAgent.value
})

/**
 * 解析当前命令输入
 * 复用单一解析逻辑，避免 commandHint 与 handleSend 中重复解析命令字符串。
 * @returns {{cmd: string, args: string[]} | null} 命令对象（含命令名与参数数组）；非命令输入返回 null
 */
const parsedCommand = computed(() => {
  if (!isCommand.value) return null
  const parts = inputValue.value.trim().slice(1).split(/\s+/)
  return { cmd: parts[0], args: parts.slice(1) }
})

/**
 * 命令提示文本
 * 根据输入内容匹配 COMMAND_REGISTRY 中的命令定义，返回描述与用法提示。
 * @returns {string} 命令提示文本；非命令输入或仅输入 "/" 时返回空字符串
 */
const commandHint = computed(() => {
  const parsed = parsedCommand.value
  if (!parsed) return ''
  // 仅输入 "/" 时不显示命令提示，由下拉菜单替代
  if (parsed.cmd === '') return ''
  const reg = COMMAND_REGISTRY.find((r) => r.name === parsed.cmd)
  return reg ? `命令：${reg.description}（用法：${reg.usage}）` : `未知命令：/${parsed.cmd}`
})

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    const newHeight = Math.max(80, Math.min(textarea.scrollHeight, 200))
    textarea.style.height = newHeight + 'px'
  }
}

/**
 * 加载可用智能体列表（供下拉菜单使用）
 */
async function loadAgents() {
  if (agentList.value.length > 0 || isLoadingAgents.value) return
  isLoadingAgents.value = true
  try {
    const agents = await fetchAgentList()
    agentList.value = agents || []
  } catch (err) {
    console.error('加载智能体列表失败:', err)
    agentList.value = []
  } finally {
    isLoadingAgents.value = false
  }
}

// 页面加载时自动获取智能体列表，确保用户输入 "/" 时列表已就绪
onMounted(() => {
  loadAgents()
})

/**
 * 过滤后的智能体列表（当输入 "/" 后，可继续输入字符进行过滤）
 */
const filteredAgents = computed(() => {
  const trimmed = inputValue.value.trim()
  if (trimmed === '/') return agentList.value
  if (!trimmed.startsWith('/')) return []
  const query = trimmed.slice(1).toLowerCase()
  return agentList.value.filter(
    (a) =>
      a.name.toLowerCase().includes(query) ||
      (a.display_name && a.display_name.toLowerCase().includes(query))
  )
})

const handleInput = (event) => {
  inputValue.value = event.target.value
  autoResize()
  // 若当前 session 已绑定非 default 智能体，禁止唤起 /command 下拉菜单
  if (props.boundAgentName && props.boundAgentName !== 'default') {
    showAgentDropdown.value = false
    activeAgentIndex.value = -1
    return
  }
  // 仅输入 "/" 时加载智能体列表并显示下拉菜单
  const trimmed = inputValue.value.trim()
  if (trimmed === '/') {
    showAgentDropdown.value = true
    activeAgentIndex.value = -1
    loadAgents()
  } else if (!trimmed.startsWith('/')) {
    showAgentDropdown.value = false
    activeAgentIndex.value = -1
  } else {
    // 输入 "/xxx" 时继续显示下拉菜单（过滤模式）
    showAgentDropdown.value = true
    activeAgentIndex.value = -1
  }
}

/**
 * 选中智能体（从下拉菜单）
 * @param {Object} agent - 智能体对象
 */
function selectAgent(agent) {
  selectedAgent.value = agent
  inputValue.value = ''
  showAgentDropdown.value = false
  activeAgentIndex.value = -1
  nextTick(() => {
    autoResize()
    textareaRef.value?.focus()
  })
}

/**
 * 移除已选中的智能体
 */
function removeSelectedAgent() {
  selectedAgent.value = null
  emit('agent-switched', null)
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

const handleKeydown = (event) => {
  // 下拉菜单打开时，支持键盘导航
  if (showAgentDropdown.value && filteredAgents.value.length > 0) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      activeAgentIndex.value = (activeAgentIndex.value + 1) % filteredAgents.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      activeAgentIndex.value =
        (activeAgentIndex.value - 1 + filteredAgents.value.length) % filteredAgents.value.length
      return
    }
    if (event.key === 'Enter' && !event.shiftKey && activeAgentIndex.value >= 0) {
      event.preventDefault()
      selectAgent(filteredAgents.value[activeAgentIndex.value])
      return
    }
    if (event.key === 'Escape') {
      showAgentDropdown.value = false
      activeAgentIndex.value = -1
      return
    }
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

/**
 * 执行斜杠命令
 * 在命令执行期间设置 isExecutingCommand 锁，防止用户重复点击发送；
 * 命令结果通过 send 事件作为系统消息显示，switchAgent 信号通过 agent-switched 事件传递。
 * @param {string} text - 已 trim 的输入文本（以 / 开头）
 * @returns {Promise<void>}
 * @throws {Error} 命令执行失败时通过 emit('send', '命令执行失败：...') 兜底处理，不向上抛出
 */
const executeCommand = async (text) => {
  const parsed = parsedCommand.value
  if (!parsed) return
  const { cmd, args } = parsed
  isExecutingCommand.value = true
  try {
    const result = await handleCommand(cmd, args)
    if (result.switchAgent) {
      // 2026-06-26 改造：若 result.switchAgent 是字符串，包装为对象以兼容 App.vue
      const payload = typeof result.switchAgent === 'string'
        ? { name: result.switchAgent, display_name: result.switchAgent }
        : result.switchAgent
      emit('agent-switched', payload)
    }
    // 命令结果作为系统消息显示（通过 send 事件传递）
    emit('send', result.text, [])
  } catch (err) {
    emit('send', `命令执行失败：${err.message}`, [])
  } finally {
    isExecutingCommand.value = false
    inputValue.value = ''
    nextTick(() => {
      autoResize()
    })
  }
}

const handleSend = async () => {
  if (!canSend.value) return

  const text = inputValue.value.trim()
  if (!text && !selectedAgent.value) return

  // 命令检测：以 / 开头视为命令，不走普通发送流程
  if (text.startsWith('/')) {
    await executeCommand(text)
    return
  }

  isRefreshingToken.value = true
  try {
    await refreshToken()
  } catch (err) {
    alert('获取认证信息失败，请稍后重试')
    isRefreshingToken.value = false
    return
  }
  isRefreshingToken.value = false

  const uploadedFiles = selectedFiles.value
    .filter(f => f.status === 'success')
    .map(f => ({
      file_name: f.uploadResult.filename,
      stored_path: f.uploadResult.stored_path,
      file_type: f.uploadResult.file_type,
      original_name: f.name,
      file_size: f.size
    }))

  // 2026-06-24 新增：若通过下拉菜单选中了智能体，先切换智能体再发送消息
  // 2026-06-26 改造：emit 对象包含 display_name，供 App.vue 同步展示名称
  if (selectedAgent.value) {
    emit('agent-switched', {
      name: selectedAgent.value.name,
      display_name: selectedAgent.value.display_name || selectedAgent.value.name
    })
  }

  emit('send', text, uploadedFiles)

  inputValue.value = ''
  selectedFiles.value = []
  selectedAgent.value = null

  nextTick(() => {
    autoResize()
  })
}

const handleFocus = () => {
  isFocused.value = true
}

const handleBlur = () => {
  isFocused.value = false
  // 延迟关闭下拉菜单，确保点击菜单项的 mousedown 能先触发
  setTimeout(() => {
    showAgentDropdown.value = false
    activeAgentIndex.value = -1
  }, 200)
}

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
  emit('tool-action', action)
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

const emit = defineEmits(['send', 'tool-action', 'stop', 'agent-switched', 'project-changed', 'select-project', 'create-project', 'pick-existing'])
</script>

<template>
  <div class="input-box-container">
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

        <!-- 2026-06-24 新增：已选智能体标签（可移除） -->
        <div v-if="selectedAgent" class="selected-agent-tag">
          <span class="agent-slash">/</span>
          <span class="agent-name">{{ selectedAgent.display_name || selectedAgent.name }}</span>
          <button class="agent-remove-btn" @click="removeSelectedAgent" title="移除">
            <svg viewBox="0 0 20 20" fill="currentColor" class="agent-remove-icon">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </button>
        </div>

        <!-- 2026-06-26 新增：会话已绑定智能体标签（不可移除） -->
        <div v-if="boundAgentName && boundAgentName !== 'default'" class="selected-agent-tag bound-agent-tag">
          <span class="agent-slash">/</span>
          <span class="agent-name">{{ boundAgentDisplayName || boundAgentName }}</span>
        </div>

        <!-- 2026-06-24 新增：智能体下拉菜单 -->
        <div
          v-if="showAgentDropdown && isCommand && inputValue.trim() === '/'"
          ref="agentDropdownRef"
          class="agent-dropdown"
        >
          <div v-if="isLoadingAgents" class="agent-dropdown-loading">加载中...</div>
          <div v-else-if="filteredAgents.length === 0" class="agent-dropdown-empty">暂无可用智能体</div>
          <div
            v-for="(agent, index) in filteredAgents"
            :key="agent.name"
            class="agent-dropdown-item"
            :class="{ active: activeAgentIndex === index }"
            @mousedown.prevent="selectAgent(agent)"
            @mouseenter="activeAgentIndex = index"
          >
            <div class="agent-dropdown-name">{{ agent.display_name || agent.name }}</div>
          </div>
        </div>

        <textarea
          ref="textareaRef"
          v-model="inputValue"
          class="text-input"
          :placeholder="selectedAgent ? '请输入消息，按「Enter」发送' : (boundAgentName ? `当前智能体：${boundAgentDisplayName || boundAgentName}` : '输入 / 快速使用智能体')"
          rows="3"
          @input="handleInput"
          @keydown="handleKeydown"
          @focus="handleFocus"
          @blur="handleBlur"
        ></textarea>

        <div v-if="isCommand && inputValue.trim() !== '/'" class="command-hint">
          {{ commandHint }}
        </div>

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
              'send-mode': !isStreaming,
              'stop-mode': isStreaming,
              'disabled': !canSend && !isStreaming
            }"
            :disabled="!canSend && !isStreaming"
            :title="isStreaming ? '停止生成' : '发送消息'"
            @click="isStreaming ? emit('stop') : handleSend()"
          >
            <!-- 发送模式：纸飞机图标 -->
            <svg v-if="!isStreaming" viewBox="0 0 20 20" fill="currentColor" class="send-icon">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
            </svg>
            <!-- 停止模式：实心方块图标 -->
            <svg v-else viewBox="0 0 20 20" fill="currentColor" class="stop-icon">
              <rect x="5" y="5" width="10" height="10" rx="1.5" />
            </svg>
          </button>
        </div>
      </div>

      <!-- 2026-07-01 调整：项目下拉框置于 .input-main 外部，
           作为独立浅灰卡片紧跟主卡下方，与主卡形成「主卡 + 次卡」分层结构。 -->
      <div class="project-dropdown-slot">
        <ProjectDropdown
          :current-project="currentProject"
          :disabled="isStreaming"
          @select-project="$emit('select-project', $event)"
          @create-project="$emit('create-project')"
          @pick-existing="$emit('pick-existing')"
        />
      </div>
    </div>

    <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
  </div>
</template>

<style scoped>
.input-box-container {
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
  contain: layout style paint;
}

/* 2026-07-01 样式微调：.input-wrapper 保持为透明容器（仅约束宽度与居中），
   视觉外壳由 .input-main 独立承担。 */
.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

/* 2026-07-01 样式微调：.input-main 保留 2px 实色蓝边框与厚重阴影，
   与下方的项目卡形成「主卡 + 独立次卡」的视觉层级。 */
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
  max-width: 900px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);

  &:hover:not(.focused):not(.dragging) {
    box-shadow: 0 10px 32px rgba(0, 0, 0, 0.16), 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  &.focused {
    box-shadow: 0 10px 32px rgba(99, 102, 241, 0.25), 0 4px 12px rgba(99, 102, 241, 0.15), 0 0 0 4px rgba(99, 102, 241, 0.12);
  }

  &.dragging {
    box-shadow: 0 10px 32px rgba(99, 102, 241, 0.3), 0 4px 12px rgba(99, 102, 241, 0.2), 0 0 0 4px rgba(99, 102, 241, 0.18);
    background-color: var(--color-accent-light);
  }
}

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

/* 命令提示样式：以 / 开头输入时显示命令说明 */
.command-hint {
  padding: 6px 8px;
  font-size: var(--font-size-sm);
  color: var(--color-accent);
  background-color: var(--color-accent-light);
  border-radius: var(--radius-sm);
  margin-top: 4px;
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

/* 2026-06-24 新增：已选智能体标签 */
.selected-agent-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background-color: var(--color-accent-light);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  margin-bottom: 4px;
  align-self: flex-start;
}

.agent-slash {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
}

.agent-name {
  line-height: 1.4;
}

.agent-remove-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  margin-left: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-accent);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors);

  &:hover {
    background-color: rgba(99, 102, 241, 0.15);
  }
}

.agent-remove-icon {
  width: 12px;
  height: 12px;
}

/* 2026-06-26 新增：已绑定智能体标签（不可移除） */
.bound-agent-tag {
  background-color: var(--color-bg-tertiary);
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

/* 2026-06-24 新增：智能体下拉菜单 */
.agent-dropdown {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 240px;
  overflow-y: auto;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);
  margin-bottom: 8px;
  padding: 6px;
  z-index: 10;

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
}

.agent-dropdown-loading,
.agent-dropdown-empty {
  padding: 12px 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  text-align: center;
}

.agent-dropdown-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover,
  &.active {
    background-color: var(--color-accent-light);
  }
}

.agent-dropdown-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: 1.4;
}

/* 2026-07-01 样式微调：项目下拉框作为独立浅灰卡片置于 .input-main 外部下方，
   8px 间距，无阴影无边框，圆角与主卡风格一致，
   与上方主卡形成「主卡 + 次卡」视觉层级。 */
.project-dropdown-slot {
  margin-top: 8px;
  display: flex;
  justify-content: flex-start;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  box-shadow: none;
  border: none;
}
</style>
