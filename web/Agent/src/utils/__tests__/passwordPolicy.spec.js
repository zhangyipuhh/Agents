/* -*- coding:utf-8 -*- */
/**
 * 口令复杂度策略共享工具的单元测试（2026-08-09 新增）。
 *
 * 测试目标：web/Agent/src/utils/passwordPolicy.js
 * 覆盖：
 *   - MIN_LENGTH 常量值
 *   - validatePassword 各分支（长度、大写、小写、数字、特殊字符、空串）
 *   - getPasswordHints 与 validatePassword 同步语义
 */

import { describe, it, expect } from 'vitest'
import { MIN_LENGTH, validatePassword, getPasswordHints } from '../passwordPolicy.js'

describe('passwordPolicy', () => {
  it('MIN_LENGTH 等于 8', () => {
    expect(MIN_LENGTH).toBe(8)
  })
  it('7 位被拒', () => {
    expect(validatePassword('Aa1!aaa').ok).toBe(false)
  })
  it('8 位四类齐全通过', () => {
    const r = validatePassword('Aa1!aaaa')
    expect(r.ok).toBe(true)
    expect(r.reasons).toEqual([])
  })
  it('缺大写被拒', () => {
    expect(validatePassword('aa1!aaaa').ok).toBe(false)
  })
  it('缺小写被拒', () => {
    expect(validatePassword('AA1!AAAA').ok).toBe(false)
  })
  it('缺数字被拒', () => {
    expect(validatePassword('Aaa!aaaa').ok).toBe(false)
  })
  it('缺特殊字符被拒', () => {
    expect(validatePassword('Aa1aaaaa').ok).toBe(false)
  })
  it('空串被拒', () => {
    expect(validatePassword('').ok).toBe(false)
  })
  it('getPasswordHints 与 ok 同步', () => {
    const h = getPasswordHints('Aa1!aaaa')
    expect(h.minLength && h.hasUpper && h.hasLower && h.hasDigit && h.hasSpecial).toBe(true)
  })
})
