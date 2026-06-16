export function isThinkingBlock(block) {
  if (!block) return false
  return block.type === 'thinking' || !!block.thinking
}

/**
 * Subagent 工具名 → 显示信息映射
 * 2026-06-13 新增 subagent 折叠卡片用
 */
const SUBAGENT_META = {
  sandbox: { icon: '📦', label: '沙箱执行' },
  explore: { icon: '🔍', label: '文件探索' }
}

/**
 * 已知子智能体工具名集合（2026-06-14 改造导出）
 *
 * 用途：MessageBubble 等上游组件用此判断是否要把当前 tool 调用渲染为
 * SubAgentCard 折叠卡（而不是普通的 tools-body JSON 列表项），
 * 避免 subagent 的消息在「工具调用」块与 SubAgentCard `div` 中重复展示。
 */
export const SUBAGENT_TOOLS = new Set(Object.keys(SUBAGENT_META))

/**
 * 2026-06-15 新增：SSE queue 事件集合
 *
 * queue 事件由后端 chat_concurrency_dependency 在 SSE 排队/衔接阶段发送，
 * 携带 waiting_count / active_count / position 等信息用于前端动态排队提示。
 * 该事件是「应用级全局状态」，不应写入 aiMsg.timeline / aiMsg.text，
 * 通过 callbacks.onQueueEvent 回调由调用方维护响应式 queueStatus。
 */
export const QUEUE_EVENT_TYPES = new Set(['queue'])

/**
 * 2026-06-15 新增：判断 SSE 事件是否为 queue 类型
 *
 * 入参：data（SSE 事件 dict）
 * 返回：boolean
 */
export function isQueueEvent(data) {
  return !!(data && typeof data === 'object' && QUEUE_EVENT_TYPES.has(data.type))
}

/**
 * 判断给定工具名是否属于子智能体工具（2026-06-14 新增导出）
 *
 * 入参：tool（string | undefined | null）
 * 返回：boolean
 */
export function isSubAgentTool(tool) {
  if (!tool || typeof tool !== 'string') return false
  return SUBAGENT_TOOLS.has(tool)
}

/**
 * 判断 SSE message 事件是否属于子智能体内部输出（2026-06-14 新增，2026-06-14-2 增强）
 *
 * 用途：在 processSSEEvent('message') 中跳过子智能体内部的流式输出，
 * 避免在父气泡的 thinking/text/timeline 中重复展示。这些内容已通过
 * custom 事件的 child_messages 累积到 SubAgentDrawer.messages 中。
 *
 * 设计依据：当前后端实现（SandboxTools.py / FilesystemReadTools.py）保证
 * tool_start custom 事件先于子智能体首个 message 事件到达，因此 subAgent
 * 条目在子智能体 message 到达前一定已注册到 aiMsg.subAgents 中。
 *
 * 2026-06-14-2 增强：除 thread_id 匹配外，额外检查 metadata.lc_agent_name /
 * metadata.langgraph_node。当 subAgent 注册尚未完成时（tool_start 与 message
 * 到达顺序抖动的 race condition），仍可通过后端标记识别为子智能体消息。
 *
 * 入参：
 *   aiMsg - 父 AI 消息对象（来自 createAiMessage）
 *   eventThreadId - SSE 事件 metadata.thread_id（string | undefined | null）
 *   metadata - SSE 事件的 metadata 对象（可选，用于 lc_agent_name/langgraph_node 判定）
 * 返回：boolean - true 表示该消息应被视为子智能体内容，应跳过
 */
export function isSubAgentMessage(aiMsg, eventThreadId, metadata = {}) {
  if (!aiMsg || !Array.isArray(aiMsg.subAgents)) return false
  if (typeof eventThreadId === 'string' && eventThreadId) {
    if (aiMsg.subAgents.some(sa => sa && sa.threadId === eventThreadId)) return true
  }
  // 防御性增强：通过后端 agent / 节点名识别已知子智能体
  const agentName = metadata && metadata.lc_agent_name
  const nodeName = metadata && metadata.langgraph_node
  if (typeof agentName === 'string' && SUBAGENT_TOOLS.has(agentName)) return true
  if (typeof nodeName === 'string' && SUBAGENT_TOOLS.has(nodeName)) return true
  return false
}

/**
 * 根据 tool 名返回 {icon, label}，未知工具使用通用图标
 */
export function getSubAgentMeta(tool) {
  return SUBAGENT_META[tool] || { icon: '🤖', label: tool || '子智能体' }
}

/**
 * 从 aiMsg.subAgents 列表中按 toolCallId 查找 subagent
 */
export function getSubAgentById(aiMsg, toolCallId) {
  if (!aiMsg || !Array.isArray(aiMsg.subAgents)) return null
  return aiMsg.subAgents.find(sa => sa.toolCallId === toolCallId) || null
}

/**
 * 把毫秒数格式化为友好字符串（用于 subagent 卡片耗时显示）
 */
export function formatSubAgentDuration(ms) {
  if (!ms || ms < 0) return ''
  if (ms < 1000) return ms + 'ms'
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's'
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.floor((ms % 60000) / 1000)
  return minutes + '分' + seconds + '秒'
}

/**
 * 维护 aiMsg.subAgents 列表的内部工具
 *  - toolStart: 初始化或更新条目
 *  - toolProgress: 累计 messages / events，标记 running
 *  - toolStop: 标记 success，记录 endTime
 *  - toolError: 标记 error，记录 error
 *
 * @param {Object} aiMsg - 父 AI 消息对象
 * @param {Object} event - custom SSE 事件 data（ToolEvent TypedDict）
 * @param {string} topLevelThreadId - SSE 事件顶层 thread_id 字段（map_router 注入）
 */
function updateSubAgentFromCustomEvent(aiMsg, event, topLevelThreadId) {
  if (!aiMsg) return null
  if (!Array.isArray(aiMsg.subAgents)) {
    aiMsg.subAgents = []
  }

  const eventType = event && event.type
  const tool = (event && event.tool) || 'unknown'
  const toolCallId = (event && event.tool_call_id) || topLevelThreadId || ''
  if (!toolCallId) return null

  // 查找或创建
  let sa = aiMsg.subAgents.find(s => s.toolCallId === toolCallId)
  if (!sa) {
    sa = {
      toolCallId,
      threadId: topLevelThreadId || toolCallId,
      tool,
      parentPrompt: '',
      messages: [],
      events: [],
      status: 'running',
      startTime: Date.now(),
      endTime: null,
      error: null
    }
    aiMsg.subAgents.push(sa)
  }

  const inner = (event && event.data) || {}

  // parent_prompt（tool_start 时填充，后续兜底保留）
  if (typeof inner.parent_prompt === 'string' && inner.parent_prompt) {
    sa.parentPrompt = inner.parent_prompt
  }

  // child_messages（tool_progress 累积）
  if (Array.isArray(inner.child_messages)) {
    sa.messages = inner.child_messages
  }

  // events（sandbox_summary / sandbox_events 透传，便于抽屉内时间线复用）
  if (Array.isArray(inner.sandbox_events)) {
    sa.events = inner.sandbox_events
  }

  // sandbox_summary：tool_start/tool_progress 阶段保留当前快照
  if (inner.sandbox_summary && typeof inner.sandbox_summary === 'object') {
    sa.summary = Object.assign({}, sa.summary || {}, inner.sandbox_summary)
  }

  // 状态推进
  if (eventType === 'tool_start') {
    sa.status = 'running'
    if (!sa.startTime && inner.sandbox_summary && inner.sandbox_summary.elapsed_ms) {
      sa.startTime = Date.now() - inner.sandbox_summary.elapsed_ms
    }
  } else if (eventType === 'tool_progress') {
    sa.status = 'running'
  } else if (eventType === 'tool_stop') {
    // 2026-06-15 新增：data.status='stopped_by_user' → 单独状态（用户停止按钮触发）
    // 优先级（向后兼容）：
    //   1. inner.status === 'stopped_by_user' → stopped_by_user（用户主动停止）
    //   2. inner.status === 'error' / 'failure' → error（明确失败）
    //   3. 其他情况（含无 status / 'success'）→ success（默认成功，向后兼容旧事件）
    if (inner.status === 'stopped_by_user') {
      sa.status = 'stopped_by_user'
    } else if (inner.status === 'error' || inner.status === 'failure') {
      sa.status = 'error'
    } else {
      sa.status = 'success'
    }
    sa.endTime = Date.now()
    // final_messages 优先覆盖 messages（最终态）
    if (Array.isArray(inner.final_messages)) {
      sa.messages = inner.final_messages
    }
    // final_summary 合并到 subAgent.summary（最终态摘要）
    if (inner.final_summary && typeof inner.final_summary === 'object') {
      sa.summary = Object.assign({}, sa.summary || {}, inner.final_summary)
    }
  } else if (eventType === 'tool_error') {
    sa.status = 'error'
    sa.endTime = Date.now()
    sa.error = (inner.error_type || 'error') + ': ' + (inner.error_message || '')
  }

  return sa
}

export function tryParsePythonLiteral(content) {
  if (typeof content !== 'string') return null
  const trimmed = content.trim()
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) return null

  try {
    return JSON.parse(trimmed)
  } catch {}

  // 智能替换：逐个字符遍历，正确识别字符串边界（单/双引号），
  // 只替换边界引号为双引号，避免破坏字符串内部的引号
  let result = ''
  let i = 0
  while (i < trimmed.length) {
    const char = trimmed[i]

    if (char === "'" || char === '"') {
      // 字符串开始
      const quote = char
      let j = i + 1
      let escaped = false
      while (j < trimmed.length) {
        if (escaped) {
          escaped = false
          j++
        } else if (trimmed[j] === '\\') {
          escaped = true
          j++
        } else if (trimmed[j] === quote) {
          break
        } else {
          j++
        }
      }
      // 提取字符串内容（不含引号），将内部双引号转义以适配 JSON
      const inner = trimmed.slice(i + 1, j).replace(/"/g, '\\"')
      result += '"' + inner + '"'
      i = j + 1
    } else if (trimmed.slice(i, i + 4) === 'True' && !/[a-zA-Z0-9_]/.test(trimmed[i - 1] || '')) {
      result += 'true'
      i += 4
    } else if (trimmed.slice(i, i + 5) === 'False' && !/[a-zA-Z0-9_]/.test(trimmed[i - 1] || '')) {
      result += 'false'
      i += 5
    } else if (trimmed.slice(i, i + 4) === 'None' && !/[a-zA-Z0-9_]/.test(trimmed[i - 1] || '')) {
      result += 'null'
      i += 4
    } else {
      result += char
      i++
    }
  }

  try {
    return JSON.parse(result)
  } catch {}

  // 回退到 regex：支持单双引号混合的键值对
  const fallbackResult = []

  // 匹配 thinking 块：key 和 value 均可使用单引号或双引号
  const thinkRegex = /['"]thinking['"]:\s*(['"])((?:\\\1|.)*?)\1[^}]*['"]type['"]:\s*['"]thinking['"]/g
  let match
  while ((match = thinkRegex.exec(trimmed)) !== null) {
    const thinking = match[2].replace(/\\'/g, "'").replace(/\\"/g, '"').replace(/\\n/g, '\n')
    fallbackResult.push({ type: 'thinking', thinking })
  }

  // 匹配 text 块：key 和 value 均可使用单引号或双引号
  const textRegex = /['"]text['"]:\s*(['"])((?:\\\1|.)*?)\1[^}]*['"]type['"]:\s*['"]text['"]/g
  while ((match = textRegex.exec(trimmed)) !== null) {
    const text = match[2].replace(/\\'/g, "'").replace(/\\"/g, '"').replace(/\\n/g, '\n')
    fallbackResult.push({ type: 'text', text })
  }

  return fallbackResult.length > 0 ? fallbackResult : null
}

export function extractTextFromBlock(block) {
  if (typeof block === 'string') return block
  if (!block) return ''
  return block.text || block.content || ''
}

export function processContentBlocks(aiMsg, blocks, isMainThread = true) {
  for (const block of blocks) {
    if (typeof block === 'string') {
      if (isMainThread) {
        aiMsg.text += block
        aiMsg.timeline.push({ type: 'text', content: block })
      } else {
        aiMsg.thinking.push(block)
        aiMsg.timeline.push({ type: 'thinking', content: block, isSubAgentText: true })
      }
    } else if (isThinkingBlock(block)) {
      const thinkingText = block.thinking || ''
      if (thinkingText) {
        aiMsg.thinking.push(thinkingText)
        aiMsg.timeline.push({ type: 'thinking', content: thinkingText })
      }
      aiMsg.isThinkingActive = true
    } else {
      const t = extractTextFromBlock(block)
      if (t) {
        if (isMainThread) {
          aiMsg.text += t
          aiMsg.timeline.push({ type: 'text', content: t })
        } else {
          aiMsg.thinking.push(t)
          aiMsg.timeline.push({ type: 'thinking', content: t, isSubAgentText: true })
        }
      }
    }
  }
}

export function parseMessageContent(content, aiMsg, isMainThread = true) {
  if (!content && content !== '') return

  if (Array.isArray(content)) {
    processContentBlocks(aiMsg, content, isMainThread)
    return
  }

  if (typeof content === 'object' && content !== null) {
    if (isThinkingBlock(content)) {
      const thinkingText = content.thinking || ''
      if (thinkingText) {
        aiMsg.thinking.push(thinkingText)
        aiMsg.timeline.push({ type: 'thinking', content: thinkingText })
      }
      aiMsg.isThinkingActive = true
    } else {
      const t = extractTextFromBlock(content)
      if (isMainThread) {
        const textContent = t || JSON.stringify(content)
        aiMsg.text += textContent
        aiMsg.timeline.push({ type: 'text', content: textContent })
      } else {
        const textContent = t || JSON.stringify(content)
        aiMsg.thinking.push(textContent)
        aiMsg.timeline.push({ type: 'thinking', content: textContent, isSubAgentText: true })
      }
    }
    return
  }

  if (typeof content === 'string') {
    const parsed = tryParsePythonLiteral(content)
    if (parsed && Array.isArray(parsed)) {
      processContentBlocks(aiMsg, parsed, isMainThread)
      return
    }
    if (isMainThread) {
      aiMsg.text += content
      aiMsg.timeline.push({ type: 'text', content })
    } else {
      aiMsg.thinking.push(content)
      aiMsg.timeline.push({ type: 'thinking', content, isSubAgentText: true })
    }
    return
  }

  const str = String(content)
  if (isMainThread) {
    aiMsg.text += str
    aiMsg.timeline.push({ type: 'text', content: str })
  } else {
    aiMsg.thinking.push(str)
    aiMsg.timeline.push({ type: 'thinking', content: str, isSubAgentText: true })
  }
}

export function extractInterruptInfo(data) {
  if (!data) return null

  // 标准化格式：后端修复后发送的 { requests: [...] }
  if (data.requests && Array.isArray(data.requests)) {
    return data.requests
  }

  // 兼容旧格式：{ __interrupt__: [...] }
  if (data.__interrupt__ && Array.isArray(data.__interrupt__)) {
    return parseInterruptArray(data.__interrupt__)
  }

  return null
}

function parseInterruptArray(interruptArray) {
  const results = []
  for (const item of interruptArray) {
    if (typeof item === 'string' && item.startsWith('Interrupt(')) {
      const parsed = parseInterruptRepr(item)
      if (parsed) results.push(parsed)
    } else if (typeof item === 'object' && item !== null) {
      results.push(item)
    }
  }
  return results
}

function parseInterruptRepr(reprStr) {
  try {
    // 提取 value=... 部分，匹配到 ], id= 为止
    const valueMatch = reprStr.match(/value=(\[.*?\]),?\s*id=/s)
    if (!valueMatch) return null
    let valueStr = valueMatch[1]
    // 使用已有的 tryParsePythonLiteral 解析 Python 字面量
    const parsed = tryParsePythonLiteral(valueStr)
    if (parsed && Array.isArray(parsed) && parsed.length > 0) {
      return parsed[0]
    }
    return null
  } catch (e) {
    console.warn('解析 Interrupt repr 失败:', e)
    return null
  }
}

export function processSSEEvent(data, aiMsg, callbacks) {
  const metadata = data.metadata || {}
  const eventThreadId = metadata.thread_id || ''

  // 2026-06-15 新增：SSE queue 事件由后端 chat_concurrency_dependency 在排队/衔接阶段发送。
  // 该事件是应用级全局状态（dynamic queue banner），不写入 aiMsg。
  // 通过 callbacks.onQueueEvent 回调由调用方维护响应式 queueStatus；
  // 若未提供回调则静默忽略（保持向后兼容）。
  if (isQueueEvent(data)) {
    if (callbacks && typeof callbacks.onQueueEvent === 'function') {
      try {
        callbacks.onQueueEvent(data)
      } catch (err) {
        console.warn('[sseParser] onQueueEvent 回调异常:', err)
      }
    }
    return
  }

  if (data.type === 'message' && !aiMsg.threadId && eventThreadId
      && !isSubAgentMessage(aiMsg, eventThreadId, metadata)) {
    // 2026-06-14 改造：thread_id 属于子智能体时不写入父气泡 threadId
    // 避免首个 message 事件恰好来自子智能体时把父气泡 threadId 设错
    aiMsg.threadId = eventThreadId
  }

  const isMainThread = !eventThreadId || eventThreadId === aiMsg.threadId

  // 顶层 thread_id 由后端 map_router 在 custom 模式注入（2026-06-13 新增）
  // 2026-06-14-2 新增：update 模式也可能注入 thread_id（统一格式，可能为空）
  // subagent 事件 data.data.tool_call_id == thread_id
  const topLevelThreadId = (data && data.thread_id) || ''

  switch (data.type) {
    case 'interrupt': {
      const interruptInfo = extractInterruptInfo(data.data)
      if (interruptInfo) {
        aiMsg.interrupt = interruptInfo
        aiMsg.isStreaming = false
        aiMsg.isLoading = false
        aiMsg.isThinkingActive = false
      }
      break
    }
    case 'update': {
      const updateData = data.data || data

      // 兼容模式：检测 data 中是否直接包含 __interrupt__
      if (updateData && updateData.__interrupt__) {
        const interruptInfo = extractInterruptInfo(updateData)
        if (interruptInfo) {
          aiMsg.interrupt = interruptInfo
          aiMsg.isStreaming = false
          aiMsg.isLoading = false
          aiMsg.isThinkingActive = false
          break
        }
      }

      if (updateData.summarize) break
      // 2026-06-14-2 修复：hitl_check 节点的 update 是状态同步/历史 dump，
      // 其中包含 ToolMessage(sandbox) 等子智能体历史回复，不能落入父气泡 thinking。
      if (updateData.hitl_check) break
      if (updateData.llm_call) {
        const msgs = updateData.llm_call.messages
        if (msgs && Array.isArray(msgs)) {
          for (const msg of msgs) {
            if (typeof msg === 'string') {
              const parsed = tryParsePythonLiteral(msg)
              if (parsed && Array.isArray(parsed)) {
                processContentBlocks(aiMsg, parsed, true)
              }
            }
          }
        }
        break
      }
      aiMsg.thinking.push(data)
      aiMsg.timeline.push({ type: 'thinking', content: data })
      aiMsg.isThinkingActive = true
      break
    }
    case 'message': {
      // 2026-06-14 改造：识别子智能体内部消息并跳过，避免在父气泡中重复展示
      // 子智能体的结构化 child_messages 已通过 custom 事件累积到 subAgents[i].messages
      // 这里命中时直接 break，不写入父气泡的 thinking / text / timeline
      // 2026-06-14-2 改造：将 metadata 透传给 isSubAgentMessage，支持 lc_agent_name 防御判定
      if (isSubAgentMessage(aiMsg, eventThreadId, metadata)) {
        break
      }
      const c = data.content || data.data
      parseMessageContent(c, aiMsg, isMainThread)
      if (!isMainThread) {
        aiMsg.isThinkingActive = true
      }
      break
    }
    case 'custom':
      aiMsg.tools.push(data)
      aiMsg.timeline.push({ type: 'tool', content: data })
      // 检查是否是 tool_stop 类型的自定义事件
      console.log('[sseParser] custom event:', JSON.stringify(data))
      // 注意：custom 事件的 data 字段包含实际的工具事件数据
      var customToolData = data.data || {}

      // 2026-06-13 新增：维护 aiMsg.subAgents 列表（折叠卡片 / 抽屉用）
      // 注意：data.data 是 ToolEvent TypedDict；顶层 data.thread_id 由 map_router 注入
      // 2026-06-14 改造：沙箱执行数据通过 subAgent（tool='sandbox'）统一承接，避免双重维护 sandboxExecution
      updateSubAgentFromCustomEvent(aiMsg, customToolData, topLevelThreadId)

      if (customToolData.tool && customToolData.type === 'tool_stop') {
        console.log('[sseParser] Detected tool_stop in custom event')
        var toolResultData = customToolData.data || {}
        if (toolResultData.status === 'success' && toolResultData.type === 'download') {
          console.log('[sseParser] Detected download type in custom tool_stop')
          var result = toolResultData.result || {}
          var downloadUrl = null
          var fileName = null
          if (typeof result === 'object') {
            downloadUrl = result.download_url || result.downloadUrl
            fileName = result.file_name || result.fileName || result.filename
          }
          console.log('[sseParser] Custom event - downloadUrl:', downloadUrl, 'fileName:', fileName)
          if (downloadUrl) {
            aiMsg.downloadInfo = {
              downloadUrl: downloadUrl,
              fileName: fileName || '报告文件'
            }
            console.log('[sseParser] Set downloadInfo from custom:', JSON.stringify(aiMsg.downloadInfo))
          }
        }
      }
      break
    case 'end':
      aiMsg.ended = true
      aiMsg.isThinkingActive = false
      break
    case 'error':
      aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
      break
    case 'tool_stop': {
      // tool_stop 事件的 data 字段在根级别
      // 格式: { type: 'tool_stop', tool: '...', data: { status: 'success', type: 'download', result: {...} } }
      const toolData = data.data || {}
      console.log('[sseParser] tool_stop event, data:', JSON.stringify(data))
      console.log('[sseParser] tool_stop toolData:', JSON.stringify(toolData))
      // 检查是否是下载类型工具成功执行
      if (toolData.status === 'success' && toolData.type === 'download') {
        console.log('[sseParser] Detected download type tool success')
        // 尝试从 result 中解析下载信息
        const result = toolData.result || {}
        console.log('[sseParser] result:', JSON.stringify(result))
        // result 可能是对象或字符串
        let downloadUrl = null
        let fileName = null
        if (typeof result === 'string') {
          // 尝试从字符串中提取下载地址
          const urlMatch = result.match(/下载地址[:：]\s*(\S+)/)
          if (urlMatch) {
            downloadUrl = urlMatch[1]
          }
          // 尝试提取文件名
          const fileMatch = result.match(/文件[:：]\s*(\S+)/)
          if (fileMatch) {
            fileName = fileMatch[1]
          }
        } else if (typeof result === 'object') {
          downloadUrl = result.download_url || result.downloadUrl
          fileName = result.file_name || result.fileName || result.filename
        }
        console.log('[sseParser] Extracted downloadUrl:', downloadUrl, 'fileName:', fileName)
        if (downloadUrl) {
          aiMsg.downloadInfo = {
            downloadUrl: downloadUrl,
            fileName: fileName || '报告文件'
          }
          console.log('[sseParser] Set downloadInfo:', JSON.stringify(aiMsg.downloadInfo))
        }
      }
      break
    }
  }
}

export function createAiMessage() {
  return {
    id: Date.now() + 1,
    type: 'ai',
    threadId: '',
    isThinkingActive: false,
    timeline: [],
    thinking: [],
    tools: [],
    text: '',
    ended: false,
    error: '',
    downloadInfo: null,
    interrupt: null,
    subAgents: []             // 2026-06-13 新增：子智能体执行列表（折叠卡片 / 抽屉用，统一承接沙箱/文件探索等子智能体）
  }
}
