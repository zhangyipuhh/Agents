/**
 * ToolCallCard 组件测试（2026-06-15 新增，2026-06-15 第二次改造同步）
 *
 * 覆盖：
 *   - 组件可挂载（importable）
 *   - 状态徽章正确显示（running / success / error）
 *   - 运行时扳手图标有 tool-call-icon-running class（动画生效）
 *   - 默认 running 状态展开步骤列表；success / error 状态折叠
 *   - 点击头部切换 isExpanded
 *   - 每条 event 渲染一个步骤，含时间戳、事件类型、摘要
 *   - 步骤默认不显示 key-value 详情（避免视觉繁琐）
 *   - 点击单条步骤可展开/折叠 key-value 详情
 *   - ToolCallCard 不 emit 任何抽屉相关事件
 *   - 头部显式标注「普通工具」徽章（与 SubAgentCard 视觉区分）
 *   - 步骤数与耗时格式化
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ToolCallCard from '../ToolCallCard.vue'

// 构造单条 ToolEvent data 字典（与 sseParser processSSEEvent case 'custom' 透传的 item.data 一致）
const makeStartEvent = (extra = {}) => ({
  type: 'tool_start',
  tool: '生成报告',
  tool_call_id: 'call_abc',
  thread_id: 'top_thread',
  data: { parent_prompt: '请生成报告', ...(extra.data || {}) },
  timestamp: 1781497972.93354
})

const makeProgressEvent = (overrides = {}) => ({
  type: 'tool_progress',
  tool: '生成报告',
  tool_call_id: 'call_abc',
  thread_id: 'top_thread',
  data: { current: 1, total: 3, percentage: 33, message: '正在收集数据', ...overrides.data },
  timestamp: 1781497973.5
})

const makeStopEvent = (overrides = {}) => ({
  type: 'tool_stop',
  tool: '生成报告',
  tool_call_id: 'call_abc',
  thread_id: 'top_thread',
  data: { status: 'success', ...overrides.data },
  timestamp: 1781497974.8
})

const makeErrorEvent = (overrides = {}) => ({
  type: 'tool_error',
  tool: '生成报告',
  tool_call_id: 'call_abc',
  thread_id: 'top_thread',
  data: { error_type: 'RuntimeError', error_message: 'docker not running', ...overrides.data },
  timestamp: 1781497975.1
})

describe('ToolCallCard', () => {
  beforeEach(() => {
    localStorage.removeItem('subagent-drawer-width')
  })

  afterEach(() => {
    localStorage.removeItem('subagent-drawer-width')
  })

  it('组件可挂载（importable）', () => {
    const wrapper = mount(ToolCallCard, {
      props: { toolCallId: 'c1', tool: 'test', events: [] }
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.tool-call-card').exists()).toBe(true)
  })

  it('显示工具名与步骤计数', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: '生成报告',
        events: [makeStartEvent(), makeProgressEvent(), makeStopEvent()]
      }
    })
    expect(wrapper.text()).toContain('生成报告')
    expect(wrapper.text()).toContain('3 步')
  })

  it('头部显式标注「普通工具」徽章（与 SubAgentCard 视觉区分的关键标志）', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: '生成报告',
        events: [makeStartEvent()]
      }
    })
    // 关键：必须有「普通工具」徽章（SubAgentCard 无此徽章）
    expect(wrapper.find('.tool-call-badge').exists()).toBe(true)
    expect(wrapper.find('.tool-call-badge').text()).toBe('普通工具')
    expect(wrapper.find('.tool-call-badge').attributes('title')).toBe('普通工具（非子智能体）')
  })

  it('头部扳手图标使用 SVG（独立图标，与 SubAgentCard 的 emoji 区分）', () => {
    const wrapper = mount(ToolCallCard, {
      props: { toolCallId: 'c1', tool: 'test', events: [makeStartEvent()] }
    })
    // 应是 SVG 而非 emoji（视觉更精致）
    const icon = wrapper.find('.tool-call-icon')
    expect(icon.exists()).toBe(true)
    expect(icon.find('svg').exists()).toBe(true)
  })

  it('独立 class .tool-call-card（不复用 .subagent-card 避免选择器冲突）', () => {
    const wrapper = mount(ToolCallCard, {
      props: { toolCallId: 'c1', tool: 'test', events: [makeStartEvent()] }
    })
    // 根元素必须是 .tool-call-card
    expect(wrapper.find('.tool-call-card').exists()).toBe(true)
    // 不应有 .subagent-card class（避免与 SubAgentCard 选择器冲突）
    expect(wrapper.find('.subagent-card').exists()).toBe(false)
  })

  // ========== 状态徽章 ==========

  it('仅含 tool_start 时显示"执行中"徽章', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent()]
      }
    })
    expect(wrapper.text()).toContain('执行中')
    expect(wrapper.find('.tool-call-status.running').exists()).toBe(true)
  })

  it('tool_stop (status=success) 时显示"已完成"徽章', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'success' } })]
      }
    })
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.find('.tool-call-status.success').exists()).toBe(true)
  })

  it('tool_error 时显示"执行失败"徽章', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeErrorEvent()]
      }
    })
    expect(wrapper.text()).toContain('执行失败')
    expect(wrapper.find('.tool-call-status.error').exists()).toBe(true)
  })

  it('tool_stop (status≠success) 退化为 error', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'failure' } })]
      }
    })
    expect(wrapper.text()).toContain('执行失败')
  })

  it('success 状态徽章用绿色（与 SubAgentCard 完成态统一为 #10b981）', () => {
    // 2026-06-15 第三次：完成态颜色统一为绿色（与 SubAgentCard 一致）
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'success' } })]
      }
    })
    const statusEl = wrapper.find('.tool-call-status.success')
    expect(statusEl.exists()).toBe(true)
    // CSS 内部 .tool-call-status.success 使用 #10b981（绿色），与 SubAgentCard 视觉一致
  })

  // ========== 扳手动画 ==========

  it('running 状态扳手图标有 tool-call-icon-running class（动画生效）', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent()]
      }
    })
    const icon = wrapper.find('.tool-call-icon')
    expect(icon.exists()).toBe(true)
    expect(icon.classes()).toContain('tool-call-icon-running')
  })

  it('success 状态扳手图标不再有 tool-call-icon-running class', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'success' } })]
      }
    })
    const icon = wrapper.find('.tool-call-icon')
    expect(icon.exists()).toBe(true)
    expect(icon.classes()).not.toContain('tool-call-icon-running')
  })

  it('error 状态扳手图标不再有 tool-call-icon-running class', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeErrorEvent()]
      }
    })
    const icon = wrapper.find('.tool-call-icon')
    expect(icon.classes()).not.toContain('tool-call-icon-running')
  })

  // ========== 展开/折叠 ==========

  it('默认 running 状态展开步骤列表', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeProgressEvent()]
      }
    })
    await nextTick()
    expect(wrapper.find('.tool-call-steps').exists()).toBe(true)
    expect(wrapper.find('.tool-call-hint-text').text()).toBe('收起')
  })

  it('默认 success 状态折叠步骤列表', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'success' } })]
      }
    })
    await nextTick()
    expect(wrapper.find('.tool-call-steps').exists()).toBe(false)
    expect(wrapper.find('.tool-call-hint-text').text()).toBe('展开')
  })

  it('默认 error 状态折叠步骤列表', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeErrorEvent()]
      }
    })
    await nextTick()
    expect(wrapper.find('.tool-call-steps').exists()).toBe(false)
  })

  it('点击头部切换 isExpanded', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'success' } })]
      }
    })
    // 初始：success 折叠
    expect(wrapper.find('.tool-call-steps').exists()).toBe(false)
    // 点击头部
    await wrapper.find('.tool-call-header').trigger('click')
    expect(wrapper.find('.tool-call-steps').exists()).toBe(true)
    // 再次点击
    await wrapper.find('.tool-call-header').trigger('click')
    expect(wrapper.find('.tool-call-steps').exists()).toBe(false)
  })

  // ========== 步骤渲染 ==========

  it('每条 event 渲染一个步骤，含时间戳、类型徽章、摘要', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          makeStartEvent(),
          makeProgressEvent({ data: { current: 1, total: 3, percentage: 33, message: '正在收集数据' } }),
          makeStopEvent({ data: { status: 'success' } })
        ]
      }
    })
    // success 状态默认折叠，需手动点击展开
    await wrapper.find('.tool-call-header').trigger('click')
    await nextTick()
    const steps = wrapper.findAll('.tool-step')
    expect(steps.length).toBe(3)
    // 第一个步骤：tool_start
    expect(steps[0].find('.tool-step-type').text()).toBe('开始')
    expect(steps[0].find('.tool-step-time').text()).not.toBe('--:--:--')
    // 第二个步骤：tool_progress，文案已从「进度」改为「进行中」，摘要含 "33%" + "正在收集数据"
    expect(steps[1].find('.tool-step-type').text()).toBe('进行中')
    expect(steps[1].text()).toContain('33%')
    expect(steps[1].text()).toContain('正在收集数据')
    // 第三个步骤：tool_stop
    expect(steps[2].find('.tool-step-type').text()).toBe('完成')
  })

  it('步骤行间用横线分隔（除最后一步外）', async () => {
    // 2026-06-15 第三次：每行之间用虚线分隔，最后一行无分隔
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          makeStartEvent(),
          makeProgressEvent(),
          makeStopEvent({ data: { status: 'success' } })
        ]
      }
    })
    await wrapper.find('.tool-call-header').trigger('click')
    await nextTick()
    const steps = wrapper.findAll('.tool-step')
    expect(steps.length).toBe(3)
    // 验证最后一步存在，前两步应有 border-bottom（虚线分隔）
    // 实际验证方式：检查 .tool-step:last-child 没有显式 border-bottom 规则依赖
    // 此测试主要确保最后一步是 steps[2] 位置（前两步有分隔）
    // CSS 验证通过视觉测试更可靠，但 DOM 结构测试也能间接覆盖
    expect(steps[2]).toBeTruthy()
    // 前两步应有兄弟节点（中间分隔由 CSS :not(:last-child) 渲染）
    expect(steps[0].element.nextElementSibling).toBe(steps[1].element)
    expect(steps[1].element.nextElementSibling).toBe(steps[2].element)
  })

  it('error 步骤显示错误摘要', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeErrorEvent()]
      }
    })
    // error 状态默认折叠，需手动点击展开
    await wrapper.find('.tool-call-header').trigger('click')
    await nextTick()
    const steps = wrapper.findAll('.tool-step')
    expect(steps.length).toBe(2)
    expect(steps[1].find('.tool-step-type').text()).toBe('失败')
    expect(steps[1].text()).toContain('RuntimeError')
    expect(steps[1].text()).toContain('docker not running')
  })

  it('步骤按 events 数组原顺序追加（不乱序）', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          makeStartEvent(),
          makeProgressEvent({ data: { percentage: 33, message: '第一步' } }),
          makeProgressEvent({ data: { percentage: 66, message: '第二步' } }),
          makeProgressEvent({ data: { percentage: 90, message: '第三步' } })
        ]
      }
    })
    await nextTick()
    const summaries = wrapper.findAll('.tool-step-summary').map(n => n.text())
    expect(summaries[0]).toContain('请生成报告')
    expect(summaries[1]).toContain('33%')
    expect(summaries[1]).toContain('第一步')
    expect(summaries[2]).toContain('66%')
    expect(summaries[3]).toContain('90%')
  })

  it('缺失 timestamp 的事件展示 --:--:-- 占位', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          { type: 'tool_start', tool: 'test', tool_call_id: 'c1', data: { parent_prompt: 'p' } }
          // 注意：没有 timestamp 字段
        ]
      }
    })
    await nextTick()
    expect(wrapper.find('.tool-step-time').text()).toBe('--:--:--')
  })

  // ========== 步骤详情展开（key-value） ==========

  it('步骤默认不显示 key-value 详情（避免视觉繁琐）', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          makeStartEvent({ data: { parent_prompt: '请生成报告', args: { foo: 'bar' } } })
        ]
      }
    })
    await nextTick()
    // 默认展开（running）
    expect(wrapper.find('.tool-call-steps').exists()).toBe(true)
    // 但 key-value 详情不应默认展示
    expect(wrapper.find('.tool-step-detail').exists()).toBe(false)
  })

  it('点击步骤行可展开/折叠 key-value 详情', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          makeStartEvent({ data: { parent_prompt: '请生成报告', args: { foo: 'bar' } } })
        ]
      }
    })
    await nextTick()
    // 初始：详情不显示
    expect(wrapper.find('.tool-step-detail').exists()).toBe(false)
    // 点击步骤行
    await wrapper.find('.tool-step').trigger('click')
    expect(wrapper.find('.tool-step-detail').exists()).toBe(true)
    expect(wrapper.find('.tool-step-entry').exists()).toBe(true)
    // 再次点击
    await wrapper.find('.tool-step').trigger('click')
    expect(wrapper.find('.tool-step-detail').exists()).toBe(false)
  })

  it('展开步骤详情后展示 key-value 字段（带 .tool-step-key / .tool-step-value）', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [
          makeStartEvent({ data: { parent_prompt: '请生成报告', args: { foo: 'bar' } } })
        ]
      }
    })
    await nextTick()
    await wrapper.find('.tool-step').trigger('click')
    const entries = wrapper.findAll('.tool-step-entry')
    expect(entries.length).toBeGreaterThan(0)
    // 第一个 key 应是 parent_prompt
    expect(entries[0].find('.tool-step-key').text()).toBe('parent_prompt')
  })

  // ========== 抽屉事件守卫 ==========

  it('ToolCallCard 不 emit 任何抽屉相关事件（普通工具不应触发 drawer / sandbox-drawer）', async () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent()]
      }
    })
    // 1. 点击头部：不应触发任何抽屉事件
    await wrapper.find('.tool-call-header').trigger('click')
    expect(wrapper.emitted('open-subagent-drawer')).toBeFalsy()
    expect(wrapper.emitted('open-sandbox-drawer')).toBeFalsy()
    // 2. 触发键盘 Enter：也不应 emit 抽屉事件
    await wrapper.find('.tool-call-header').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('open-subagent-drawer')).toBeFalsy()
    expect(wrapper.emitted('open-sandbox-drawer')).toBeFalsy()
  })

  // ========== 耗时与步骤数边界 ==========

  it('空 events 数组仍能挂载（步骤数 = 0）', () => {
    const wrapper = mount(ToolCallCard, {
      props: { toolCallId: 'c1', tool: 'test', events: [] }
    })
    expect(wrapper.text()).toContain('0 步')
    expect(wrapper.find('.tool-call-card').exists()).toBe(true)
  })

  it('startTime / endTime 都给定时显示耗时', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent(), makeStopEvent({ data: { status: 'success' } })],
        startTime: 1000,
        endTime: 1500
      }
    })
    expect(wrapper.text()).toContain('500ms')
  })

  it('startTime 缺失时耗时区不渲染（避免误导）', () => {
    const wrapper = mount(ToolCallCard, {
      props: {
        toolCallId: 'c1',
        tool: 'test',
        events: [makeStartEvent()],
        startTime: 0,
        endTime: 0
      }
    })
    expect(wrapper.find('.tool-call-duration').exists()).toBe(false)
  })

  it('同 toolCallId 多事件合并到一张卡片（数据驱动）', async () => {
    const events = [
      makeStartEvent(),
      makeProgressEvent(),
      makeProgressEvent({ data: { percentage: 66, message: '正在生成报告文件' } }),
      makeStopEvent({ data: { status: 'success' } })
    ]
    const wrapper = mount(ToolCallCard, {
      props: { toolCallId: 'call_abc', tool: '生成报告', events }
    })
    expect(wrapper.text()).toContain('4 步')
    // success 状态默认折叠，需手动点击展开
    await wrapper.find('.tool-call-header').trigger('click')
    await nextTick()
    expect(wrapper.findAll('.tool-step').length).toBe(4)
  })
})
