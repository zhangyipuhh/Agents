<script setup>
/**
 * DislikeDialog - AI 回复点踩反馈弹窗（2026-07-02 新增）
 *
 * 用户点击消息气泡的"踩"按钮时弹出，收集：
 *   - problem_description：问题描述（必填，3-2000 字符）
 *   - expected_answer：期望的样子（可选，0-2000 字符）
 *   - problem_type：问题类型（事实错误 / 逻辑不通 / 答非所问 / 其他）
 * 提交时调用 utils/api.js 的 submitMessageFeedback，成功后 emit('submitted', id)。
 *
 * Props:
 *   visible: boolean (v-model:visible)
 *   messageId: string
 *   sessionId: string
 *   messageContent?: string - 用户原始问题内容（用于反馈时填充 message_content）
 *   aiReply?: string - AI 回复内容（用于反馈时填充 ai_reply）
 *   agentName?: string
 *
 * Emits:
 *   update:visible
 *   submitted(id: number)
 */
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { submitMessageFeedback } from '../utils/api.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  messageId: { type: String, default: '' },
  sessionId: { type: String, default: '' },
  messageContent: { type: String, default: '' },
  aiReply: { type: String, default: '' },
  agentName: { type: String, default: '' }
})

const emit = defineEmits(['update:visible', 'submitted'])

const problemDescription = ref('')
const expectedAnswer = ref('')
const problemType = ref('factual_error')
const submitting = ref(false)
const errorMessage = ref('')
const descriptionTextareaRef = ref(null)

const problemTypeOptions = [
  { value: 'factual_error', label: '事实错误' },
  { value: 'logic_error',    label: '逻辑不通' },
  { value: 'off_topic',      label: '答非所问' },
  { value: 'other',          label: '其他' }
]

const isDescriptionValid = () => {
  const t = (problemDescription.value || '').trim()
  return t.length >= 3 && t.length <= 2000
}

watch(() => props.visible, async (open) => {
  if (typeof document === 'undefined') return
  if (open) {
    document.body.style.overflow = 'hidden'
    errorMessage.value = ''
    await nextTick()
    if (descriptionTextareaRef.value && descriptionTextareaRef.value.focus) {
      descriptionTextareaRef.value.focus()
    }
  } else {
    document.body.style.overflow = ''
    // 关闭时清空内容
    setTimeout(() => {
      problemDescription.value = ''
      expectedAnswer.value = ''
      problemType.value = 'factual_error'
      errorMessage.value = ''
    }, 200)
  }
})

function close() {
  if (submitting.value) return
  emit('update:visible', false)
}

function handleBackdropClick(e) {
  if (e.target === e.currentTarget) {
    close()
  }
}

function handleKeyDown(e) {
  if (e.key === 'Escape' && props.visible) {
    close()
  }
}

async function handleSubmit() {
  errorMessage.value = ''
  if (!isDescriptionValid()) {
    errorMessage.value = '问题描述不能为空，长度需在 3-2000 字符之间'
    return
  }
  if (!props.messageId || !props.sessionId) {
    errorMessage.value = '消息上下文缺失（messageId/sessionId 为空）'
    return
  }
  submitting.value = true
  try {
    const result = await submitMessageFeedback({
      session_id: props.sessionId,
      message_id: props.messageId,
      feedback_type: 'dislike',
      problem_type: problemType.value,
      problem_description: problemDescription.value.trim(),
      expected_answer: (expectedAnswer.value || '').trim() || null,
      message_content: props.messageContent || null,
      ai_reply: props.aiReply || null,
      agent_name: props.agentName || null
    })
    emit('submitted', result.id)
    emit('update:visible', false)
  } catch (e) {
    errorMessage.value = e && e.message ? e.message : '提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeyDown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown)
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dislike-fade">
      <div
        v-if="visible"
        class="dislike-modal"
        @click="handleBackdropClick"
        role="dialog"
        aria-modal="true"
        aria-label="反馈问题"
      >
        <div class="dislike-panel" @click.stop>
          <div class="dislike-header">
            <span class="dislike-title">反馈问题</span>
            <button
              type="button"
              class="dislike-close-btn"
              :disabled="submitting"
              @click="close"
              aria-label="关闭"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="close-icon">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>

          <div class="dislike-body">
            <div class="form-row">
              <label class="form-label required">问题描述</label>
              <textarea
                ref="descriptionTextareaRef"
                v-model="problemDescription"
                class="form-textarea"
                placeholder="请具体描述问题在哪里（不少于 3 个字符）"
                rows="4"
                maxlength="2000"
                :disabled="submitting"
              />
              <div class="form-hint">{{ problemDescription.length }} / 2000</div>
            </div>

            <div class="form-row">
              <label class="form-label">期望的样子（可选）</label>
              <textarea
                v-model="expectedAnswer"
                class="form-textarea"
                placeholder="您觉得应该是什么样的回答（可选）"
                rows="3"
                maxlength="2000"
                :disabled="submitting"
              />
            </div>

            <div class="form-row">
              <label class="form-label">问题类型</label>
              <select
                v-model="problemType"
                class="form-select"
                :disabled="submitting"
              >
                <option
                  v-for="opt in problemTypeOptions"
                  :key="opt.value"
                  :value="opt.value"
                >{{ opt.label }}</option>
              </select>
            </div>

            <div v-if="errorMessage" class="form-error">{{ errorMessage }}</div>
          </div>

          <div class="dislike-footer">
            <button
              type="button"
              class="btn-cancel"
              :disabled="submitting"
              @click="close"
            >取消</button>
            <button
              type="button"
              class="btn-submit"
              :disabled="submitting || !isDescriptionValid()"
              @click="handleSubmit"
            >{{ submitting ? '提交中...' : '提交反馈' }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dislike-modal {
  position: fixed;
  inset: 0;
  z-index: 2100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background-color: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
}

.dislike-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 520px;
  max-height: calc(100vh - 48px);
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.dislike-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.dislike-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.dislike-close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors);
  border: none;
  background: none;
}
.dislike-close-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  background-color: var(--color-bg-hover);
}
.dislike-close-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.close-icon { width: 18px; height: 18px; }

.dislike-body {
  flex: 1;
  min-height: 0;
  padding: 18px;
  overflow-y: auto;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.form-row:last-child { margin-bottom: 0; }

.form-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}
.form-label.required::after {
  content: ' *';
  color: var(--color-error, #e53935);
}

.form-textarea,
.form-select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  font-family: inherit;
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  box-sizing: border-box;
  transition: var(--transition-colors);
}
.form-textarea { resize: vertical; min-height: 64px; line-height: 1.5; }
.form-textarea:focus,
.form-select:focus {
  outline: none;
  border-color: var(--color-primary, #1E5AA8);
  box-shadow: 0 0 0 2px rgba(30, 90, 168, 0.12);
}
.form-textarea:disabled,
.form-select:disabled {
  background-color: var(--color-bg-secondary);
  cursor: not-allowed;
}

.form-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-align: right;
}

.form-error {
  margin-top: 8px;
  padding: 8px 10px;
  font-size: var(--font-size-sm);
  color: var(--color-error, #e53935);
  background-color: rgba(229, 57, 53, 0.08);
  border-radius: var(--radius-sm);
}

.dislike-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.btn-cancel,
.btn-submit {
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  border: 1px solid transparent;
  transition: var(--transition-colors);
}

.btn-cancel {
  background-color: var(--color-bg-primary);
  border-color: var(--color-border);
  color: var(--color-text-primary);
}
.btn-cancel:hover:not(:disabled) {
  background-color: var(--color-bg-hover);
}
.btn-cancel:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-submit {
  background-color: var(--color-primary, #1E5AA8);
  color: #fff;
}
.btn-submit:hover:not(:disabled) {
  background-color: var(--color-primary-dark, #174A8C);
}
.btn-submit:disabled {
  background-color: var(--color-text-muted);
  cursor: not-allowed;
}

.dislike-fade-enter-active,
.dislike-fade-leave-active { transition: opacity 0.2s ease; }
.dislike-fade-enter-from,
.dislike-fade-leave-to { opacity: 0; }
</style>