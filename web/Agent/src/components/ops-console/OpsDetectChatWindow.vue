<!--
  运维控制台 - 智能检测聊天窗口（2026-08-17 新增）

  用途：
    - 由 OpsServerWindow 卡片头「智能检测」按钮触发（emit('open-detect', srv)）；
    - onMounted 自动向 /api/agent/chat 发起一次 SSE 流式对话（agent=project），
      通过 context_overrides.referenced_servers 注入当前服务器 business_name；
    - 固定两段式问题：① 最新巡检记录问题分析 + 优化建议；② 最近 2 天巡检趋势总结；
    - 回答经 safeMarkdown（DOMPurify）渲染，防 XSS。

  会话策略：
    - 合成 ops-detect:{server_id}:{ts} session_id，不调 createNewSession：
      sessions 表无记录、不污染主侧边栏；每次点击全新上下文（一次性检测语义）。

  Props:
    - win: { x, y, z, max }  窗口位置/层级/最大化状态
    - server: ServerItem     当前服务器卡片对象（需含 id / name / businessName / serverType）

  Emits:
    - close / max / front / drag  窗口控制（与 OpsInspectionLogWindow 契约一致）
-->
<script>
/**
 * 固定检测问题文本（产品契约，两段式回答）。
 * @type {string}
 */
export const DETECT_QUESTION = '按照两部分回答，1.根据最新服务器的巡检记录分析问题并提出后续的优化建议，2查询最近2天的巡检记录分析最近趋势并进行总结'

/**
 * 智能检测目标智能体（project 已绑定 query_inspection_records / get_current_time）。
 * @type {string}
 */
export const DETECT_AGENT_NAME = 'project'

/**
 * 构造本次检测的合成 session_id（不创建 sessions 表记录）。
 *
 * @param {Object} server 当前服务器 ServerItem
 * @param {number} [now=Date.now()] 毫秒时间戳（测试可注入）
 * @returns {string} 形如 ``ops-detect:{id}:{ts}`` 的会话 ID
 */
export function buildDetectSessionId(server, now = Date.now()) {
  const id = server && server.id != null ? server.id : 'unknown'
  return `ops-detect:${id}:${now}`
}

/**
 * 构造 chatStream extras（并入 context_overrides）。
 *
 * name 必须使用 business_name：后端 query_inspection_records 按
 * DevOpsServerService.list_public_servers().business_name 精确反查 server_id；
 * 卡片显示名（node_name || business_name）与 business_name 可能不同，
 * 故优先取 server.businessName，兜底 server.name。
 *
 * @param {Object} server 当前服务器 ServerItem
 * @returns {Object} ``{ referenced_servers: [{ name, server_type }] }``；空名返回 ``{}``
 */
export function buildDetectOverrides(server) {
  const name = (server && (server.businessName || server.name)) || ''
  const serverType = (server && server.serverType) || ''
  if (!name) return {}
  return { referenced_servers: [{ name, server_type: serverType }] }
}
</script>

<script setup>
import { reactive, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { chatStream, triggerAbort } from '../../utils/api.js'
import { createAiMessage, processSSEEvent } from '../../utils/sseParser.js'
import { safeMarkdown } from '../../utils/sanitize-marked.js'

const props = defineProps({
  win: { type: Object, required: true },
  server: { type: Object, required: true },
})
const emit = defineEmits(['close', 'max', 'front', 'drag'])

/** 本次检测的合成会话 ID（组件生命周期内固定） */
const sessionId = buildDetectSessionId(props.server)
/** SSE 累积消息对象（text 字段为流式正文，见 sseParser.createAiMessage） */
const aiMsg = reactive(createAiMessage())
/** 错误横幅文本（HTTP 403/429/网络错误） */
const errorMsg = ref('')
/** 是否正在流式接收 */
const isStreaming = ref(false)
/** 当前 SSE reader（unmount 时 cancel） */
let currentReader = null

/** 回答区 HTML（safeMarkdown 已过 DOMPurify，可安全 v-html） */
const renderedHtml = computed(() => safeMarkdown(aiMsg.text || ''))

/**
 * 发起一次智能检测流式对话。
 *
 * 流程：chatStream 建立 SSE → TextDecoder 按 ``\n\n`` 分帧 →
 * processSSEEvent 累积 aiMsg.text → done/error 收尾。
 * interrupt（HITL）场景直接 cancel reader 收尾（本窗口为一次性问答，不支持追问）。
 *
 * @returns {Promise<void>}
 * @throws 不向外抛；HTTP 错误写入 errorMsg 展示横幅
 */
async function runDetect() {
  errorMsg.value = ''
  isStreaming.value = true
  try {
    const stream = await chatStream(
      sessionId, DETECT_QUESTION, [], null, DETECT_AGENT_NAME, null,
      buildDetectOverrides(props.server),
    )
    currentReader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await currentReader.read()
      if (done) { aiMsg.ended = true; break }
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
          processSSEEvent(data, aiMsg, {})
          if (aiMsg.interrupt) {
            aiMsg.ended = true
            try { await currentReader.cancel() } catch { /* 忽略 */ }
          }
        } catch { /* 单帧解析失败跳过 */ }
      }
      if (aiMsg.interrupt) break
    }
  } catch (err) {
    // chatStream 抛出的 err 携带 status / detail（api.js:1047-1054）
    errorMsg.value = (typeof err?.detail === 'string' ? err.detail : err?.detail?.message)
      || err?.message || '智能检测请求失败'
    aiMsg.ended = true
  } finally {
    isStreaming.value = false
    currentReader = null
  }
}

onMounted(runDetect)

onBeforeUnmount(() => {
  // 关闭窗口时中止后端流（幂等，须在 reader.cancel 之前）+ 断开本地 reader
  triggerAbort(sessionId).catch(() => {})
  if (currentReader) {
    try { currentReader.cancel() } catch { /* 忽略 */ }
    currentReader = null
  }
})
</script>

<template>
  <div class="win win-detect" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">{{ server.name }} — 智能检测</span>
      <div class="win-controls">
        <button type="button" class="win-control win-control--max" aria-label="最大化" title="最大化"
                @click.stop="emit('max')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="5" y="5" width="14" height="14" rx="1.5"/>
          </svg>
        </button>
        <button type="button" class="win-control win-control--close" aria-label="关闭" title="关闭"
                @click.stop="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <line x1="6" y1="6" x2="18" y2="18"/>
            <line x1="18" y1="6" x2="6" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="detect-body">
      <!-- 固定问题（用户侧气泡） -->
      <div class="detect-question">{{ DETECT_QUESTION }}</div>
      <!-- 错误横幅（403 无 agent 权限 / 429 排队 / 网络错误） -->
      <div v-if="errorMsg" class="detect-error">{{ errorMsg }}</div>
      <!-- AI 流式回答（safeMarkdown 渲染） -->
      <div class="detect-answer" v-html="renderedHtml"></div>
      <span v-if="isStreaming" class="detect-cursor">▌</span>
    </div>
  </div>
</template>