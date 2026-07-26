/**
 * 触发器注册表（triggerRegistry）
 *
 * 与 commandRegistry（"/" 斜杠命令）平级的另一种"输入触发"体系：以单字符为锚，
 * 在 textarea 中输入该字符触发选择面板，选中项以 chips 形式落到输入区上方，
 * 发送时由 buildOverrides 转换为 context_overrides 片段统一经 chatStream 提交。
 *
 * 设计要点：
 *   1. 通用数据：TRIGGER_REGISTRY 条目声明触发字符、数据源、搜索字段、
 *      去重键、chip 显示、context_overrides 构建函数；
 *   2. 可扩展：未来新增触发类型（如 "@" 知识库）只需在此追加一条 + 提供数据源，
 *      InputBox.vue / TriggerPanel.vue / api.js 无需改动；
 *   3. 前端数据源已是用户权限范围（fetchUserServerTree 已按 OwnershipScope 过滤），
 *      后端 sanitize_dynamic_nodes 不做归属校验，仅做白名单字段过滤。
 */

import { fetchUserServerTree } from './api.js'

/**
 * 拉取「服务器」触发器所需的候选项：
 * 调 GET /api/admin/user-servers/tree → 取 resp.nodes → 仅保留 node_type='server'。
 * 后端返回 { nodes: [...] }；若旧接口直接返回数组也做兼容兜底。
 *
 * @returns {Promise<Array<{business_name: string, server_type: string, ...}>>}
 *          服务端用户权限内的服务器节点列表
 */
async function fetchServerItems() {
  const resp = await fetchUserServerTree()
  // 后端 GET /api/admin/user-servers/tree 返回 { nodes: [...] }
  const nodes = resp?.nodes ?? resp
  if (!Array.isArray(nodes)) return []
  return nodes.filter((n) => n && n.node_type === 'server')
}

/**
 * 按业务名去重（保持首次出现顺序）。
 *
 * @param {Array} items - 候选项数组
 * @returns {Array} 去重后数组
 */
function dedupByBusinessName(items) {
  const seen = new Set()
  const result = []
  for (const item of items) {
    const key = item?.business_name
    if (!key || seen.has(key)) continue
    seen.add(key)
    result.push(item)
  }
  return result
}

/**
 * TRIGGER_REGISTRY：触发器注册表。
 *
 * 每条定义：
 *   id:           唯一标识
 *   char:         触发字符
 *   title:        按钮 tooltip / 面板标题
 *   fetchItems:   异步拉取候选项（fetchUserServerTree 等）
 *   searchKeys:   面板搜索时匹配的字段集合（OR 匹配，case-insensitive）
 *   itemKey:      去重键（已选 + 候选）
 *   chipLabel:    chip 显示文本（取自 item）
 *   buildOverrides: 选中项数组 → context_overrides 片段（与后端 DYNAMIC_NODE_REGISTRY 镜像）
 *
 * 未来新增触发类型：在此数组追加一条；后端 dynamic_context.DYNAMIC_NODE_REGISTRY
 * 追加一条 DynamicNodeSpec。两侧键名（buildOverrides 输出键）必须一致。
 */
export const TRIGGER_REGISTRY = [
  {
    id: 'server',
    char: '#',
    title: '引用服务器',
    mentionLabel: '引用服务器',
    mentionClass: 'mention-server',
    fetchItems: async () => dedupByBusinessName(await fetchServerItems()),
    searchKeys: ['business_name', 'server_type'],
    itemKey: (item) => item?.business_name,
    chipLabel: (item) => item?.business_name,
    buildOverrides: (items) => ({
      referenced_servers: items.map((i) => ({
        name: i.business_name,
        server_type: i.server_type,
      })),
    }),
  },
]

const _registryByChar = new Map(TRIGGER_REGISTRY.map((t) => [t.char, t]))

/**
 * 按触发字符查找注册条目。
 *
 * @param {string} char - 触发字符
 * @returns {Object|undefined} 注册条目；未注册时返回 undefined
 */
export function searchTriggerByChar(char) {
  return _registryByChar.get(char)
}

/**
 * 按 id 查找注册条目。
 *
 * @param {string} id - 注册 id
 * @returns {Object|undefined} 注册条目
 */
export function searchTriggerById(id) {
  return TRIGGER_REGISTRY.find((t) => t.id === id)
}

/**
 * 把当前选中项经对应 trigger 的 buildOverrides 转换为 context_overrides 片段。
 *
 * @param {string} triggerId - trigger 注册 id
 * @param {Array} items - 当前选中项
 * @returns {Object} context_overrides 片段；未注册 id 返回空对象
 */
export function buildOverridesFor(triggerId, items) {
  const trigger = searchTriggerById(triggerId)
  if (!trigger || !Array.isArray(items) || items.length === 0) return {}
  return trigger.buildOverrides(items) || {}
}

/**
 * 转义 HTML 特殊字符，防止用户输入破坏页面结构。
 *
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
function escapeHtml(str) {
  if (typeof str !== 'string') return String(str)
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 为正则字面量转义特殊字符。
 *
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
function escapeRegExp(str) {
  if (typeof str !== 'string') return String(str)
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 将文本中的 trigger mention 标记统一渲染为样式化 HTML。
 *
 * 匹配格式：⟦{mentionLabel}：value1、value2⟧
 * 每个 value 渲染为一个 .mention-chip；整个标记包裹在 .mention-block 中。
 * 未来新增 trigger 时，只要补充 mentionLabel/mentionClass 即可自动获得渲染。
 *
 * @param {string} text - 原始文本
 * @param {Object} options - 配置项
 * @param {boolean} [options.escapeHtml=false] - 是否对非标记文本做 HTML 转义（用户消息建议 true）
 * @returns {string} 渲染后的 HTML 字符串；无标记时原样返回文本
 */
export function renderTriggerMentions(text, options = {}) {
  const { escapeHtml: shouldEscape = false } = options
  if (!text) return ''

  // 收集所有可能匹配 mention 的 trigger（要求定义了 mentionLabel）
  const triggers = TRIGGER_REGISTRY.filter((t) => t.mentionLabel)
  if (triggers.length === 0) return text

  // 收集所有匹配位置，并按起始索引排序
  const matches = []
  for (const trigger of triggers) {
    const regex = new RegExp(
      `⟦${escapeRegExp(trigger.mentionLabel)}：([^⟧]+)⟧`,
      'g'
    )
    let match
    while ((match = regex.exec(text)) !== null) {
      matches.push({
        index: match.index,
        end: match.index + match[0].length,
        values: match[1],
        trigger,
      })
    }
  }

  // 按位置排序；重叠时保留先出现者
  matches.sort((a, b) => a.index - b.index)

  const fragments = []
  let lastIndex = 0
  for (const m of matches) {
    if (m.index < lastIndex) continue
    // 非标记文本
    if (m.index > lastIndex) {
      const raw = text.slice(lastIndex, m.index)
      fragments.push(shouldEscape ? escapeHtml(raw) : raw)
    }
    // mention 块：按 、拆分多个值
    const values = m.values
      .split(/、/)
      .map((v) => v.trim())
      .filter(Boolean)
    const chips = values
      .map((v) => {
        const safeValue = escapeHtml(v)
        return `<span class="mention-chip ${m.trigger.mentionClass}"><span class="mention-char">${m.trigger.char}</span><span class="mention-value">${safeValue}</span></span>`
      })
      .join('')
    fragments.push(
      `<span class="mention-block ${m.trigger.mentionClass}" title="${escapeHtml(m.trigger.title)}">${chips}</span>`
    )
    lastIndex = m.end
  }

  // 尾部非标记文本
  if (lastIndex < text.length) {
    const raw = text.slice(lastIndex)
    fragments.push(shouldEscape ? escapeHtml(raw) : raw)
  }

  return fragments.join('')
}