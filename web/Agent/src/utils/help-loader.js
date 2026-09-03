// -*- coding:utf-8 -*-
/**
 * 帮助文档加载器（fetch + 内存缓存）
 *
 * 职责：
 *   1. fetch /help/index.json 返回目录树（NavTreeNode[]）
 *   2. fetch /help/<path>.md 返回 markdown 文本
 *   3. 内存缓存避免重复请求（会话内常驻）
 *
 * 设计要点：
 *   - 路径规范化：去掉前导斜杠 + 自动补 .md 后缀
 *   - 失败语义：fetch 非 2xx 抛 Error（调用方 try/catch 显示「加载失败」）
 *   - 单例：模块级缓存 Map，跨组件共享
 *   - SSR 兜底：typeof window === 'undefined' 时不发起请求
 *
 * 使用示例：
 *   const { loadIndex, loadDoc } = await import('../utils/help-loader.js')
 *   const tree = await loadIndex()
 *   const md = await loadDoc('overview')
 */

/** @type {Map<string, any>} 索引缓存 */
const indexCache = new Map()

/** @type {Map<string, string>} 文档缓存（key: path, value: markdown 文本） */
const docCache = new Map()

/**
 * 索引文件路径常量（vite public 资源）
 * @returns {string}
 */
export function getIndexUrl() {
  return '/help/index.json'
}

/**
 * 获取文档 URL（自动拼接 .md 后缀）
 * @param {string} path - 文档路径，如 'overview' 或 'features/chat'
 * @returns {string}
 */
export function getDocUrl(path) {
  const normalized = normalizePath(path)
  return `/help/${normalized}.md`
}

/**
 * 规范化路径
 * - 去除前导斜杠
 * - 去除尾部斜杠
 * - 空拼接 → 'overview'（默认首页）
 *
 * @param {string} path
 * @returns {string}
 */
export function normalizePath(path) {
  if (typeof path !== 'string') return 'overview'
  let p = path.trim()
  if (!p) return 'overview'
  // 去掉前导斜杠
  while (p.startsWith('/')) p = p.slice(1)
  // 去掉尾部斜杠
  while (p.endsWith('/')) p = p.slice(0, -1)
  // 防 ../ 路径遍历
  if (p.includes('..')) return 'overview'
  return p || 'overview'
}

/**
 * 加载帮助文档目录树
 * @returns {Promise<{title: string, tree: Array}>}
 * @throws {Error} 网络错误或非 2xx 响应
 */
export async function loadIndex() {
  const url = getIndexUrl()
  if (indexCache.has(url)) {
    return indexCache.get(url)
  }
  const resp = await fetch(url)
  if (!resp.ok) {
    throw new Error(`加载帮助目录失败: HTTP ${resp.status}`)
  }
  const data = await resp.json()
  // 简单结构校验
  if (!data || typeof data !== 'object' || !Array.isArray(data.tree)) {
    throw new Error('帮助目录结构非法：缺少 tree 数组')
  }
  indexCache.set(url, data)
  return data
}

/**
 * 加载指定文档的 markdown 内容
 * @param {string} path - 文档路径，如 'overview'
 * @returns {Promise<string>} markdown 文本
 * @throws {Error} 网络错误或非 2xx 响应
 */
export async function loadDoc(path) {
  const normalized = normalizePath(path)
  if (docCache.has(normalized)) {
    return docCache.get(normalized)
  }
  const url = getDocUrl(normalized)
  const resp = await fetch(url)
  if (!resp.ok) {
    throw new Error(`加载文档失败: HTTP ${resp.status}（${normalized}）`)
  }
  const text = await resp.text()
  docCache.set(normalized, text)
  return text
}

/**
 * 清空所有缓存（测试用）
 * @returns {void}
 */
export function clearHelpCache() {
  indexCache.clear()
  docCache.clear()
}

/**
 * 从 markdown 文本提取 h2/h3 headings（用于右侧 anchor 索引）
 * @param {string} markdown
 * @returns {Array<{level: 2|3, text: string, id: string}>}
 */
export function extractHeadings(markdown) {
  if (typeof markdown !== 'string' || !markdown) return []
  const lines = markdown.split('\n')
  const headings = []
  let inCodeBlock = false
  for (const line of lines) {
    // 跳过 fenced code block 内的 # 行
    if (line.trim().startsWith('```')) {
      inCodeBlock = !inCodeBlock
      continue
    }
    if (inCodeBlock) continue
    const m = line.match(/^(##|###)\s+(.+?)\s*$/)
    if (!m) continue
    const level = m[1] === '##' ? 2 : 3
    const text = m[2].trim()
    const id = slugifyHeading(text)
    headings.push({ level, text, id })
  }
  return headings
}

/**
 * 将 heading 文本转为 slug（用于 anchor id）
 * - 中文保留（浏览器原生支持中文 anchor）
 * - 去除标点 / 空格替换为 -
 *
 * @param {string} text
 * @returns {string}
 */
export function slugifyHeading(text) {
  if (typeof text !== 'string') return ''
  return text
    .trim()
    .replace(/[\s]+/g, '-')
    .replace(/[^\w\u4e00-\u9fa5-]/g, '')
    .toLowerCase()
}

export default {
  getIndexUrl,
  getDocUrl,
  normalizePath,
  loadIndex,
  loadDoc,
  clearHelpCache,
  extractHeadings,
  slugifyHeading,
}