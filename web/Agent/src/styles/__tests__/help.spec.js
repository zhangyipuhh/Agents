/**
 * help.css 防回归测试
 *
 * 通过源码静态扫描验证关键 CSS 类存在（防止后续误删或被覆盖）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const cssPath = resolve(__dirname, '../help.css')
let cssContent = ''
try {
  cssContent = readFileSync(cssPath, 'utf-8')
} catch (e) {
  // 文件不存在时让下方断言失败
  cssContent = ''
}

describe('help.css 内容完整性', () => {
  it('CSS 文件存在且非空', () => {
    expect(cssContent).not.toBe('')
    expect(cssContent.length).toBeGreaterThan(100)
  })

  it('含关键类名 .help-root（layout 容器）', () => {
    expect(cssContent).toMatch(/\.help-root\s*\{/)
  })

  it('含 .help-topbar（顶部品牌栏）', () => {
    expect(cssContent).toMatch(/\.help-topbar\s*\{/)
  })

  it('含 .help-sidebar（左侧目录）', () => {
    expect(cssContent).toMatch(/\.help-sidebar\s*\{/)
  })

  it('含 .help-toc（右侧 anchor）', () => {
    expect(cssContent).toMatch(/\.help-toc\s*\{/)
  })

  it('含 .help-content（中部内容区）', () => {
    expect(cssContent).toMatch(/\.help-content\s*\{/)
  })

  it('含 .help-article（markdown 容器）', () => {
    expect(cssContent).toMatch(/\.help-article\s*\{/)
  })

  it('含响应式断点（@media）', () => {
    expect(cssContent).toMatch(/@media/)
  })

  it('含政务蓝强调色（#1e5cff）', () => {
    expect(cssContent).toContain('#1e5cff')
  })

  it('无全局裸标签选择器（防止污染主应用）', () => {
    // 禁止出现 `body {` 或 `html {` 这类全局选择器
    expect(cssContent).not.toMatch(/^\s*body\s*\{/m)
    expect(cssContent).not.toMatch(/^\s*html\s*\{/m)
  })
})