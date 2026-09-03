/**
 * 帮助文档加载器单元测试
 *
 * 覆盖：
 *   1. normalizePath：去除前导斜杠 / 尾部斜杠 / 空值 / ../ 防护
 *   2. getDocUrl：自动补 .md 后缀
 *   3. extractHeadings：提取 h2/h3（避开代码块）
 *   4. slugifyHeading：中英混合 + 标点去除
 *   5. loadIndex / loadDoc：fetch + 缓存
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  normalizePath,
  getDocUrl,
  extractHeadings,
  slugifyHeading,
  loadIndex,
  loadDoc,
  clearHelpCache,
  getIndexUrl,
} from '../help-loader.js'

describe('help-loader 工具', () => {
  describe('normalizePath', () => {
    it('去除前导斜杠', () => {
      expect(normalizePath('/overview')).toBe('overview')
    })
    it('去除尾部斜杠', () => {
      expect(normalizePath('overview/')).toBe('overview')
    })
    it('去除前后斜杠', () => {
      expect(normalizePath('/features/chat/')).toBe('features/chat')
    })
    it('空值/非字符串 → 默认 overview', () => {
      expect(normalizePath('')).toBe('overview')
      expect(normalizePath(null)).toBe('overview')
      expect(normalizePath(undefined)).toBe('overview')
      expect(normalizePath(123)).toBe('overview')
    })
    it('包含 ../ 路径遍历 → 回退 overview', () => {
      expect(normalizePath('../../../etc/passwd')).toBe('overview')
      expect(normalizePath('overview/../passwd')).toBe('overview')
    })
    it('首尾空白去除', () => {
      expect(normalizePath('  overview  ')).toBe('overview')
    })
  })

  describe('getDocUrl', () => {
    it('自动补 .md 后缀', () => {
      expect(getDocUrl('overview')).toBe('/help/overview.md')
    })
    it('嵌套路径 + 规范化', () => {
      expect(getDocUrl('/features/chat/')).toBe('/help/features/chat.md')
    })
    it('空值 → /help/overview.md', () => {
      expect(getDocUrl('')).toBe('/help/overview.md')
    })
  })

  describe('getIndexUrl', () => {
    it('返回固定路径 /help/index.json', () => {
      expect(getIndexUrl()).toBe('/help/index.json')
    })
  })

  describe('slugifyHeading', () => {
    it('英文转小写 + 空格转 -', () => {
      expect(slugifyHeading('Hello World')).toBe('hello-world')
    })
    it('保留中文', () => {
      expect(slugifyHeading('登录问题')).toBe('登录问题')
    })
    it('去除标点', () => {
      expect(slugifyHeading('Section 1: 介绍!')).toBe('section-1-介绍')
    })
    it('空值/非字符串 → 空字符串', () => {
      expect(slugifyHeading('')).toBe('')
      expect(slugifyHeading(null)).toBe('')
    })
  })

  describe('extractHeadings', () => {
    it('提取 h2/h3 headings', () => {
      const md = `# 一级标题（跳过）
## 二级标题 A
### 三级标题 A1
## 二级标题 B
`
      const headings = extractHeadings(md)
      expect(headings).toEqual([
        { level: 2, text: '二级标题 A', id: '二级标题-a' },
        { level: 3, text: '三级标题 A1', id: '三级标题-a1' },
        { level: 2, text: '二级标题 B', id: '二级标题-b' },
      ])
    })
    it('跳过 fenced code block 内的 # 行', () => {
      const md = `
## 真标题
\`\`\`
## 这是代码不是标题
\`\`\`
## 又一真标题
`
      const headings = extractHeadings(md)
      expect(headings).toHaveLength(2)
      expect(headings[0].text).toBe('真标题')
      expect(headings[1].text).toBe('又一真标题')
    })
    it('空字符串/非字符串 → 空数组', () => {
      expect(extractHeadings('')).toEqual([])
      expect(extractHeadings(null)).toEqual([])
      expect(extractHeadings(undefined)).toEqual([])
    })
  })

  describe('loadIndex / loadDoc', () => {
    beforeEach(() => {
      clearHelpCache()
      vi.restoreAllMocks()
    })

    it('loadIndex: fetch index.json + 缓存命中', async () => {
      const data = { title: '帮助中心', tree: [{ title: '概述', path: 'overview' }] }
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => data,
      })

      const r1 = await loadIndex()
      expect(r1).toEqual(data)
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock).toHaveBeenCalledWith('/help/index.json')

      // 第二次调用应走缓存
      const r2 = await loadIndex()
      expect(r2).toEqual(data)
      expect(fetchMock).toHaveBeenCalledTimes(1) // 仍是 1
    })

    it('loadIndex: 非 2xx 抛 Error', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        status: 500,
      })
      await expect(loadIndex()).rejects.toThrow(/HTTP 500/)
    })

    it('loadIndex: 非法 JSON 结构（缺 tree）抛 Error', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ title: 'no tree' }),
      })
      await expect(loadIndex()).rejects.toThrow(/缺少 tree 数组/)
    })

    it('loadDoc: fetch .md + 缓存命中', async () => {
      const md = '# overview\n## 一级章节'
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => md,
      })

      const r1 = await loadDoc('overview')
      expect(r1).toBe(md)
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock).toHaveBeenCalledWith('/help/overview.md')

      const r2 = await loadDoc('overview')
      expect(r2).toBe(md)
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('loadDoc: 404 抛 Error（含路径信息）', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        status: 404,
      })
      await expect(loadDoc('not-exist')).rejects.toThrow(/HTTP 404/)
    })

    it('loadDoc: 路径 ../ 防护 → 实际请求 /help/overview.md', async () => {
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => '# fallback',
      })
      await loadDoc('../../../etc/passwd')
      expect(fetchMock).toHaveBeenCalledWith('/help/overview.md')
    })

    it('clearHelpCache: 清空缓存后续请求重发', async () => {
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ tree: [] }),
        text: async () => '# t',
      })
      await loadIndex()
      expect(fetchMock).toHaveBeenCalledTimes(1)
      clearHelpCache()
      await loadIndex()
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
  })
})