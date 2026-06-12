export function isThinkingBlock(block) {
  if (!block) return false
  return block.type === 'thinking' || !!block.thinking
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

export function processSSEEvent(data, aiMsg) {
  const metadata = data.metadata || {}
  const eventThreadId = metadata.thread_id || ''

  if (data.type === 'message' && !aiMsg.threadId && eventThreadId) {
    aiMsg.threadId = eventThreadId
  }

  const isMainThread = !eventThreadId || eventThreadId === aiMsg.threadId

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

      // 检测沙盒工具事件
      if (customToolData.tool === 'sandbox') {
        if (!aiMsg.sandboxExecution) {
          aiMsg.sandboxExecution = {
            status: 'running',
            summary: null,
            events: [],
            startTime: Date.now()
          }
        }

        // 更新摘要信息
        if (customToolData.data && customToolData.data.sandbox_summary) {
          aiMsg.sandboxExecution.summary = customToolData.data.sandbox_summary
        }

        // 追加事件
        if (customToolData.data && customToolData.data.sandbox_events && Array.isArray(customToolData.data.sandbox_events)) {
          // 去重追加：只添加时间戳不存在的事件
          var existingTimestamps = new Set(aiMsg.sandboxExecution.events.map(function(e) { return e.timestamp }))
          for (var idx = 0; idx < customToolData.data.sandbox_events.length; idx++) {
            var evt = customToolData.data.sandbox_events[idx]
            if (!existingTimestamps.has(evt.timestamp)) {
              aiMsg.sandboxExecution.events.push(evt)
              existingTimestamps.add(evt.timestamp)
            }
          }
        }

        // 处理完成
        if (customToolData.type === 'tool_stop') {
          aiMsg.sandboxExecution.status =
            customToolData.data && customToolData.data.status === 'success' ? 'success' : 'error'
          if (customToolData.data && customToolData.data.final_summary) {
            aiMsg.sandboxExecution.summary = Object.assign(
              {},
              aiMsg.sandboxExecution.summary || {},
              customToolData.data.final_summary
            )
          }
        }
      }

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
    sandboxExecution: null  // 新增：沙盒执行状态
  }
}
