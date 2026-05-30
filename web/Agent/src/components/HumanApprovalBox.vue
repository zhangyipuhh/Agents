<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  title: {
    type: String,
    default: '需要您的确认'
  },
  content: {
    type: String,
    default: ''
  },
  config: {
    type: Object,
    default: () => ({
      allow_ignore: false,
      allow_respond: true,
      allow_edit: false,
      allow_accept: true
    })
  },
  interaction_type: {
    type: String,
    default: 'input'
  },
  options: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['submit'])

const feedback = ref('')
const loading = ref(false)
const selectedOption = ref(null)

const isOptionsMode = computed(() => {
  return props.interaction_type === 'options' && props.options.length > 0
})

const showInput = computed(() => {
  if (isOptionsMode.value) return false
  return props.config.allow_respond || props.config.allow_edit
})

const canSubmit = computed(() => {
  if (loading.value) return false
  if (isOptionsMode.value) {
    return selectedOption.value !== null
  }
  if (showInput.value) {
    return feedback.value.trim().length > 0
  }
  return true
})

const handleOptionSelect = (option) => {
  selectedOption.value = option
}

const handleSubmit = (decision) => {
  if (!canSubmit.value && decision === 'approve') return
  loading.value = true
  if (isOptionsMode.value && selectedOption.value) {
    emit('submit', {
      decision: selectedOption.value.value,
      feedback: selectedOption.value.label
    })
  } else {
    emit('submit', {
      decision,
      feedback: feedback.value.trim()
    })
  }
}
</script>

<template>
  <div class="approval-box-container">
    <div class="input-wrapper">
      <div class="approval-main">
        <div class="approval-header">
          <svg class="approval-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
          </svg>
          <span class="approval-title">{{ title }}</span>
        </div>

        <div class="approval-content">{{ content }}</div>

        <div v-if="isOptionsMode" class="options-list">
          <button
            v-for="option in options"
            :key="option.value"
            class="option-btn"
            :class="{ selected: selectedOption && selectedOption.value === option.value }"
            :disabled="loading"
            @click="handleOptionSelect(option)"
          >
            {{ option.label }}
          </button>
        </div>

        <textarea
          v-if="showInput"
          v-model="feedback"
          class="approval-input"
          :placeholder="config.allow_edit ? '请输入修改后的内容...' : '请输入您的反馈...'"
          rows="3"
        ></textarea>

        <div class="approval-actions">
          <button
            v-if="config.allow_ignore"
            class="action-btn ignore-btn"
            :disabled="loading"
            @click="handleSubmit('ignore')"
          >
            忽略
          </button>
          <button
            v-if="config.allow_accept !== false"
            class="action-btn confirm-btn"
            :class="{ disabled: !canSubmit }"
            :disabled="!canSubmit"
            @click="handleSubmit('approve')"
          >
            <span v-if="loading" class="loading-spinner"></span>
            <span v-else>确认</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.approval-box-container {
  padding: 16px 40px 24px;
  background-color: rgb(249, 250, 251);
}

.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

.approval-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--color-accent);
  border-radius: var(--radius-lg);
  transition: var(--transition-colors), var(--transition-shadow), border-color 0.25s ease;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), 0 2px 6px rgba(0, 0, 0, 0.1);
}

.approval-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.approval-icon {
  width: 20px;
  height: 20px;
  color: var(--color-accent);
  flex-shrink: 0;
}

.approval-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  line-height: var(--line-height-normal);
}

.approval-content {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
  white-space: pre-wrap;
  word-break: break-word;
}

.approval-input {
  width: 100%;
  min-height: 80px;
  max-height: 160px;
  padding: 10px 12px;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  resize: vertical;
  overflow-y: auto;
  transition: var(--transition-colors), border-color 0.2s ease;
}

.approval-input::placeholder {
  color: var(--color-text-muted);
}

.approval-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.approval-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 4px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 20px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  border: none;
}

.action-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.ignore-btn {
  background-color: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}

.ignore-btn:hover:not(:disabled) {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.confirm-btn {
  background-color: var(--color-accent);
  color: white;
}

.confirm-btn:hover:not(.disabled) {
  background-color: var(--color-accent-hover);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.confirm-btn.disabled {
  background-color: var(--color-border);
  cursor: not-allowed;
  opacity: var(--opacity-disabled);
}

.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.options-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 4px 0;
}

.option-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 20px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
}

.option-btn:hover:not(:disabled) {
  background-color: var(--color-bg-hover);
  border-color: var(--color-accent);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
}

.option-btn.selected {
  background-color: var(--color-accent);
  color: white;
  border-color: var(--color-accent);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.option-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.option-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}
</style>
