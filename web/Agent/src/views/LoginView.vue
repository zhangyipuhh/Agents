<script setup>
/**
 * LoginView - 登录页面组件（2026-08-07 改造：MFA 两阶段）
 *
 * 三阶段渲染：
 * - 'password'：用户名 + 密码 + 图形验证码
 * - 'mfa_verify'：MFA 已启用用户的 6 位 TOTP / 恢复码校验
 * - 'mfa_enroll'：管理员首次绑定的启用向导（二维码 + 确认码）
 *
 * 关键约束：
 * - 第一阶段响应若是 mfa_required / mfa_enrollment_required，
 *   绝不能写 localStorage，绝不能 emit login-success；
 * - challenge_token / enrollment_token / 二维码 / 恢复码 仅存组件内存；
 * - 错误或过期清空 mfa token / code / qr / recovery，并刷新图形验证码；
 * - 三阶段全部成功才走统一完成登录逻辑（写 localStorage + emit login-success）。
 */

import { ref, onMounted, computed } from 'vue'
import {
  login,
  getCaptcha,
  loginMfaVerify,
  startLoginMfaEnrollment,
  confirmLoginMfaEnrollment
} from '../utils/api.js'
import { appConfig } from '../config/portal.js'

/* ===== 密码阶段 ===== */

/** @type {import('vue').Ref<string>} 用户名输入值 */
const username = ref('')

/** @type {import('vue').Ref<string>} 密码输入值 */
const password = ref('')

/** @type {import('vue').Ref<string>} 验证码输入值 */
const captchaCode = ref('')

/** @type {import('vue').Ref<string>} 验证码 ID，由服务端返回 */
const captchaId = ref('')

/** @type {import('vue').Ref<string>} 验证码图片的 Base64 数据 */
const captchaImage = ref('')

/* ===== MFA 阶段通用 ===== */

/**
 * 当前阶段：'password' | 'mfa_verify' | 'mfa_enroll'
 * @type {import('vue').Ref<'password' | 'mfa_verify' | 'mfa_enroll'>}
 */
const stage = ref('password')

/** @type {import('vue').Ref<string>} MFA 第一阶段返回的 challenge_token，仅内存 */
const mfaChallengeToken = ref('')

/** @type {import('vue').Ref<string>} MFA 第一阶段返回的 username，便于回显 */
const mfaUsername = ref('')

/** @type {import('vue').Ref<string>} 错误提示信息（密码/MFA 共用） */
const errorMessage = ref('')

/** @type {import('vue').Ref<boolean>} 是否正在提交 */
const loading = ref(false)

/** @type {import('vue').Ref<boolean>} 大写锁定状态 */
const capsLockOn = ref(false)

/* ===== MFA verify 阶段 ===== */

/** @type {import('vue').Ref<string>} 6 位 TOTP 码或恢复码 */
const mfaCode = ref('')

/** @type {import('vue').Ref<'totp'|'recovery_code'>} 第二因素类型 */
const mfaMethod = ref('totp')

/** @type {import('vue').Ref<string[]>} 可用的第二因素列表 */
const mfaMethodsAvailable = ref([])

/* ===== MFA enroll 阶段 ===== */

/** @type {import('vue').Ref<string>} enroll 阶段的 enrollment_token，仅内存 */
const mfaEnrollmentToken = ref('')

/** @type {import('vue').Ref<string>} TOTP secret 二维码 dataURL，仅内存 */
const mfaEnrollQr = ref('')

/** @type {import('vue').Ref<string>} otpauth URI，可选展示给用户 */
const mfaEnrollOtpauthUri = ref('')

/** @type {import('vue').Ref<number>} enroll 阶段有效期（秒），仅展示用 */
const mfaEnrollExpiresIn = ref(0)

/** @type {import('vue').Ref<string>} enroll 确认输入 6 位码 */
const mfaEnrollCode = ref('')

/** @type {import('vue').Ref<string[]>} 启用成功后一次性返回的恢复码，仅内存 */
const recoveryCodes = ref([])

/** @type {import('vue').Ref<string>} enroll 阶段的成功提示文案 */
const enrollSuccessMessage = ref('')

/* ===== 通用 ===== */

/**
 * 当前是否处于 enroll 阶段且恢复码已展示（用于切换回密码阶段时的清理提示）。
 * @type {import('vue').ComputedRef<boolean>}
 */
const isRecoveryStage = computed(() => stage.value === 'mfa_enroll' && recoveryCodes.value.length > 0)

/**
 * 检测大写锁定键状态
 * @param {KeyboardEvent} event - 键盘事件对象
 */
function checkCapsLock(event) {
  capsLockOn.value = event.getModifierState('CapsLock')
}

/**
 * 组件事件定义
 * @event login-success - 登录成功时触发，参数: { access_token, role, username, user_id }
 * @event switch-to-register - 点击"去注册"时触发
 */
const emit = defineEmits(['login-success', 'switch-to-register'])

/**
 * 加载图形验证码
 * 调用 getCaptcha API 获取验证码 ID 与图片数据
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
 * 完成登录：统一把 LoginResponse 写 localStorage 并 emit login-success。
 * 不在此处清空错误信息——调用方已保证此时没有错误。
 *
 * @param {Object} data - LoginResponse
 * @returns {void}
 */
function finalizeLogin(data) {
  localStorage.setItem('auth_token', data.access_token)
  localStorage.setItem('user_role', data.role)
  localStorage.setItem('username', data.username)
  if (data.user_id !== undefined && data.user_id !== null) {
    localStorage.setItem('user_id', String(data.user_id))
  }
  emit('login-success', {
    access_token: data.access_token,
    role: data.role,
    username: data.username,
    user_id: data.user_id
  })
}

/**
 * 清空 MFA 临时状态（challenge / enrollment token、二维码、恢复码、码值）。
 * 仅清组件内存，不触碰 localStorage / sessionStorage。
 *
 * @returns {void}
 */
function resetMfaState() {
  mfaChallengeToken.value = ''
  mfaEnrollmentToken.value = ''
  mfaEnrollQr.value = ''
  mfaEnrollOtpauthUri.value = ''
  mfaEnrollExpiresIn.value = 0
  mfaEnrollCode.value = ''
  mfaCode.value = ''
  mfaMethod.value = 'totp'
  mfaMethodsAvailable.value = []
  recoveryCodes.value = []
  enrollSuccessMessage.value = ''
}

/**
 * 切换回密码阶段：清空所有 MFA 临时状态并刷新验证码。
 *
 * @returns {Promise<void>}
 */
async function backToPasswordStage() {
  resetMfaState()
  mfaUsername.value = ''
  stage.value = 'password'
  await loadCaptcha()
}

/**
 * 处理密码阶段提交。
 * 响应三态：
 * - 普通 LoginResponse：直接完成登录。
 * - auth_stage=mfa_required：切到 mfa_verify 阶段。
 * - auth_stage=mfa_enrollment_required：切到 mfa_enroll 阶段并自动调用 start 获取二维码。
 *
 * @returns {Promise<void>}
 */
async function handleLogin() {
  errorMessage.value = ''

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

    // 1) 普通成功
    if (!data || !data.auth_stage) {
      finalizeLogin(data)
      return
    }

    // 2) MFA 已绑定 → 第二因素校验阶段
    if (data.auth_stage === 'mfa_required') {
      mfaChallengeToken.value = String(data.challenge_token || '')
      mfaUsername.value = data.username || username.value
      mfaMethodsAvailable.value = Array.isArray(data.mfa_methods) ? [...data.mfa_methods] : []
      // 默认 TOTP；若只有 recovery_code 仍让用户手动切换
      mfaMethod.value = mfaMethodsAvailable.value.includes('totp') ? 'totp' : 'recovery_code'
      stage.value = 'mfa_verify'
      return
    }

    // 3) 强制绑定阶段（管理员首次登录）
    if (data.auth_stage === 'mfa_enrollment_required') {
      mfaChallengeToken.value = String(data.challenge_token || '')
      mfaUsername.value = data.username || username.value
      stage.value = 'mfa_enroll'
      // 自动获取二维码
      try {
        const enroll = await startLoginMfaEnrollment(mfaChallengeToken.value)
        mfaEnrollmentToken.value = enroll.enrollment_token
        mfaEnrollQr.value = enroll.qr_png_base64
        mfaEnrollOtpauthUri.value = enroll.otpauth_uri || ''
        mfaEnrollExpiresIn.value = Number(enroll.expires_in || 0)
      } catch (enrollErr) {
        errorMessage.value = enrollErr.message || '启动 MFA 绑定失败'
        await backToPasswordStage()
      }
      return
    }

    errorMessage.value = '登录响应格式异常，请重试'
    await loadCaptcha()
  } catch (err) {
    errorMessage.value = err.message || '登录失败，请重试'
    captchaCode.value = ''
    await loadCaptcha()
  } finally {
    loading.value = false
  }
}

/**
 * 处理 MFA verify 阶段提交。
 * @returns {Promise<void>}
 */
async function handleMfaVerify() {
  errorMessage.value = ''
  if (!mfaCode.value.trim()) {
    errorMessage.value = '请输入 6 位验证码或恢复码'
    return
  }
  loading.value = true
  try {
    const data = await loginMfaVerify(mfaChallengeToken.value, mfaCode.value.trim(), mfaMethod.value)
    finalizeLogin(data)
  } catch (err) {
    errorMessage.value = err.message || 'MFA 校验失败'
    mfaCode.value = ''
    // 错误时清理 challenge（防止错误码继续吃 challenge 配额）
    mfaChallengeToken.value = ''
    await loadCaptcha()
  } finally {
    loading.value = false
  }
}

/**
 * 切换 MFA verify 阶段的 method。
 * @param {'totp'|'recovery_code'} method - 切换目标
 * @returns {void}
 */
function switchMfaMethod(method) {
  if (method !== 'totp' && method !== 'recovery_code') return
  mfaMethod.value = method
  mfaCode.value = ''
}

/**
 * 处理 enroll 阶段确认提交。
 * 成功 → finalize + 展示一次性恢复码。
 * @returns {Promise<void>}
 */
async function handleEnrollConfirm() {
  errorMessage.value = ''
  if (!mfaEnrollCode.value.trim()) {
    errorMessage.value = '请输入 6 位验证码'
    return
  }
  loading.value = true
  try {
    const result = await confirmLoginMfaEnrollment(
      mfaEnrollmentToken.value,
      mfaEnrollCode.value.trim()
    )
    recoveryCodes.value = Array.isArray(result.recovery_codes) ? [...result.recovery_codes] : []
    enrollSuccessMessage.value = '绑定成功，请妥善保存以下恢复码：'
    finalizeLogin(result.auth)
  } catch (err) {
    errorMessage.value = err.message || '确认 MFA 绑定失败'
    mfaEnrollCode.value = ''
  } finally {
    loading.value = false
  }
}

/**
 * 重新拉取 enroll 阶段的二维码（旧的 enrollment_token 已被消费或过期）。
 * @returns {Promise<void>}
 */
async function refreshEnrollQr() {
  if (!mfaChallengeToken.value) return
  try {
    const enroll = await startLoginMfaEnrollment(mfaChallengeToken.value)
    mfaEnrollmentToken.value = enroll.enrollment_token
    mfaEnrollQr.value = enroll.qr_png_base64
    mfaEnrollOtpauthUri.value = enroll.otpauth_uri || ''
    mfaEnrollExpiresIn.value = Number(enroll.expires_in || 0)
    mfaEnrollCode.value = ''
    errorMessage.value = ''
  } catch (err) {
    errorMessage.value = err.message || '刷新二维码失败'
  }
}

// 组件挂载时自动加载验证码
onMounted(() => {
  loadCaptcha()
  console.log('[LoginView] appConfig.brandTitle =', appConfig.brandTitle)
})
</script>

<template>
  <div class="login-container">
    <div class="login-brand">
      <div class="brand-title">{{ appConfig.brandTitle }}</div>
      <div class="brand-divider"></div>
      <p class="brand-desc">{{ appConfig.brandDesc }}</p>
    </div>
    <div class="login-card">
      <div class="login-header">
        <div class="system-title">{{ appConfig.brandTitle }}</div>
        <div class="title-divider"></div>
        <h1 class="login-title">欢迎登录</h1>
        <p class="login-subtitle">
          <span v-if="stage === 'password'">请输入您的账号信息</span>
          <span v-else-if="stage === 'mfa_verify'">用户 {{ mfaUsername }} 启用了双因素认证</span>
          <span v-else-if="stage === 'mfa_enroll'">首次登录，请绑定身份认证器</span>
        </p>
      </div>

      <!-- 阶段 1：密码 + 图形验证码 -->
      <form
        v-if="stage === 'password'"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <!-- 用户名 -->
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

        <!-- 密码 -->
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
            @keydown="checkCapsLock"
            @keyup="checkCapsLock"
          />
          <div v-if="capsLockOn" class="caps-lock-hint">
            <span class="caps-lock-icon">⚠</span>
            <span>大写锁定已开启</span>
          </div>
        </div>

        <!-- 图形验证码 -->
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
              <div v-else class="captcha-placeholder">加载中...</div>
            </div>
          </div>
        </div>

        <div v-if="errorMessage" class="error-message">{{ errorMessage }}</div>

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

      <!-- 阶段 2：MFA verify（TOTP / 恢复码） -->
      <form
        v-else-if="stage === 'mfa_verify'"
        class="login-form"
        data-testid="mfa-verify-stage"
        @submit.prevent="handleMfaVerify"
      >
        <div class="form-group">
          <label class="form-label" for="mfa-method">第二因素类型</label>
          <div class="mfa-method-tabs">
            <button
              type="button"
              class="mfa-method-tab"
              :class="{ active: mfaMethod === 'totp' }"
              :disabled="!mfaMethodsAvailable.includes('totp') || loading"
              @click="switchMfaMethod('totp')"
            >
              身份认证器
            </button>
            <button
              type="button"
              class="mfa-method-tab"
              :class="{ active: mfaMethod === 'recovery_code' }"
              :disabled="!mfaMethodsAvailable.includes('recovery_code') || loading"
              @click="switchMfaMethod('recovery_code')"
            >
              恢复码
            </button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label" for="mfa-code">验证码</label>
          <input
            id="mfa-code"
            v-model="mfaCode"
            type="text"
            inputmode="numeric"
            class="form-input"
            placeholder="请输入 6 位验证码或恢复码"
            autocomplete="one-time-code"
            data-testid="mfa-code-input"
            :disabled="loading"
            @keydown="checkCapsLock"
            @keyup="checkCapsLock"
          />
          <p class="form-hint">
            <span v-if="mfaMethod === 'totp'">打开手机身份认证器（如 Google Authenticator / 微软 Authenticator），输入 6 位动态码。</span>
            <span v-else>请输入注册时一次性下发的恢复码（形如 XXXX-XXXX）。</span>
          </p>
          <div v-if="capsLockOn" class="caps-lock-hint">
            <span class="caps-lock-icon">⚠</span>
            <span>大写锁定已开启</span>
          </div>
        </div>

        <div v-if="errorMessage" class="error-message">{{ errorMessage }}</div>

        <button
          type="submit"
          class="login-button"
          :disabled="loading"
          data-testid="mfa-verify-form"
        >
          <span v-if="loading" class="button-loading">
            <span class="loading-spinner"></span>
            校验中...
          </span>
          <span v-else>校验并登录</span>
        </button>

        <button
          type="button"
          class="login-secondary-button"
          :disabled="loading"
          @click="backToPasswordStage"
        >
          返回重新输入密码
        </button>
      </form>

      <!-- 阶段 3：MFA enroll（首次绑定） -->
      <div
        v-else-if="stage === 'mfa_enroll'"
        class="login-form"
        data-testid="mfa-enroll-stage"
      >
        <div v-if="!isRecoveryStage">
          <p class="form-hint">
            请使用手机身份认证器（如 Google Authenticator / 微软 Authenticator）
            扫描下方二维码绑定账号 <strong>{{ mfaUsername }}</strong>，绑定完成后输入 6 位动态码。
          </p>

          <div class="mfa-enroll-qr-wrap">
            <img
              v-if="mfaEnrollQr"
              :src="mfaEnrollQr"
              alt="MFA 二维码"
              class="mfa-enroll-qr"
              data-testid="mfa-enroll-qr"
            />
            <div v-else class="captcha-placeholder">二维码加载中...</div>
          </div>

          <p class="form-hint">
            无法扫描？将 otpauth URI 手动粘贴到认证器：
            <code class="mfa-enroll-uri">{{ mfaEnrollOtpauthUri || '—' }}</code>
          </p>

          <button
            type="button"
            class="login-secondary-button"
            :disabled="loading"
            @click="refreshEnrollQr"
          >
            刷新二维码
          </button>

          <form @submit.prevent="handleEnrollConfirm" data-testid="mfa-enroll-form">
            <div class="form-group">
              <label class="form-label" for="mfa-enroll-code">动态码</label>
              <input
                id="mfa-enroll-code"
                v-model="mfaEnrollCode"
                type="text"
                inputmode="numeric"
                class="form-input"
                placeholder="请输入 6 位动态码"
                autocomplete="one-time-code"
                data-testid="mfa-enroll-code-input"
                :disabled="loading"
                @keydown="checkCapsLock"
                @keyup="checkCapsLock"
              />
            </div>

            <div v-if="errorMessage" class="error-message">{{ errorMessage }}</div>

            <button
              type="submit"
              class="login-button"
              :disabled="loading"
              data-testid="mfa-enroll-confirm-btn"
            >
              <span v-if="loading" class="button-loading">
                <span class="loading-spinner"></span>
              绑定中...
              </span>
              <span v-else>确认绑定</span>
            </button>
          </form>
        </div>

        <div v-else class="mfa-recovery-block">
          <p class="form-hint success">{{ enrollSuccessMessage }}</p>
          <ul class="mfa-recovery-codes" data-testid="mfa-recovery-codes-list">
            <li v-for="code in recoveryCodes" :key="code">{{ code }}</li>
          </ul>
          <p class="form-hint warning">每个恢复码仅可使用一次，请立即抄写到安全位置。</p>
        </div>
      </div>

      <!-- 底部注册链接（仅密码阶段展示） -->
      <div v-if="stage === 'password'" class="login-footer">
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
  background: linear-gradient(135deg, #EBF4FF 0%, #F0F7FF 40%, #FFFFFF 100%);
  background-attachment: fixed;
  position: relative;
  padding: var(--space-lg);
}

/* 极淡的几何纹理背景叠加 */
.login-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, #1E5AA8 0.5px, transparent 0.5px);
  background-size: 24px 24px;
  opacity: 0.06;
  pointer-events: none;
}

/* 左侧品牌区域 - 默认窄屏下隐藏 */
.login-brand {
  display: none;
}

/* 登录卡片 */
.login-card {
  width: 100%;
  max-width: 420px;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  border-top: 4px solid #1E5AA8;
  padding: var(--space-2xl) var(--space-xl);
  position: relative;
  z-index: 1;
}

/* 卡片头部 */
.login-header {
  text-align: center;
  margin-bottom: var(--space-xl);
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

/* 宽屏左右分栏布局 */
@media (min-width: 960px) {
  .login-container {
    justify-content: center;
    gap: 80px;
    padding: var(--space-lg) var(--space-xl);
  }

  .login-brand {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    max-width: 460px;
    z-index: 1;
  }

  .brand-title {
    font-size: 28px;
    font-weight: var(--font-weight-bold);
    color: #1E5AA8;
    line-height: 1.3;
    margin-bottom: var(--space-base);
    white-space: nowrap;
  }

  .brand-divider {
    width: 56px;
    height: 4px;
    background: linear-gradient(90deg, #1E5AA8, #4A90D9);
    border-radius: 2px;
    margin-bottom: var(--space-base);
  }

  .brand-desc {
    font-size: var(--font-size-lg);
    color: var(--color-text-secondary);
    line-height: var(--line-height-normal);
  }

  /* 宽屏下卡片内标题隐藏，由左侧品牌区域展示 */
  .login-header .system-title,
  .login-header .title-divider {
    display: none;
  }
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

/* 表单内提示文字 */
.form-hint {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);

  &.success {
    color: #166534;
    font-weight: var(--font-weight-semibold);
  }

  &.warning {
    color: #92400E;
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

/* 大写锁定提示 */
.caps-lock-hint {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  font-size: var(--font-size-sm);
  color: #92400E;
  background-color: #FFFBEB;
  border-radius: var(--radius-sm);
  border: 1px solid #FCD34D;
  line-height: var(--line-height-normal);
}

.caps-lock-icon {
  font-size: var(--font-size-base);
}

/* MFA method 切换 tab */
.mfa-method-tabs {
  display: flex;
  gap: var(--space-sm);
}

.mfa-method-tab {
  flex: 1;
  height: 40px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover:not(:disabled) {
    border-color: #1E5AA8;
    color: #1E5AA8;
  }

  &.active {
    color: #ffffff;
    background-color: #1E5AA8;
    border-color: #1E5AA8;
  }

  &:disabled {
    opacity: var(--opacity-disabled);
    cursor: not-allowed;
  }
}

/* MFA enroll 二维码 */
.mfa-enroll-qr-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: var(--space-base);
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  margin-bottom: var(--space-base);
}

.mfa-enroll-qr {
  width: 200px;
  height: 200px;
  object-fit: contain;
  background-color: #ffffff;
  padding: 8px;
  border-radius: var(--radius-sm);
}

.mfa-enroll-uri {
  display: inline-block;
  margin-top: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  word-break: break-all;
}

/* 恢复码展示块 */
.mfa-recovery-block {
  padding: var(--space-base);
  background-color: #F0FDF4;
  border: 1px solid #86EFAC;
  border-radius: var(--radius-md);
}

.mfa-recovery-codes {
  list-style: none;
  padding: 0;
  margin: var(--space-sm) 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-sm);

  li {
    padding: var(--space-sm);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: var(--font-size-base);
    font-weight: var(--font-weight-semibold);
    background-color: #ffffff;
    border: 1px dashed #86EFAC;
    border-radius: var(--radius-sm);
    text-align: center;
    color: #166534;
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

/* 登录按钮 */
.login-button {
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

/* 次级按钮（返回 / 刷新二维码） */
.login-secondary-button {
  width: 100%;
  height: 38px;
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: #1E5AA8;
  background-color: transparent;
  border: 1px solid #1E5AA8;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors);

  &:hover:not(:disabled) {
    background-color: rgba(30, 90, 168, 0.08);
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
  color: #1E5AA8;
  cursor: pointer;
  font-weight: var(--font-weight-medium);
  transition: var(--transition-colors);

  &:hover {
    color: #155A9E;
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