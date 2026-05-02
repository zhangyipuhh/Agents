<script setup>
import { ref, computed, nextTick } from 'vue'

// 输入框内容
const inputValue = ref('')

// 输入框引用
const textareaRef = ref(null)

// 是否聚焦
const isFocused = ref(false)

// 计算属性：是否可以发送（输入框不为空）
const canSend = computed(() => inputValue.value.trim().length > 0)

// 自适应文本框高度
const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
  }
}

// 处理输入事件
const handleInput = (event) => {
  inputValue.value = event.target.value
  autoResize()
}

// 处理键盘事件（Enter 发送，Shift+Enter 换行）
const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

// 处理发送
const handleSend = () => {
  if (!canSend.value) return

  // 触发发送事件
  emit('send', inputValue.value.trim())

  // 清空输入框
  inputValue.value = ''

  // 重置高度
  nextTick(() => {
    autoResize()
  })
}

// 处理聚焦
const handleFocus = () => {
  isFocused.value = true
}

// 处理失焦
const handleBlur = () => {
  isFocused.value = false
}

const handleToolAction = (action) => {
  emit('tool-action', action)
}

const emit = defineEmits(['send', 'tool-action'])
</script>

<template>
  <div class="input-box-container">
    <div class="input-wrapper">
      <!-- 主输入区域 -->
      <div class="input-main" :class="{ focused: isFocused }">
        <!-- 文本输入区 -->
        <textarea
          ref="textareaRef"
          v-model="inputValue"
          class="text-input"
          placeholder="请输入你的需求，按「Enter」发送"
          rows="1"
          :style="{ minHeight: '60px' }"
          @input="handleInput"
          @keydown="handleKeydown"
          @focus="handleFocus"
          @blur="handleBlur"
        ></textarea>

        <!-- 底部操作栏 -->
        <div class="bottom-row">
          <!-- 工具栏 -->
          <div class="toolbar">
            <button
              class="tool-btn"
              title="附件"
              @click="handleToolAction('attachment')"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path fill-rule="evenodd" d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z" clip-rule="evenodd"/>
              </svg>
            </button>

            <button
              class="tool-btn"
              title="工具"
              @click="handleToolAction('tools')"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
              </svg>
            </button>

            <button
              class="tool-btn text-btn"
              title="技能"
              @click="handleToolAction('skills')"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/>
              </svg>
              <span>技能</span>
            </button>

            <button
              class="tool-btn"
              title="设置"
              @click="handleToolAction('settings')"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="tool-icon">
                <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
              </svg>
            </button>
          </div>

          <!-- 发送按钮 -->
          <button
            class="send-btn"
            :class="{ disabled: !canSend }"
            :disabled="!canSend"
            @click="handleSend"
            title="发送消息"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" class="send-icon">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 底部声明 -->
    <p class="disclaimer">内容由AI生成，重要信息请务必核查</p>
  </div>
</template>

<style scoped>
.input-box-container {
  padding: 16px 40px 24px;
  background-color: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-light);
  contain: layout style paint;
}

.input-wrapper {
  max-width: 900px;
  margin: 0 auto;
}

.input-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  background-color: var(--color-bg-secondary);
  border: 2px solid transparent;
  border-radius: var(--radius-lg);
  transition: var(--transition-colors), var(--transition-shadow), border-color 0.25s ease;
  position: relative;

  &:hover:not(.focused) {
    border-color: var(--color-border);
    box-shadow: var(--shadow-sm);
  }
}

/* 底部操作栏 */
.bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 10px;
  background-color: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background-color: var(--color-bg-hover);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover {
    color: var(--color-text-primary);

    &::before {
      opacity: 1;
    }
  }

  &:active:not(:disabled) {
    transform: scale(0.95);
  }

  /* Ensure content is above pseudo-element */
  > * {
    position: relative;
    z-index: 1;
  }

  &.text-btn {
    font-size: var(--font-size-sm);
    font-weight: var(--font-weight-medium);
    padding: 6px 12px;
  }
}

.tool-icon {
  width: 18px;
  height: 18px;
}

/* 文本输入框 */
.text-input {
  width: 100%;
  min-height: 60px;
  max-height: 200px;
  padding: 0;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  color: var(--color-text-primary);
  background-color: transparent;
  resize: none;
  overflow-y: auto;

  &::placeholder {
    color: var(--color-text-muted);
  }

  /* 隐藏滚动条 */
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

  &:focus {
    outline: none;
  }
}

/* 发送按钮 */
.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 50%;
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow);
  flex-shrink: 0;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover:not(.disabled) {
    background-color: var(--color-accent-hover);
    transform: scale(1.08);
    box-shadow:
      0 4px 12px rgba(99, 102, 241, 0.3),
      0 2px 4px rgba(99, 102, 241, 0.2);

    &::before {
      opacity: 1;
    }
  }

  &:active:not(.disabled) {
    transform: scale(0.95);
  }

  &.disabled {
    background-color: var(--color-border);
    cursor: not-allowed;
    opacity: var(--opacity-disabled);

    &:hover {
      box-shadow: none;
      transform: none;
    }
  }
}

.send-icon {
  width: 16px;
  height: 16px;
}

/* 底部声明 */
.disclaimer {
  text-align: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin: 12px 0 0;
  line-height: 1.4;
  letter-spacing: 0.01em;
  transition: var(--transition-opacity);

  &:hover {
    color: var(--color-text-secondary);
  }
}
</style>
