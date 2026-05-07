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

export function processContentBlocks(aiMsg, blocks) {
  for (const block of blocks) {
    if (typeof block === 'string') {
      aiMsg.text += block
      aiMsg.timeline.push({ type: 'text', content: block })
    } else if (isThinkingBlock(block)) {
      const thinkingText = block.thinking || ''
      if (thinkingText) {
        aiMsg.thinking.push(thinkingText)
        aiMsg.timeline.push({ type: 'thinking', content: thinkingText })
      }
    } else {
      const t = extractTextFromBlock(block)
      if (t) {
        aiMsg.text += t
        aiMsg.timeline.push({ type: 'text', content: t })
      }
    }
  }
}

export function parseMessageContent(content, aiMsg) {
  if (!content && content !== '') return

  if (Array.isArray(content)) {
    processContentBlocks(aiMsg, content)
    return
  }

  if (typeof content === 'object' && content !== null) {
    if (isThinkingBlock(content)) {
      const thinkingText = content.thinking || ''
      if (thinkingText) {
        aiMsg.thinking.push(thinkingText)
        aiMsg.timeline.push({ type: 'thinking', content: thinkingText })
      }
    } else {
      const t = extractTextFromBlock(content)
      const textContent = t || JSON.stringify(content)
      aiMsg.text += textContent
      aiMsg.timeline.push({ type: 'text', content: textContent })
    }
    return
  }

  if (typeof content === 'string') {
    const parsed = tryParsePythonLiteral(content)
    if (parsed && Array.isArray(parsed)) {
      processContentBlocks(aiMsg, parsed)
      return
    }
    aiMsg.text += content
    aiMsg.timeline.push({ type: 'text', content })
    return
  }

  aiMsg.text += String(content)
  aiMsg.timeline.push({ type: 'text', content: String(content) })
}

export function processSSEEvent(data, aiMsg) {
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
                processContentBlocks(aiMsg, parsed)
              }
            }
          }
        }
        break
      }
      aiMsg.thinking.push(data)
      aiMsg.timeline.push({ type: 'thinking', content: data })
      break
    }
    case 'message': {
      const c = data.content || data.data
      parseMessageContent(c, aiMsg)
      break
    }
    case 'custom':
      aiMsg.tools.push(data)
      aiMsg.timeline.push({ type: 'tool', content: data })
      break
    case 'end':
      aiMsg.ended = true
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
    timeline: [],
    thinking: [],
    tools: [],
    text: '',
    ended: false,
    error: ''
  }
}
