/* -*- coding:utf-8 -*- */
/**
 * 口令复杂度策略共享工具（2026-08-09 新增）。
 *
 * 强校验规则与后端 app/shared/utils/auth/password_policy.py::validate_password
 * 必须保持完全一致：
 *   - 长度 >= 8
 *   - 同时包含 ASCII 大写字母、ASCII 小写字母、数字、特殊字符
 *   - 特殊字符白名单：!@#$%^&*()_+\-=\[\]{}|;:,.<>?
 *
 * 该工具供前端 RegisterView、UserSettingsDialog 复用，禁止各组件自实现。
 *
 * 抛出异常：无（输入非法时按长度 0 / 不匹配处理，不会主动抛错）。
 */

export const MIN_LENGTH = 8
export const UPPER_RE = /[A-Z]/
export const LOWER_RE = /[a-z]/
export const DIGIT_RE = /\d/
export const SPECIAL_RE = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/

/**
 * 校验口令复杂度。
 *
 * @param {string} value 明文口令
 * @returns {{ok: boolean, reasons: string[]}} ok=true 时 reasons 为空数组
 */
export function validatePassword(value) {
  const reasons = []
  if (typeof value !== 'string' || value.length < MIN_LENGTH) {
    reasons.push(`密码长度不能少于${MIN_LENGTH}位`)
  }
  if (!UPPER_RE.test(value || '')) reasons.push('密码必须包含大写字母')
  if (!LOWER_RE.test(value || '')) reasons.push('密码必须包含小写字母')
  if (!DIGIT_RE.test(value || '')) reasons.push('密码必须包含数字')
  if (!SPECIAL_RE.test(value || '')) reasons.push('密码必须包含特殊字符')
  return { ok: reasons.length === 0, reasons }
}

/**
 * 提供给 UI 实时高亮的布尔提示集合。
 *
 * @param {string} value
 * @returns {{minLength: boolean, hasUpper: boolean, hasLower: boolean, hasDigit: boolean, hasSpecial: boolean}}
 */
export function getPasswordHints(value) {
  const v = value || ''
  return {
    minLength: v.length >= MIN_LENGTH,
    hasUpper: UPPER_RE.test(v),
    hasLower: LOWER_RE.test(v),
    hasDigit: DIGIT_RE.test(v),
    hasSpecial: SPECIAL_RE.test(v)
  }
}
