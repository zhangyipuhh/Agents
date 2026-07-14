/**
 * SubAgentSuggestionStrip 组件测试（2026-07-14 新增）
 *
 * 覆盖：
 *   1. 组件可被导入（importable）
 *   2. agents 非空时渲染对应胶囊条；空数组时不渲染
 *   3. 点击胶囊 → emit('select', agent)
 *   4. disabled=true 时按钮 disabled，点击不发 select
 *   5. 使用 display_name 时优先显示 display_name，否则回退到 name
 *
 * 测试策略：mount + 直接断言 DOM 结构 / 事件 / 属性。
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import SubAgentSuggestionStrip from '../SubAgentSuggestionStrip.vue'

beforeAll(() => {
  // happy-dom 不提供 alert()，避免无关告警
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

const SAMPLE_AGENTS = [
  { name: 'project', display_name: '项目智能体' },
  { name: 'contract_doc', display_name: '合同文档' },
  { name: 'map' } // 仅 name，无 display_name
]

describe('SubAgentSuggestionStrip 子智能体快选条（2026-07-14 新增）', () => {
  it('test_sub_agent_strip_importable 组件可被 import', () => {
    expect(SubAgentSuggestionStrip).toBeDefined()
  })

  it('test_sub_agent_strip_renders_only_when_agents_non_empty 仅当 agents 非空时渲染胶囊条', () => {
    // 空数组 → 不渲染
    const wrapperEmpty = mount(SubAgentSuggestionStrip, {
      props: { agents: [] }
    })
    expect(wrapperEmpty.find('.sub-agent-strip').exists()).toBe(false)

    // 非空 → 渲染对应数量的胶囊
    const wrapperFilled = mount(SubAgentSuggestionStrip, {
      props: { agents: SAMPLE_AGENTS }
    })
    const chips = wrapperFilled.findAll('.sub-agent-chip')
    expect(chips).toHaveLength(SAMPLE_AGENTS.length)
  })

  it('test_sub_agent_strip_emits_select_on_click 点击胶囊触发 select 事件，载荷为被点击的 agent', async () => {
    const wrapper = mount(SubAgentSuggestionStrip, {
      props: { agents: SAMPLE_AGENTS }
    })
    const chips = wrapper.findAll('.sub-agent-chip')
    expect(chips).toHaveLength(SAMPLE_AGENTS.length)

    // 点击第 2 个胶囊（contract_doc）
    await chips[1].trigger('click')

    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted).toHaveLength(1)
    // 载荷必须是原 agent 对象
    expect(emitted[0][0]).toEqual({ name: 'contract_doc', display_name: '合同文档' })
  })

  it('test_sub_agent_strip_respects_disabled disabled=true 时按钮 disabled 且点击不发 select', async () => {
    const wrapper = mount(SubAgentSuggestionStrip, {
      props: {
        agents: SAMPLE_AGENTS,
        disabled: true
      }
    })
    const chips = wrapper.findAll('.sub-agent-chip')
    // 全部按钮应带 disabled 属性 + .disabled class
    chips.forEach((chip) => {
      expect(chip.attributes('disabled')).toBeDefined()
      expect(chip.classes()).toContain('disabled')
    })

    // 点击不应触发 emit（因为 handleClick 在 props.disabled 时短路 return）
    await chips[0].trigger('click')
    expect(wrapper.emitted('select')).toBeFalsy()
  })

  it('test_sub_agent_strip_prefers_display_name 文本展示优先用 display_name 否则回退到 name', () => {
    const wrapper = mount(SubAgentSuggestionStrip, {
      props: { agents: SAMPLE_AGENTS }
    })
    const labels = wrapper.findAll('.chip-label').map((node) => node.text())
    expect(labels[0]).toBe('项目智能体')
    expect(labels[1]).toBe('合同文档')
    expect(labels[2]).toBe('map') // 回退
  })
})
