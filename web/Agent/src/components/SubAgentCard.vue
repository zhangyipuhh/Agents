<script setup>
/**
 * SubAgentCard - 通用子智能体折叠卡片（2026-06-13 新增）
 *
 * 用途：在父 AI 聊天气泡内展示子智能体（如 sandbox / explore）的折叠摘要。
 * 点击后由父组件触发 open-subagent-drawer 事件，打开右侧 SubAgentDrawer。
 *
 * Props:
 *   subAgent: SubAgentSummary，必填
 *     {
 *       toolCallId, threadId, tool, parentPrompt, messages,
 *       events, status: 'running' | 'success' | 'error',
 *       startTime, endTime, error
 *     }
 *
 * Emits:
 *   click: 用户点击卡片（父组件负责打开抽屉）
 */
import { computed } from 'vue'
import { getSubAgentMeta, formatSubAgentDuration } from '../utils/sseParser.js'

const props = defineProps({
  subAgent: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['click'])

function handleClick() {
  emit('click', props.subAgent)
}

const meta = computed(() => getSubAgentMeta(props.subAgent.tool))
const status = computed(() => props.subAgent.status || 'running')

// 状态徽章文本与样式
const statusTextMap = {
  running: '执行中',
  success: '已完成',
  error: '执行失败'
}
const statusText = computed(() => statusTextMap[status.value] || '执行中')

// 父 agent 提问预览（前 30 字符）
const promptPreview = computed(() => {
  const p = props.subAgent.parentPrompt || ''
  if (!p) return ''
  return p.length > 30 ? p.slice(0, 30) + '…' : p
})

// 消息数
const messageCount = computed(() => {
  const m = props.subAgent.messages
  return Array.isArray(m) ? m.length : 0
})

// 耗时（endTime 已设置时计算；否则使用当前时间 - startTime）
const duration = computed(() => {
  if (!props.subAgent.startTime) return ''
  const end = props.subAgent.endTime || Date.now()
  return formatSubAgentDuration(end - props.subAgent.startTime)
})
</script>

<template>
  <!--
    通用子智能体折叠卡片：
    - 浅色背景 + 边框 + 圆角，参考 SandboxProgress 视觉风格
    - 4-6px padding 适合在主时间线中并排多个
    - 整卡片可点击
  -->
  <div
    class="subagent-card"
    :class="[status, { clickable: true }]"
    role="button"
    :aria-label="`查看子智能体 ${meta.label} 详情`"
    @click="handleClick"
  >
    <div class="subagent-row">
      <span class="subagent-icon" :class="{ 'subagent-icon-running': status === 'running' }">{{ meta.icon }}</span>
      <span class="subagent-name">{{ meta.label }}</span>
      <span v-if="promptPreview" class="subagent-prompt" :title="subAgent.parentPrompt">
        {{ promptPreview }}
      </span>
      <span class="subagent-status" :class="status">{{ statusText }}</span>
      <span v-if="messageCount > 0" class="subagent-meta">{{ messageCount }} 条消息</span>
      <span v-if="duration" class="subagent-duration">{{ duration }}</span>
      <span class="subagent-hint">
        <span class="hint-text">查看详情</span>
        <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </span>
    </div>
    <div v-if="status === 'error' && subAgent.error" class="subagent-error">
      {{ subAgent.error }}
    </div>
  </div>
</template>

<style scoped>
.subagent-card {
  width: 100%;
  max-width: 100%;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 5px 10px;
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  margin: 4px 0;
}

.subagent-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
  border-color: var(--color-accent);
}

.subagent-card.running {
  border-color: var(--color-accent);
  background: linear-gradient(135deg, var(--color-accent-light) 0%, #ffffff 100%);
}

.subagent-card.success {
  border-color: #10b981;
}

.subagent-card.error {
  border-color: #ef4444;
  background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
}

.subagent-row {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  font-size: 12px;
}

.subagent-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.subagent-icon-running {
  animation: subagentIconBounce 1.2s ease-in-out infinite;
  display: inline-block;
}

@keyframes subagentIconBounce {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  25% {
    transform: translateY(-3px) scale(1.15);
  }
  50% {
    transform: translateY(0) scale(1);
  }
  75% {
    transform: translateY(-2px) scale(1.1);
  }
}

.subagent-name {
  font-weight: 500;
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.subagent-prompt {
  color: var(--color-text-secondary);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.subagent-status {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 9999px;
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.subagent-status.running {
  background-color: rgba(30, 90, 168, 0.1);
  color: var(--color-accent);
  animation: statusPulse 2s ease-in-out infinite;
}

@keyframes statusPulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

.subagent-status.success {
  background-color: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.subagent-status.error {
  background-color: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.subagent-meta,
.subagent-duration {
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.subagent-hint {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.hint-text {
  white-space: nowrap;
}

.arrow-icon {
  width: 10px;
  height: 10px;
}

.subagent-error {
  margin-top: 4px;
  padding: 4px 8px;
  background-color: rgba(239, 68, 68, 0.08);
  border-radius: 4px;
  color: #b91c1c;
  font-size: 11px;
  line-height: 1.4;
}
</style>
