/**
 * vue-router 路由表与全局守卫
 *
 * 设计要点：
 * - 三个一级路由：/（主聊天）、/knowledge（知识库）、/ops-console（智能运维中心）
 * - /login 是独立 HTML 入口（由 login.html + login-main.js 承载），不纳入本路由表
 *   原因：避免「主应用挂载 → 渲染 LoginView → /login 独立挂载」的双 mount + 双 captcha 调用
 * - meta 字段 schema 已为后续等保三级条款预留接缝（详见 AGENTS.md / 项目记忆）：
 *     menuAcl / requiredRole / ownershipScope / auditEvent / auditFields /
 *     redactFields / csrf / sessionTimeoutSec / sensitiveOperation / logoutOnLeave
 *   本期仅消费 requiresAuth / pageKey / title；其余字段保留 key，value 留空
 *
 * 全局守卫：
 * - requiresAuth 路由 + 本地无 username 线索 → **整页跳转** /login?redirect=<from>
 *   （/login 是独立 HTML 入口，刻意不在本路由表内；应用内 return { path: '/login' }
 *   会命中 not-found 兜底 → 回 / → 再被守卫拦截 → 无限重定向循环，微任务链饿死
 *   fetch 回调导致白屏 + 主线程占满。必须 window.location.href 整页跳转）
 * - 不在守卫内 await validateToken，避免每次切路由阻塞；真正鉴权由 fetchWithAuth
 *   链路自动处理（401 → refresh → 重试），组件 onMounted 内做权威校验
 */
import { createRouter, createWebHistory } from 'vue-router'
import { hasLocalAuthToken, buildLoginUrl } from '../utils/auth.js'

const routes = [
  {
    path: '/',
    name: 'agent',
    component: () => import('../views/AgentWorkspace.vue'),
    meta: {
      requiresAuth: true,
      pageKey: 'agent',
      title: '智能运维中心',
      // —— 等保扩展字段预留（本期不消费）——
      menuAcl: null,
      requiredRole: null,
      ownershipScope: false,
      auditEvent: null,
      auditFields: null,
      redactFields: null,
      csrf: false,
      sessionTimeoutSec: null,
      sensitiveOperation: false,
      logoutOnLeave: false,
    },
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: () => import('../views/KnowledgeWorkspace.vue'),
    meta: {
      requiresAuth: true,
      pageKey: 'knowledge',
      title: '知识库',
      menuAcl: null,
      requiredRole: null,
      ownershipScope: false,
      auditEvent: null,
      auditFields: null,
      redactFields: null,
      csrf: false,
      sessionTimeoutSec: null,
      sensitiveOperation: false,
      logoutOnLeave: false,
    },
  },
  {
    path: '/ops-console',
    name: 'ops-console',
    component: () => import('../views/OpsConsoleWorkspace.vue'),
    meta: {
      requiresAuth: true,
      pageKey: 'ops-console',
      title: '智能运维中心',
      menuAcl: null,
      requiredRole: null,
      ownershipScope: false,
      auditEvent: null,
      auditFields: null,
      redactFields: null,
      csrf: false,
      sessionTimeoutSec: null,
      sensitiveOperation: false,
      logoutOnLeave: false,
    },
  },
  {
    // SPA 兜底：未知路径回退到 /，由 nginx.conf `try_files $uri $uri/ /index.html` 配合
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * 鉴权预检守卫：未登录访问受保护路由 → 整页跳转 /login 独立入口
 *
 * 为什么不能用 return { path: '/login?redirect=...' } 应用内跳转：
 * /login 是独立 HTML 入口（login.html + login-main.js），刻意不在本路由表内；
 * 应用内跳转会命中 not-found 兜底 → redirect '/' → 再次触发本守卫 → 无限重定向循环。
 * 循环产生的微任务链会饿死 fetch 回调（macrotask），导致 App.vue checkAuth 的
 * refresh/validate 永不返回，页面白屏且主线程占满，外部调试器 evaluate 也会挂起。
 *
 * 修复方式：window.location.href 整页跳转到 /login（由 nginx location /login →
 * login.html 承载 LoginView），并 return false 终止本次应用内导航。
 *
 * @param {Object} to - vue-router 目标路由对象（需含 meta.requiresAuth / fullPath）
 * @returns {boolean} true 放行；false 终止导航（已触发整页跳转 /login）
 * @throws {Error} 不主动抛错；buildLoginUrl 对非法 redirect 已做安全过滤
 */
export function requiresAuthGuard(to) {
  // [P0] 鉴权预检：未登录访问受保护路由 → 整页跳 /login?redirect=<from>
  if (to.meta.requiresAuth && !hasLocalAuthToken()) {
    window.location.href = buildLoginUrl(to.fullPath)
    return false
  }

  // [P1 待落地] 路由级 ACL（与后端 require_admin_or_menu_acl 对齐）
  // if (to.meta.menuAcl) {
  //   const { visibleMenus } = await fetchValidate()
  //   if (!Array.isArray(visibleMenus) || !visibleMenus.includes(to.meta.menuAcl)) {
  //     return { path: '/403' }
  //   }
  // }

  // [P1 待落地] 角色校验
  // if (to.meta.requiredRole && currentRole !== to.meta.requiredRole) {
  //   return { path: '/403' }
  // }

  // [P2 待落地] 路由切换审计
  // if (to.meta.auditEvent) {
  //   LogService.emit({
  //     event: to.meta.auditEvent,
  //     user_id: currentUser.userId,
  //     ip: await getClientIp(),
  //     target: to.fullPath,
  //   })
  // }

  return true
}

router.beforeEach(requiresAuthGuard)

export default router