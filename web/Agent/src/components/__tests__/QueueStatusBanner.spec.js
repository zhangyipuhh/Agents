/**
 * QueueStatusBanner 组件测试（2026-06-15 新增）
 *
 * 覆盖场景：
 * - 组件可正常 import（P0）
 * - idle 状态默认隐藏
 * - waiting 状态显示，含位置 + 排队文本
 * - ready 状态立即触发淡出动画
 * - 缺失可选字段不报错
 * - 连续 waiting 更新时使用最新 snapshot
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import QueueStatusBanner from '../QueueStatusBanner.vue'

const DEFAULT_QUEUE_STATUS = () => ({
  event: 'idle',
  waitingCount: 0,
  activeCount: 0,
  maxConcurrency: 0,
  position: 0,
  timestamp: 0
})

const WAITING_QUEUE_STATUS = (overrides = {}) => ({
  event: 'waiting',
  waitingCount: 2,
  activeCount: 1,
  maxConcurrency: 1,
  position: 2,
  timestamp: 1700000000,
  ...overrides
})

describe('QueueStatusBanner', () => {
  // 1. P0：可导入
  it('test_banner_importable', () => {
    expect(QueueStatusBanner).toBeDefined()
    expect(typeof QueueStatusBanner).toBe('object')
  })

  // 2. P1：event=idle + isVisible=false → 隐藏
  it('test_banner_hidden_when_event_idle', async () => {
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: DEFAULT_QUEUE_STATUS(), isVisible: false }
    })
    await nextTick()
    expect(wrapper.find('.queue-status-banner').exists()).toBe(false)
  })

  // 3. P1：event=waiting + isVisible=true → 显示
  it('test_banner_visible_when_event_waiting', async () => {
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: WAITING_QUEUE_STATUS(), isVisible: true }
    })
    await nextTick()
    expect(wrapper.find('.queue-status-banner').exists()).toBe(true)
  })

  // 4. P1：waiting 状态显示排队人数文本
  it('test_banner_shows_waiting_count_text', async () => {
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: WAITING_QUEUE_STATUS(), isVisible: true }
    })
    await nextTick()
    const text = wrapper.find('.queue-text').text()
    expect(text).toContain('1/1')
    expect(text).toContain('前面还有 1 位')
  })

  // 5. P1：position badge 显示当前位置
  it('test_banner_shows_position_text', async () => {
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: WAITING_QUEUE_STATUS({ position: 3 }), isVisible: true }
    })
    await nextTick()
    const badge = wrapper.find('.queue-position-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('3')
  })

  // 6. P1：ready 事件 → showBanner 应为 false
  it('test_banner_fade_out_transition_when_event_ready', async () => {
    const readyStatus = WAITING_QUEUE_STATUS({ event: 'ready' })
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: readyStatus, isVisible: false }
    })
    await nextTick()
    expect(wrapper.find('.queue-status-banner').exists()).toBe(false)
  })

  // 7. P2：active/max 显示比例
  it('test_banner_shows_active_over_max_ratio', async () => {
    const wrapper = mount(QueueStatusBanner, {
      props: {
        queueStatus: WAITING_QUEUE_STATUS({
          activeCount: 3,
          maxConcurrency: 5
        }),
        isVisible: true
      }
    })
    await nextTick()
    expect(wrapper.find('.queue-text').text()).toContain('3/5')
  })

  // 8. P2：缺失可选字段不报错
  it('test_banner_handles_missing_optional_fields', async () => {
    const minimalStatus = { event: 'waiting' }
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: minimalStatus, isVisible: true }
    })
    await nextTick()
    expect(wrapper.find('.queue-status-banner').exists()).toBe(true)
    expect(wrapper.find('.queue-text').exists()).toBe(true)
  })

  // 9. P1：ready 事件触发后 isVisible 变 false 不再渲染 banner
  it('test_ready_event_does_not_reset_visible_until_transition_complete', async () => {
    const waitingStatus = WAITING_QUEUE_STATUS()
    const wrapper = mount(QueueStatusBanner, {
      props: { queueStatus: waitingStatus, isVisible: true }
    })
    await nextTick()
    expect(wrapper.find('.queue-status-banner').exists()).toBe(true)

    // 模拟 ready 事件：父组件应将 isVisible 置 false
    await wrapper.setProps({
      queueStatus: { ...waitingStatus, event: 'ready' },
      isVisible: false
    })
    await nextTick()
    expect(wrapper.find('.queue-status-banner').exists()).toBe(false)
  })

  // 10. P2：连续 waiting 更新时，组件使用最新 snapshot
  it('test_banner_queues_consecutive_waiting_updates_with_latest_snapshot', async () => {
    const wrapper = mount(QueueStatusBanner, {
      props: {
        queueStatus: WAITING_QUEUE_STATUS({ position: 5 }),
        isVisible: true
      }
    })
    await nextTick()
    expect(wrapper.find('.queue-position-badge').text()).toBe('5')

    // 第二次更新：位置递减
    await wrapper.setProps({
      queueStatus: WAITING_QUEUE_STATUS({ position: 2, waitingCount: 1 }),
      isVisible: true
    })
    await nextTick()
    expect(wrapper.find('.queue-position-badge').text()).toBe('2')
    expect(wrapper.find('.queue-text').text()).toContain('前面还有 1 位')
  })
})