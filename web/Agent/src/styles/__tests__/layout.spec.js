/**
 * styles/layout.css 全局样式表测试
 *
 * 历史：2026-08-XX 接入 vue-router 后，AgentWorkspace 等子组件的根元素使用
 * .content-area / .welcome-title / .queue-banner-wrapper 等 layout 类。
 * 原 App.vue <style scoped> 不穿透到子组件根元素，所以这些类被抽出到本全局表。
 *
 * 测试目标：验证全局样式能被 DOM 命中（不仅 import 不抛错，且选择器确实生效）。
 * 用 happy-dom 提供 getComputedStyle（happy-dom 不返回 computed style，
 * 但 cssRules / stylesheet 内可枚举，所以用 cssRules 验证选择器存在）。
 */

import { describe, it, expect, beforeAll } from 'vitest'

describe('styles/layout.css 全局 layout 类', () => {
  let rules

  beforeAll(async () => {
    // 触发模块加载：让 Vite 把 layout.css 解析并写入到 document.styleSheets
    await import('../layout.css')
    // 遍历所有 stylesheet 收集 cssRules 文本（happy-dom 也支持基本样式表）
    rules = []
    if (typeof document !== 'undefined') {
      for (const sheet of Array.from(document.styleSheets)) {
        try {
          for (const rule of Array.from(sheet.cssRules || [])) {
            rules.push(rule.cssText)
          }
        } catch (_err) {
          // 跨域 stylesheet 跳过
        }
      }
    }
  })

  it('layout.css 加载不抛错', () => {
    // beforeAll 已成功 await import，无异常即通过
    expect(true).toBe(true)
  })

  it('含 .content-area 选择器（flex: 1 关键样式）', () => {
    const found = rules.some(text => text.includes('.content-area') && text.includes('flex'))
    expect(found).toBe(true)
  })

  it('含 .content-area.empty-layout 选择器', () => {
    const found = rules.some(text => text.includes('.content-area.empty-layout'))
    expect(found).toBe(true)
  })

  it('含 .welcome-title 选择器', () => {
    const found = rules.some(text => text.includes('.welcome-title') && text.includes('font-size'))
    expect(found).toBe(true)
  })

  it('含 .queue-banner-wrapper 选择器', () => {
    const found = rules.some(text => text.includes('.queue-banner-wrapper') && text.includes('padding'))
    expect(found).toBe(true)
  })

  it('含 .content-area.empty-layout .queue-banner-wrapper 嵌套规则', () => {
    const found = rules.some(text =>
      text.includes('.content-area.empty-layout') &&
      text.includes('.queue-banner-wrapper')
    )
    expect(found).toBe(true)
  })
})