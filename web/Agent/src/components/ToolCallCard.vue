<script setup>
/**
 * ToolCallCard - 普通工具调用卡片（2026-06-15 新增，2026-06-15 第二次改造）
 *
 * 用途：在父 AI 聊天气泡的 timeline.tool 块内展示普通（非 subagent）工具调用。
 * 与 SubAgentCard 视觉风格对齐：折叠头部 + 状态徽章 + 扳手闪动动画。
 * 与 SubAgentCard 关键差异：点击不触发抽屉，body 内以"步骤"形式逐步展示每条事件。
 *
 * 设计要点：
 *   - 同一 toolCallId 的所有 SSE 事件（tool_start / tool_progress / tool_stop / tool_error）
 *     合并为一张卡片，步骤按 events 数组顺序追加
 *   - 状态推断：tool_stop (data.status=success) → success；tool_error → error；否则 running
 *   - 运行时扳手图标使用 SubAgentCard 同款 subagentIconBounce 动画
 *   - 默认展开规则：running 默认展开，success/error 默认折叠
 *   - 头部显式标注「普通工具」徽章（蓝色），与 SubAgentCard（无此徽章）视觉区分
 *   - 步骤默认只显示时间戳 + 类型 + 摘要；点击单条步骤可展开 key-value 详情
 *   - 不 emit 任何抽屉相关事件
 *
 * Props:
 *   toolCallId: string - DOM key 用
 *   tool: string - 工具名（显示用）
 *   events: Array<ToolEventData> - 同一 toolCallId 下全部 custom 事件的 item.data 部分
 *   startTime?: number - 可选，开始时间 ms
 *   endTime?: number - 可选，结束时间 ms
 *
 * Emits: 无（普通工具不需要抽屉）
 */
import { ref, computed, watch } from 'vue'
import { formatSubAgentDuration } from '../utils/sseParser.js'

const props = defineProps({
  toolCallId: {
    type: String,
    required: true
  },
  tool: {
    type: String,
    required: true
  },
  events: {
    type: Array,
    required: true,
    default: () => []
  },
  startTime: {
    type: Number,
    default: 0
  },
  endTime: {
    type: Number,
    default: 0
  }
})

// 内部展开状态：卡片整体展开（控制步骤列表可见性）
const isExpanded = ref(false)
// 展开某条步骤的 key-value 详情（Set 存 step index，null 表示全部折叠）
const expandedStepIndexes = ref(new Set())

/**
 * 状态推断：遍历 events 找到 tool_stop / tool_error
 * 入参：无（读 props.events）
 * 返回：'running' | 'success' | 'error' | 'stopped_by_user'（2026-06-15 新增）
 */
const status = computed(() => {
  if (!Array.isArray(props.events) || props.events.length === 0) return 'running'
  // 倒序遍历，优先取最终事件状态
  for (let i = props.events.length - 1; i >= 0; i--) {
    const ev = props.events[i]
    if (!ev || typeof ev !== 'object') continue
    if (ev.type === 'tool_error') return 'error'
    if (ev.type === 'tool_stop') {
      // 2026-06-15 新增：data.status='stopped_by_user' → 单独状态（用户停止按钮触发）
      // 优先级（向后兼容）：
      //   1. inner.status === 'stopped_by_user' → stopped_by_user
      //   2. inner.status === 'error' / 'failure' → error
      //   3. 其他（含无 status / 'success'）→ success（默认成功）
      const inner = ev.data || {}
      if (inner.status === 'stopped_by_user') return 'stopped_by_user'
      if (inner.status === 'error' || inner.status === 'failure') return 'error'
      return 'success'
    }
  }
  return 'running'
})

const statusTextMap = {
  running: '执行中',
  success: '已完成',
  error: '执行失败',
  stopped_by_user: '已中止'  // 2026-06-15 新增：用户点击停止按钮触发的工具中止
}
const statusText = computed(() => statusTextMap[status.value] || '执行中')

const isRunning = computed(() => status.value === 'running')

// 步骤数
const stepCount = computed(() => Array.isArray(props.events) ? props.events.length : 0)

/**
 * 耗时：endTime 存在时算 endTime - startTime
 * 入参：无（读 props）
 * 返回：格式化后的字符串
 */
const duration = computed(() => {
  const start = props.startTime || 0
  const end = props.endTime || (status.value === 'running' ? Date.now() : 0)
  if (!start || !end) return ''
  return formatSubAgentDuration(end - start)
})

/**
 * 头部点击切换卡片整体展开
 * 入参：无
 * 返回：无
 */
function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

/**
 * 切换某条步骤的 key-value 详情展开
 * 入参：index - 步骤索引
 * 返回：无
 */
function toggleStepDetail(index) {
  // 触发响应式更新（Vue 3 响应式 Set）
  const next = new Set(expandedStepIndexes.value)
  if (next.has(index)) {
    next.delete(index)
  } else {
    next.add(index)
  }
  expandedStepIndexes.value = next
}

/**
 * 判断某条步骤是否处于详情展开状态
 * 入参：index
 * 返回：boolean
 */
function isStepExpanded(index) {
  return expandedStepIndexes.value.has(index)
}

// 状态变化时自动重置默认展开行为：running → 展开；success/error → 折叠
watch(status, (newStatus) => {
  isExpanded.value = newStatus === 'running'
  // 收起时清空步骤详情
  if (newStatus !== 'running') {
    expandedStepIndexes.value = new Set()
  }
}, { immediate: true })

/**
 * 事件类型中文标签
 * 入参：type（'tool_start' | 'tool_progress' | 'tool_stop' | 'tool_error'）
 * 返回：中文标签
 */
function typeLabel(type) {
  const map = {
    tool_start: '开始',
    tool_progress: '进行中',
    tool_stop: '完成',
    tool_error: '失败'
  }
  return map[type] || type
}

/**
 * 事件类型徽章配色
 * 入参：type
 * 返回：CSS class 后缀
 */
function typeClass(type) {
  const map = {
    tool_start: 'start',
    tool_progress: 'progress',
    tool_stop: 'stop',
    tool_error: 'error'
  }
  return map[type] || 'progress'
}

/**
 * 把事件 data 字典转为 key/value 列表
 * 规则：跳过 null/undefined；空 dict 返回 []；其余按 key 顺序
 * 入参：data
 * 返回：[ [key, value], ... ]
 */
function dataToEntries(data) {
  if (!data || typeof data !== 'object') return []
  const out = []
  for (const key of Object.keys(data)) {
    const v = data[key]
    if (v === null || v === undefined) continue
    if (typeof v === 'string' && v.length === 0) continue
    out.push([key, v])
  }
  return out
}

/**
 * 提取 tool_progress 的进度摘要（如 "33% 正在收集数据"）
 * 优先用 percentage + message 拼接；其次 current/total/message
 * 入参：data
 * 返回：摘要字符串；无则返回 ''
 */
function progressSummary(data) {
  if (!data || typeof data !== 'object') return ''
  const pct = data.percentage
  const msg = data.message
  if (typeof pct === 'number' && typeof msg === 'string' && msg) {
    return pct + '% ' + msg
  }
  if (typeof pct === 'number') {
    return '进度 ' + pct + '%'
  }
  if (typeof msg === 'string' && msg) {
    return msg
  }
  if (typeof data.current === 'number' && typeof data.total === 'number') {
    return data.current + ' / ' + data.total
  }
  return ''
}

/**
 * 提取 tool_start 的摘要（"开始：工具名"）
 * 入参：data
 * 返回：摘要字符串
 */
function startSummary(data) {
  if (!data || typeof data !== 'object') return ''
  if (typeof data.parent_prompt === 'string' && data.parent_prompt) {
    const p = data.parent_prompt
    return p.length > 40 ? p.slice(0, 40) + '…' : p
  }
  if (data.args && typeof data.args === 'object') {
    const argsStr = JSON.stringify(data.args)
    return argsStr.length > 60 ? argsStr.slice(0, 60) + '…' : argsStr
  }
  return ''
}

/**
 * 提取 tool_stop 的摘要
 * 入参：data
 * 返回：摘要字符串
 */
function stopSummary(data) {
  if (!data || typeof data !== 'object') return ''
  if (typeof data.status_message === 'string' && data.status_message) {
    return data.status_message
  }
  if (data.type === 'download' && data.result) {
    return '已生成可下载文件'
  }
  if (data.status === 'success') {
    return '执行成功'
  }
  return ''
}

/**
 * 提取 tool_error 的摘要
 * 入参：data
 * 返回：摘要字符串
 */
function errorSummary(data) {
  if (!data || typeof data !== 'object') return ''
  const type = data.error_type || '错误'
  const msg = data.error_message || data.message || ''
  return msg ? (type + '：' + msg) : type
}

/**
 * 按事件类型分发摘要
 * 入参：ev (item.data)
 * 返回：摘要字符串
 */
function getStepSummary(ev) {
  if (!ev || typeof ev !== 'object') return ''
  const data = ev.data || {}
  switch (ev.type) {
    case 'tool_start':
      return startSummary(data)
    case 'tool_progress':
      return progressSummary(data)
    case 'tool_stop':
      return stopSummary(data)
    case 'tool_error':
      return errorSummary(data)
    default:
      return ''
  }
}

/**
 * 时间戳转换：timestamp 字段是秒单位（来自 sseParser 透传的后端值），需 *1000
 * 入参：ts（number | string | undefined）
 * 返回：ms 数字；无则返回 0
 */
function toMillis(ts) {
  if (ts === null || ts === undefined) return 0
  const n = typeof ts === 'string' ? parseFloat(ts) : Number(ts)
  if (!isFinite(n) || n <= 0) return 0
  // 后端 timestamp 形如 1781497972.93354（秒级），乘 1000 转 ms
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n)
}

/**
 * 时间戳格式化（HH:MM:SS.mmm）
 * 入参：ms
 * 返回：字符串
 */
function formatTime(ms) {
  if (!ms) return '--:--:--'
  const d = new Date(ms)
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) + '.' + pad(d.getMilliseconds(), 3)
}

/**
 * 构造步骤列表（每条 ev 渲染一个步骤）
 * 返回：[{ tsMs, type, typeLabel, typeClass, summary, entries }]
 */
const orderedSteps = computed(() => {
  if (!Array.isArray(props.events)) return []
  return props.events.map((ev) => {
    const tsMs = toMillis(ev && ev.timestamp)
    return {
      tsMs,
      type: (ev && ev.type) || 'unknown',
      typeLabelValue: typeLabel((ev && ev.type) || 'unknown'),
      typeClass: typeClass((ev && ev.type) || 'unknown'),
      summary: getStepSummary(ev),
      entries: dataToEntries(ev && ev.data)
    }
  })
})
</script>

<template>
  <!--
    普通工具调用卡片（与 SubAgentCard 视觉区分：独立 class .tool-call-card）
    - 头部：扳手图标（running 时 bounce 动画）+ 工具名 + 「普通工具」蓝色徽章 + 步骤数 + 状态徽章 + 耗时 + 展开箭头
    - 单击头部切换整体展开
    - body：步骤列表（每步仅显示时间戳/类型/摘要，点击单条可展开 key-value 详情）
  -->
  <div
    class="tool-call-card"
    :class="[status]"
    role="region"
    :aria-label="`工具 ${tool} 调用详情`"
  >
    <div class="tool-call-header" @click="toggleExpand" role="button" tabindex="0" @keydown.enter="toggleExpand" @keydown.space.prevent="toggleExpand">
      <span class="tool-call-icon" :class="{ 'tool-call-icon-running': isRunning }" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
      </span>
      <span class="tool-call-name">{{ tool || '工具调用' }}</span>
      <span class="tool-call-badge" title="普通工具（非子智能体）">普通工具</span>
      <span class="tool-call-step-count">{{ stepCount }} 步</span>
      <span class="tool-call-status" :class="status">{{ statusText }}</span>
      <span v-if="duration" class="tool-call-duration">{{ duration }}</span>
      <span class="tool-call-hint">
        <span class="tool-call-hint-text">{{ isExpanded ? '收起' : '展开' }}</span>
        <svg
          class="tool-call-arrow"
          :class="{ expanded: isExpanded }"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </span>
    </div>

    <!--
      步骤列表（逐步追加）
      - 每步默认仅显示：时间戳 + 类型徽章 + 摘要
      - 点击单条步骤可展开 key-value 详情（不默认展示，避免视觉繁琐）
    -->
    <div v-if="isExpanded" class="tool-call-steps">
      <div
        v-for="(step, idx) in orderedSteps"
        :key="toolCallId + '-step-' + idx"
        class="tool-step"
        :class="['type-' + step.typeClass, { 'tool-step-expanded': isStepExpanded(idx) }]"
        @click="toggleStepDetail(idx)"
        role="button"
        tabindex="0"
        :aria-label="`步骤 ${idx + 1} ${step.typeLabelValue} ${step.summary}`"
        @keydown.enter="toggleStepDetail(idx)"
        @keydown.space.prevent="toggleStepDetail(idx)"
      >
        <div class="tool-step-line">
          <span class="tool-step-time">{{ formatTime(step.tsMs) }}</span>
          <span class="tool-step-type" :class="step.typeClass">{{ step.typeLabelValue }}</span>
          <span v-if="step.summary" class="tool-step-summary">{{ step.summary }}</span>
          <span v-if="step.entries.length > 0" class="tool-step-detail-toggle" :class="{ expanded: isStepExpanded(idx) }">
            <svg viewBox="0 0 20 20" fill="currentColor" width="10" height="10" aria-hidden="true">
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </span>
        </div>
        <div v-if="isStepExpanded(idx) && step.entries.length > 0" class="tool-step-detail" @click.stop>
          <div
            v-for="(entry, ei) in step.entries"
            :key="toolCallId + '-entry-' + idx + '-' + ei"
            class="tool-step-entry"
          >
            <span class="tool-step-key">{{ entry[0] }}</span>
            <span class="tool-step-value">{{ typeof entry[1] === 'object' ? JSON.stringify(entry[1]) : String(entry[1]) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   普通工具调用卡片（2026-06-15 第二次改造）
   - 与 SubAgentCard 视觉解耦：独立根 class `.tool-call-card`
   - 「普通工具」蓝色徽章显式标注，避免与 SubAgentCard 混淆
   - 步骤默认仅显示摘要，key-value 详情折叠在子步骤内（点击展开）
   - 状态色：running=accent 蓝、success=accent 蓝（与 SubAgentCard 的 success 绿色区分）、error=红
   ============================================================ */

.tool-call-card {
  width: 100%;
  max-width: 100%;
  border: 1px solid #d0d8e0;
  border-radius: 8px;
  padding: 5px 10px;
  background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  margin: 4px 0;
}

.tool-call-card:hover {
  box-shadow: 0 4px 12px rgba(30, 90, 168, 0.1);
  transform: translateY(-1px);
  border-color: var(--color-accent);
}

.tool-call-card.running {
  border-color: var(--color-accent);
  background: linear-gradient(135deg, rgba(30, 90, 168, 0.06) 0%, #ffffff 100%);
}

.tool-call-card.success {
  /* 2026-06-15 第三次：与 SubAgentCard 完成态统一为绿色（#10b981） */
  border-color: #10b981;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.04) 0%, #ffffff 100%);
}

.tool-call-card.error {
  border-color: #ef4444;
  background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
}

/* 头部 */
.tool-call-header {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  font-size: 12px;
  outline: none;
}

.tool-call-header:focus-visible {
  box-shadow: 0 0 0 2px var(--color-accent);
  border-radius: 4px;
}

.tool-call-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
  flex-shrink: 0;
}

.tool-call-icon svg {
  width: 12px;
  height: 12px;
}

.tool-call-icon-running {
  animation: toolCallIconBounce 1.2s ease-in-out infinite;
  display: inline-flex;
}

@keyframes toolCallIconBounce {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  25% {
    transform: translateY(-2px) scale(1.12);
  }
  50% {
    transform: translateY(0) scale(1);
  }
  75% {
    transform: translateY(-1px) scale(1.06);
  }
}

.tool-call-name {
  font-weight: 500;
  color: var(--color-text-primary);
  flex-shrink: 0;
}

/* 「普通工具」徽章（与 SubAgentCard 视觉区分的关键标志） */
.tool-call-badge {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 9999px;
  background-color: rgba(30, 90, 168, 0.12);
  color: var(--color-accent);
  flex-shrink: 0;
  letter-spacing: 0.02em;
}

.tool-call-step-count {
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
  padding: 1px 6px;
  background-color: var(--color-bg-tertiary);
  border-radius: 9999px;
}

.tool-call-status {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 9999px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.tool-call-status.running {
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
  animation: toolCallStatusPulse 2s ease-in-out infinite;
}

@keyframes toolCallStatusPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.tool-call-status.success {
  /* 与 SubAgentCard 的 success 绿色 (#10b981) 区分：这里用蓝色（accent） */
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
}

.tool-call-status.error {
  background-color: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

/* 2026-06-15 新增：用户中止状态（停止按钮触发） */
.tool-call-status.stopped_by_user {
  background-color: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
  /* 静态显示（无 pulse 动画） */
}

.tool-call-duration {
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.tool-call-hint {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
  margin-left: auto;
}

.tool-call-hint-text {
  white-space: nowrap;
}

.tool-call-arrow {
  width: 10px;
  height: 10px;
  transition: transform 0.2s ease;
}

.tool-call-arrow.expanded {
  transform: rotate(180deg);
}

/* ============================================================
   步骤列表（每步仅显示摘要，详情可展开）
   ============================================================ */
.tool-call-steps {
  margin-top: 6px;
  padding: 4px 0 2px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 240px;
  overflow-y: auto;
  border-top: 1px dashed rgba(30, 90, 168, 0.15);
  padding-top: 6px;
}

.tool-call-steps::-webkit-scrollbar {
  width: 4px;
}

.tool-call-steps::-webkit-scrollbar-track {
  background: transparent;
}

.tool-call-steps::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: var(--radius-full);
}

scrollbar-width: thin;
scrollbar-color: var(--color-border) transparent;

/* 单个步骤（单行紧凑） */
.tool-step {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 6px;
  border-radius: 4px;
  background-color: transparent;
  border-left: 2px solid transparent;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.08); /* 2026-06-15 第三次：步骤行间横线分隔 */
  font-size: 11px;
  line-height: 1.4;
  animation: toolStepFadeIn 0.2s ease-out;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.tool-step:last-child {
  border-bottom: none; /* 最后一步不显示分隔线 */
}

.tool-step:hover {
  background-color: rgba(30, 90, 168, 0.04);
}

.tool-step.type-start {
  border-left-color: var(--color-accent);
}

.tool-step.type-progress {
  border-left-color: #f59e0b;
}

.tool-step.type-stop {
  border-left-color: var(--color-accent);
}

.tool-step.type-error {
  border-left-color: #ef4444;
  background-color: rgba(239, 68, 68, 0.04);
}

.tool-step-expanded {
  background-color: rgba(30, 90, 168, 0.06);
}

@keyframes toolStepFadeIn {
  from {
    opacity: 0;
    transform: translateY(-2px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 单行（时间戳 + 类型 + 摘要 + 详情切换按钮） */
.tool-step-line {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tool-step-time {
  font-family: 'Courier New', monospace;
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.tool-step-type {
  font-size: 10px;
  font-weight: 600;
  padding: 0 5px;
  border-radius: 3px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  flex-shrink: 0;
  line-height: 1.6;
}

.tool-step-type.start {
  background-color: rgba(30, 90, 168, 0.12);
  color: var(--color-accent);
}

.tool-step-type.progress {
  background-color: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.tool-step-type.stop {
  background-color: rgba(30, 90, 168, 0.12);
  color: var(--color-accent);
}

.tool-step-type.error {
  background-color: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}

.tool-step-summary {
  font-size: 11px;
  color: var(--color-text-primary);
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-step-detail-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  flex-shrink: 0;
  cursor: pointer;
  transition: transform 0.2s ease, color 0.2s ease;
}

.tool-step-detail-toggle:hover {
  color: var(--color-accent);
}

.tool-step-detail-toggle.expanded {
  transform: rotate(180deg);
  color: var(--color-accent);
}

/* 详情区（点击步骤展开后的 key-value 表格） */
.tool-step-detail {
  margin-top: 4px;
  padding: 4px 6px;
  background-color: rgba(30, 90, 168, 0.04);
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-left: 2px solid rgba(30, 90, 168, 0.2);
  margin-left: 4px;
}

.tool-step-entry {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 10px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.tool-step-key {
  font-weight: 500;
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 60px;
}

.tool-step-value {
  word-break: break-all;
  white-space: pre-wrap;
  font-family: 'Courier New', monospace;
  color: var(--color-text-secondary);
}
</style>
