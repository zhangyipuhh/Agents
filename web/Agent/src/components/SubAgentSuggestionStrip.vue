<script setup>
/**
 * SubAgentSuggestionStrip 组件（2026-07-14 新增）
 *
 * 常驻展示当前用户可用的子智能体胶囊条。
 * - 数据来自 props.agents（已由父组件按 allowedAgents 过滤）
 * - 点击胶囊 → emit('select', agent)，由父组件负责切换 InputBox 智能体
 * - 仅在 agents.length > 0 时显示，否则不渲染（v-if 控制）
 *
 * Props:
 *   - agents: Array<{ name: string, display_name?: string, icon?: string }>
 *             已按 allowedAgents 过滤后的智能体列表
 *   - disabled: boolean 是否禁用所有胶囊交互（如 streaming 时）
 *
 * Emits:
 *   - select(agent): 用户点击胶囊时触发，由父组件决定后续行为
 */
import { computed } from 'vue'

const props = defineProps({
  agents: {
    type: Array,
    default: () => []
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['select'])

/**
 * 是否渲染胶囊条
 * @returns {boolean} 仅当 agents 是非空数组时为 true
 */
const hasAgents = computed(() => Array.isArray(props.agents) && props.agents.length > 0)

/**
 * 处理胶囊点击
 * @param {Object} agent - 被点击的智能体对象
 * @returns {void}
 */
function handleClick(agent) {
  if (props.disabled) return
  emit('select', agent)
}
</script>

<template>
  <div v-if="hasAgents" class="sub-agent-strip">
    <button
      v-for="agent in agents"
      :key="agent.name"
      type="button"
      class="sub-agent-chip"
      :class="{ disabled }"
      :disabled="disabled"
      @click="handleClick(agent)"
    >
      <svg class="chip-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <!-- 通用机器人图标 -->
        <path d="M10 2a1 1 0 011 1v1.07A7.002 7.002 0 0116.93 10H18a1 1 0 110 2h-1.07A7.002 7.002 0 0111 16.93V18a1 1 0 11-2 0v-1.07A7.002 7.002 0 013.07 12H2a1 1 0 110-2h1.07A7.002 7.002 0 019 4.07V3a1 1 0 011-1zm-3 8a1 1 0 100 2h6a1 1 0 100-2H7z" />
      </svg>
      <span class="chip-label">{{ agent.display_name || agent.name }}</span>
    </button>
  </div>
</template>

<style scoped>
.sub-agent-strip {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 4px 0;
}

.sub-agent-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);
  font-family: inherit;
}

.sub-agent-chip:hover:not(.disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background-color: var(--color-accent-light);
  transform: translateY(-1px);
}

.sub-agent-chip:active:not(.disabled) {
  transform: translateY(0);
}

.sub-agent-chip.disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.chip-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.chip-label {
  line-height: 1.4;
}
</style>
