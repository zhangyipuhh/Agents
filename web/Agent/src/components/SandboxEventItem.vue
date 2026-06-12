<script setup>
/**
 * SandboxEventItem - 单个沙盒事件展示组件
 *
 * Props:
 *   event: 沙盒事件对象，包含 type, title, content, command, file_path, status 等字段
 *   isActive: 是否为当前激活步骤
 *
 * 支持的事件类型:
 *   code_generation: 代码生成（带语法高亮）
 *   file_write: 写入文件（显示文件路径和代码预览）
 *   file_read: 读取文件（显示文件路径）
 *   command_execute: 执行命令（命令行样式）
 *   command_output: 命令输出（终端输出样式）
 *   result_analysis: 结果分析（摘要样式）
 *   error: 错误信息（红色错误样式）
 */
const props = defineProps({
  event: {
    type: Object,
    required: true
  },
  isActive: {
    type: Boolean,
    default: false
  }
})

const eventTypeMap = {
  code_generation: { icon: '📝', label: '生成代码' },
  file_write: { icon: '💾', label: '写入文件' },
  file_read: { icon: '📖', label: '读取文件' },
  command_execute: { icon: '▶️', label: '执行命令' },
  command_output: { icon: '📤', label: '获取输出' },
  result_analysis: { icon: '✅', label: '分析结果' },
  error: { icon: '❌', label: '错误' }
}

const typeInfo = computed(() => {
  return eventTypeMap[props.event.type] || { icon: '•', label: props.event.type || '未知' }
})

const statusClass = computed(() => {
  const status = props.event.status
  if (status === 'running') return 'status-running'
  if (status === 'error') return 'status-error'
  return 'status-completed'
})

const statusIcon = computed(() => {
  const status = props.event.status
  if (status === 'running') return '⏳'
  if (status === 'error') return '❌'
  return '✓'
})
</script>

<script>
import { computed } from 'vue'
export default {
  name: 'SandboxEventItem'
}
</script>

<template>
  <div class="sandbox-event-item" :class="[statusClass, { active: isActive }]">
    <div class="event-marker">
      <div class="marker-dot"></div>
      <div v-if="isActive" class="marker-pulse"></div>
    </div>

    <div class="event-content">
      <div class="event-header">
        <span class="event-icon">{{ typeInfo.icon }}</span>
        <span class="event-title">{{ event.title || typeInfo.label }}</span>
        <span class="event-status-icon">{{ statusIcon }}</span>
      </div>

      <!-- 代码生成 / 文件写入：展示代码块 -->
      <div v-if="event.content && (event.type === 'code_generation' || event.type === 'file_write')" class="event-code-block">
        <div v-if="event.file_path" class="event-file-path">{{ event.file_path }}</div>
        <pre class="event-code"><code>{{ event.content }}</code></pre>
      </div>

      <!-- 执行命令：展示命令行 -->
      <div v-else-if="event.command || event.type === 'command_execute'" class="event-command">
        <div class="command-line">
          <span class="command-prompt">$</span>
          <span class="command-text">{{ event.command || event.content || '' }}</span>
        </div>
      </div>

      <!-- 命令输出：展示终端输出 -->
      <div v-else-if="event.type === 'command_output' && event.content" class="event-output">
        <pre class="output-text">{{ event.content }}</pre>
      </div>

      <!-- 文件读取：展示文件路径 -->
      <div v-else-if="event.type === 'file_read' && event.file_path" class="event-file-info">
        <span class="file-path">{{ event.file_path }}</span>
      </div>

      <!-- 错误信息 -->
      <div v-else-if="event.type === 'error' && event.content" class="event-error">
        <span class="error-text">{{ event.content }}</span>
      </div>

      <!-- 通用内容 -->
      <div v-else-if="event.content" class="event-generic">
        <span class="generic-text">{{ event.content }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sandbox-event-item {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  position: relative;
}

.event-marker {
  position: relative;
  width: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.marker-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #10b981;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 2px #e0e0e0;
  z-index: 1;
}

.sandbox-event-item.status-running .marker-dot {
  background-color: #f59e0b;
}

.sandbox-event-item.status-error .marker-dot {
  background-color: #ef4444;
}

.sandbox-event-item.active .marker-dot {
  background-color: #10b981;
  box-shadow: 0 0 0 2px #10b981;
}

.marker-pulse {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #10b981;
  animation: markerPulse 2s ease-in-out infinite;
  z-index: 0;
}

@keyframes markerPulse {
  0% {
    transform: scale(1);
    opacity: 0.6;
  }
  100% {
    transform: scale(3);
    opacity: 0;
  }
}

.event-content {
  flex: 1;
  min-width: 0;
  background-color: var(--color-bg-tertiary);
  border-radius: 8px;
  padding: 10px 12px;
  border: 1px solid transparent;
  transition: border-color 0.2s ease;
}

.sandbox-event-item.active .event-content {
  border-color: #10b981;
  background-color: #f0fdf4;
}

.event-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.event-icon {
  font-size: 14px;
}

.event-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.event-status-icon {
  font-size: 12px;
  color: var(--color-text-muted);
}

.sandbox-event-item.status-error .event-status-icon {
  color: #ef4444;
}

/* 代码块样式 */
.event-code-block {
  margin-top: 6px;
}

.event-file-path {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-bottom: 4px;
  font-family: monospace;
}

.event-code {
  margin: 0;
  padding: 8px 10px;
  background-color: #1f2937;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}

.event-code code {
  color: #e5e7eb;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
}

/* 命令行样式 */
.event-command {
  margin-top: 6px;
}

.command-line {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background-color: #1f2937;
  border-radius: 6px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
}

.command-prompt {
  color: #10b981;
  font-weight: bold;
}

.command-text {
  color: #e5e7eb;
}

/* 输出样式 */
.event-output {
  margin-top: 6px;
}

.output-text {
  margin: 0;
  padding: 8px 10px;
  background-color: #f3f4f6;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

/* 文件信息样式 */
.event-file-info {
  margin-top: 6px;
  padding: 6px 10px;
  background-color: #eff6ff;
  border-radius: 6px;
  font-size: 12px;
  color: #3b82f6;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
}

/* 错误样式 */
.event-error {
  margin-top: 6px;
  padding: 8px 10px;
  background-color: #fef2f2;
  border-radius: 6px;
  font-size: 12px;
  color: #ef4444;
}

/* 通用内容样式 */
.event-generic {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.generic-text {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
