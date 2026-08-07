// -*- coding:utf-8 -*-
/**
 * 公共 Markdown 安全渲染工具
 *
 * 职责:
 * 1. 用 marked 解析 markdown 为 HTML。
 * 2. 用 DOMPurify sanitize 去掉 <script> / onerror / javascript: 等危险节点与属性,
 *    防止 v-html 注入引发 XSS。
 * 3. 后置字符串注入:为 <a> 附加 target=_blank + rel=noopener noreferrer,
 *    为 <img> 附加 loading=lazy + style=max-width:100%。
 *
 * 适用范围(2026-08-07 整理):
 *   - MessageBubble.vue: AI 回复 / 历史会话 markdown
 *   - FilePreview.vue: markdown 文件预览
 *
 * 设计要点:
 *   - 单一全局 DOMPurify 实例,避免每次渲染重新分配。
 *   - 显式列出允许的标签 / 属性,白名单策略。
 *   - URL 协议用 DOMPurify 默认 ALLOWED_URI_REGEXP:
 *     /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix):|[^a-z]|[a-z+."]+(?:[^a-z+."]|$))/i
 *     —— 支持 http/https/mailto 等 + 相对路径(以 /、?、# 开头)。
 *     显式禁止 javascript: / data: / vbscript: 等。
 *   - 显式 marked.parse(text, { async: false }) 强制同步返回 string,
 *     不受全局 marked.use({ async: true }) 影响。
 *
 * 关于"DOMPurify hook + 后置字符串注入"双保险:
 *   - 浏览器/happy-dom 下 DOMPurify 的 afterSanitizeAttributes hook 行为并不一致,
 *     happy-dom 测试环境 setAttribute 写入后会被最终字符串化时丢失。
 *   - 因此本工具在 sanitize() 之后,在最终 HTML 字符串上做一次属性注入:
 *       - <a href=...>:注入 target=_blank + rel=noopener noreferrer(若已存在则不重复)
 *       - <img src=...>:注入 loading=lazy + style=max-width:100%;height:auto(若已存在则不重复)
 *   - 字符串不可达的情况也能从 marked 的输出保证 <a href=...> 至少出现一次。
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 在 happy-dom / browser 环境下 window 都存在;SSR 场景暂不需要
const purify = typeof window !== 'undefined'
  ? DOMPurify(window)
  : null

// 公共白名单:覆盖 markdown 渲染所需标签 + 必要的 link code block 等
const ALLOWED_TAGS = [
  'a', 'b', 'blockquote', 'br', 'code', 'del', 'div', 'em', 'h1', 'h2',
  'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'ol',
  'p', 'pre', 's', 'span', 'strong', 'sub', 'sup', 'table', 'tbody',
  'td', 'th', 'thead', 'tr', 'ul', 'mark', 'input'
]

const ALLOWED_ATTR = [
  'href', 'title', 'alt', 'src', 'class', 'data-trigger-id',
  'data-business-name', 'data-server-type', 'data-mention-class',
  'disabled', 'type', 'checked', 'id', 'loading', 'style',
  'data-mention-block', 'data-mention-char', 'data-mention-value'
]

// 兜底:happy-dom / jsdom 等 DOMPurify 半残环境下 hook 不生效时,
// 在字符串上二次注入 <a>/<img> 安全属性 + 二次过滤 javascript:/data:。
// 浏览器原生 DOMPurify hook 路径也作为补充,见模块底部 addHook。
const DANGEROUS_URL_REGEX = /(\s(?:href|src|xlink:href)\s*=\s*["']?)\s*(javascript|data|vbscript|file):[^"'>\s]+/gi

/**
 * 在最终 HTML 字符串上做属性注入 + 二次 URL 过滤。
 * 纯字符串操作,DOM 无关,行为在 happy-dom / jsdom / 浏览器下完全一致。
 * @param {string} html - DOMPurify sanitize 后的 HTML
 * @returns {string} 注入安全属性后的 HTML
 */
function injectSafeAttrs(html) {
  if (!html) return html
  // 1. 二次过滤 javascript:/data: 等危险 URL(防止 ALLOWED_URI_REGEXP 在某些环境下未生效)
  let result = html.replace(DANGEROUS_URL_REGEX, '$1=""')
  // 2. 为 <a href=...> 注入 target=_blank + rel=noopener noreferrer(若已存在则不重复)
  result = result.replace(
    /<a\s([^>]*?)>/gi,
    (match, attrs) => {
      // 跳过无 href 的锚链(<a name="...">、<a id="...">)
      if (!/\shref\s*=/i.test(attrs)) return match
      let next = attrs
      if (!/\starget\s*=/i.test(next)) next += ' target="_blank"'
      if (!/\srel\s*=/i.test(next)) next += ' rel="noopener noreferrer"'
      return `<a ${next}>`
    }
  )
  // 3. 为 <img src=...> 注入 loading=lazy + style=max-width:100%;height:auto(若已存在则不重复)
  result = result.replace(
    /<img\s([^>]*?)>/gi,
    (match, attrs) => {
      let next = attrs
      if (!/\sloading\s*=/i.test(next)) next += ' loading="lazy"'
      if (!/\sstyle\s*=/i.test(next)) next += ' style="max-width:100%;height:auto"'
      return `<img ${next}>`
    }
  )
  return result
}

// 浏览器原生 DOMPurify 实例上注册 hook(在 happy-dom / jsdom 测试环境可能无效,见函数注释)
if (purify) {
  purify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A' && node.hasAttribute('href')) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
    if (node.tagName === 'IMG') {
      node.setAttribute('loading', 'lazy')
      node.setAttribute('style', 'max-width:100%;height:auto')
    }
  })
}

/**
 * 渲染 markdown 文本,经 DOMPurify 净化 + 字符串兜底后,返回安全的 HTML。
 * @param {string} text - 原始 markdown 文本
 * @returns {string} 经 sanitize 的 HTML 字符串
 */
export function safeMarkdown(text) {
  if (!text) return ''
  // 1. 显式 { async: false } 强制同步返回 string
  const raw = marked.parse(text, { async: false })
  // 2. DOMPurify sanitize(浏览器/happy-dom 均能去掉 <script> / onerror)
  let html = purify ? purify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // ALLOWED_URI_REGEXP 不显式传,使用 DOMPurify 默认
  }) : raw
  // 3. 字符串兜底:注入 <a>/<img> 安全属性 + 二次过滤 javascript:/data:
  html = injectSafeAttrs(html)
  return html
}
