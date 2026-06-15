<script setup>
import { ref, computed, reactive, watch, nextTick } from 'vue'
import { marked } from 'marked'
import { formatFileSize, getFileExtension, getAuthHeaders } from '../utils/api.js'
import { isSubAgentTool } from '../utils/sseParser.js'
import SubAgentCard from './SubAgentCard.vue'

const props = defineProps({
  type: {
    type: String,
    default: 'user',
    validator: (value) => ['user', 'ai'].includes(value)
  },
  content: {
    type: [String, Object],
    default: ''
  },
  attachments: {
    type: Array,
    default: () => []
  },
  timeline: {
    type: Array,
    default: () => []
  },
  thinking: {
    type: Array,
    default: () => []
  },
  tools: {
    type: Array,
    default: () => []
  },
  text: {
    type: String,
    default: ''
  },
  ended: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },
  messageId: {
    type: [String, Number],
    default: ''
  },
  isThinkingActive: {
    type: Boolean,
    default: false
  },
  downloadInfo: {
    type: Object,
    default: null
  },
  // 2026-06-13 新增：子智能体执行列表（折叠卡片 / 抽屉用）
  subAgents: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['copy', 'regenerate', 'like', 'dislike', 'open-sandbox-drawer', 'open-subagent-drawer'])

const isThinkingExpanded = ref(false)
const isToolsExpanded = ref(false)
const thinkingContainer = ref(null)
const showCopyToast = ref(false)
const likeStatus = ref(0)
const thinkingExpandedMap = reactive({})
const userToggledThinking = ref(false)

const isUserMessage = computed(() => props.type === 'user')
const hasAttachments = computed(() => props.attachments && props.attachments.length > 0)
const hasThinking = computed(() => props.thinking && props.thinking.length > 0)
const hasTools = computed(() => props.tools && props.tools.length > 0)
const hasText = computed(() => props.text && props.text.length > 0)
const hasError = computed(() => props.error && props.error.length > 0)
const isStreaming = computed(() => !props.ended && !hasError.value && hasThinking.value)
const hasDownloadInfo = computed(() => {
  const hasInfo = props.downloadInfo && props.downloadInfo.downloadUrl
  console.log('[MessageBubble] hasDownloadInfo:', hasInfo, 'downloadInfo:', JSON.stringify(props.downloadInfo))
  return hasInfo
})

const hasTimeline = computed(() => props.timeline && props.timeline.length > 0)

// 2026-06-13 新增：子智能体卡片列表
const hasSubAgents = computed(() => Array.isArray(props.subAgents) && props.subAgents.length > 0)

// 新增：判断是否有正在运行的子智能体（用于抑制主智能体思考动画）
const hasRunningSubAgent = computed(() => {
  if (!Array.isArray(props.subAgents)) return false
  return props.subAgents.some(sa => sa && sa.status === 'running')
})

function handleSubAgentClick(subAgent) {
  emit('open-subagent-drawer', subAgent)
}

const mergedTimeline = computed(() => {
  if (!props.timeline || props.timeline.length === 0) return []
  const result = []
  for (const item of props.timeline) {
    const last = result[result.length - 1]
    if (last && last.type === item.type) {
      last.items.push(item.content)
    } else {
      result.push({ type: item.type, items: [item.content] })
    }
  }
  return result
})

/**
 * 根据 timeline.tool group 的 items 提取对应的子智能体列表
 * 2026-06-14 改造：原 SandboxProgress 替换为 SubAgentCard，
 * 子智能体卡片按 toolCallId 匹配，渲染在 timeline.tool 内以符合事件时序。
 *
 * 入参：group.items（来自 mergedTimeline 中的 tool 组的 raw event 数组）
 * 返回：去重后的子智能体列表
 *
 * SSE 事件结构（sseParser.js case 'custom' 写入）：
 *   item = { type: 'custom', thread_id: 'top_thread', data: <ToolEvent TypedDict> }
 *   item.data = { type, tool, tool_call_id, thread_id, data: { ... } }
 *   toolCallId 取值优先级：item.data.tool_call_id > item.data.thread_id > item.thread_id
 */
function extractToolCallId(item) {
  if (!item || typeof item !== 'object') return ''
  // item 是 sseParser push 进去的整个 SSE 事件 data 对象；
  // item.data 才是 ToolEvent TypedDict（参见 sseParser.js case 'custom'）。
  const inner = (item.data && typeof item.data === 'object') ? item.data : {}
  return inner.tool_call_id || inner.thread_id || item.thread_id || ''
}

const toolSubAgentMap = computed(() => {
  // 构建一个 toolCallId -> subAgent 的索引，供模板 O(1) 查找
  const map = new Map()
  if (!Array.isArray(props.subAgents)) return map
  for (const sa of props.subAgents) {
    if (sa && sa.toolCallId) {
      map.set(sa.toolCallId, sa)
    }
  }
  return map
})

// 2026-06-14 新增：跨 timeline group 去重（computed 版）
// 同一次子智能体执行（同一 toolCallId）的 custom 事件可能被
// thinking / text 事件拆成多个 tool group，导致每个 group 都渲染
// 一张重复的 SubAgentCard。本 computed 对 mergedTimeline 做一次完整
// 扫描，在 group 维度上"每个 toolCallId 仅首次出现"返回 subAgent 列表。
//
// 用 computed 而非普通函数 + 组件级 Set 的原因：
//   - Vue 3 mount 阶段会多次调用 render function，普通函数内部用 Set
//     记录"已渲染"会在 mount 内的连续 render 间互相污染（同一组数据
//     在第二次 render 时被错误地判定为"已渲染过"而跳过）；
//   - computed 由 Vue 缓存，仅在依赖（props.timeline / props.subAgents
//     / mergedTimeline）变化时重算，多次 render 期间返回同一结果；
//   - 计算内部用本地 Set（每次重算时新建），天然避免跨 render 污染。
//
// 返回：与 mergedTimeline 等长的数组，元素为该 group 内"首次出现"的
// subAgent 列表（去重后）。subAgent.messages 仍由 sseParser 持续累积，
// 不影响 SubAgentDrawer 详情展示。
const subAgentsByGroup = computed(() => {
  const groups = mergedTimeline.value
  const result = []
  const seen = new Set() // 跨 group 去重：每个 toolCallId 仅首次出现
  const map = toolSubAgentMap.value
  for (const group of groups) {
    if (!group || group.type !== 'tool' || !Array.isArray(group.items)) {
      result.push([])
      continue
    }
    const groupResult = []
    for (const item of group.items) {
      const id = extractToolCallId(item)
      if (!id || !map.has(id) || seen.has(id)) continue
      seen.add(id)
      groupResult.push(map.get(id))
    }
    result.push(groupResult)
  }
  return result
})

// 2026-06-14 兼容层：保留旧函数名 getSubAgentsForGroup
// 新实现：直接读 subAgentsByGroup 计算结果。
// 入参：group（mergedTimeline 中的一个元素）
// 返回：该 group 内"首次出现"的 subAgent 列表（自动跨 group 去重）
// 注意：本函数作为模板调用入口，最终值由 subAgentsByGroup 决定。
function getSubAgentsForGroup(group) {
  if (!group) return []
  const groups = mergedTimeline.value
  const idx = groups.indexOf(group)
  if (idx < 0) return []
  return subAgentsByGroup.value[idx] || []
}

/**
 * 判断 timeline 内的 tool 项目是否属于子智能体调用（2026-06-14 新增）
 *
 * 入参：item（sseParser push 进去的 SSE 事件 data 对象）
 * 返回：true 当且仅当 item.data.tool 是已知的子智能体工具名
 *
 * 背景：subagent 类的工具调用（sandbox / explore 等）由 SubAgentCard 折叠卡统一
 * 展示父 prompt + 子消息流 + 沙箱摘要，不应在「工具调用」块内的 tools-body 再
 * 重复渲染一次原始事件 JSON。
 */
function isSubAgentItem(item) {
  if (!item || typeof item !== 'object') return false
  // item 形如 { type:'custom', thread_id, data: <ToolEvent TypedDict> }
  // data.data 才是 ToolEvent（参见 sseParser.js case 'custom'）。
  const inner = (item.data && typeof item.data === 'object') ? item.data : {}
  return isSubAgentTool(inner.tool)
}

/**
 * 过滤掉子智能体调用项目，返回纯普通工具调用列表（2026-06-14 新增）
 *
 * 入参：items（来自 mergedTimeline 中 tool 组的 raw event 数组）
 * 返回：保留非子智能体工具调用的新数组（不会修改原数组）
 */
function getNonSubAgentItems(items) {
  if (!Array.isArray(items)) return []
  return items.filter(item => !isSubAgentItem(item))
}

const formattedThinking = computed(() => {
  if (!props.thinking || props.thinking.length === 0) return ''
  return props.thinking.map(item => formatThinkingItem(item)).join('')
})

const renderedText = computed(() => {
  if (!hasText.value) return ''
  try {
    return marked.parse(props.text)
  } catch {
    return props.text.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>').replace(/^/, '<p>').replace(/$/, '</p>')
  }
})

function isThinkingGroupActive(index) {
  if (!props.isThinkingActive || props.ended) return false
  const groups = mergedTimeline.value
  for (let i = groups.length - 1; i >= 0; i--) {
    if (groups[i].type === 'thinking') {
      return i === index
    }
  }
  return false
}

watch(() => [props.isThinkingActive, props.ended, mergedTimeline.value.length], (newVal, oldVal) => {
  const [newIsActive, newEnded, newLength] = newVal || []
  const [oldIsActive, oldEnded, oldLength] = oldVal || []

  // 当 ended 从 false 变为 true 时，强制关闭思考组（无论 userToggledThinking 状态）
  if (!oldEnded && newEnded) {
    for (const key in thinkingExpandedMap) {
      thinkingExpandedMap[key] = false
    }
    // 重置用户操作标志，以便下一条消息可以正常工作
    userToggledThinking.value = false
    return
  }

  // 如果用户手动操作过，不再自动干预（但 ended 变化除外，已在上面的逻辑中处理）
  if (userToggledThinking.value) {
    return
  }

  if (newIsActive && !newEnded) {
    const groups = mergedTimeline.value
    for (let i = groups.length - 1; i >= 0; i--) {
      if (groups[i].type === 'thinking') {
        thinkingExpandedMap[i] = true
        break
      }
    }
  }
}, { immediate: true })

watch(() => [props.isThinkingActive, props.ended], () => {
  // 如果用户手动操作过，不再自动干预
  if (userToggledThinking.value) {
    return
  }

  if (props.isThinkingActive && !props.ended) {
    isThinkingExpanded.value = true
  } else if (props.ended) {
    isThinkingExpanded.value = false
  }
}, { immediate: true })

// 当新消息开始时重置用户操作标志
watch(() => props.messageId, (newId, oldId) => {
  if (newId !== oldId) {
    userToggledThinking.value = false
  }
})

// 监听思考内容变化，自动滚动到底部（降级模式）
watch(() => props.thinking, () => {
  if (isThinkingExpanded.value && props.isThinkingActive && !props.ended) {
    nextTick(() => {
      if (thinkingContainer.value) {
        thinkingContainer.value.scrollTop = thinkingContainer.value.scrollHeight
      }
    })
  }
}, { deep: true })

// 监听时间线变化，自动滚动活跃思考组到底部
watch(() => props.timeline, () => {
  if (props.isThinkingActive && !props.ended) {
    nextTick(() => {
      const groups = mergedTimeline.value
      for (let i = groups.length - 1; i >= 0; i--) {
        if (groups[i].type === 'thinking' && thinkingExpandedMap[i]) {
          // 找到对应的思考体元素并滚动
          const thinkingBody = document.querySelector(`.timeline-thinking:nth-child(${i + 1}) .thinking-body`)
          if (thinkingBody) {
            thinkingBody.scrollTop = thinkingBody.scrollHeight
          }
          break
        }
      }
    })
  }
}, { deep: true })

function formatThinkingItem(item) {
  if (typeof item === 'string') return item
  if (!item) return ''
  if (item.thinking) return item.thinking
  if (item.text) return item.text
  if (item.data) {
    const d = item.data
    const nodeName = Object.keys(d)[0]
    const nodeData = d[nodeName]
    if (!nodeData) return JSON.stringify(d, null, 2)
    if (typeof nodeData === 'string') return nodeData
    if (nodeData.messages && Array.isArray(nodeData.messages)) {
      return nodeData.messages.map(m => typeof m === 'string' ? m : JSON.stringify(m)).join('\n')
    }
    return JSON.stringify(nodeData, null, 2)
  }
  return JSON.stringify(item, null, 2)
}

function formatMergedThinkingItems(items) {
  return items.map(item => formatThinkingItem(item)).join('')
}

function formatToolItem(item) {
  if (typeof item === 'string') return item
  if (!item) return ''
  if (item.data) return JSON.stringify(item.data)
  if (item.name || item.tool) return item.name || item.tool
  return JSON.stringify(item)
}

function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch {
    return text.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>').replace(/^/, '<p>').replace(/$/, '</p>')
  }
}

function isThinkingGroupExpanded(index) {
  return thinkingExpandedMap[index] ?? false
}

function toggleThinkingGroup(index) {
  const currentState = isThinkingGroupExpanded(index)
  const newState = !currentState

  userToggledThinking.value = true
  thinkingExpandedMap[index] = newState
}

function handleThinkingClick(index) {
  if (isThinkingGroupActive(index)) return
  toggleThinkingGroup(index)
}

const toggleThinking = () => {
  const currentState = isThinkingExpanded.value
  const newState = !currentState

  userToggledThinking.value = true
  isThinkingExpanded.value = newState
}

const toggleTools = () => {
  isToolsExpanded.value = !isToolsExpanded.value
}

const handleCopy = async () => {
  const textToCopy = props.text || ''
  try {
    await navigator.clipboard.writeText(textToCopy)
    showCopyToast.value = true
    setTimeout(() => {
      showCopyToast.value = false
    }, 2000)
    emit('copy', { success: true, messageId: props.messageId })
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = textToCopy
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    showCopyToast.value = true
    setTimeout(() => {
      showCopyToast.value = false
    }, 2000)
    emit('copy', { success: true, messageId: props.messageId })
  }
}

const handleCopyUserContent = async () => {
  const textToCopy = typeof props.content === 'string' ? props.content : JSON.stringify(props.content)
  try {
    await navigator.clipboard.writeText(textToCopy)
    showCopyToast.value = true
    setTimeout(() => {
      showCopyToast.value = false
    }, 2000)
    emit('copy', { success: true, messageId: props.messageId })
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = textToCopy
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    showCopyToast.value = true
    setTimeout(() => {
      showCopyToast.value = false
    }, 2000)
    emit('copy', { success: true, messageId: props.messageId })
  }
}

const handleRegenerate = () => {
  emit('regenerate', props.messageId)
}

const handleLike = () => {
  likeStatus.value = likeStatus.value === 1 ? 0 : 1
  emit('like', props.messageId)
}

const handleDislike = () => {
  likeStatus.value = likeStatus.value === -1 ? 0 : -1
  emit('dislike', props.messageId)
}

const handleDownload = async () => {
  if (!props.downloadInfo) return

  const { downloadUrl, fileName } = props.downloadInfo
  const baseUrl = window.location.origin
  const fullUrl = `${baseUrl}${downloadUrl}`

  try {
    const headers = getAuthHeaders()
    const response = await fetch(fullUrl, { headers })

    if (!response.ok) {
      throw new Error(`下载失败: ${response.status}`)
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName || 'download'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err) {
    console.error('下载失败:', err)
    alert('文件下载失败，请重试')
  }
}

const getFileIconColor = (filename) => {
  const ext = getFileExtension(filename)
  const colorMap = {
    pdf: '#EF4444',
    doc: '#3B82F6', docx: '#3B82F6',
    xls: '#10B981', xlsx: '#10B981', csv: '#10B981',
    jpg: '#8B5CF6', jpeg: '#8B5CF6', png: '#8B5CF6', gif: '#8B5CF6',
    txt: '#6B7280', md: '#6B7280',
    ppt: '#F59E0B', pptx: '#F59E0B',
  }
  return colorMap[ext] || '#9CA3AF'
}
</script>

<template>
  <div class="message-bubble" :class="[type]">
    <!-- 用户消息 -->
    <div v-if="isUserMessage" class="user-message">
      <button class="action-btn user-copy-btn" :data-tooltip="'复制消息'" @click="handleCopyUserContent">
        <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>
      </button>
      <div class="bubble-content">
        <div v-if="hasAttachments" class="bubble-attachments">
          <div
            v-for="(att, idx) in attachments"
            :key="idx"
            class="bubble-attachment-tag"
          >
            <svg class="att-icon" viewBox="0 0 20 20" fill="currentColor" :style="{ color: getFileIconColor(att.original_name || att.file_name || att.filename) }">
              <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>
            <span class="att-name">{{ att.original_name || att.file_name || att.filename }}</span>
            <span v-if="att.file_size || att.size" class="att-size">{{ formatFileSize(att.file_size || att.size) }}</span>
          </div>
        </div>
        <div v-if="content" class="bubble-text">{{ content }}</div>
      </div>
    </div>

    <!-- AI 消息 -->
    <div v-else class="ai-message">
      <!-- 时间线模式：按流式输出顺序展示 -->
      <template v-if="hasTimeline">
        <template v-for="(group, index) in mergedTimeline" :key="'tl-' + index">
          <!-- 思考块 -->
          <div v-if="group.type === 'thinking'" class="timeline-thinking" :class="{ 'thinking-active': isThinkingGroupActive(index) }">
            <div class="thinking-header" :class="{ 'thinking-header-active': isThinkingGroupActive(index) }" @click="handleThinkingClick(index)">
              <span class="thinking-icon" :class="{ 'thinking-pulse': isThinkingGroupActive(index) && !hasRunningSubAgent }">🧠</span>
              <span class="thinking-label" :class="{ 'thinking-label-active': isThinkingGroupActive(index) }">
                {{ isThinkingGroupActive(index) ? '思考中...' : '思考过程' }}
              </span>
              <svg
                class="expand-icon"
                :class="{ expanded: isThinkingGroupExpanded(index) }"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </div>
            <div v-if="isThinkingGroupExpanded(index)" class="thinking-body">
              <pre class="thinking-content">{{ formatMergedThinkingItems(group.items) }}</pre>
              <span v-if="isThinkingGroupActive(index) && !hasRunningSubAgent" class="streaming-cursor">▌</span>
            </div>
          </div>

          <!--
            工具调用块
            2026-06-14 改造：原 sandboxExecution 条件分支移除，
            改为统一渲染工具调用列表 + 在底部按 toolCallId 嵌入 SubAgentCard
            （子智能体卡片按事件时序出现，不再堆在末尾）
            2026-06-14 再改造：subagent 类工具不再在 tools-body 重复展示，
            tools-header / tools-body 只显示普通工具调用；SubAgentCard `div` 仍是
            subagent 的唯一展示位。
          -->
          <div v-else-if="group.type === 'tool'" class="timeline-tool">
            <!--
              tools-header / tools-body 仅在「存在非子智能体项目」时渲染
              - 避免当 group.items 全是 subagent 时仍显示误导性计数
              - 子智能体的展示完全交给下方 timeline-subagent-list
            -->
            <template v-if="getNonSubAgentItems(group.items).length > 0">
              <div class="tools-header" @click="toggleTools">
                <span class="tools-icon">🔧</span>
                <span class="tools-label">工具调用 ({{ getNonSubAgentItems(group.items).length }})</span>
                <svg
                  class="expand-icon"
                  :class="{ expanded: isToolsExpanded }"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
                </svg>
              </div>
              <div v-if="isToolsExpanded" class="tools-body">
                <div
                  v-for="(item, idx) in getNonSubAgentItems(group.items)"
                  :key="'tool-item-' + idx"
                  class="tool-item"
                >
                  <span class="tool-icon">🔧</span>
                  <span class="tool-text">{{ formatToolItem(item) }}</span>
                </div>
              </div>
            </template>
            <!--
              子智能体卡片嵌入（2026-06-14 改造）
              按 toolCallId 在 group.items 中查找匹配的 subAgent 列表，
              渲染在工具调用块内，遵循事件流时序。
              当 group.items 全是子智能体时，本块就是该组工具调用的唯一展示位。
            -->
            <div v-if="getSubAgentsForGroup(group).length > 0" class="timeline-subagent-list">
              <SubAgentCard
                v-for="sa in getSubAgentsForGroup(group)"
                :key="sa.toolCallId"
                :sub-agent="sa"
                @click="handleSubAgentClick(sa)"
              />
            </div>
          </div>

          <!-- 正文块 -->
          <div v-else-if="group.type === 'text'" class="timeline-text">
            <div class="markdown-body" v-html="renderMarkdown(group.items.join(''))"></div>
          </div>
        </template>

        <!-- 流式光标 -->
        <span v-if="!ended && !error && !isThinkingActive" class="streaming-cursor">▌</span>
      </template>

      <!-- 降级模式：无 timeline 时使用旧逻辑 -->
      <template v-else>
        <!-- 思考过程 -->
        <div v-if="hasThinking" class="thinking-section">
          <div class="thinking-header" @click="toggleThinking">
            <span class="thinking-icon">🧠</span>
            <span class="thinking-label">思考过程</span>
            <svg
              class="expand-icon"
              :class="{ expanded: isThinkingExpanded }"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </div>
          <div v-if="isThinkingExpanded" class="thinking-body" ref="thinkingContainer">
            <pre class="thinking-content">{{ formattedThinking }}</pre>
          </div>
        </div>

        <!-- 工具调用 -->
        <div v-if="hasTools" class="tools-section">
          <div class="tools-header" @click="toggleTools">
            <span class="tools-icon">🔧</span>
            <span class="tools-label">工具调用 ({{ tools.length }})</span>
            <svg
              class="expand-icon"
              :class="{ expanded: isToolsExpanded }"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </div>
          <div v-if="isToolsExpanded" class="tools-body">
            <div
              v-for="(item, index) in tools"
              :key="'tool-' + index"
              class="tool-item"
            >
              <span class="tool-icon">🔧</span>
              <span class="tool-text">{{ formatToolItem(item) }}</span>
            </div>
          </div>
        </div>

        <!-- 正文内容 -->
        <div v-if="hasText" class="text-section">
          <div class="markdown-body" v-html="renderedText"></div>
          <span v-if="!ended && !error" class="streaming-cursor">▌</span>
        </div>
      </template>

      <!-- 下载链接 -->
      <div v-if="hasDownloadInfo && ended" class="download-section">
        <div class="download-card" @click="handleDownload">
          <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          <span class="download-filename">{{ downloadInfo.fileName }}</span>
          <span class="download-hint">点击下载</span>
        </div>
      </div>

      <!-- 错误信息 -->
      <div v-if="hasError" class="error-section">
        <span class="error-text">不好意思，刚刚出了点小故障，可以晚点再问我一遍。</span>
      </div>

      <!-- 加载状态（无任何内容时） -->
      <div v-if="!hasTimeline && !hasThinking && !hasText && !hasError" class="loading-section">
        <span class="loading-dot">●</span>
        <span class="loading-dot" style="animation-delay: 0.2s">●</span>
        <span class="loading-dot" style="animation-delay: 0.4s">●</span>
      </div>

      <!-- 操作按钮 -->
      <div v-if="props.ended && (hasText || hasError)" class="message-actions">
        <button class="action-btn" :data-tooltip="'复制消息'" @click="handleCopy">
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
          </svg>
        </button>
        <button class="action-btn" :data-tooltip="'重新生成'" @click="handleRegenerate">
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
          </svg>
        </button>
        <button
          class="action-btn"
          :class="{ 'liked': likeStatus === 1 }"
          :data-tooltip="likeStatus === 1 ? '取消' : '喜欢'"
          @click="handleLike"
        >
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/>
          </svg>
        </button>
        <button
          class="action-btn"
          :class="{ 'disliked': likeStatus === -1 }"
          :data-tooltip="likeStatus === -1 ? '取消' : '不喜欢'"
          @click="handleDislike"
        >
          <svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h3a2 2 0 012 2v7a2 2 0 01-2 2h-3"/>
          </svg>
        </button>
      </div>

      <!-- 复制成功提示 -->
      <Transition name="toast">
        <div v-if="showCopyToast" class="copy-toast">
          <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <span class="toast-text">已复制到剪贴板</span>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.message-bubble {
  width: 100%;
  margin-bottom: 12px;  /* 2026-06-15 调整：与 .timeline-thinking margin-bottom 对齐，统一为窄间距 */
  animation: messageSlideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);

  &:last-child {
    margin-bottom: 0;
  }
}

@keyframes messageSlideIn {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 用户消息 */
.user-message {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.bubble-content {
  max-width: 70%;
  padding: 12px 16px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 12px 12px 4px 12px;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  word-wrap: break-word;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
  transition: var(--transition-shadow);
}

.bubble-content:hover {
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.bubble-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.bubble-attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 12px;
}

.att-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.att-name {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.att-size {
  opacity: 0.7;
  font-size: 11px;
}

.bubble-text {
  white-space: pre-wrap;
}

/* AI 消息 */
.ai-message {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
}

/* 时间线思考块 */
.timeline-thinking {
  width: 100%;             /* 2026-06-15 新增：占满父级 ai-message 容器宽度（与 .subagent-card 等宽） */
  margin-bottom: 12px;
  align-self: flex-end;    /* 2026-06-15 新增：在 .ai-message 中右对齐，与 .timeline-subagent-list 一致 */
  /* 2026-06-15 二改：移除窄屏兜底约束，让 .timeline-thinking 与 .subagent-card 容器同宽（均 100%），左右两边都对齐 */
}

.timeline-thinking.thinking-active {
  margin-bottom: 16px;
}

/* 时间线工具块 */
.timeline-tool {
  width: 100%;
  max-width: 100%;
  margin-bottom: 6px;
}

.timeline-sandbox {
  width: 100%;
}

/*
 * timeline.tool 内的子智能体卡片列表（2026-06-14 新增）
 * 子智能体卡片按 toolCallId 匹配后渲染在工具调用块内，遵循事件流时序。
 */
.timeline-subagent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 6px;
  align-items: flex-end;
}

/* 时间线正文块 */
.timeline-text {
  max-width: 85%;
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--color-text-primary);
  margin-bottom: 8px;
}

/* 思考过程 */
.thinking-section {
  width: 100%;             /* 2026-06-15 新增：占满父级 ai-message 容器宽度（与 .subagent-card 等宽） */
  margin-bottom: 12px;
  align-self: flex-end;    /* 2026-06-15 新增：在 .ai-message 中右对齐，与 timeline 模式保持一致 */
  /* 2026-06-15 二改：移除窄屏兜底约束，与 .timeline-thinking 保持一致，让降级模式也与 subagent-card 左右对齐 */
}

.thinking-header {
  display: flex;             /* 2026-06-15 改造：由 inline-flex 改为 flex，让 width:100% 生效（与 .subagent-card 等宽） */
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  width: 100%;               /* 2026-06-15 新增：与父容器同宽，与 .subagent-card 宽度对齐 */
  box-sizing: border-box;    /* 2026-06-15 新增：padding 计入宽度，避免溢出 */
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  transition: background-color 0.2s ease;
  user-select: none;
}

.thinking-header:hover {
  background-color: var(--color-bg-hover);
}

.thinking-header-active {
  background-color: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.thinking-header-active:hover {
  background-color: rgba(245, 158, 11, 0.15);
}

.thinking-icon {
  font-size: 14px;
  filter: grayscale(1);
}

.thinking-pulse {
  animation: thinkingPulse 1.5s ease-in-out infinite;
}

@keyframes thinkingPulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.1);
  }
}

.thinking-label {
  font-size: 0.875em;
}

.thinking-label-active {
  color: #F59E0B;
  font-weight: 500;
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

.thinking-body {
  margin-top: 8px;
  padding: 12px 16px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  max-height: 200px;
  overflow-y: auto;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  animation: expandIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);

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

.thinking-content {
  font-size: 0.875em;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
  line-height: 1.6;
}

/* 工具调用 */
.tools-section {
  max-width: 85%;
  margin-bottom: 10px;
}

.tools-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  transition: background-color 0.2s ease;
  user-select: none;
}

.tools-header:hover {
  background-color: var(--color-bg-hover);
}

.tools-icon {
  font-size: 14px;
}

.tools-label {
  font-size: 0.875em;
}

.tools-body {
  margin-top: 8px;
  padding: 12px 16px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  max-height: 200px;
  max-width: 85%;
  overflow-y: auto;
  animation: expandIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);

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

.tool-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 0.875em;
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin-bottom: 4px;
}

.tool-icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.tool-text {
  word-break: break-all;
  opacity: 0.85;
}

/* 正文 */
.text-section {
  max-width: 85%;
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--color-text-primary);
}

.markdown-body {
  display: inline;
}

.markdown-body :deep(p) {
  margin-bottom: 10px;
  line-height: 1.7;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: var(--font-weight-semibold);
}

.markdown-body :deep(h2) {
  font-size: 1.2em;
}

.markdown-body :deep(h3) {
  font-size: 1.1em;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin-bottom: 10px;
}

.markdown-body :deep(li) {
  margin-bottom: 4px;
}

.markdown-body :deep(code) {
  background-color: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.markdown-body :deep(pre) {
  background-color: var(--color-bg-tertiary);
  padding: 12px 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin-bottom: 12px;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-body :deep(strong) {
  font-weight: var(--font-weight-semibold);
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--color-text-secondary);
}

.streaming-cursor {
  display: inline;
  color: var(--color-accent);
  animation: blink 1s step-end infinite;
  font-size: 1em;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 错误 */
.error-section {
  max-width: 85%;
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--color-text-primary);
}

.error-text {
  word-break: break-word;
}

/* 加载动画 */
.loading-section {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 0;
}

.loading-dot {
  font-size: 12px;
  color: var(--color-text-muted);
  animation: dotPulse 1.4s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

/* 展开动画 */
@keyframes expandIn {
  from {
    opacity: 0;
    max-height: 0;
  }
  to {
    opacity: 1;
    max-height: 200px;
  }
}

/* 下载链接 */
.download-section {
  max-width: 85%;
  margin-bottom: 12px;
}

/* 2026-06-14 改造：原 .subagent-cards 容器已移除（子智能体卡片嵌入 timeline.tool 内） */

.download-card {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
}

.download-card:hover {
  background-color: var(--color-bg-hover);
  border-color: var(--color-accent);
}

.download-icon {
  width: 20px;
  height: 20px;
  color: var(--color-accent);
}

.download-filename {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  font-weight: 500;
}

.download-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin-left: 8px;
}

/* 消息操作按钮 */
.message-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding-left: 2px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);
  position: relative;

  &:hover {
    color: var(--color-text-secondary);
    background-color: var(--color-bg-hover);
  }

  &:active {
    transform: scale(0.92);
  }

  /* Tooltip 样式 - 向上弹出 */
  &[data-tooltip]::before {
    content: attr(data-tooltip);
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%) translateY(-6px);
    padding: 6px 12px;
    background-color: #1F2937;
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 500;
    line-height: 1.4;
    white-space: nowrap;
    border-radius: 6px;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s ease, visibility 0.2s ease, transform 0.2s ease;
    pointer-events: none;
    z-index: 1000;
    box-sizing: border-box;
    max-width: 120px;
    text-align: center;
    word-wrap: break-word;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  /* Tooltip 箭头 */
  &[data-tooltip]::after {
    content: '';
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%) translateY(-6px);
    border-width: 5px;
    border-style: solid;
    border-color: #1F2937 transparent transparent transparent;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s ease, visibility 0.2s ease, transform 0.2s ease;
    pointer-events: none;
    z-index: 1000;
  }

  /* 悬停时显示 tooltip */
  &[data-tooltip]:hover::before,
  &[data-tooltip]:hover::after {
    opacity: 1;
    visibility: visible;
    transform: translateX(-50%) translateY(-8px);
  }
}

.action-icon {
  width: 16px;
  height: 16px;
}

/* 点赞按钮激活状态 - 使用红色 */
.action-btn.liked {
  color: #EF4444;
}

.action-btn.liked:hover {
  color: #DC2626;
}

/* 踩按钮激活状态 - 使用深灰色 */
.action-btn.disliked {
  color: #4B5563;
}

.action-btn.disliked:hover {
  color: #374151;
}

/* 复制成功提示 */
.copy-toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background-color: #1F2937;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 9999;
}

.toast-icon {
  width: 18px;
  height: 18px;
  color: #10B981;
}

.toast-text {
  font-size: 14px;
  color: #FFFFFF;
}

/* Toast 动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-10px);
}

.toast-enter-to {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.toast-leave-from {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-10px);
}
</style>
