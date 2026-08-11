/* -*- coding:utf-8 -*- */
/**
 * RegisterView 口令复杂度校验测试（2026-08-09 新增）。
 *
 * 验证等保三级整改后，注册表单严格按 8 位 + 大写 + 小写 + 数字 + 特殊字符
 * 拒绝弱口令，且 8 位四类齐全的强口令能够进入 register API 调用。
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
vi.mock('../../utils/api.js', () => ({
  register: vi.fn(),
  getCaptcha: vi.fn().mockResolvedValue({ captcha_key: 'k', captcha_image: '' })
}))
import RegisterView from '../RegisterView.vue'

async function fill(wrapper, password) {
  await wrapper.setData({
    username: 'alice',
    password,
    confirmPassword: password,
    realName: '张三',
    phone: '13800138000',
    email: 'a@b.com',
    department: '',
    position: '',
    captchaId: 'k',
    captchaCode: '1234'
  })
}

describe('RegisterView 密码复杂度', () => {
  it('7 位被前端拦截', async () => {
    const w = mount(RegisterView)
    await flushPromises()
    await fill(w, 'Aa1!aaa')
    await w.find('form').trigger('submit.prevent')
    expect(w.vm.errorMessage).toMatch(/至少8位/)
    expect(w.vm.errorMessage).toMatch(/特殊字符/)
  })
  it('8 位四类齐全通过', async () => {
    const api = await import('../../utils/api.js')
    api.register.mockResolvedValue({ message: 'ok' })
    const w = mount(RegisterView)
    await flushPromises()
    await fill(w, 'Aa1!aaaa')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(api.register).toHaveBeenCalled()
  })
})
