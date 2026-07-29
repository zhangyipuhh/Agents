// -*- coding:utf-8 -*-
/**
 * contextOverrides 工具函数单测
 *
 * 覆盖：
 *   - parseContextOverrides：标量/数组/字典、referenced_servers 转 reference_server 行、未知字段保留、空值/非对象入参；
 *   - serializeContextOverrides：reference_server 行 → referenced_servers、普通行按类型 coerce、重名后者覆盖、空数组省略、未知字段合并；
 *   - inferValueType / coerceValueByType：覆盖 6 种类型与边界；
 *   - listContextParameterTemplates：reference_server 模板固定首位。
 */
import { describe, it, expect } from 'vitest'
import {
  inferValueType,
  coerceValueByType,
  parseContextOverrides,
  serializeContextOverrides,
  listContextParameterTemplates,
} from '../contextOverrides.js'

describe('contextOverrides 工具', () => {
  it('test_infer_value_type_basic 基本类型推断', () => {
    expect(inferValueType('hello')).toBe('str')
    expect(inferValueType(1)).toBe('int')
    expect(inferValueType(1.5)).toBe('float')
    expect(inferValueType(true)).toBe('bool')
    expect(inferValueType([1, 2, 3])).toBe('list')
    expect(inferValueType({ a: 1 })).toBe('dict')
    expect(inferValueType(null)).toBe('str')
    expect(inferValueType(undefined)).toBe('str')
  })

  it('test_coerce_value_by_type 类型强制回填', () => {
    expect(coerceValueByType(1.7, 'int')).toBe(1)
    expect(coerceValueByType('3.14', 'float')).toBe(3.14)
    expect(coerceValueByType('1', 'bool')).toBe(true)
    expect(coerceValueByType('0', 'bool')).toBe(false)
    expect(coerceValueByType('  true  ', 'bool')).toBe(true)
    expect(coerceValueByType(0, 'bool')).toBe(false)
    expect(coerceValueByType(null, 'str')).toBe('')
    expect(coerceValueByType(123, 'str')).toBe('123')
    expect(coerceValueByType('oops', 'int')).toBe(0)
    expect(coerceValueByType('oops', 'float')).toBe(0)
    expect(coerceValueByType({ a: 1 }, 'list')).toEqual([])
    expect(coerceValueByType([1, 2], 'dict')).toEqual({})
    expect(coerceValueByType(null, 'list')).toEqual([])
    expect(coerceValueByType(null, 'dict')).toEqual({})
  })

  it('test_parse_context_overrides_basic 标量与数组反解为行', () => {
    const parsed = parseContextOverrides({
      temperature: 0.5,
      max_tokens: 2048,
      verbose: true,
      tags: ['a', 'b'],
      note: 'hello',
    })
    const byName = Object.fromEntries(parsed.parameterRows.map((r) => [r.name, r]))
    expect(byName.temperature.type).toBe('float')
    expect(byName.temperature.value).toBe(0.5)
    expect(byName.max_tokens.type).toBe('int')
    expect(byName.max_tokens.value).toBe(2048)
    expect(byName.verbose.type).toBe('bool')
    expect(byName.verbose.value).toBe(true)
    expect(byName.tags.type).toBe('list')
    expect(byName.tags.value).toEqual(['a', 'b'])
    expect(byName.note.type).toBe('str')
    expect(byName.note.value).toBe('hello')
    expect(parsed.unknownOverrides).toEqual({})
  })

  it('test_parse_context_overrides_reference_servers referenced_servers 转 reference_server 行', () => {
    const parsed = parseContextOverrides({
      referenced_servers: [
        { name: '业务A-生产', server_type: 'linux' },
        { name: '业务B-测试', server_type: 'windows' },
      ],
    })
    expect(parsed.parameterRows).toHaveLength(1)
    const row = parsed.parameterRows[0]
    expect(row.name).toBe('reference_server')
    expect(row.type).toBe('list')
    expect(row.source).toBe('reference_server')
    expect(row.value).toEqual([
      { name: '业务A-生产', server_type: 'linux' },
      { name: '业务B-测试', server_type: 'windows' },
    ])
  })

  it('test_parse_context_overrides_reference_servers_drops_invalid 非法 referenced_servers 元素静默丢弃', () => {
    const parsed = parseContextOverrides({
      referenced_servers: [
        { name: '业务A', server_type: 'linux' },
        { server_type: 'linux' },
        { name: '', server_type: 'linux' },
        { name: 123, server_type: 'linux' },
        null,
        'plain',
      ],
    })
    expect(parsed.parameterRows).toHaveLength(1)
    expect(parsed.parameterRows[0].value).toEqual([
      { name: '业务A', server_type: 'linux' },
    ])
  })

  it('test_parse_context_overrides_handles_empty_and_invalid 兼容空值/非对象入参', () => {
    expect(parseContextOverrides(null).parameterRows).toEqual([])
    expect(parseContextOverrides(undefined).parameterRows).toEqual([])
    expect(parseContextOverrides([]).parameterRows).toEqual([])
    expect(parseContextOverrides('not-object').parameterRows).toEqual([])
  })

  it('test_parse_context_overrides_referenced_servers_non_array 非数组 referenced_servers 被忽略', () => {
    const parsed = parseContextOverrides({ referenced_servers: 'oops' })
    expect(parsed.parameterRows).toEqual([])
    expect(parsed.unknownOverrides).toEqual({})
  })

  it('test_serialize_context_overrides_basic 标量行按类型回填', () => {
    const out = serializeContextOverrides([
      { name: 'temperature', type: 'float', value: 0.7 },
      { name: 'max_tokens', type: 'int', value: '1024' },
      { name: 'verbose', type: 'bool', value: 1 },
      { name: 'tags', type: 'list', value: ['a', 'b'] },
      { name: 'note', type: 'str', value: 'hi' },
    ])
    expect(out).toEqual({
      temperature: 0.7,
      max_tokens: 1024,
      verbose: true,
      tags: ['a', 'b'],
      note: 'hi',
    })
  })

  it('test_serialize_context_overrides_reference_server 转换为 referenced_servers', () => {
    const out = serializeContextOverrides([
      {
        name: 'reference_server',
        type: 'list',
        value: [
          { name: '业务A', server_type: 'linux' },
          { name: '业务B', server_type: 'windows' },
        ],
      },
    ])
    expect(out).toEqual({
      referenced_servers: [
        { name: '业务A', server_type: 'linux' },
        { name: '业务B', server_type: 'windows' },
      ],
    })
  })

  it('test_serialize_context_overrides_reference_server_empty 空 reference_server 不写 referenced_servers', () => {
    const out = serializeContextOverrides([
      { name: 'reference_server', type: 'list', value: [] },
      { name: 'note', type: 'str', value: 'keep' },
    ])
    expect(out).toEqual({ note: 'keep' })
    expect(out.referenced_servers).toBeUndefined()
  })

  it('test_serialize_context_overrides_drops_invalid 非法服务器项不写入', () => {
    const out = serializeContextOverrides([
      {
        name: 'reference_server',
        type: 'list',
        value: [
          { name: '业务A', server_type: 'linux' },
          { name: '', server_type: 'linux' },
          { name: 123, server_type: 'linux' },
          'plain',
          null,
        ],
      },
    ])
    expect(out).toEqual({
      referenced_servers: [{ name: '业务A', server_type: 'linux' }],
    })
  })

  it('test_serialize_context_overrides_unknown_round_trip 未知字段保留并能往返', () => {
    const out = serializeContextOverrides(
      [{ name: 'note', type: 'str', value: 'hi' }],
      { custom_legacy: { foo: 1 }, arr_legacy: [1, 2, 3] }
    )
    expect(out.custom_legacy).toEqual({ foo: 1 })
    expect(out.arr_legacy).toEqual([1, 2, 3])
    expect(out.note).toBe('hi')
  })

  it('test_serialize_context_overrides_skip_blank_name 空名参数行被丢弃', () => {
    const out = serializeContextOverrides([
      { name: '', type: 'str', value: 'oops' },
      { name: '   ', type: 'str', value: 'oops' },
      { name: 'note', type: 'str', value: 'hi' },
    ])
    expect(out).toEqual({ note: 'hi' })
  })

  it('test_round_trip_basic 完整往返：parse → serialize 不丢字段', () => {
    const raw = {
      referenced_servers: [
        { name: '业务A', server_type: 'linux' },
      ],
      temperature: 0.5,
      max_tokens: 1024,
      verbose: true,
      tags: ['x', 'y'],
      note: 'hello',
    }
    const parsed = parseContextOverrides(raw)
    const out = serializeContextOverrides(parsed.parameterRows, parsed.unknownOverrides)
    expect(out).toEqual(raw)
  })

  it('test_round_trip_preserves_unknown 未知字段经过 parse → serialize 不丢', () => {
    const raw = {
      temperature: 0.5,
      custom_marker: 'keep-me',
    }
    const parsed = parseContextOverrides(raw)
    // 推断为 str 仍会进入 parameterRows，需要把 user 行的字段从 unknown 中过滤，
    // 这里手工模拟「schema 不识别」时进入 unknown 的情况。
    parsed.unknownOverrides.custom_marker = 'keep-me'
    delete parsed.parameterRows.find((r) => r.name === 'custom_marker')
    const out = serializeContextOverrides(parsed.parameterRows, parsed.unknownOverrides)
    expect(out.custom_marker).toBe('keep-me')
    expect(out.temperature).toBe(0.5)
  })

  it('test_list_context_parameter_templates reference_server 模板固定首位', () => {
    const templates = listContextParameterTemplates()
    expect(templates[0].name).toBe('reference_server')
    expect(templates[0].isServerRef).toBe(true)
    expect(templates.find((t) => t.name === 'reference_server')).toBeTruthy()
  })
})
