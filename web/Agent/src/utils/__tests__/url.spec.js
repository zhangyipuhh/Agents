// -*- coding:utf-8 -*-
/**
 * utils/url.js 单元测试
 *
 * 覆盖：
 * - appendQueryParam 在纯路径 / 带 search / 带 hash / 已有同名 key 等场景下的行为
 * - readQueryParam 的安全性与异常处理
 *
 * 设计原则：appendQueryParam 是退出登录场景下传递 theme 的核心链路；
 * 测试要覆盖正常路径、边界路径（hash 单独存在 / 仅 hash 等），防止 URL 解析细节回归。
 */
import { describe, it, expect } from 'vitest'
import { appendQueryParam, readQueryParam } from '../url.js'

describe('utils/url.js', () => {
  describe('appendQueryParam', () => {
    it('test_append_to_plain_path 纯路径追加 query', () => {
      expect(appendQueryParam('/login', 'theme', 'shenyang')).toBe('/login?theme=shenyang')
    })

    it('test_append_preserves_existing_search 已存在 search 时追加新参数', () => {
      expect(appendQueryParam('/portal?key=val', 'theme', 'xemployee')).toBe('/portal?key=val&theme=xemployee')
    })

    it('test_append_overrides_existing_same_key 同名 key 覆盖而非追加', () => {
      // 同名 key 必须覆盖，避免出现 ?theme=a&theme=b 双值歧义
      expect(appendQueryParam('/login?theme=old', 'theme', 'new')).toBe('/login?theme=new')
    })

    it('test_append_preserves_hash 保留 URL hash 段', () => {
      expect(appendQueryParam('/login#section', 'theme', 'shenyang')).toBe('/login?theme=shenyang#section')
    })

    it('test_append_with_search_and_hash 同时保留 search 与 hash', () => {
      const result = appendQueryParam('/login?x=1#top', 'theme', 'xemployee')
      expect(result).toContain('theme=xemployee')
      expect(result).toContain('x=1')
      expect(result.endsWith('#top')).toBe(true)
    })

    it('test_append_with_empty_search 已有 ? 但无参数时正确处理', () => {
      expect(appendQueryParam('/login?', 'theme', 'shenyang')).toBe('/login?theme=shenyang')
    })

    it('test_append_encodes_special_chars value 中的特殊字符会被 URLSearchParams 编码', () => {
      // space → '+' 是 URLSearchParams 的行为
      const out = appendQueryParam('/login', 'q', 'a b')
      expect(out).toBe('/login?q=a+b')
    })

    it('test_append_invalid_input_returns_empty 非字符串输入返回空串（不抛错）', () => {
      expect(appendQueryParam(undefined, 'theme', 'x')).toBe('')
      expect(appendQueryParam(null, 'theme', 'x')).toBe('')
      expect(appendQueryParam(123, 'theme', 'x')).toBe('')
    })
  })

  describe('readQueryParam', () => {
    it('test_read_existing_param 读取已存在的 query', () => {
      expect(readQueryParam('/login?theme=shenyang', 'theme')).toBe('shenyang')
    })

    it('test_read_missing_param 返回 null', () => {
      expect(readQueryParam('/login', 'theme')).toBeNull()
      expect(readQueryParam('/login?other=x', 'theme')).toBeNull()
    })

    it('test_read_handles_hash_only URL 仅有 hash 时不抛错', () => {
      expect(readQueryParam('/login#top', 'theme')).toBeNull()
    })

    it('test_read_invalid_input_returns_null 非字符串输入返回 null', () => {
      expect(readQueryParam(undefined, 'theme')).toBeNull()
      expect(readQueryParam(null, 'theme')).toBeNull()
    })
  })
})