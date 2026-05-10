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

  try {
    const jsonStr = trimmed
      .replace(/'/g, '"')
      .replace(/True/g, 'true')
      .replace(/False/g, 'false')
      .replace(/None/g, 'null')
    return JSON.parse(jsonStr)
  } catch {}

  const result = []
  const thinkRegex = /'thinking':\s*'((?:[^'\\]|\\.)*)'[^}]*'type':\s*'thinking'/g
  const textRegex = /'text':\s*'((?:[^'\\]|\\.)*)'[^}]*'type':\s*'text'/g

  let match
  while ((match = thinkRegex.exec(trimmed)) !== null) {
    const thinking = match[1].replace(/\\'/g, "'").replace(/\\n/g, '\n')
    result.push({ type: 'thinking', thinking })
  }
  while ((match = textRegex.exec(trimmed)) !== null) {
    const text = match[1].replace(/\\'/g, "'").replace(/\\n/g, '\n')
    result.push({ type: 'text', text })
  }

  return result.length > 0 ? result : null
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

export function processSSEEvent(data, aiMsg) {
  const metadata = data.metadata || {}
  const eventThreadId = metadata.thread_id || ''

  if (data.type === 'message' && !aiMsg.threadId && eventThreadId) {
    aiMsg.threadId = eventThreadId
  }

  const isMainThread = !eventThreadId || eventThreadId === aiMsg.threadId

  switch (data.type) {
    case 'update': {
      const updateData = data.data || data
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
      break
    case 'end':
      aiMsg.ended = true
      aiMsg.isThinkingActive = false
      break
    case 'error':
      aiMsg.error = '不好意思，刚刚出了点小故障，可以晚点再问我一遍。'
      break
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
    error: ''
  }
}
