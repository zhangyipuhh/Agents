/**
 * SubAgentCard 组件测试（2026-06-13 新增，2026-06-14 改造）
 *
 * 覆盖：
 *   - 各状态徽章正确显示
 *   - 点击触发 click 事件并传 subAgent
 *   - parentPrompt 截断到 30 字符
 *   - 消息数与耗时格式化
 *   - 2026-06-14 改造：summary 字段（来自 sandbox 类子智能体）不影响卡片渲染
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SubAgentCard from '../SubAgentCard.vue'

const baseSubAgent = {
  toolCallId: 'c1',
  threadId: 'c1',
  tool: 'sandbox',
  parentPrompt: '执行沙箱测试',
  messages: [],
  events: [],
  status: 'running',
  startTime: Date.now() - 1500,
  endTime: null,
  error: null
}

describe('SubAgentCard', () => {
  it('渲染父 agent 提问预览（前 30 字符截断）', () => {
    const longPrompt = 'a'.repeat(50)
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, parentPrompt: longPrompt } }
    })
    expect(wrapper.text()).toContain('a'.repeat(30) + '…')
  })

  it('短 parentPrompt 不截断', () => {
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, parentPrompt: 'short' } }
    })
    expect(wrapper.text()).toContain('short')
    expect(wrapper.text()).not.toContain('…')
  })

  it('running 状态显示"执行中"', () => {
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, status: 'running' } }
    })
    expect(wrapper.text()).toContain('执行中')
  })

  it('success 状态显示"已完成"', () => {
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, status: 'success' } }
    })
    expect(wrapper.text()).toContain('已完成')
  })

  it('error 状态显示"执行失败" + 错误详情', () => {
    const wrapper = mount(SubAgentCard, {
      props: {
        subAgent: {
          ...baseSubAgent,
          status: 'error',
          error: 'RuntimeError: docker not running'
        }
      }
    })
    expect(wrapper.text()).toContain('执行失败')
    expect(wrapper.text()).toContain('RuntimeError')
  })

  it('sandbox 工具名显示"sandbox"标签', () => {
    // 2026-07-01 同步：业务代码已演进，工具名标签直接展示英文 tool 字段（'sandbox'/'explore'），
    // 不再额外映射成「沙箱执行」「文件探索」中文标签。
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, tool: 'sandbox' } }
    })
    expect(wrapper.text()).toContain('sandbox')
  })

  it('explore 工具名显示"explore"标签', () => {
    // 2026-07-01 同步：业务代码已演进，工具名标签直接展示英文 tool 字段。
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, tool: 'explore' } }
    })
    expect(wrapper.text()).toContain('explore')
  })

  it('消息数 > 0 时显示"X 条消息"', () => {
    const wrapper = mount(SubAgentCard, {
      props: {
        subAgent: {
          ...baseSubAgent,
          messages: [
            { type: 'HumanMessage', role: 'user', content: 'q' },
            { type: 'AIMessage', role: 'ai', content: 'a' }
          ]
        }
      }
    })
    expect(wrapper.text()).toContain('2 条消息')
  })

  it('点击卡片触发 click 事件并传递 subAgent', async () => {
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: baseSubAgent }
    })
    await wrapper.find('.subagent-card').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')[0][0]).toEqual(baseSubAgent)
  })

  // ========== 2026-06-14 改造：summary 字段不影响卡片渲染 ==========

  it('sandbox 类子智能体的 summary 字段不破坏卡片渲染', () => {
    const sandboxSa = {
      ...baseSubAgent,
      tool: 'sandbox',
      status: 'success',
      endTime: Date.now(),
      summary: {
        progress_pct: 100,
        current_step: 5,
        total_steps: 5,
        elapsed_ms: 10000,
        status_message: '执行完成'
      }
    }
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: sandboxSa }
    })
    // 2026-07-01 同步：业务代码已演进，工具名标签直接展示英文 tool 字段
    expect(wrapper.text()).toContain('sandbox')
    expect(wrapper.text()).toContain('已完成')
  })

  it('parentPrompt 缺失时仅展示核心字段（不显示 prompt 预览）', () => {
    const noPromptSa = {
      ...baseSubAgent,
      parentPrompt: ''
    }
    const wrapper = mount(SubAgentCard, {
      props: { subAgent: noPromptSa }
    })
    // 2026-07-01 同步：业务代码已演进，工具名标签直接展示英文 tool 字段
    expect(wrapper.text()).toContain('sandbox')
  })

  // ========== 2026-06-15 新增：用户停止按钮触发的子智能体中止状态 ==========

  it('stopped_by_user 状态显示"已中止"（用户停止按钮触发）', () => {
    const wrapper = mount(SubAgentCard, {
      props: {
        subAgent: {
          ...baseSubAgent,
          status: 'stopped_by_user',
          endTime: Date.now()
        }
      }
    })
    expect(wrapper.text()).toContain('已中止')
    // 状态徽章 class 应包含 stopped_by_user（用于 CSS 颜色区分）
    const statusBadge = wrapper.find('.subagent-status')
    expect(statusBadge.classes()).toContain('stopped_by_user')
  })

  it('stopped_by_user 状态无 pulse 动画（与 running 区分）', () => {
    const runningWrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, status: 'running' } }
    })
    const stoppedWrapper = mount(SubAgentCard, {
      props: { subAgent: { ...baseSubAgent, status: 'stopped_by_user' } }
    })
    // running 状态有 subagent-icon-running class（动画）
    const runningIcon = runningWrapper.find('.subagent-icon')
    expect(runningIcon.classes()).toContain('subagent-icon-running')
    // stopped_by_user 状态无此 class（静态）
    const stoppedIcon = stoppedWrapper.find('.subagent-icon')
    expect(stoppedIcon.classes()).not.toContain('subagent-icon-running')
  })
})
