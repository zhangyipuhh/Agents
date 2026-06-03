<script setup>
/**
 * UserSettingsDialog - 用户设置对话框组件
 * 根据 role prop 显示不同内容：
 * - 普通用户（role='user'）：修改密码和修改用户名表单
 * - 管理员（role='admin'）：占位设置界面
 */

import { ref, watch, computed } from 'vue'
import { updatePassword, updateUsername } from '../utils/api.js'

/**
 * 组件属性定义
 * @prop {boolean} visible - 对话框是否可见，支持 v-model:visible
 * @prop {string} role - 用户角色，'user' 或 'admin'
 * @prop {number} userId - 用户ID
 * @prop {string} username - 当前用户名
 */
const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  role: {
    type: String,
    default: 'user',
    validator: (value) => ['user', 'admin'].includes(value)
  },
  userId: {
    type: Number,
    default: null
  },
  username: {
    type: String,
    default: ''
  }
})

/**
 * 组件事件定义
 * @event update:visible - 更新对话框可见状态，用于 v-model:visible
 * @event username-updated - 用户名修改成功时触发，参数: { username: string }
 */
const emit = defineEmits(['update:visible', 'username-updated'])

/* ---- 修改密码相关状态 ---- */

/** @type {import('vue').Ref<string>} 旧密码 */
const oldPassword = ref('')

/** @type {import('vue').Ref<string>} 新密码 */
const newPassword = ref('')

/** @type {import('vue').Ref<string>} 确认新密码 */
const confirmNewPassword = ref('')

/** @type {import('vue').Ref<string>} 修改密码错误信息 */
const passwordError = ref('')

/** @type {import('vue').Ref<string>} 修改密码成功信息 */
const passwordSuccess = ref('')

/* ---- 修改用户名相关状态 ---- */

/** @type {import('vue').Ref<string>} 新用户名 */
const newUsername = ref('')

/** @type {import('vue').Ref<string>} 修改用户名错误信息 */
const usernameError = ref('')

/** @type {import('vue').Ref<string>} 修改用户名成功信息 */
const usernameSuccess = ref('')

/** @type {import('vue').Ref<boolean>} 是否正在保存设置 */
const isSaving = ref(false)

/**
 * 是否为普通用户角色
 * @type {import('vue').ComputedRef<boolean>}
 */
const isUser = computed(() => props.role === 'user')

/**
 * 关闭对话框
 * 重置所有表单状态并触发 update:visible 事件
 */
function closeDialog() {
  resetForms()
  emit('update:visible', false)
}

/**
 * 重置所有表单状态
 * 清空输入框和提示信息
 */
function resetForms() {
  oldPassword.value = ''
  newPassword.value = ''
  confirmNewPassword.value = ''
  newUsername.value = ''
  passwordError.value = ''
  passwordSuccess.value = ''
  usernameError.value = ''
  usernameSuccess.value = ''
}

/**
 * 判断是否有密码修改意图
 * 任一密码相关字段非空即视为有修改意图
 * @returns {boolean}
 */
function hasPasswordIntent() {
  return !!(oldPassword.value || newPassword.value || confirmNewPassword.value)
}

/**
 * 判断是否有用户名修改意图
 * @returns {boolean}
 */
function hasUsernameIntent() {
  return !!(newUsername.value.trim())
}

/**
 * 验证密码表单
 * 如有错误则设置 passwordError 并返回 false
 * @returns {boolean}
 */
function validatePasswordForm() {
  if (!oldPassword.value) {
    passwordError.value = '请输入旧密码'
    return false
  }
  if (!newPassword.value) {
    passwordError.value = '请输入新密码'
    return false
  }
  if (newPassword.value.length < 6) {
    passwordError.value = '新密码至少6个字符'
    return false
  }
  if (newPassword.value !== confirmNewPassword.value) {
    passwordError.value = '两次输入的新密码不一致'
    return false
  }
  if (oldPassword.value === newPassword.value) {
    passwordError.value = '新密码不能与旧密码相同'
    return false
  }
  return true
}

/**
 * 验证用户名表单
 * 如有错误则设置 usernameError 并返回 false
 * @returns {boolean}
 */
function validateUsernameForm() {
  if (!newUsername.value.trim()) {
    usernameError.value = '请输入新用户名'
    return false
  }
  if (newUsername.value.trim().length < 3) {
    usernameError.value = '用户名至少3个字符'
    return false
  }
  if (newUsername.value.trim() === props.username) {
    usernameError.value = '新用户名不能与当前用户名相同'
    return false
  }
  return true
}

/**
 * 统一保存处理函数
 * 根据用户填写的表单内容，仅提交已修改的部分
 * @returns {Promise<void>}
 */
async function handleSave() {
  // 清空所有提示信息
  passwordError.value = ''
  passwordSuccess.value = ''
  usernameError.value = ''
  usernameSuccess.value = ''

  const passwordIntent = hasPasswordIntent()
  const usernameIntent = hasUsernameIntent()

  // 如果两者都没有填写，提示用户
  if (!passwordIntent && !usernameIntent) {
    passwordError.value = '请至少填写一项修改内容'
    return
  }

  // 分别验证有修改意图的表单
  if (passwordIntent && !validatePasswordForm()) {
    return
  }
  if (usernameIntent && !validateUsernameForm()) {
    return
  }

  if (!props.userId) {
    passwordError.value = '用户ID无效，请重新登录'
    return
  }

  isSaving.value = true

  try {
    const promises = []

    if (passwordIntent) {
      promises.push(
        (async () => {
          try {
            await updatePassword(props.userId, oldPassword.value, newPassword.value)
            passwordSuccess.value = '密码修改成功'
            oldPassword.value = ''
            newPassword.value = ''
            confirmNewPassword.value = ''
          } catch (err) {
            passwordError.value = err.message || '修改密码失败'
          }
        })()
      )
    }

    if (usernameIntent) {
      promises.push(
        (async () => {
          try {
            const data = await updateUsername(props.userId, newUsername.value.trim())
            usernameSuccess.value = '用户名修改成功'
            // 通知父组件用户名已更新
            emit('username-updated', { username: data.new_username || newUsername.value.trim() })
            // 更新 localStorage 中的用户名
            localStorage.setItem('username', data.new_username || newUsername.value.trim())
            newUsername.value = ''
          } catch (err) {
            usernameError.value = err.message || '修改用户名失败'
          }
        })()
      )
    }

    await Promise.all(promises)
  } finally {
    isSaving.value = false
  }
}

/**
 * 点击遮罩层关闭对话框
 * @param {Event} event - 点击事件对象
 */
function handleOverlayClick(event) {
  if (event.target === event.currentTarget) {
    closeDialog()
  }
}

/**
 * 监听对话框可见状态变化，打开时重置表单
 */
watch(() => props.visible, (newVal) => {
  if (newVal) {
    resetForms()
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="dialog-overlay" @click="handleOverlayClick">
        <div class="dialog-card" @click.stop>
          <!-- 对话框头部 -->
          <div class="dialog-header">
            <h2 class="dialog-title">用户设置</h2>
            <button class="dialog-close" @click="closeDialog" aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5l10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          </div>

          <!-- 对话框内容 -->
          <div class="dialog-body">
            <!-- 普通用户设置 -->
            <template v-if="isUser">
              <form @submit.prevent="handleSave">
                <!-- 修改密码区域 -->
                <div class="settings-section">
                  <h3 class="section-title">修改密码</h3>
                  <div class="form-group">
                    <label class="form-label" for="settings-old-password">旧密码</label>
                    <input
                      id="settings-old-password"
                      v-model="oldPassword"
                      type="password"
                      class="form-input"
                      placeholder="请输入旧密码"
                      autocomplete="current-password"
                      :disabled="isSaving"
                    />
                  </div>

                  <div class="form-group">
                    <label class="form-label" for="settings-new-password">新密码</label>
                    <input
                      id="settings-new-password"
                      v-model="newPassword"
                      type="password"
                      class="form-input"
                      placeholder="请输入新密码（至少6个字符）"
                      autocomplete="new-password"
                      :disabled="isSaving"
                    />
                  </div>

                  <div class="form-group">
                    <label class="form-label" for="settings-confirm-new-password">确认新密码</label>
                    <input
                      id="settings-confirm-new-password"
                      v-model="confirmNewPassword"
                      type="password"
                      class="form-input"
                      placeholder="请再次输入新密码"
                      autocomplete="new-password"
                      :disabled="isSaving"
                    />
                  </div>

                  <!-- 修改密码提示信息 -->
                  <div v-if="passwordError" class="error-message">{{ passwordError }}</div>
                  <div v-if="passwordSuccess" class="success-message">{{ passwordSuccess }}</div>
                </div>

                <!-- 分隔线 -->
                <div class="section-divider"></div>

                <!-- 修改用户名区域 -->
                <div class="settings-section">
                  <h3 class="section-title">修改用户名</h3>
                  <p class="section-desc">当前用户名：<strong>{{ username }}</strong></p>
                  <div class="form-group">
                    <label class="form-label" for="settings-new-username">新用户名</label>
                    <input
                      id="settings-new-username"
                      v-model="newUsername"
                      type="text"
                      class="form-input"
                      placeholder="请输入新用户名（至少3个字符）"
                      autocomplete="off"
                      :disabled="isSaving"
                    />
                  </div>

                  <!-- 修改用户名提示信息 -->
                  <div v-if="usernameError" class="error-message">{{ usernameError }}</div>
                  <div v-if="usernameSuccess" class="success-message">{{ usernameSuccess }}</div>
                </div>

                <!-- 统一保存按钮 -->
                <button
                  type="submit"
                  class="action-button"
                  :disabled="isSaving"
                >
                  <span v-if="isSaving" class="button-loading">
                    <span class="loading-spinner"></span>
                    保存中...
                  </span>
                  <span v-else>保存设置</span>
                </button>
              </form>
            </template>

            <!-- 管理员设置占位 -->
            <template v-else>
              <div class="admin-placeholder">
                <svg class="placeholder-icon" width="64" height="64" viewBox="0 0 64 64" fill="none">
                  <circle cx="32" cy="32" r="30" stroke="var(--color-border)" stroke-width="2" fill="var(--color-bg-secondary)" />
                  <path d="M32 20a8 8 0 100 16 8 8 0 000-16zM20 44c0-6.627 5.373-12 12-12s12 5.373 12 12" stroke="var(--color-text-muted)" stroke-width="2" stroke-linecap="round" fill="none" />
                </svg>
                <h3 class="placeholder-title">管理员设置</h3>
                <p class="placeholder-desc">管理员专属设置功能正在开发中，敬请期待...</p>
              </div>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 遮罩层 */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
}

/* 对话框卡片 */
.dialog-card {
  width: 100%;
  max-width: 480px;
  max-height: 85vh;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 对话框头部 */
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.dialog-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.dialog-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  transition: var(--transition-colors), var(--transition-transform);

  &:hover {
    background-color: var(--color-bg-hover);
    color: var(--color-text-primary);
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

/* 对话框内容区域 */
.dialog-body {
  padding: var(--space-xl);
  overflow-y: auto;
  flex: 1;
}

/* 设置分区 */
.settings-section {
  margin-bottom: var(--space-lg);
}

.settings-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-base);
}

.section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-base);
}

.section-desc strong {
  color: var(--color-accent);
  font-weight: var(--font-weight-medium);
}

/* 分隔线 */
.section-divider {
  height: 1px;
  background-color: var(--color-border);
  margin: var(--space-lg) 0;
}

/* 表单组 */
.form-group {
  margin-bottom: var(--space-base);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.form-input {
  width: 100%;
  height: 40px;
  padding: 0 var(--space-base);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: var(--transition-colors), var(--transition-shadow);

  &:hover {
    border-color: var(--color-text-muted);
  }

  &:focus {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px var(--color-accent-light);
    background-color: var(--color-bg-primary);
  }

  &::placeholder {
    color: var(--color-text-muted);
  }

  &:disabled {
    opacity: var(--opacity-disabled);
    cursor: not-allowed;
  }
}

/* 错误提示 */
.error-message {
  padding: var(--space-sm) var(--space-base);
  margin-bottom: var(--space-base);
  font-size: var(--font-size-sm);
  color: var(--color-error);
  background-color: #FEF2F2;
  border-radius: var(--radius-sm);
  border: 1px solid #FECACA;
  line-height: var(--line-height-normal);
}

/* 成功提示 */
.success-message {
  padding: var(--space-sm) var(--space-base);
  margin-bottom: var(--space-base);
  font-size: var(--font-size-sm);
  color: var(--color-success);
  background-color: #ECFDF5;
  border-radius: var(--radius-sm);
  border: 1px solid #A7F3D0;
  line-height: var(--line-height-normal);
}

/* 操作按钮 */
.action-button {
  width: 100%;
  height: 40px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-inverse);
  background-color: var(--color-accent);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);

  &:hover:not(:disabled) {
    background-color: var(--color-accent-hover);
    transform: scale(var(--scale-hover-button));
  }

  &:active:not(:disabled) {
    transform: scale(var(--scale-active));
  }

  &:disabled {
    opacity: var(--opacity-disabled);
    cursor: not-allowed;
  }
}

/* 按钮加载状态 */
.button-loading {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
}

.loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 管理员占位界面 */
.admin-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl) var(--space-lg);
  text-align: center;
}

.placeholder-icon {
  margin-bottom: var(--space-lg);
  opacity: 0.6;
}

.placeholder-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-sm);
}

.placeholder-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed);
}

/* 对话框过渡动画 */
.dialog-fade-enter-active {
  transition: opacity 0.25s ease;
}

.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-active .dialog-card {
  animation: dialog-scale-in 0.25s ease;
}

.dialog-fade-leave-active .dialog-card {
  animation: dialog-scale-out 0.2s ease;
}

@keyframes dialog-scale-in {
  from {
    transform: scale(0.95);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes dialog-scale-out {
  from {
    transform: scale(1);
    opacity: 1;
  }
  to {
    transform: scale(0.95);
    opacity: 0;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
