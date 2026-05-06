<script setup>
import { reactive, onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import SkillTags from './components/SkillTags.vue'
import ChatArea from './components/ChatArea.vue'
import InputBox from './components/InputBox.vue'
import { chatStream, ensureAuth, createNewSession } from './utils/api.js'

const messages = reactive([])
const sessionId = reactive({ value: '' })
const isStreaming = reactive({ value: false })

onMounted(async () => {
  try {
    await ensureAuth()
    sessionId.value = localStorage.getItem('session_id') || ''
  } catch {}
})

async function newSession() {
  // 先清除旧的 session_id，确保新建任务时一定会重新生成
  localStorage.removeItem('session_id')
  sessionId.value = ''
  messages.splice(0, messages.length)

  try {
    const newId = await createNewSession()
    sessionId.value = newId
  } catch (err) {
    console.error('新建会话失败:', err)
  }
}

function isThinkingBlock(block) {
  if (!block) return false
  return block.type === 'thinking' || !!block.thinking
}

function tryParsePythonLiteral(content) {
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

function extractTextFromBlock(block) {
  if (typeof block === 'string') return block
  if (!block) return ''
  return block.text || block.content || ''
}

function processContentBlocks(aiMsg, blocks) {
  for (const block of blocks) {
    if (typeof block === 'string') {
      aiMsg.text += block
    } else if (isThinkingBlock(block)) {
      const thinkingText = block.thinking || ''
      if (thinkingText) {
        aiMsg.thinking.push(thinkingText)
      }
    } else {
      const t = extractTextFromBlock(block)
      if (t) aiMsg.text += t
    }
  }
}

function parseMessageContent(content, aiMsg) {
  if (!content && content !== '') return

  if (Array.isArray(content)) {
    processContentBlocks(aiMsg, content)
    return
  }

  if (typeof content === 'object' && content !== null) {
    if (isThinkingBlock(content)) {
      const thinkingText = content.thinking || ''
      if (thinkingText) aiMsg.thinking.push(thinkingText)
    } else {
      const t = extractTextFromBlock(content)
      aiMsg.text += t || JSON.stringify(content)
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
    return
  }

  aiMsg.text += String(content)
}

function processSSEEvent(data, aiMsg) {
  switch (data.type) {
    case 'update': {
      const updateData = data.data || data
      // 跳过 summarize 节点（仅为消息历史摘要，用户无需看到）
      if (updateData.summarize) break
      // llm_call 节点：提取 thinking/text 内容块，不展示原始 state dump
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
      break
    }
    case 'message': {
      const c = data.content || data.data
      parseMessageContent(c, aiMsg)
      break
    }
    case 'custom':
      aiMsg.tools.push(data)
      break
    case 'end':
      aiMsg.ended = true
      break
    case 'error':
      aiMsg.error = data.message || '未知错误'
      break
  }
}

function createAiMessage() {
  return reactive({
    id: Date.now() + 1,
    type: 'ai',
    thinking: [],
    tools: [],
    text: '',
    ended: false,
    error: ''
  })
}

async function handleSendMessage(message, attachments = []) {
  if (!message.trim() && attachments.length === 0) return
  if (isStreaming.value) return

  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: message,
    attachments
  }
  messages.push(userMsg)

  const aiMsg = createAiMessage()
  messages.push(aiMsg)

  isStreaming.value = true

  try {
    const stream = await chatStream(sessionId.value, message, attachments)
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const event of events) {
        if (!event.startsWith('data: ')) continue
        try {
          const data = JSON.parse(event.slice(6))
          processSSEEvent(data, aiMsg)
        } catch {}
      }
    }
  } catch (err) {
    aiMsg.error = err.message || '连接失败'
  } finally {
    isStreaming.value = false
  }
}

function handleTagSelect(tag, index) {
  console.log('选择技能标签:', tag.label)
}

function handleToolAction(action) {
  console.log('工具操作:', action)
}
</script>

<template>
  <div class="app-layout">
    <Sidebar @new-chat="newSession" />

    <main class="content-area">
      <SkillTags @tag-select="handleTagSelect" />

      <ChatArea
        :messages="messages"
        :is-streaming="isStreaming.value"
      />

      <InputBox
        :session-id="sessionId.value"
        :is-streaming="isStreaming.value"
        @send="handleSendMessage"
        @tool-action="handleToolAction"
      />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  background-color: var(--color-bg-secondary);
  overflow: hidden;
}

.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}
</style>
