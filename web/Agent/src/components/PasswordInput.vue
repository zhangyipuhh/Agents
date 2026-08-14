<script setup>
/**
 * PasswordInput - 密码输入框 + 显示/隐藏切换（眼睛图标 SVG）
 *
 * 设计要点：
 * - 默认 type=password；点击右侧眼睛图标在 type=password ↔ type=text 之间切换；
 * - 当 usePasswordMask=true（用于 UserSettingsDialog 旧密码/MFA 当前密码），
 *   始终保持 type=text，通过 toggle .password-mask class 控制 -webkit-text-security: disc
 *   实现「脱敏 ↔ 明文」切换——避免改 type 触发浏览器密码管理器重置。
 * - 透传 autocomplete 属性，保证密码管理器（Chrome/Edge/1Password 等）正确识别字段；
 * - 通过 emit('caps-lock', on) 通知父级显示大写锁定提示；
 * - 使用 inline SVG（heroicons-style 24x24 stroke）避免引入图标库依赖。
 *
 * Props:
 *   modelValue       {String}  v-model 绑定值
 *   inputId          {String}  透传到 <input id>，保留原页面 DOM 选择器
 *   inputClass       {String}  透传 class（如 form-input / password-mask）
 *   placeholder      {String}
 *   autocomplete     {String}  current-password / new-password 等
 *   disabled         {Boolean}
 *   usePasswordMask  {Boolean} 默认 false；true 时切显示 = toggle class，不改 type
 *
 * Emits:
 *   update:modelValue
 *   caps-lock        {Boolean} 大写锁定状态
 */
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  inputId: { type: String, default: '' },
  inputClass: { type: String, default: 'form-input' },
  placeholder: { type: String, default: '请输入密码' },
  autocomplete: { type: String, default: 'current-password' },
  disabled: { type: Boolean, default: false },
  usePasswordMask: { type: Boolean, default: false },
  inputTestId: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue', 'caps-lock'])

/** @type {import('vue').Ref<boolean>} 密码是否以明文显示 */
const visible = ref(false)

/**
 * 实际渲染的 input type：
 * - usePasswordMask=true 时永远为 'text'（脱敏靠 CSS class 控制）
 * - 否则根据 visible 切 'password' / 'text'
 * @type {import('vue').ComputedRef<'password'|'text'>}
 */
const inputType = computed(() => {
  if (props.usePasswordMask) return 'text'
  return visible.value ? 'text' : 'password'
})

/**
 * 实际渲染的 input class：
 * - usePasswordMask=true 时，class 包含 password-mask = 可见时移出（明文），不可见时加回（圆点）
 * - 透传 inputClass（如 form-input）
 * @type {import('vue').ComputedRef<string>}
 */
const computedClass = computed(() => {
  const base = props.inputClass || 'form-input'
  if (!props.usePasswordMask) return base
  return visible.value ? base.replace(/\s*password-mask\s*/g, '').trim() : `${base} password-mask`
})

/**
 * 切换密码可见性
 * @returns {void}
 */
function toggleVisible() {
  if (props.disabled) return
  visible.value = !visible.value
}

/**
 * v-model 桥接：input 变化时 emit update:modelValue
 * @param {Event} event
 */
function onInput(event) {
  emit('update:modelValue', event.target.value)
}

/**
 * 检测大写锁定键状态
 * @param {KeyboardEvent} event - 键盘事件对象
 */
function checkCapsLock(event) {
  emit('caps-lock', event.getModifierState('CapsLock'))
}

// 显式暴露内部状态给父级（用于测试 / 编程式控制可见性）
defineExpose({
  visible,
  inputType,
  computedClass,
  toggleVisible
})
</script>

<template>
  <div class="password-input-wrapper">
    <input
      :id="inputId"
      :value="modelValue"
      :type="inputType"
      :class="computedClass"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      :disabled="disabled"
      :data-testid="inputTestId || undefined"
      @input="onInput"
      @keydown="checkCapsLock"
      @keyup="checkCapsLock"
    />
    <button
      type="button"
      class="password-toggle"
      :disabled="disabled"
      :aria-label="visible ? '隐藏密码' : '显示密码'"
      :aria-pressed="visible"
      :title="visible ? '隐藏密码' : '显示密码'"
      data-testid="password-toggle"
      @click="toggleVisible"
    >
      <!-- 闭眼图标（密码隐藏态，默认显示） -->
      <svg
        v-if="!visible"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="password-toggle-icon"
        aria-hidden="true"
      >
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
      <!-- 睁眼 + 斜线图标（密码可见态） -->
      <svg
        v-else
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="password-toggle-icon"
        aria-hidden="true"
      >
        <path d="M17.94 17.94A10.5 10.5 0 0 1 12 19c-6.5 0-10-7-10-7a18.5 18.5 0 0 1 4.06-5.06" />
        <path d="M9.9 4.24A10.4 10.4 0 0 1 12 4c6.5 0 10 7 10 7a18.6 18.6 0 0 1-2.16 3.19" />
        <path d="M14.12 14.12A3 3 0 1 1 9.88 9.88" />
        <line x1="2" y1="2" x2="22" y2="22" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
/* 2026-08-14:wrapper 用 position: relative 容纳 absolute 定位的眼睛按钮，
   按钮放在 input 框内部右侧（不挤压 input 视觉宽度）—— input 完整保留
   .form-input 边框/背景/圆角/高度/focus 态，与用户名等输入框视觉一致。 */
.password-input-wrapper {
  position: relative;
  width: 100%;
}

/* 2026-08-14 关键修复：scoped CSS 不会从父组件（LoginView/RegisterView/UserSettingsDialog）
   传到 PasswordInput 渲染的 input 元素——input 元素没有父组件的 data-v-hash 属性，
   父组件的 .form-input[data-v-parent] 选不中。这里把 .form-input 同款样式复制一份给
   PasswordInput 自己的 input，让边框/背景/高度/圆角/focus 态都跟用户名等输入框一致。
   padding-right 增加到 44px 给眼睛按钮预留视觉空间，避免文字被遮挡。 */
.password-input-wrapper :deep(.form-input) {
  width: 100%;
  height: 44px;
  padding: 0 44px 0 var(--space-base);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: var(--transition-colors), var(--transition-shadow);
  box-sizing: border-box;
}

.password-input-wrapper :deep(.form-input:hover) {
  border-color: var(--color-text-muted);
}

.password-input-wrapper :deep(.form-input:focus) {
  border-color: #1E5AA8;
  box-shadow: 0 0 0 3px rgba(30, 90, 168, 0.15);
  background-color: var(--color-bg-primary);
  outline: none;
}

.password-input-wrapper :deep(.form-input::placeholder) {
  color: var(--color-text-muted);
}

.password-input-wrapper :deep(.form-input:disabled) {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.password-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-sm, 4px);
  color: var(--color-text-secondary, #6b7280);
  cursor: pointer;
  transition: var(--transition-colors, color 0.15s ease, background-color 0.15s ease);
  padding: 0;
}

.password-toggle:hover:not(:disabled) {
  color: #1E5AA8;
  background-color: rgba(30, 90, 168, 0.08);
}

.password-toggle:focus-visible {
  outline: 2px solid #1E5AA8;
  outline-offset: 1px;
}

.password-toggle:disabled {
  opacity: var(--opacity-disabled, 0.5);
  cursor: not-allowed;
}

.password-toggle-icon {
  width: 18px;
  height: 18px;
  display: block;
}
</style>
