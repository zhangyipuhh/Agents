<script setup>
/**
 * SubAgentDrawer - 通用子智能体详情抽屉（2026-06-13 新增，2026-06-14 改造，2026-06-15 精简）
 *
 * 2026-06-14 改造：合并原 SandboxDrawer 职责；
 * 沙箱类型的子智能体（tool='sandbox'）会在头部下方展示沙箱执行摘要，
 * 因为沙箱执行本质上就是子智能体的一种（统一由 subAgents 维护）。
 *
 * 2026-06-15 精简：移除独立的"沙箱事件"时间线区块；
 * ToolMessage 的步骤信息已通过子智能体消息流区完整呈现，无需重复展示。
 *
 * 2026-06-15 再次精简：移除"沙箱执行摘要"区块（状态指示 + 耗时）；
 * 该信息与底部摘要、消息流中的 ToolMessage 重复，进一步简化抽屉 UI。
 *
 * 内容分区（自上而下）：
 *   1. 头部：工具图标 + 工具名 + 状态徽章 + 关闭 X 按钮
 *   2. 父 Agent 提问区（可折叠）
 *   3. 消息流区：HumanMessage / AIMessage / ToolMessage 顺序展示
 *   4. 底部：状态摘要（耗时、消息数、工具调用次数）
 *
 * Props:
 *   visible: boolean
 *   subAgent: SubAgentSummary | null
 *
 * Emits:
 *   close
 */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { getSubAgentMeta, formatSubAgentDuration } from '../utils/sseParser.js'

// 抽屉宽度相关常量（单位：px）
const DEFAULT_DRAWER_WIDTH = 480
const MIN_DRAWER_WIDTH = 320
const MAX_DRAWER_WIDTH = 800
const CLOSE_THRESHOLD_WIDTH = 180
const STORAGE_KEY = 'subagent-drawer-width'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  subAgent: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close'])

const promptCollapsed = ref(false)
const messagesScrollRef = ref(null)
const drawerRef = ref(null)
const drawerWidth = ref(DEFAULT_DRAWER_WIDTH)
const isResizing = ref(false)

function handleClose() {
  emit('close')
}

/**
 * 将抽屉宽度限制在合法区间内
 * 入参：number 原始宽度；返回：number 限制后的宽度
 */
function clampDrawerWidth(width) {
  const maxAllowed = Math.min(MAX_DRAWER_WIDTH, window.innerWidth - 200)
  return Math.max(MIN_DRAWER_WIDTH, Math.min(width, maxAllowed))
}

/**
 * 从 localStorage 读取保存的抽屉宽度
 * 首次使用或无有效记录时返回默认值
 */
function loadDrawerWidth() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = parseInt(saved, 10)
      if (!isNaN(parsed)) {
        return clampDrawerWidth(parsed)
      }
    }
  } catch {
    // localStorage 不可用时使用默认值
  }
  return DEFAULT_DRAWER_WIDTH
}

/**
 * 将当前抽屉宽度持久化到 localStorage
 */
function saveDrawerWidth() {
  try {
    localStorage.setItem(STORAGE_KEY, String(drawerWidth.value))
  } catch {
    // 忽略写入失败
  }
}

/**
 * 开始拖拽调整宽度
 * 入参：MouseEvent 鼠标按下事件
 */
function startResize(e) {
  e.preventDefault()
  isResizing.value = true
  // 拖拽期间禁用页面文本选择，避免拖动时误选内容
  document.body.style.userSelect = 'none'
}

/**
 * 拖拽过程中实时计算抽屉宽度
 * 抽屉位于最右侧，宽度 = 抽屉右边界 x - 当前鼠标 x
 */
function handleResizeMove(e) {
  if (!isResizing.value) return
  const rect = drawerRef.value?.getBoundingClientRect()
  if (!rect) return
  const newWidth = rect.right - e.clientX
  drawerWidth.value = clampDrawerWidth(newWidth)
}

/**
 * 拖拽结束：若宽度小于关闭阈值则自动收起抽屉；否则保存宽度
 */
function stopResize() {
  if (!isResizing.value) return
  isResizing.value = false
  document.body.style.userSelect = ''
  if (drawerWidth.value < CLOSE_THRESHOLD_WIDTH) {
    emit('close')
    // 关闭后恢复默认宽度，保证下次打开体验一致
    drawerWidth.value = loadDrawerWidth()
  } else {
    saveDrawerWidth()
  }
}

onMounted(() => {
  drawerWidth.value = loadDrawerWidth()
  window.addEventListener('mousemove', handleResizeMove)
  window.addEventListener('mouseup', stopResize)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', handleResizeMove)
  window.removeEventListener('mouseup', stopResize)
})

const drawerStyle = computed(() => ({
  '--drawer-width': drawerWidth.value + 'px'
}))

const meta = computed(() => {
  if (!props.subAgent) return { icon: '🤖', label: '子智能体' }
  return getSubAgentMeta(props.subAgent.tool)
})

const status = computed(() => (props.subAgent && props.subAgent.status) || 'running')

const statusTextMap = {
  running: '执行中',
  success: '已完成',
  error: '执行失败'
}
const statusText = computed(() => statusTextMap[status.value] || '执行中')

const messages = computed(() => {
  if (!props.subAgent || !Array.isArray(props.subAgent.messages)) return []
  return props.subAgent.messages
})

const messageCount = computed(() => messages.value.length)
const toolCallCount = computed(() => {
  // AIMessage 中含 tool_calls 的累计
  return messages.value.filter(m => m && m.role === 'ai' && Array.isArray(m.tool_calls) && m.tool_calls.length > 0).length
})

const duration = computed(() => {
  if (!props.subAgent || !props.subAgent.startTime) return ''
  const end = props.subAgent.endTime || Date.now()
  return formatSubAgentDuration(end - props.subAgent.startTime)
})

// 是否为沙箱类型子智能体（2026-06-14 新增：合并原 SandboxDrawer 职责；2026-06-15 再次精简后整段展示已移除，computed 同步清理）

// 当 messages 变化时自动滚动到底部
watch(() => messages.value.length, async () => {
  if (status.value === 'running' || status.value === 'success') {
    await nextTick()
    if (messagesScrollRef.value) {
      messagesScrollRef.value.scrollTop = messagesScrollRef.value.scrollHeight
    }
  }
})

/**
 * 把 content 字段归一化为可显示字符串
 *   - str 原样
 *   - list[ContentBlock] 拼接 text/thinking 块（LangChain 0.3+ 多模态格式）
 *   - dict 取 text / content
 *   - 其它 str() 兜底
 *
 * 支持的 ContentBlock 类型（参考 LangChain 0.3 文档）：
 *   - { type: 'text', text: string }  文本
 *   - { type: 'thinking', thinking: string }  思考块（部分模型扩展）
 *   - { type: 'tool_use', name: string, input: object }  工具调用请求
 *   - { type: 'tool_result', content: string, tool_use_id: string }  工具结果
 *   - { type: 'image', source: {...} }  多模态图片（不展开）
 */
function renderMessageContent(content) {
  if (content === null || content === undefined) return ''
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map(b => {
        if (typeof b === 'string') return b
        if (!b || typeof b !== 'object') return ''
        if (b.type === 'text' && typeof b.text === 'string') return b.text
        if (b.type === 'thinking' && typeof b.thinking === 'string') return '[思考] ' + b.thinking
        if (b.type === 'tool_use') {
          const name = b.name || 'unknown_tool'
          let argsStr = ''
          try {
            argsStr = JSON.stringify(b.input || b.args || {}, null, 2)
          } catch {
            argsStr = ''
          }
          return argsStr
            ? '[工具调用] ' + name + '\n' + argsStr
            : '[工具调用] ' + name
        }
        if (b.type === 'tool_result') {
          const c = typeof b.content === 'string' ? b.content : JSON.stringify(b.content || '')
          return '[工具结果 #' + (b.tool_use_id || '') + ']\n' + c
        }
        return ''
      })
      .filter(Boolean)
      .join('\n')
  }
  if (typeof content === 'object') {
    if (typeof content.text === 'string') return content.text
    if (typeof content.content === 'string') return content.content
    try {
      return JSON.stringify(content, null, 2)
    } catch {
      return ''
    }
  }
  return String(content)
}

/**
 * 截断长 content（用于 ToolMessage 结果卡）
 */
function truncate(text, max = 500) {
  if (typeof text !== 'string') return text
  if (text.length <= max) return text
  return text.slice(0, max) + '…（已截断，共 ' + text.length + ' 字符）'
}

/**
 * role 标签（中文）
 */
const roleLabelMap = {
  user: '用户',
  ai: 'AI',
  tool: '工具结果',
  system: '系统',
  unknown: '未知'
}
function roleLabel(role) {
  return roleLabelMap[role] || '消息'
}
</script>

<template>
  <!--
    Push Drawer 模式：
    - 与 .app-layout (display:flex) 推挤布局
    - 关闭时 flex-basis=0 + overflow:hidden
    - 开启时 flex-basis=480px，从右向左平滑展开
    - 无遮罩（push drawer 无遮罩）
  -->
  <aside
    ref="drawerRef"
    v-show="visible"
    class="subagent-drawer"
    :class="{ visible, resizing: isResizing }"
    :style="drawerStyle"
    role="complementary"
    aria-label="子智能体详情"
  >
    <!-- 左侧拖拽条：用于调整抽屉宽度 -->
    <div
      class="resize-handle"
      :class="{ active: isResizing }"
      @mousedown="startResize"
      aria-label="调整抽屉宽度"
      role="separator"
    ></div>

    <!-- 头部 -->
    <div class="drawer-header">
      <div class="drawer-title">
        <span class="title-icon">{{ meta.icon }}</span>
        <span>{{ meta.label }} 详情</span>
        <span class="status-badge" :class="status">{{ statusText }}</span>
      </div>
      <button class="close-btn" @click="handleClose" aria-label="关闭抽屉">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>

    <!--
      沙箱执行摘要（2026-06-14 新增，2026-06-15 再次精简时整段移除）
      原逻辑：tool='sandbox' 时展示状态指示 + 耗时；现该信息已在底部摘要 + 消息流 ToolMessage 中完整呈现，无需重复展示。
    -->

    <!-- 父 Agent 提问区（可折叠） -->
    <div class="parent-prompt-section">
      <div class="section-header" @click="promptCollapsed = !promptCollapsed">
        <span class="section-title">父智能体提问</span>
        <svg class="expand-icon" :class="{ expanded: !promptCollapsed }"
             viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
        </svg>
      </div>
      <div v-if="!promptCollapsed" class="parent-prompt-content">
        <pre class="prompt-text">{{ subAgent && subAgent.parentPrompt || '（无）' }}</pre>
      </div>
    </div>

    <!--
      消息流区（支持 LangChain 0.3+ 多模态消息格式）
      消息来源：subAgent.messages（子智能体内的完整对话流，含 HumanMessage/AIMessage/ToolMessage）
      消息格式参考 LangChain 0.3 文档：
        - HumanMessage  { role: 'user', content: str | list[ContentBlock] }
        - AIMessage     { role: 'assistant', content: str | list[ContentBlock], tool_calls?: [...] }
        - ToolMessage   { role: 'tool', content: str, name?: str, tool_call_id?: str }
        - SystemMessage { role: 'system', content: str }
      ContentBlock 类型见 renderMessageContent 函数
    -->
    <div class="messages-section">
      <div class="section-header section-header-static">
        <span class="section-title">子智能体消息</span>
        <span class="section-count">{{ messageCount }} 条</span>
      </div>
      <div class="messages-scroll" ref="messagesScrollRef">
        <div v-if="messages.length === 0" class="messages-empty">
          <span class="empty-icon">⏳</span>
          <span class="empty-text">暂无消息</span>
        </div>

        <template v-else>
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            class="message-item"
            :class="['role-' + (msg.role || 'unknown')]"
          >
            <div class="message-item-header">
              <span class="role-tag" :class="msg.role">{{ roleLabel(msg.role) }}</span>
              <span class="message-type">{{ msg.type || 'Unknown' }}</span>
            </div>
            <!--
              消息内容区：始终渲染（只要 content 不为空）。
              2026-06-15 修复：原本用 v-if/v-else，AIMessage 含 tool_calls 时内容区被跳过，
              导致子智能体的思考/正式文本无法展示。现改为独立 v-if，与下方 tool-calls 并存。
            -->
            <div v-if="renderMessageContent(msg.content)" class="message-content" :class="{ 'message-content-truncated': msg.role === 'tool' }">
              <pre class="content-text">{{ truncate(renderMessageContent(msg.content), msg.role === 'tool' ? 500 : 10000) }}</pre>
            </div>
            <!--
              工具调用决策区：仅 AIMessage 含 tool_calls 时渲染。
              位置放在内容区下方，保持"先内容、后决策"的阅读顺序。
            -->
            <div v-if="msg.role === 'ai' && Array.isArray(msg.tool_calls) && msg.tool_calls.length"
                 class="tool-calls">
              <div class="tool-calls-title">决策（工具调用 {{ msg.tool_calls.length }}）</div>
              <div v-for="(tc, tci) in msg.tool_calls" :key="'tc-' + tci" class="tool-call-item">
                <span class="tool-call-name">🔧 {{ tc.name || 'unknown' }}</span>
                <span v-if="tc.id" class="tool-call-id">#{{ tc.id }}</span>
                <pre v-if="tc.args" class="tool-call-args">{{ JSON.stringify(tc.args, null, 2) }}</pre>
              </div>
            </div>
            <div v-if="msg.role === 'tool' && msg.name" class="message-meta">
              工具：<code>{{ msg.name }}</code>
              <span v-if="msg.tool_call_id" class="tool-call-id">· #{{ msg.tool_call_id }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 底部：状态摘要 -->
    <div class="drawer-footer">
      <span v-if="duration" class="footer-item">⏱ 耗时 {{ duration }}</span>
      <span class="footer-item">💬 {{ messageCount }} 条消息</span>
      <span class="footer-item">🔧 {{ toolCallCount }} 次工具调用</span>
      <span v-if="subAgent && subAgent.threadId" class="footer-item footer-thread">
        thread: {{ subAgent.threadId.slice(0, 12) }}{{ subAgent.threadId.length > 12 ? '…' : '' }}
      </span>
    </div>
  </aside>
</template>

<style scoped>
/* Push Drawer 根容器 - 与 SandboxDrawer 同布局机制，但样式完全独立 */
.subagent-drawer {
  position: relative;
  flex: 0 0 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: var(--drawer-width, 480px);
  max-width: min(800px, calc(100vw - 200px));
  background: #ffffff;
  border-left: 1px solid transparent;
  transition: flex-basis 0.3s ease, border-color 0.3s ease;
  flex-shrink: 0;
}

.subagent-drawer.visible {
  flex-basis: var(--drawer-width, 480px);
  border-left-color: var(--color-border);
}

.subagent-drawer.resizing {
  /* 拖拽时关闭动画，避免 width/flex-basis 变化出现延迟 */
  transition: none;
}

/* 左侧拖拽条 */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 10;
  background: transparent;
  transition: background-color 0.2s ease;
}

.resize-handle:hover,
.resize-handle.active {
  background: var(--color-accent, #1E5AA8);
}

/* 头部 */
.drawer-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.title-icon {
  font-size: 18px;
}

.status-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 9999px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.status-badge.running {
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
}

.status-badge.success {
  background-color: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.status-badge.error {
  background-color: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--color-text-muted);
  transition: all 0.2s ease;
}

.close-btn:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-secondary);
}

.close-btn svg {
  width: 18px;
  height: 18px;
}

/* 父 Agent 提问区 */
.parent-prompt-section {
  border-bottom: 1px solid #e8e8e8;
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
  flex-shrink: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  cursor: pointer;
  user-select: none;
}

.section-header-static {
  cursor: default;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-count {
  font-size: 11px;
  color: var(--color-text-muted);
}

.expand-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  transition: transform 0.2s ease;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.parent-prompt-content {
  padding: 0 20px 12px;
  max-height: 200px;
  overflow-y: auto;
}

.prompt-text {
  margin: 0;
  padding: 10px 12px;
  background-color: rgba(30, 90, 168, 0.05);
  border-left: 3px solid var(--color-accent);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

/* 消息流区 */
.messages-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.messages-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px 16px;
}

.messages-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  gap: 8px;
}

.empty-icon {
  font-size: 32px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
  color: var(--color-text-muted);
}

/* 单条消息 */
.message-item {
  margin: 8px 0;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
  background-color: #fafbfc;
}

.message-item.role-user {
  background-color: rgba(99, 102, 241, 0.05);
  border-color: rgba(99, 102, 241, 0.2);
}

.message-item.role-ai {
  background-color: rgba(30, 90, 168, 0.05);
  border-color: rgba(30, 90, 168, 0.2);
}

.message-item.role-tool {
  background-color: #f0f0f0;
  border-color: #d0d0d0;
}

.message-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.role-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  text-transform: uppercase;
}

.role-tag.user { background-color: rgba(99, 102, 241, 0.15); color: #4f46e5; }
.role-tag.ai { background-color: rgba(30, 90, 168, 0.15); color: #1E5AA8; }
.role-tag.tool { background-color: #e0e0e0; color: #4b5563; }

.message-type {
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: 'Courier New', monospace;
}

.message-content {
  margin-top: 4px;
}

.content-text {
  margin: 0;
  padding: 6px 8px;
  background-color: rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  max-height: 400px;
  overflow-y: auto;
}

.message-content-truncated .content-text {
  max-height: 200px;
}

/* 工具调用区（AIMessage 含 tool_calls） */
.tool-calls {
  margin-top: 6px;
  padding: 8px 10px;
  background-color: rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  border-left: 3px solid #f59e0b;
}

.tool-calls-title {
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
  margin-bottom: 4px;
}

.tool-call-item {
  margin-top: 4px;
  padding: 4px 0;
  border-top: 1px dashed rgba(245, 158, 11, 0.3);
}

.tool-call-item:first-of-type {
  border-top: none;
}

.tool-call-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.tool-call-id {
  font-size: 10px;
  color: var(--color-text-muted);
  font-family: 'Courier New', monospace;
  margin-left: 4px;
}

.tool-call-args {
  margin: 4px 0 0;
  padding: 4px 6px;
  background-color: #fafbfc;
  border-radius: 3px;
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Courier New', monospace;
  max-height: 150px;
  overflow-y: auto;
}

/* 消息元数据（ToolMessage 显示工具名） */
.message-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.message-meta code {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
}

/* 底部摘要 */
.drawer-footer {
  border-top: 1px solid #e8e8e8;
  padding: 10px 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
  color: var(--color-text-secondary);
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  flex-shrink: 0;
}

.footer-item {
  white-space: nowrap;
}

.footer-thread {
  color: var(--color-text-muted);
  font-family: 'Courier New', monospace;
  font-size: 10px;
}
</style>
