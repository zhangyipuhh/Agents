/**
 * 运维控制台样式按需加载工具
 *
 * 历史：2026-08-08 等保三级改造时与 ops-console 子页面一同落地；
 *       原 ensureOpsConsoleStyles() 定义在 App.vue 中，
 *       2026-08-XX 接入 vue-router 后从 App.vue 抽出到本文件，
 *       由 OpsConsoleWorkspace 在 onMounted 主动调一次。
 *
 * 设计要点：
 * - 单例守卫：避免多次切到 ops-console 页面时重复动态 import CSS
 * - 失败可重试：CSS 加载失败时清回标志位，允许下次再试
 * - 样式作用域：ops-console.css 内部全部选择器已加 `.ops-console-root` 前缀，
 *   不会污染主应用其他页面
 */

let loaded = false

/**
 * 加载运维控制台样式表（按需、单例守卫）
 * @returns {Promise<void>} 加载完成的 Promise；重复调用直接返回 resolved
 */
export async function ensureOpsConsoleStyles() {
  if (loaded) return
  loaded = true
  try {
    await import('../styles/ops-console.css')
  } catch (err) {
    console.error('[ops-console-styles] 加载运维控制台样式失败:', err)
    loaded = false  // 允许下次重试
  }
}