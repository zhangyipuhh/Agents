<script setup>
/**
 * RegisterView - 注册页面组件
 * 提供用户名、密码、确认密码输入和注册功能
 * 注册成功后自动跳转回登录页
 */

import { ref } from 'vue'
import { register } from '../utils/api.js'

/** @type {import('vue').Ref<string>} 用户名输入值 */
const username = ref('')

/** @type {import('vue').Ref<string>} 密码输入值 */
const password = ref('')

/** @type {import('vue').Ref<string>} 确认密码输入值 */
const confirmPassword = ref('')

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
  if (password.value.length < 6) {
    errorMessage.value = '密码至少6个字符'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  loading.value = true

  try {
    await register(username.value.trim(), password.value, confirmPassword.value)
    successMessage.value = '注册成功！即将跳转到登录页...'

    // 注册成功后延迟跳转到登录页
    setTimeout(() => {
      emit('switch-to-login')
    }, 1500)
  } catch (err) {
    errorMessage.value = err.message || '注册失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-container">
    <div class="register-card">
      <div class="register-header">
        <h1 class="register-title">创建账号</h1>
        <p class="register-subtitle">请填写以下信息完成注册</p>
      </div>

      <form class="register-form" @submit.prevent="handleRegister">
        <!-- 用户名输入框 -->
        <div class="form-group">
          <label class="form-label" for="register-username">用户名</label>
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

        <!-- 密码输入框 -->
        <div class="form-group">
          <label class="form-label" for="register-password">密码</label>
          <input
            id="register-password"
            v-model="password"
            type="password"
            class="form-input"
            placeholder="请输入密码（至少6个字符）"
            autocomplete="new-password"
            :disabled="loading"
          />
        </div>

        <!-- 确认密码输入框 -->
        <div class="form-group">
          <label class="form-label" for="register-confirm-password">确认密码</label>
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

        <!-- 错误提示 -->
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>

        <!-- 成功提示 -->
        <div v-if="successMessage" class="success-message">
          {{ successMessage }}
        </div>

        <!-- 注册按钮 -->
        <button
          type="submit"
          class="register-button"
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
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  width: 100%;
  background-color: var(--color-bg-secondary);
  padding: var(--space-lg);
}

/* 注册卡片 */
.register-card {
  width: 100%;
  max-width: 420px;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  padding: var(--space-2xl) var(--space-xl);
}

/* 卡片头部 */
.register-header {
  text-align: center;
  margin-bottom: var(--space-xl);
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
.register-footer {
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
