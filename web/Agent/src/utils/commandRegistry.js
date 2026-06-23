/**
 * 命令注册表模块
 *
 * 提供 /agent <name>（切换智能体）与 /agents（列出可用智能体）两个斜杠命令。
 * InputBox.vue 检测到 / 开头时调用 handleCommand。
 */
import { fetchAgentList } from './api.js'

/**
 * 命令注册表
 * @type {Array<{name: string, description: string, usage: string, requiresBackend: boolean}>}
 */
export const COMMAND_REGISTRY = [
  {
    name: 'agent',
    description: '切换智能体',
    usage: '/agent <name>',
    requiresBackend: true, // 预留字段：用于未来离线模式跳过后端调用
  },
  {
    name: 'agents',
    description: '列出可用智能体',
    usage: '/agents',
    requiresBackend: true, // 预留字段：用于未来离线模式跳过后端调用
  },
]

/**
 * 处理命令
 * @param {string} command - 命令名（不含 /）
 * @param {string[]} args - 参数数组
 * @returns {Promise<{text: string, switchAgent?: string}>} 响应对象，包含文本提示与可选的切换目标
 * @throws {Error} 当 fetchAgentList 网络请求失败时抛出，调用方需捕获并展示友好提示
 */
export async function handleCommand(command, args) {
  if (command === 'agents') {
    const text = await listAgentsCommand()
    return { text }
  }
  if (command === 'agent') {
    if (args.length === 0) {
      return { text: '用法：/agent <name>\n\n使用 /agents 查看可用智能体列表' }
    }
    const targetAgent = args[0]
    const agents = await fetchAgentList()
    const found = agents.find((a) => a.name === targetAgent)
    if (!found) {
      const available = agents
        .map((a) => `${a.name}（${a.display_name}）`)
        .join('\n')
      return {
        text: `智能体 '${targetAgent}' 不存在。\n\n可用：\n${available}`,
      }
    }
    return {
      text: `已切换到智能体：${found.display_name}`,
      switchAgent: targetAgent,
    }
  }
  return { text: `未知命令：/${command}` }
}

/**
 * 处理 /agents 命令，列出所有智能体
 * @returns {Promise<string>} 智能体列表文本
 * @throws {Error} 当后端 fetchAgentList 请求失败时抛出
 */
export async function listAgentsCommand() {
  const agents = await fetchAgentList()
  if (agents.length === 0) {
    return '暂无可用智能体'
  }
  return '可用智能体：\n' + agents
    .map((a) => `- ${a.name}（${a.display_name}）`)
    .join('\n')
}
