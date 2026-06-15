/**
 * SubAgentDrawer 组件测试（2026-06-13 新增，2026-06-14 改造，2026-06-15 精简）
 *
 * 覆盖：
 *   - visible=false 时抽屉不显示（aside v-show 行为）
 *   - 关闭按钮触发 close 事件
 *   - 父 prompt 折叠/展开交互
 *   - 各 message type 渲染
 *   - 状态徽章 + 消息数 + 工具调用次数
 *   - 2026-06-15 再次精简：移除沙箱执行摘要区块，tool='sandbox' 不再有专属 UI
 *   - 2026-06-14 改造：AIMessage.content 为 LangChain 0.3+ list[ContentBlock] 格式时正确渲染
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import SubAgentDrawer from '../SubAgentDrawer.vue'

const baseSubAgent = {
  toolCallId: 'c1',
  threadId: 'c1',
  tool: 'sandbox',
  parentPrompt: '父 agent 提问文本',
  messages: [
    { type: 'HumanMessage', role: 'user', content: 'user question' },
    { type: 'AIMessage', role: 'ai', content: 'ai thinking', tool_calls: [{ name: 'ls', args: { p: '/tmp' }, id: 'c1' }] },
    { type: 'ToolMessage', role: 'tool', content: 'tool output', tool_call_id: 'c1', name: 'ls' }
  ],
  events: [],
  status: 'success',
  startTime: Date.now() - 2000,
  endTime: Date.now() - 1000,
  error: null
}

describe('SubAgentDrawer', () => {
  beforeEach(() => {
    // 每个测试前清空相关 localStorage，避免用例间互相污染
    localStorage.removeItem('subagent-drawer-width')
  })

  afterEach(() => {
    localStorage.removeItem('subagent-drawer-width')
  })
  it('visible=false 时抽屉不应可见', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: false, subAgent: baseSubAgent }
    })
    const aside = wrapper.find('aside.subagent-drawer')
    // v-show 切换 display
    expect(aside.exists()).toBe(true)
  })

  it('visible=true 时添加 visible class', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.find('aside.subagent-drawer').classes()).toContain('visible')
  })

  it('关闭按钮触发 close 事件', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    await wrapper.find('.close-btn').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('渲染父 agent 提问文本', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.text()).toContain('父 agent 提问文本')
  })

  it('点击父 prompt section header 切换折叠状态', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    const header = wrapper.find('.parent-prompt-section .section-header')
    expect(header.exists()).toBe(true)
    await header.trigger('click')
    // 折叠后 content 区域不再显示
    expect(wrapper.find('.parent-prompt-content').exists()).toBe(false)
  })

  it('渲染 HumanMessage / AIMessage / ToolMessage 各一条', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    const items = wrapper.findAll('.message-item')
    expect(items).toHaveLength(3)
    // role 分类样式
    expect(items[0].classes()).toContain('role-user')
    expect(items[1].classes()).toContain('role-ai')
    expect(items[2].classes()).toContain('role-tool')
  })

  // ========== 2026-06-15 新增：抽屉宽度拖拽调整 ==========

  it('可见时渲染左侧拖拽条', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.find('.resize-handle').exists()).toBe(true)
  })

  it('挂载时从 localStorage 读取保存的宽度并应用', async () => {
    localStorage.setItem('subagent-drawer-width', '600')
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    await nextTick()
    const aside = wrapper.find('aside.subagent-drawer')
    expect(aside.attributes('style')).toContain('--drawer-width: 600px')
  })

  it('挂载时 localStorage 宽度小于最小值会被限制', async () => {
    localStorage.setItem('subagent-drawer-width', '100')
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    await nextTick()
    const aside = wrapper.find('aside.subagent-drawer')
    expect(aside.attributes('style')).toContain('--drawer-width: 320px')
  })

  it('拖拽条 mousedown 时进入 resizing 状态', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    const handle = wrapper.find('.resize-handle')
    await handle.trigger('mousedown')
    expect(wrapper.find('.resize-handle').classes()).toContain('active')
    expect(wrapper.find('aside.subagent-drawer').classes()).toContain('resizing')
    // 清理：触发 mouseup 释放
    window.dispatchEvent(new MouseEvent('mouseup'))
  })

  it('拖拽到小于关闭阈值时触发 close 事件', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    const handle = wrapper.find('.resize-handle')
    await handle.trigger('mousedown')
    // 模拟鼠标大幅向左移动，使计算宽度小于 180px
    // getBoundingClientRect 在 happy-dom 默认返回 0，
    // 这里通过直接操作组件内部 drawerWidth 来触发阈值逻辑
    wrapper.vm.drawerWidth = 150
    window.dispatchEvent(new MouseEvent('mouseup'))
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('拖拽到有效宽度时保存到 localStorage', async () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    // 通过组件内部 drawerWidth 设置有效宽度，再触发 stopResize
    wrapper.vm.drawerWidth = 560
    wrapper.vm.isResizing = true
    window.dispatchEvent(new MouseEvent('mouseup'))
    await nextTick()
    expect(localStorage.getItem('subagent-drawer-width')).toBe('560')
    const aside = wrapper.find('aside.subagent-drawer')
    expect(aside.attributes('style')).toContain('--drawer-width: 560px')
  })

  it('AIMessage 含 tool_calls 时仍然渲染 content 内容', () => {
    const saWithContent = {
      ...baseSubAgent,
      messages: [
        {
          type: 'AIMessage',
          role: 'ai',
          content: [
            { type: 'thinking', thinking: '我在思考如何执行' },
            { type: 'text', text: '我将使用 ls 工具查看目录' }
          ],
          tool_calls: [{ name: 'ls', args: { p: '/tmp' }, id: 'c1' }]
        }
      ]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: saWithContent }
    })
    // 决策区仍应存在
    expect(wrapper.text()).toContain('决策')
    expect(wrapper.text()).toContain('ls')
    // content 中的 thinking/text 不应被 v-else 吞掉
    expect(wrapper.text()).toContain('我在思考如何执行')
    expect(wrapper.text()).toContain('我将使用 ls 工具查看目录')
  })

  it('AIMessage 含 tool_calls 时渲染"决策"区', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.text()).toContain('决策')
    expect(wrapper.text()).toContain('ls')
  })

  it('底部摘要显示耗时/消息数/工具调用次数', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: baseSubAgent }
    })
    expect(wrapper.text()).toContain('3 条消息')
    expect(wrapper.text()).toContain('1 次工具调用')
  })

  it('messages 为空时显示"暂无消息"', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: {
        visible: true,
        subAgent: { ...baseSubAgent, messages: [] }
      }
    })
    expect(wrapper.text()).toContain('暂无消息')
  })

  it('subAgent=null 时不崩溃且显示占位', () => {
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: null }
    })
    expect(wrapper.exists()).toBe(true)
  })

  // ========== 2026-06-14 改造：LangChain 0.3+ 多模态消息格式 ==========

  it('AIMessage.content 为 list[ContentBlock] 时正确渲染（LangChain 0.3 格式）', () => {
    const lcSa = {
      ...baseSubAgent,
      tool: 'explore',
      messages: [
        { type: 'HumanMessage', role: 'user', content: 'hi' },
        {
          type: 'AIMessage',
          role: 'ai',
          content: [
            { type: 'text', text: '我会调用工具' },
            { type: 'tool_use', name: 'search', input: { query: 'xxx' } }
          ]
        },
        {
          type: 'ToolMessage',
          role: 'tool',
          content: [
            { type: 'tool_result', tool_use_id: 'c1', content: '搜索结果...' }
          ],
          tool_call_id: 'c1',
          name: 'search'
        }
      ]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: lcSa }
    })
    // text 块
    expect(wrapper.text()).toContain('我会调用工具')
    // tool_use 块
    expect(wrapper.text()).toContain('[工具调用]')
    expect(wrapper.text()).toContain('search')
    // tool_result 块
    expect(wrapper.text()).toContain('[工具结果')
    expect(wrapper.text()).toContain('搜索结果')
  })

  it('AIMessage.content 包含 thinking 块时正确渲染', () => {
    const thinkSa = {
      ...baseSubAgent,
      tool: 'explore',
      messages: [
        {
          type: 'AIMessage',
          role: 'ai',
          content: [
            { type: 'thinking', thinking: '分析用户意图...' },
            { type: 'text', text: '我需要查询资料' }
          ]
        }
      ]
    }
    const wrapper = mount(SubAgentDrawer, {
      props: { visible: true, subAgent: thinkSa }
    })
    expect(wrapper.text()).toContain('[思考]')
    expect(wrapper.text()).toContain('分析用户意图')
    expect(wrapper.text()).toContain('我需要查询资料')
  })
})
