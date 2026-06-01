<script setup>
import { ref, computed, watch, nextTick } from 'vue'

/**
 * HumanApprovalBox
 * 多问题结构化问答组件（替代旧的 request_human_approval 单题审批 UI）。
 *
 * Props:
 *   questions: Array<{
 *     question: string,
 *     header: string,    // Tab 标题（≤12 字符）
 *     options: Array<{ label: string, description: string }>,
 *     multiple: boolean  // 是否允许多选
 *   }>
 *
 * Emits:
 *   submit({ answers: string[][] })  // answers[i] = 第 i 个问题选中的 label 列表
 */
const props = defineProps({
  questions: {
    type: Array,
    default: () => [],
    validator: (val) => Array.isArray(val)
  }
})

const emit = defineEmits(['submit'])

const activeTab = ref(0)
const answers = ref([])
const customInputs = ref([])
const freeformInputs = ref([])
const editing = ref([])
const loading = ref(false)
const textareaRefs = ref([])

watch(
  () => props.questions,
  (newQuestions) => {
    activeTab.value = 0
    answers.value = newQuestions.map((q) => (q.multiple ? [] : null))
    customInputs.value = newQuestions.map(() => '')
    freeformInputs.value = newQuestions.map(() => '')
    editing.value = newQuestions.map(() => false)
  },
  { immediate: true, deep: true }
)

/**
 * 判断某个问题是否已回答（用于 Tab 状态指示器）
 */
const isAnswered = (idx) => {
  if (idx < 0 || idx >= answers.value.length) return false
  const q = props.questions[idx]
  // 纯文本问题：检查 freeform 输入
  if (!q.options || q.options.length === 0) {
    return (freeformInputs.value[idx] || '').trim().length > 0
  }
  const ans = answers.value[idx]
  if (Array.isArray(ans)) return ans.length > 0
  return ans !== null && ans !== undefined
}

/**
 * 判断当前问题是否为纯文本（无 options）模式
 */
const isCurrentFreeform = computed(() => {
  const q = currentQuestion.value
  return q && (!q.options || q.options.length === 0)
})

const isOtherItem = (option) => option.label === 'Other'

/**
 * 切换选项（单选覆盖 / 多选累加）
 * 点击 Other 时切到编辑模式，弹出 textarea
 */
const toggleOption = (qIdx, option) => {
  const q = props.questions[qIdx]
  if (q.multiple) {
    const cur = answers.value[qIdx] || []
    const i = cur.indexOf(option.label)
    if (i >= 0) cur.splice(i, 1)
    else cur.push(option.label)
    answers.value[qIdx] = [...cur]
  } else {
    if (answers.value[qIdx] === option.label) {
      answers.value[qIdx] = null
    } else {
      answers.value[qIdx] = option.label
    }
  }

  if (isOtherItem(option)) {
    editing.value[qIdx] = true
    nextTick(() => {
      const el = textareaRefs.value[qIdx]
      if (el && el.focus) el.focus()
    })
  } else {
    editing.value[qIdx] = false
  }
}

/**
 * 提交 Other 项的输入文本：
 * - 选中的 label 为"Other"
 * - 文本非空时同步写入 answers（仅在 multiple=false 下覆盖）
 * - 文本为空时清空 answers
 */
const commitOther = (qIdx) => {
  const text = (customInputs.value[qIdx] || '').trim()
  if (text) {
    if (!props.questions[qIdx].multiple) {
      answers.value[qIdx] = text
    } else {
      const cur = answers.value[qIdx] || []
      if (!cur.includes('Other')) cur.push('Other')
      answers.value[qIdx] = [...cur]
    }
    editing.value[qIdx] = false
  } else {
    if (props.questions[qIdx].multiple) {
      answers.value[qIdx] = (answers.value[qIdx] || []).filter((l) => l !== 'Other')
    } else {
      answers.value[qIdx] = null
    }
    editing.value[qIdx] = false
  }
}

/**
 * 取消 Other 编辑：清空文本并收起 textarea
 */
const cancelOther = (qIdx) => {
  customInputs.value[qIdx] = ''
  editing.value[qIdx] = false
  if (!props.questions[qIdx].multiple) {
    answers.value[qIdx] = null
  } else {
    answers.value[qIdx] = (answers.value[qIdx] || []).filter((l) => l !== 'Other')
  }
}

/**
 * 切换到指定 Tab（提交当前 Tab 的 Other 输入）
 */
const switchTab = (idx) => {
  if (editing.value[activeTab.value]) {
    commitOther(activeTab.value)
  }
  activeTab.value = idx
}

/**
 * 全局提交：构造 answers 二维数组
 */
const handleSubmit = () => {
  if (loading.value) return
  if (!canSubmit.value) return
  loading.value = true
  if (editing.value[activeTab.value]) {
    commitOther(activeTab.value)
  }
  const finalAnswers = props.questions.map((q, i) => {
    // 纯文本问题：从 freeformInputs 取值
    if (!q.options || q.options.length === 0) {
      const text = (freeformInputs.value[i] || '').trim()
      return text ? [text] : []
    }
    const ans = answers.value[i]
    if (q.multiple) {
      return Array.isArray(ans) && ans.length > 0 ? [...ans] : []
    } else {
      return ans ? [ans] : []
    }
  })
  emit('submit', { answers: finalAnswers })
}

const isCurrentAnswered = computed(() => isAnswered(activeTab.value))

/**
 * 全局可提交条件：所有问题都答了
 */
const canSubmit = computed(() => {
  if (loading.value) return false
  if (props.questions.length === 0) return false
  return props.questions.every((_, i) => isAnswered(i))
})

const currentQuestion = computed(() => props.questions[activeTab.value] || null)
</script>

<template>
  <div v-if="currentQuestion" class="approval-box-container">
    <div class="input-wrapper">
      <div class="approval-main">
        <div class="approval-header">
          <svg class="approval-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
          </svg>
          <span class="approval-title">{{ currentQuestion.question }}</span>
        </div>

        <div v-if="questions.length > 1" class="tab-bar">
          <button
            v-for="(q, i) in questions"
            :key="i"
            class="tab-btn"
            :class="{ active: activeTab === i, answered: isAnswered(i) && activeTab !== i }"
            @click="switchTab(i)"
          >
            {{ q.header || `问题 ${i + 1}` }}
            <span v-if="isAnswered(i)" class="tab-check">✓</span>
          </button>
        </div>

        <div v-if="isCurrentFreeform" class="freeform-editor">
          <textarea
            v-model="freeformInputs[activeTab]"
            class="freeform-input"
            placeholder="请输入您的回答..."
            rows="3"
            :disabled="loading"
          ></textarea>
        </div>

        <div v-else class="options-list">
          <button
            v-for="option in currentQuestion.options"
            :key="option.label"
            class="option-btn"
            :class="{
              selected: currentQuestion.multiple
                ? (answers[activeTab] || []).includes(option.label)
                : answers[activeTab] === option.label
            }"
            :disabled="loading"
            @click="toggleOption(activeTab, option)"
          >
            <span class="option-marker" v-if="currentQuestion.multiple">
              <span v-if="(answers[activeTab] || []).includes(option.label)">☑</span>
              <span v-else>☐</span>
            </span>
            <span class="option-marker" v-else>
              <span v-if="answers[activeTab] === option.label">●</span>
              <span v-else>○</span>
            </span>
            <div class="option-content">
              <div class="option-label">{{ option.label }}</div>
              <div v-if="option.description" class="option-desc">{{ option.description }}</div>
            </div>
          </button>
        </div>

        <div v-if="editing[activeTab]" class="other-editor">
          <textarea
            :ref="(el) => { if (el) textareaRefs[activeTab] = el }"
            v-model="customInputs[activeTab]"
            class="other-input"
            placeholder="请输入您的具体内容..."
            rows="2"
            @keydown.enter.exact.prevent="commitOther(activeTab)"
            @keydown.escape.prevent="cancelOther(activeTab)"
            @blur="commitOther(activeTab)"
          ></textarea>
          <div class="other-hint">回车提交 · Esc 取消</div>
        </div>

        <div class="approval-actions">
          <button
            class="action-btn confirm-btn"
            :class="{ disabled: !canSubmit }"
            :disabled="!canSubmit"
            @click="handleSubmit"
          >
            <span v-if="loading" class="loading-spinner"></span>
            <span v-else>{{ questions.length > 1 ? '提交所有回答' : '提交' }}</span>
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
  align-items: flex-start;
  gap: 8px;
}

.approval-icon {
  width: 20px;
  height: 20px;
  color: var(--color-accent);
  flex-shrink: 0;
  margin-top: 2px;
}

.approval-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  line-height: var(--line-height-normal);
}

.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--color-border);
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  background-color: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-btn:hover:not(.active) {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.tab-btn.active {
  background-color: var(--color-accent);
  color: white;
  border-color: var(--color-accent);
}

.tab-btn.answered {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.tab-check {
  font-size: 11px;
  line-height: 1;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}

.option-btn {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
}

.option-btn:hover:not(:disabled) {
  background-color: var(--color-bg-hover);
  border-color: var(--color-accent);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
}

.option-btn.selected {
  background-color: rgba(99, 102, 241, 0.08);
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.option-btn:active:not(:disabled) {
  transform: scale(0.99);
}

.option-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.option-marker {
  font-size: 16px;
  line-height: 1.3;
  color: var(--color-accent);
  flex-shrink: 0;
  min-width: 16px;
}

.option-content {
  flex: 1;
  min-width: 0;
}

.option-label {
  font-weight: var(--font-weight-medium);
  margin-bottom: 2px;
}

.option-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
}

.other-editor {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 4px;
}

.other-input {
  width: 100%;
  min-height: 60px;
  max-height: 120px;
  padding: 8px 12px;
  font-size: var(--font-size-sm);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-md);
  resize: vertical;
  overflow-y: auto;
  transition: var(--transition-colors), border-color 0.2s ease;
}

.other-input:focus {
  outline: none;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.other-hint {
  font-size: 11px;
  color: var(--color-text-muted);
  text-align: right;
}

.freeform-editor {
  padding: 0 4px;
}

.freeform-input {
  width: 100%;
  min-height: 80px;
  max-height: 160px;
  padding: 10px 12px;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-md);
  resize: vertical;
  overflow-y: auto;
  transition: var(--transition-colors), border-color 0.2s ease;
}

.freeform-input::placeholder {
  color: var(--color-text-muted);
}

.freeform-input:focus {
  outline: none;
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
</style>
