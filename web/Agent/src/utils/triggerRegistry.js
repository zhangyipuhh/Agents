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
 * 调 GET /api/admin/user-servers/tree → 拍平 nodes → 仅保留 node_type='server'。
 *
 * @returns {Promise<Array<{business_name: string, server_type: string, ...}>>}
 *          服务端用户权限内的服务器节点列表
 */
async function fetchServerItems() {
  const tree = await fetchUserServerTree()
  if (!Array.isArray(tree)) return []
  return tree.filter((n) => n && n.node_type === 'server')
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