<script setup>
/**
 * QueueStatusBanner — 动态排队提示横幅（2026-06-15 新增）
 *
 * 显示在 ChatArea 下方、InputBox 上方，提示用户当前 Agent 聊天接口的并发排队状态。
 * 数据由后端 SSE `queue` 事件（chat_concurrency_dependency 推送）或 HTTP 429 响应驱动。
 *
 * Props:
 *   queueStatus: {
 *     event: 'idle' | 'waiting' | 'ready',
 *     waitingCount: number,
 *     activeCount: number,
 *     maxConcurrency: number,
 *     position: number,
 *     timestamp: number
 *   }
 *
 * isVisible 由父组件根据 event==='waiting' 计算并传入，用于控制显示/隐藏。
 */
import { computed } from 'vue'

const props = defineProps({
  queueStatus: {
    type: Object,
    default: () => ({
      event: 'idle',
      waitingCount: 0,
      activeCount: 0,
      maxConcurrency: 0,
      position: 0,
      timestamp: 0
    })
  },
  isVisible: {
    type: Boolean,
    default: false
  }
})

/**
 * 计算展示文案
 * - waiting + 槽位已满（active >= max）：显示 "X/Y 个并发槽位已满，您前面还有 N 位..."
 * - waiting + 槽位已空闲（active < max）：显示 "队列即将处理您的请求..."
 * - ready / idle: 不显示文案（banner 立即消失）
 */
const displayText = computed(() => {
  const s = props.queueStatus
  if (s.event !== 'waiting') return ''
  const total = s.maxConcurrency || 0
  const active = s.activeCount || 0
  // 2026-06-15 修复：避免"槽位已空闲但文案仍说已满"的语义矛盾
  if (active < total) {
    return `队列即将处理您的请求（${active}/${total}）`
  }
  // 排在自己前面的人数 = position - 1（position 是 1-based）
  const ahead = Math.max(0, (s.position || 1) - 1)
  return `当前并发槽位已满（${active}/${total}），您前面还有 ${ahead} 位用户正在排队…`
})

/**
 * 计算 badge 数字（显示自己位置）
 */
const positionBadge = computed(() => {
  const s = props.queueStatus
  if (s.event !== 'waiting') return null
  return Math.max(1, s.position || 1)
})

/**
 * 是否展示 banner
 */
const showBanner = computed(() => {
  return props.isVisible && props.queueStatus.event === 'waiting'
})
</script>

<template>
  <transition name="queue-banner">
    <div v-if="showBanner" class="queue-status-banner" role="status" aria-live="polite">
      <svg class="queue-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625l6.28-10.875zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>
      </svg>
      <span class="queue-text">{{ displayText }}</span>
      <span v-if="positionBadge" class="queue-position-badge">{{ positionBadge }}</span>
    </div>
  </transition>
</template>

<style scoped>
.queue-status-banner {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 10px 16px;
  margin: 0 auto;
  max-width: 900px;
  background-color: #FEF3C7;
  border: 1px solid #FCD34D;
  border-radius: var(--radius-md);
  color: #92400E;
  font-size: var(--font-size-sm);
  line-height: var(--line-height-normal);
  box-shadow: var(--shadow-sm);
}

.queue-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: var(--color-warning);
}

.queue-text {
  flex: 1;
  min-width: 0;
  font-weight: var(--font-weight-medium);
}

.queue-position-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  background-color: var(--color-warning);
  color: var(--color-text-inverse);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-full);
  animation: queueBadgePulse 2s ease-in-out infinite;
}

/* 进场：从上方滑入 */
.queue-banner-enter-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.queue-banner-enter-from {
  opacity: 0;
  transform: translateY(-12px);
}

/* 退场：淡出 */
.queue-banner-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.queue-banner-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@keyframes queueBadgePulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.85;
  }
}
</style>