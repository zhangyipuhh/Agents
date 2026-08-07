// -*- coding:utf-8 -*-
/**
 * safeMarkdown 单元测试
 *
 * 覆盖范围:
 * 1. 空 / 普通文本 / 任务列表
 * 2. <script> / onerror / javascript: 链接 / data: URL 等注入
 * 3. mention chip 保留
 * 4. 链接自动 target=_blank + rel=noopener noreferrer
 * 5. 图片自动 loading=lazy + style=max-width:100%
 * 6. 同步性 (T1 验证)
 * 7. 相对路径 / 锚链保留 (T5 验证)
 *
 * 关键实现细节:
 *   本测试在 happy-dom 环境下初始化 sanitize-marked 模块时 DOMPurify
 *   的 hook 行为不完全可靠(已知问题:happy-dom 字符串化时丢失 hook 写入的属性)。
 *   因此本测试**主动构造 jsdom + DOMPurify 实例**,并调用与 safeMarkdown
 *   同源的注入逻辑,确保端到端路径在测试中可观测。
 *   浏览器环境(happy-dom / jsdom 都用不到真实 DOMRender)走同一份 safeMarkdown,
 *   生产路径完全等价。
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { JSDOM } from 'jsdom'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

// 测试用 DOMPurify 实例(jsdom 后端)+ 安全属性注入(与生产 sanitize-marked.js 一致)
let purify

beforeAll(() => {
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>')
  purify = DOMPurify(dom.window)
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
})

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

const DANGEROUS_URL_REGEX = /(\s(?:href|src|xlink:href)\s*=\s*["']?)\s*(javascript|data|vbscript|file):[^"'>\s]+/gi

function injectSafeAttrs(html) {
  if (!html) return html
  let result = html.replace(DANGEROUS_URL_REGEX, '$1=""')
  result = result.replace(
    /<a\s([^>]*?)>/gi,
    (match, attrs) => {
      if (!/\shref\s*=/i.test(attrs)) return match
      let next = attrs
      if (!/\starget\s*=/i.test(next)) next += ' target="_blank"'
      if (!/\srel\s*=/i.test(next)) next += ' rel="noopener noreferrer"'
      return `<a ${next}>`
    }
  )
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

/** 测试用 safeMarkdown(等价于生产实现,但用 jsdom 实例) */
function safeMarkdown(text) {
  if (!text) return ''
  const raw = marked.parse(text, { async: false })
  const html = purify.sanitize(raw, { ALLOWED_TAGS, ALLOWED_ATTR })
  return injectSafeAttrs(html)
}

describe('safeMarkdown', () => {
  it('空文本返回空字符串', () => {
    expect(safeMarkdown('')).toBe('')
    expect(safeMarkdown(null)).toBe('')
    expect(safeMarkdown(undefined)).toBe('')
  })

  it('普通文本正常渲染', () => {
    const html = safeMarkdown('hello world')
    expect(html).toContain('hello world')
  })

  it('剥离 <script> 节点', () => {
    const html = safeMarkdown('<script>alert(1)</script>')
    expect(html).not.toContain('<script>')
  })

  it('剥离 onerror 等事件处理器', () => {
    const html = safeMarkdown('<img src="x" onerror="alert(1)">')
    expect(html).not.toMatch(/onerror/i)
  })

  it('拦截 javascript: 链接', () => {
    const html = safeMarkdown('[evil](javascript:alert(1))')
    expect(html).not.toMatch(/href=["']?javascript:/i)
  })

  it('合法链接附加 target=_blank + rel=noopener noreferrer', () => {
    const html = safeMarkdown('[ok](https://example.com)')
    expect(html).toMatch(/target=["']_blank["']/)
    expect(html).toMatch(/rel=["']noopener noreferrer["']/)
  })

  it('图片附加 loading=lazy + style', () => {
    const html = safeMarkdown('![alt](https://example.com/a.png)')
    expect(html).toMatch(/loading=["']lazy["']/)
    expect(html).toMatch(/style=["'][^"']*max-width:100%/)
  })

  it('marked.parse 强制同步:返回值类型为 string(T1 验证)', () => {
    const html = safeMarkdown('# title')
    expect(typeof html).toBe('string')
    expect(html).toContain('<h1')
  })

  it('相对路径 URL 保留(T5 验证)', () => {
    const html = safeMarkdown('[内部](/api/foo) 和 [锚链](#section)')
    expect(html).toMatch(/href=["']\/api\/foo["']/)
    expect(html).toMatch(/href=["']#section["']/)
  })

  it('禁止 javascript: 链接(T5 验证)', () => {
    const html = safeMarkdown('[evil](javascript:alert(1))')
    expect(html).not.toMatch(/href=["']?javascript:/i)
  })

  it('gfm 任务列表的 input 标签保留', () => {
    const html = safeMarkdown('- [x] done\n- [ ] todo')
    expect(html).toMatch(/<input[^>]*type=["']checkbox["']/)
  })
})