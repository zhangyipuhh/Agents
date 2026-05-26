<script setup>
/**
 * LoginView - 登录页面组件
 * 提供用户名、密码、验证码输入和登录功能
 * 登录成功后将 token、role、username 存储到 localStorage，并通过 emit 通知父组件
 */

import { ref, onMounted } from 'vue'
import { login, getCaptcha } from '../utils/api.js'

/** @type {import('vue').Ref<string>} 用户名输入值 */
const username = ref('')

/** @type {import('vue').Ref<string>} 密码输入值 */
const password = ref('')

/** @type {import('vue').Ref<string>} 验证码输入值 */
const captchaCode = ref('')

/** @type {import('vue').Ref<string>} 验证码ID，由服务端返回 */
const captchaId = ref('')

/** @type {import('vue').Ref<string>} 验证码图片的Base64数据 */
const captchaImage = ref('')

/** @type {import('vue').Ref<boolean>} 是否正在提交登录请求 */
const loading = ref(false)

/** @type {import('vue').Ref<string>} 错误提示信息 */
const errorMessage = ref('')

/**
 * 组件事件定义
 * @event login-success - 登录成功时触发，参数: { token: string, role: string, username: string }
 */
const emit = defineEmits(['login-success'])

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
 * 处理登录表单提交
 * 验证输入后调用 login API，成功后将认证信息存储到 localStorage
 * @returns {Promise<void>}
 */
async function handleLogin() {
  errorMessage.value = ''

  // 表单验证
  if (!username.value.trim()) {
    errorMessage.value = '请输入用户名'
    return
  }
  if (!password.value.trim()) {
    errorMessage.value = '请输入密码'
    return
  }
  if (!captchaCode.value.trim()) {
    errorMessage.value = '请输入验证码'
    return
  }

  loading.value = true

  try {
    const data = await login(
      username.value.trim(),
      password.value,
      captchaId.value,
      captchaCode.value.trim()
    )

    // 登录成功，存储认证信息到 localStorage
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('user_role', data.role)
    localStorage.setItem('username', data.username)

    // 通知父组件登录成功
    emit('login-success', {
      token: data.access_token,
      role: data.role,
      username: data.username
    })
  } catch (err) {
    errorMessage.value = err.message || '登录失败，请重试'
    // 登录失败后刷新验证码
    captchaCode.value = ''
    await loadCaptcha()
  } finally {
    loading.value = false
  }
}

/**
 * 点击验证码图片刷新验证码
 */
function refreshCaptcha() {
  captchaCode.value = ''
  loadCaptcha()
}

// 组件挂载时自动加载验证码
onMounted(() => {
  loadCaptcha()
})
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1 class="login-title">欢迎登录</h1>
        <p class="login-subtitle">请输入您的账号信息</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <!-- 用户名输入框 -->
        <div class="form-group">
          <label class="form-label" for="login-username">用户名</label>
          <input
            id="login-username"
            v-model="username"
            type="text"
            class="form-input"
            placeholder="请输入用户名"
            autocomplete="username"
            :disabled="loading"
          />
        </div>

        <!-- 密码输入框 -->
        <div class="form-group">
          <label class="form-label" for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            class="form-input"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
          />
        </div>

        <!-- 验证码输入框和图片 -->
        <div class="form-group">
          <label class="form-label" for="login-captcha">验证码</label>
          <div class="captcha-row">
            <input
              id="login-captcha"
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
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>

        <!-- 登录按钮 -->
        <button
          type="submit"
          class="login-button"
          :disabled="loading"
        >
          <span v-if="loading" class="button-loading">
            <span class="loading-spinner"></span>
            登录中...
          </span>
          <span v-else>登 录</span>
        </button>
      </form>

      <!-- 底部注册链接 -->
      <div class="login-footer">
        <span class="footer-text">没有账号？</span>
        <a class="footer-link" @click="$emit('switch-to-register')">去注册</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 登录页面容器 - 全屏居中布局 */
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  width: 100%;
  background-color: var(--color-bg-secondary);
  padding: var(--space-lg);
}

/* 登录卡片 */
.login-card {
  width: 100%;
  max-width: 420px;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  padding: var(--space-2xl) var(--space-xl);
}

/* 卡片头部 */
.login-header {
  text-align: center;
  margin-bottom: var(--space-xl);
}

.login-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-sm);
}

.login-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
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
    box-shadow: 0 0 0 2px var(--color-accent-light);
    border-color: var(--color-accent);
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

/* 登录按钮 */
.login-button {
  width: 100%;
  height: 44px;
  font-size: var(--font-size-lg);
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
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 底部链接 */
.login-footer {
  text-align: center;
  margin-top: var(--space-lg);
  font-size: var(--font-size-sm);
}

.footer-text {
  color: var(--color-text-secondary);
}

.footer-link {
  color: var(--color-accent);
  cursor: pointer;
  font-weight: var(--font-weight-medium);
  transition: var(--transition-colors);

  &:hover {
    color: var(--color-accent-hover);
    text-decoration: underline;
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
