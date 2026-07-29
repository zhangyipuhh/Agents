// -*- coding:utf-8 -*-
/**
 * 定时任务 context_overrides 参数编辑器工具
 *
 * 负责把后端存储的 ``context_overrides`` 字典与前端可编辑的「参数行」互相转换，
 * 同时把 ``reference_server`` 特殊参数与后端契约 ``referenced_servers`` 对齐。
 *
 * 设计要点：
 *   - 参数行采用 ``{ name, type, value, source }`` 形式，``source`` 标识值来源
 *     （``reference_server`` / ``user`` / ``unknown``）；
 *   - 转换过程对未知字段做无损保留（旧 ``context_overrides`` 中非标量也支持）；
 *   - ``reference_server`` 行的值以 ``referenced_servers`` 元素结构
 *     （``{name, server_type}``）存储，序列化时再回填到 ``context_overrides.referenced_servers``；
 *   - 单独导出 ``parseContextOverrides`` / ``serializeContextOverrides`` 便于单测覆盖。
 *
 * Date: 2026-07-29
 * Author: AI Assistant
 */

/**
 * 推断值的 JSON Schema 类型。
 * 仅识别 ``str`` / ``int`` / ``float`` / ``bool`` / ``list`` / ``dict`` 六种；
 * 不可识别类型回退为 ``str``，避免丢字段。
 * @param {unknown} value - 任意 JS 值
 * @returns {string} 类型名
 */
export function inferValueType(value) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? 'int' : 'float'
  }
  if (typeof value === 'boolean') return 'bool'
  if (Array.isArray(value)) return 'list'
  if (value && typeof value === 'object') return 'dict'
  return 'str'
}

/**
 * 把任意 JS 值按目标类型回填为可控的 JS 值。
 * 不抛错；类型不匹配时回退为该类型的零值。
 * @param {unknown} value - 原始值
 * @param {string} type - 目标类型（``str``/``int``/``float``/``bool``/``list``/``dict``）
 * @returns {unknown} 回填后的值
 */
export function coerceValueByType(value, type) {
  if (type === 'str') {
    if (value === null || value === undefined) return ''
    return String(value)
  }
  if (type === 'int') {
    const n = Number(value)
    if (!Number.isFinite(n)) return 0
    return Math.trunc(n)
  }
  if (type === 'float') {
    const n = Number(value)
    return Number.isFinite(n) ? n : 0
  }
  if (type === 'bool') {
    if (typeof value === 'boolean') return value
    if (typeof value === 'string') {
      const lower = value.trim().toLowerCase()
      if (lower === 'true' || lower === '1') return true
      if (lower === 'false' || lower === '0' || lower === '') return false
    }
    return Boolean(value)
  }
  if (type === 'list') return Array.isArray(value) ? value.slice() : []
  if (type === 'dict') {
    return value && typeof value === 'object' && !Array.isArray(value) ? { ...value } : {}
  }
  return value
}

/**
 * 把 ``referenced_servers`` 元素归一化为 ``{name, server_type}``。
 * 跳过缺 name 或 name 非字符串的元素；``server_type`` 缺省为 ``''``。
 * @param {unknown} value - 原始 ``referenced_servers`` 元素
 * @returns {{name: string, server_type: string} | null} 归一化结果
 */
function normalizeServerRefItem(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const name = value.name
  if (typeof name !== 'string' || !name.trim()) return null
  const serverTypeRaw = value.server_type
  const serverType = typeof serverTypeRaw === 'string' ? serverTypeRaw : ''
  return { name: name.trim(), server_type: serverType }
}

/**
 * 解析后端 ``context_overrides`` 为参数行 + 未知字段。
 *
 * 规则：
 *   - ``referenced_servers``（数组）→「reference_server」行（值为元素数组，元素结构 ``{name, server_type}``）；
 *     缺 name 或非对象元素静默丢弃；非数组值整体忽略。
 *   - 标量 / 数组 / 字典按 ``inferValueType`` 转成行；
 *   - 标量 / 数组之外的兼容字段（极少）保留为 unknown 字段。
 *
 * @param {unknown} raw - 后端存储的 ``context_overrides``（可能为 null / undefined）
 * @returns {{parameterRows: Array<{name: string, type: string, value: unknown, source: string}>, unknownOverrides: Object}}
 */
export function parseContextOverrides(raw) {
  const result = { parameterRows: [], unknownOverrides: {} }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return result
  for (const key of Object.keys(raw)) {
    const value = raw[key]
    if (key === 'referenced_servers') {
      if (!Array.isArray(value)) continue
      const items = []
      for (const item of value) {
        const normalized = normalizeServerRefItem(item)
        if (normalized) items.push(normalized)
      }
      result.parameterRows.push({
        name: 'reference_server',
        type: 'list',
        value: items,
        source: 'reference_server',
      })
      continue
    }
    const type = inferValueType(value)
    if (type === 'str' || type === 'int' || type === 'float' || type === 'bool'
        || type === 'list' || type === 'dict') {
      result.parameterRows.push({ name: key, type, value, source: 'user' })
    } else {
      result.unknownOverrides[key] = value
    }
  }
  return result
}

/**
 * 把参数行 + 未知字段回填为后端 ``context_overrides`` 字典。
 *
 * 规则：
 *   - ``reference_server`` 行 → ``referenced_servers``（元素 ``{name, server_type}``），值为空数组时省略；
 *   - ``reference_server`` 行外的行：按 type 强制 ``coerceValueByType``，key 重名后者覆盖前者；
 *   - 未知字段保留原样合并到结果；
 *   - 输出对象不引用入参（已深拷贝 list / dict，标量也重写），避免 Vue 响应式污染。
 *
 * @param {Array<{name: string, type: string, value: unknown, source?: string}>} parameterRows - 参数行
 * @param {Object} unknownOverrides - 未知字段（按字段原样保留）
 * @returns {Object} 后端 ``context_overrides`` 字典
 */
export function serializeContextOverrides(parameterRows, unknownOverrides = {}) {
  const out = {}
  const rows = Array.isArray(parameterRows) ? parameterRows : []
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue
    const name = typeof row.name === 'string' ? row.name.trim() : ''
    if (!name) continue
    if (name === 'reference_server') {
      const value = Array.isArray(row.value) ? row.value : []
      const items = []
      for (const item of value) {
        const normalized = normalizeServerRefItem(item)
        if (normalized) items.push(normalized)
      }
      if (items.length) out.referenced_servers = items
      continue
    }
    const coerced = coerceValueByType(row.value, row.type)
    if (row.type === 'list' || row.type === 'dict') {
      out[name] = Array.isArray(coerced) ? coerced.slice() : { ...coerced }
    } else {
      out[name] = coerced
    }
  }
  for (const [k, v] of Object.entries(unknownOverrides || {})) {
    if (!Object.prototype.hasOwnProperty.call(out, k)) {
      out[k] = v
    }
  }
  return out
}

/**
 * 给「添加参数」选择器返回一组参数模板。
 * ``reference_server`` 永远排在最前（特殊参数）；其余按字母序。
 * @returns {Array<{name: string, type: string, label: string, isServerRef: boolean}>}
 */
export function listContextParameterTemplates() {
  return [
    {
      name: 'reference_server',
      type: 'list',
      label: '引用服务器（会话注入）',
      isServerRef: true,
    },
    { name: 'max_tokens', type: 'int', label: '最大 token', isServerRef: false },
    { name: 'temperature', type: 'float', label: '采样温度', isServerRef: false },
    { name: 'verbose', type: 'bool', label: '详细输出', isServerRef: false },
    { name: 'tags', type: 'list', label: '标签列表', isServerRef: false },
    { name: 'note', type: 'str', label: '备注', isServerRef: false },
  ]
}
