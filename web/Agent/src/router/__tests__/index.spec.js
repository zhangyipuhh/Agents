/**
 * vue-router 路由表与全局守卫测试
 *
 * 用例覆盖：
 *   1) routes 表含 /、/knowledge、/ops-console 三个一级路由 + 一个 not-found 兜底
 *   2) requiresAuthGuard：未登录（localStorage 无 username）访问受保护路由
 *      → window.location.href 整页跳 /login?redirect=... 且 return false（回归：禁止
 *      再退回 return { path: '/login' } 应用内跳转——那会命中 not-found 兜底 → 回 / →
 *      无限重定向循环，微任务饿死 fetch 回调导致白屏）
 *   3) requiresAuthGuard：已登录（localStorage 有 username）放行 return true
 *   4) hasLocalAuthToken 工具行为
 *
 * 注：直接 import router 模块会触发 createRouter；守卫逻辑统一收敛在具名导出
 * requiresAuthGuard 中，测试直接调用真实守卫函数，杜绝「测试重实现守卫逻辑」
 * 与生产代码脱节的反模式。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// 测试 hasLocalAuthToken（auth.js 是单例工具，纯函数）
import { hasLocalAuthToken } from '../../utils/auth.js'
import { requiresAuthGuard } from '../index.js'

describe('router 配置与守卫', () => {
  // 单元隔离：每个用例前清空 localStorage，并重置 location stub
  const mockLocation = {
    href: '',
    origin: 'http://localhost:3000',
    pathname: '/',
    search: '',
    hash: ''
  }

  beforeEach(() => {
    localStorage.clear()
    mockLocation.href = ''
    vi.stubGlobal('location', mockLocation)
  })

  describe('routes 表结构', () => {
    it('含 /、/knowledge、/ops-console、/help 四个一级路由 + not-found 兜底', async () => {
      const { default: router } = await import('../index.js')
      const names = router.getRoutes().map(r => r.name)
      expect(names).toContain('agent')
      expect(names).toContain('knowledge')
      expect(names).toContain('ops-console')
      expect(names).toContain('help')
      expect(names).toContain('not-found')
    })

    it('四个业务路由的 requiresAuth / pageKey / title 字段齐全', async () => {
      const { default: router } = await import('../index.js')
      const agent = router.getRoutes().find(r => r.name === 'agent')
      const knowledge = router.getRoutes().find(r => r.name === 'knowledge')
      const opsConsole = router.getRoutes().find(r => r.name === 'ops-console')
      const help = router.getRoutes().find(r => r.name === 'help')

      expect(agent.meta.requiresAuth).toBe(true)
      expect(agent.meta.pageKey).toBe('agent')
      expect(typeof agent.meta.title).toBe('string')

      expect(knowledge.meta.requiresAuth).toBe(true)
      expect(knowledge.meta.pageKey).toBe('knowledge')

      expect(opsConsole.meta.requiresAuth).toBe(true)
      expect(opsConsole.meta.pageKey).toBe('ops-console')

      expect(help.meta.requiresAuth).toBe(true)
      expect(help.meta.pageKey).toBe('help')
      expect(help.meta.title).toBe('帮助中心')
    })

    it('/login 不在路由表内（独立 HTML 入口），且 not-found 兜底重定向回 /', async () => {
      const { default: router } = await import('../index.js')
      const names = router.getRoutes().map(r => r.name)
      expect(names).not.toContain('login')
      const notFound = router.getRoutes().find(r => r.name === 'not-found')
      expect(notFound.path).toBe('/:pathMatch(.*)*')
      expect(notFound.redirect).toBe('/')
    })
  })

  describe('hasLocalAuthToken 工具', () => {
    it('localStorage 无 username → false', () => {
      expect(hasLocalAuthToken()).toBe(false)
    })

    it('localStorage 有 username → true', () => {
      localStorage.setItem('username', 'admin')
      expect(hasLocalAuthToken()).toBe(true)
    })
  })

  describe('requiresAuthGuard 真实守卫行为', () => {
    it('未登录访问 / → 整页跳 /login?redirect=%2F 且 return false', () => {
      const to = { fullPath: '/', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      expect(result).toBe(false)
      expect(mockLocation.href).toBe('http://localhost:3000/login?redirect=%2F')
    })

    it('未登录访问 /ops-console → 整页跳 /login?redirect=%2Fops-console 且 return false', () => {
      const to = { fullPath: '/ops-console', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      expect(result).toBe(false)
      expect(mockLocation.href).toBe('http://localhost:3000/login?redirect=%2Fops-console')
    })

    it('未登录访问 /knowledge → 整页跳 /login?redirect=%2Fknowledge 且 return false', () => {
      const to = { fullPath: '/knowledge', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      expect(result).toBe(false)
      expect(mockLocation.href).toBe('http://localhost:3000/login?redirect=%2Fknowledge')
    })

    it('未登录访问 /help → 整页跳 /login?redirect=%2Fhelp 且 return false（2026-09-03 新增帮助路由）', () => {
      const to = { fullPath: '/help', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      expect(result).toBe(false)
      expect(mockLocation.href).toBe('http://localhost:3000/login?redirect=%2Fhelp')
    })

    it('已登录（localStorage 有 username）→ return true 放行，不触发跳转', () => {
      localStorage.setItem('username', 'admin')
      const to = { fullPath: '/ops-console', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      expect(result).toBe(true)
      expect(mockLocation.href).toBe('')
    })

    it('回归：守卫返回值必须是 boolean，绝不允许再退回应用内跳转对象 { path: "/login..." }', () => {
      const to = { fullPath: '/', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      // /login 不在路由表内；应用内 return { path: '/login' } 会命中 not-found → / → 再被守卫拦截
      // 形成无限重定向循环（白屏根因）。返回值是对象即说明退化回了应用内跳转。
      expect(typeof result).toBe('boolean')
    })

    it('redirect 参数经 buildLoginUrl 安全过滤：非法目标回退为 /', () => {
      // fullPath 本身一定以 / 开头（vue-router 契约），此处验证 buildLoginUrl 对异常输入的兜底
      const to = { fullPath: 'javascript:alert(1)', meta: { requiresAuth: true } }
      const result = requiresAuthGuard(to)
      expect(result).toBe(false)
      expect(mockLocation.href).toBe('http://localhost:3000/login')
    })
  })
})