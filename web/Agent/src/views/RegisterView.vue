<script setup>
/**
 * RegisterView - 注册页面组件
 * 提供用户名、密码、确认密码、真实姓名、手机号、邮箱、部门、职位输入和注册功能
 * 注册成功后自动跳转回登录页
 */

import { ref, computed, onMounted } from 'vue'
import { register, getCaptcha } from '../utils/api.js'
import { appConfig } from '../config/portal.js'

/** @type {import('vue').Ref<string>} 用户名输入值 */
const username = ref('')

/** @type {import('vue').Ref<string>} 密码输入值 */
const password = ref('')

/** @type {import('vue').Ref<string>} 确认密码输入值 */
const confirmPassword = ref('')

/** @type {import('vue').Ref<string>} 真实姓名输入值 */
const realName = ref('')

/** @type {import('vue').Ref<string>} 手机号输入值 */
const phone = ref('')

/** @type {import('vue').Ref<string>} 邮箱输入值 */
const email = ref('')

/** @type {import('vue').Ref<string>} 部门输入值 */
const department = ref('')

/** @type {import('vue').Ref<string>} 职位输入值 */
const position = ref('')

/** @type {import('vue').Ref<string>} 验证码输入值 */
const captchaCode = ref('')

/** @type {import('vue').Ref<string>} 验证码ID，由服务端返回 */
const captchaId = ref('')

/** @type {import('vue').Ref<string>} 验证码图片的Base64数据 */
const captchaImage = ref('')

/** @type {import('vue').Ref<boolean>} 是否正在提交注册请求 */
const loading = ref(false)

/** @type {import('vue').Ref<string>} 错误提示信息 */
const errorMessage = ref('')

/** @type {import('vue').Ref<string>} 成功提示信息 */
const successMessage = ref('')

/**
 * 组件事件定义
 * @event switch-to-login - 切换到登录页面时触发
 */
const emit = defineEmits(['switch-to-login'])

/**
 * 加载验证码图片
 * 调用 getCaptcha API 获取验证码ID和图片数据
 * @returns {Promise<void>}
 */
async function loadCaptcha() {
  try {
    const data = await getCaptcha()
    captchaId.value = data.captcha_key
    captchaImage.value = data.captcha_image
  } catch (err) {
    errorMessage.value = '获取验证码失败，请刷新重试'
  }
}

/**
 * 点击验证码图片刷新验证码
 */
function refreshCaptcha() {
  captchaCode.value = ''
  loadCaptcha()
}

/**
 * 校验密码复杂度
 * 必须同时包含大写字母、小写字母、数字、特殊字符，且长度至少6位
 * @param {string} pwd - 密码
 * @returns {boolean} 校验通过返回 true
 */
function validatePasswordComplexity(pwd) {
  if (pwd.length < 6) return false
  const hasUpper = /[A-Z]/.test(pwd)
  const hasLower = /[a-z]/.test(pwd)
  const hasDigit = /\d/.test(pwd)
  const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(pwd)
  return hasUpper && hasLower && hasDigit && hasSpecial
}

/**
 * 密码复杂度实时验证状态
 * 根据当前密码输入值计算各项要求的满足情况
 * @returns {{ minLength: boolean, hasUpper: boolean, hasLower: boolean, hasDigit: boolean, hasSpecial: boolean, isValid: boolean }}
 */
const passwordValidation = computed(() => {
  const pwd = password.value || ''
  const minLength = pwd.length >= 6
  const hasUpper = /[A-Z]/.test(pwd)
  const hasLower = /[a-z]/.test(pwd)
  const hasDigit = /\d/.test(pwd)
  const hasSpecial = /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(pwd)
  return {
    minLength,
    hasUpper,
    hasLower,
    hasDigit,
    hasSpecial,
    isValid: minLength && hasUpper && hasLower && hasDigit && hasSpecial
  }
})

/**
 * 处理注册表单提交
 * 验证输入后调用 register API，成功后显示提示并自动跳转到登录页
 * @returns {Promise<void>}
 */
async function handleRegister() {
  errorMessage.value = ''
  successMessage.value = ''

  // 表单验证
  if (!username.value.trim()) {
    errorMessage.value = '请输入用户名'
    return
  }
  if (username.value.trim().length < 3) {
    errorMessage.value = '用户名至少3个字符'
    return
  }
  if (!password.value) {
    errorMessage.value = '请输入密码'
    return
  }
  if (!validatePasswordComplexity(password.value)) {
    errorMessage.value = '密码必须至少6位，且包含大写字母、小写字母、数字和特殊字符'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }
  if (!realName.value.trim()) {
    errorMessage.value = '请输入真实姓名'
    return
  }
  if (realName.value.trim().length < 2 || realName.value.trim().length > 20) {
    errorMessage.value = '真实姓名长度应为2-20个字符'
    return
  }
  if (!phone.value.trim()) {
    errorMessage.value = '请输入手机号'
    return
  }
  if (!/^1[3-9]\d{9}$/.test(phone.value.trim())) {
    errorMessage.value = '请输入有效的中国大陆手机号'
    return
  }
  if (!email.value.trim()) {
    errorMessage.value = '请输入邮箱'
    return
  }
  if (!/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email.value.trim())) {
    errorMessage.value = '请输入有效的邮箱地址'
    return
  }
  if (!captchaCode.value.trim()) {
    errorMessage.value = '请输入验证码'
    return
  }

  loading.value = true

  try {
    await register(
      username.value.trim(),
      password.value,
      confirmPassword.value,
      realName.value.trim(),
      phone.value.trim(),
      email.value.trim(),
      department.value.trim(),
      position.value.trim(),
      captchaId.value,
      captchaCode.value.trim()
    )
    successMessage.value = '注册成功！即将跳转到登录页...'

    // 注册成功后延迟跳转到登录页
    setTimeout(() => {
      emit('switch-to-login')
    }, 1500)
  } catch (err) {
    errorMessage.value = err.message || '注册失败，请重试'
    // 注册失败后刷新验证码
    captchaCode.value = ''
    await loadCaptcha()
  } finally {
    loading.value = false
  }
}

// 组件挂载时自动加载验证码
onMounted(() => {
  loadCaptcha()
})
</script>

<template>
  <div class="register-container">
    <div class="register-card">
      <div class="register-header">
        <div class="system-title">{{ appConfig.brandTitle }}</div>
        <div class="title-divider"></div>
        <h1 class="register-title">创建账号</h1>
        <p class="register-subtitle">请填写以下信息完成注册</p>
      </div>

      <form class="register-form" @submit.prevent="handleRegister">
        <!-- 用户名输入框 -->
        <div class="form-group">
          <label class="form-label required" for="register-username">用户名</label>
          <input
            id="register-username"
            v-model="username"
            type="text"
            class="form-input"
            placeholder="请输入用户名（至少3个字符）"
            autocomplete="username"
            :disabled="loading"
          />
        </div>

        <!-- 真实姓名输入框 -->
        <div class="form-group">
          <label class="form-label required" for="register-real-name">真实姓名</label>
          <input
            id="register-real-name"
            v-model="realName"
            type="text"
            class="form-input"
            placeholder="请输入真实姓名（2-20个字符）"
            autocomplete="name"
            :disabled="loading"
          />
        </div>

        <!-- 密码输入框 -->
        <div class="form-group">
          <label class="form-label required" for="register-password">密码</label>
          <input
            id="register-password"
            v-model="password"
            type="password"
            class="form-input"
            placeholder="至少6位，含大小写字母、数字、特殊字符"
            autocomplete="new-password"
            :disabled="loading"
          />
          <div class="password-hints">
            <div class="password-hint-list">
              <span
                class="password-hint-item"
                :class="passwordValidation.minLength ? 'valid' : 'invalid'"
              >
                <span class="hint-icon">{{ passwordValidation.minLength ? '✓' : '○' }}</span>
                至少6位
              </span>
              <span
                class="password-hint-item"
                :class="passwordValidation.hasUpper ? 'valid' : 'invalid'"
              >
                <span class="hint-icon">{{ passwordValidation.hasUpper ? '✓' : '○' }}</span>
                包含大写字母
              </span>
              <span
                class="password-hint-item"
                :class="passwordValidation.hasLower ? 'valid' : 'invalid'"
              >
                <span class="hint-icon">{{ passwordValidation.hasLower ? '✓' : '○' }}</span>
                包含小写字母
              </span>
              <span
                class="password-hint-item"
                :class="passwordValidation.hasDigit ? 'valid' : 'invalid'"
              >
                <span class="hint-icon">{{ passwordValidation.hasDigit ? '✓' : '○' }}</span>
                包含数字
              </span>
              <span
                class="password-hint-item"
                :class="passwordValidation.hasSpecial ? 'valid' : 'invalid'"
              >
                <span class="hint-icon">{{ passwordValidation.hasSpecial ? '✓' : '○' }}</span>
                包含特殊字符
              </span>
            </div>
          </div>
        </div>

        <!-- 确认密码输入框 -->
        <div class="form-group">
          <label class="form-label required" for="register-confirm-password">确认密码</label>
          <input
            id="register-confirm-password"
            v-model="confirmPassword"
            type="password"
            class="form-input"
            placeholder="请再次输入密码"
            autocomplete="new-password"
            :disabled="loading"
          />
        </div>

        <!-- 手机号输入框 -->
        <div class="form-group">
          <label class="form-label required" for="register-phone">手机号</label>
          <input
            id="register-phone"
            v-model="phone"
            type="tel"
            class="form-input"
            placeholder="请输入手机号"
            autocomplete="tel"
            :disabled="loading"
          />
        </div>

        <!-- 邮箱输入框 -->
        <div class="form-group">
          <label class="form-label required" for="register-email">邮箱</label>
          <input
            id="register-email"
            v-model="email"
            type="email"
            class="form-input"
            placeholder="请输入邮箱地址"
            autocomplete="email"
            :disabled="loading"
          />
        </div>

        <!-- 部门输入框 -->
        <div class="form-group">
          <label class="form-label" for="register-department">部门</label>
          <input
            id="register-department"
            v-model="department"
            type="text"
            class="form-input"
            placeholder="请输入部门（选填）"
            autocomplete="organization"
            :disabled="loading"
          />
        </div>

        <!-- 职位输入框 -->
        <div class="form-group">
          <label class="form-label" for="register-position">职位</label>
          <input
            id="register-position"
            v-model="position"
            type="text"
            class="form-input"
            placeholder="请输入职位（选填）"
            autocomplete="organization-title"
            :disabled="loading"
          />
        </div>

        <!-- 验证码输入框和图片 -->
        <div class="form-group full-width">
          <label class="form-label required" for="register-captcha">验证码</label>
          <div class="captcha-row">
            <input
              id="register-captcha"
              v-model="captchaCode"
              type="text"
              class="form-input captcha-input"
              placeholder="请输入验证码"
              autocomplete="off"
              :disabled="loading"
            />
            <div
              class="captcha-image-wrapper"
              :title="'点击刷新验证码'"
              @click="refreshCaptcha"
            >
              <img
                v-if="captchaImage"
                :src="captchaImage"
                alt="验证码"
                class="captcha-image"
              />
              <div v-else class="captcha-placeholder">
                加载中...
              </div>
            </div>
          </div>
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMessage" class="error-message full-width">
          {{ errorMessage }}
        </div>

        <!-- 成功提示 -->
        <div v-if="successMessage" class="success-message full-width">
          {{ successMessage }}
        </div>

        <!-- 注册按钮 -->
        <button
          type="submit"
          class="register-button full-width"
          :disabled="loading"
        >
          <span v-if="loading" class="button-loading">
            <span class="loading-spinner"></span>
            注册中...
          </span>
          <span v-else>注 册</span>
        </button>
      </form>

      <!-- 底部登录链接 -->
      <div class="register-footer">
        <span class="footer-text">已有账号？</span>
        <a class="footer-link" @click="$emit('switch-to-login')">去登录</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 注册页面容器 - 全屏居中布局 */
.register-container {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  min-height: 100vh;
  width: 100%;
  background: linear-gradient(135deg, #EBF4FF 0%, #F0F7FF 40%, #FFFFFF 100%);
  background-attachment: fixed;
  position: relative;
  padding: var(--space-xl) var(--space-lg);
  overflow-y: auto;
}

/* 极淡的几何纹理背景叠加 */
.register-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, #1E5AA8 0.5px, transparent 0.5px);
  background-size: 24px 24px;
  opacity: 0.06;
  pointer-events: none;
}

/* 注册卡片 */
.register-card {
  width: 100%;
  max-width: 640px;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  border-top: 4px solid #1E5AA8;
  padding: var(--space-xl) var(--space-lg);
  position: relative;
  z-index: 1;
}

/* 卡片头部 */
.register-header {
  text-align: center;
  margin-bottom: var(--space-lg);
}

.system-title {
  font-size: 22px;
  font-weight: var(--font-weight-bold);
  color: #1E5AA8;
  margin-bottom: var(--space-sm);
  line-height: var(--line-height-tight);
}

.title-divider {
  width: 48px;
  height: 3px;
  background: linear-gradient(90deg, #1E5AA8, #4A90D9);
  border-radius: 2px;
  margin: 0 auto var(--space-base);
}

.register-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-sm);
}

.register-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

/* 宽屏左右分栏布局 */
@media (min-width: 960px) {
  .register-container {
    justify-content: center;
    gap: 60px;
    padding: var(--space-lg) var(--space-xl);
  }

}

/* 注册表单 - 双列网格布局 */
.register-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-sm) var(--space-lg);
}

/* 跨列元素 */
.full-width {
  grid-column: 1 / -1;
}

/* 表单组 */
.form-group {
  margin-bottom: 0;
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.form-label.required::after {
  content: ' *';
  color: var(--color-error);
}

.form-input {
  width: 100%;
  height: 44px;
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
    border-color: #1E5AA8;
    box-shadow: 0 0 0 3px rgba(30, 90, 168, 0.15);
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

/* 验证码行 */
.captcha-row {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
}

.captcha-input {
  flex: 1;
}

.captcha-image-wrapper {
  flex-shrink: 0;
  width: 120px;
  height: 44px;
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--color-border);
  transition: var(--transition-shadow);

  &:hover {
    box-shadow: 0 0 0 2px rgba(30, 90, 168, 0.15);
    border-color: #1E5AA8;
  }

  &:active {
    transform: scale(var(--scale-active));
  }
}

.captcha-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.captcha-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background-color: var(--color-bg-tertiary);
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

/* 注册按钮 */
.register-button {
  width: 100%;
  height: 44px;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-inverse);
  background-color: #1E5AA8;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);

  &:hover:not(:disabled) {
    background-color: #155A9E;
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
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 底部链接 */
.register-footer {
  text-align: center;
  margin-top: var(--space-lg);
  font-size: var(--font-size-sm);
}

.footer-text {
  color: var(--color-text-secondary);
}

.footer-link {
  color: #1E5AA8;
  cursor: pointer;
  font-weight: var(--font-weight-medium);
  transition: var(--transition-colors);

  &:hover {
    color: #155A9E;
    text-decoration: underline;
  }
}

/* 密码复杂度提示 */
.password-hints {
  margin-top: var(--space-xs);
}

.password-hint-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-sm);
}

.password-hint-item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  transition: var(--transition-colors);
}

.password-hint-item.valid {
  color: var(--color-success);
}

.password-hint-item.invalid {
  color: var(--color-text-muted);
}

.hint-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  font-size: 10px;
  font-weight: var(--font-weight-bold);
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 响应式：窄屏下恢复单列布局 */
@media (max-width: 640px) {
  .register-card {
    max-width: 420px;
    padding: var(--space-xl) var(--space-lg);
  }

  .register-form {
    grid-template-columns: 1fr;
    gap: var(--space-base) 0;
  }

  .full-width {
    grid-column: auto;
  }
}
</style>
