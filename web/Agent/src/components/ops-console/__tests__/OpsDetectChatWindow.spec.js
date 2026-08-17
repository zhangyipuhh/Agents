// -*- coding:utf-8 -*-
/**
 * OpsDetectChatWindow 组件测试（2026-08-17 新增）。
 *
 * 覆盖：
 *   - 纯函数：buildDetectSessionId 格式 / buildDetectOverrides businessName 优先与兜底；
 *   - 组件：onMounted 自动调 chatStream（agent_name=project + 固定问题 + referenced_servers）、
 *     SSE 流式渲染、HTTP 403 错误横幅、unmount 时 triggerAbort + reader.cancel；
 *   - UI 契约：不渲染用户问题气泡 / 不渲染最大化按钮。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// mock api.js：chatStream 返回可控假流；triggerAbort 记录调用
const { chatStreamMock, triggerAbortMock, cancelMock, readQueue } = vi.hoisted(() => ({
  chatStreamMock: vi.fn(),
  triggerAbortMock: vi.fn(async () => ({ status: 'not_found' })),
  cancelMock: vi.fn(),
  readQueue: [],
}))
vi.mock('../../../utils/api.js', () => ({
  chatStream: chatStreamMock,
  triggerAbort: triggerAbortMock,
}))

import OpsDetectChatWindow, {
  DETECT_QUESTION,
  DETECT_AGENT_NAME,
  buildDetectSessionId,
  buildDetectOverrides,
} from '../OpsDetectChatWindow.vue'

const baseWin = { open: true, max: false, x: 10, y: 10, z: 1 }
const srv = { id: 1, name: 'MyA', businessName: 'biz-A', serverType: 'linux' }

/** 构造一个按 readQueue 逐段吐 SSE 字节的假 ReadableStream。 */
function fakeStream() {
  return {
    getReader: () => ({
      read: async () => (readQueue.length
        ? { done: false, value: readQueue.shift() }
        : { done: true, value: undefined }),
      cancel: cancelMock,
    }),
  }
}

function sse(text) {
  return new TextEncoder().encode(text)
}

describe('纯函数契约', () => {
  it('test_build_detect_session_id_format session_id 格式 ops-detect:{id}:{ts}', () => {
    expect(buildDetectSessionId({ id: 7 }, 123)).toBe('ops-detect:7:123')
    expect(buildDetectSessionId({}, 1)).toBe('ops-detect:unknown:1')
  })

  it('test_build_detect_overrides_prefers_business_name override 优先取 businessName', () => {
    expect(buildDetectOverrides(srv)).toEqual({
      referenced_servers: [{ name: 'biz-A', server_type: 'linux' }],
    })
  })

  it('test_build_detect_overrides_fallback_to_name 无 businessName 时兜底卡片 name', () => {
    expect(buildDetectOverrides({ id: 2, name: 'biz-B', serverType: 'windows' })).toEqual({
      referenced_servers: [{ name: 'biz-B', server_type: 'windows' }],
    })
  })

  it('test_build_detect_overrides_empty_name_returns_empty 空名返回空对象', () => {
    expect(buildDetectOverrides({ id: 3 })).toEqual({})
  })
})

describe('OpsDetectChatWindow 组件', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    readQueue.length = 0
    chatStreamMock.mockImplementation(async () => fakeStream())
  })

  it('test_component_importable 组件与命名导出可 import', () => {
    expect(OpsDetectChatWindow).toBeTruthy()
    expect(typeof DETECT_QUESTION).toBe('string')
    expect(DETECT_AGENT_NAME).toBe('project')
  })

  it('test_onmounted_calls_chat_stream_with_fixed_contract onMounted 自动调 chatStream 并携带固定契约', async () => {
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    expect(chatStreamMock).toHaveBeenCalledTimes(1)
    const [sid, message, attachments, resume, agentName, projectId, extras] = chatStreamMock.mock.calls[0]
    expect(sid).toMatch(/^ops-detect:1:\d+$/)
    expect(message).toBe('按照两部分回答，1.根据最新服务器的巡检记录分析问题并提出后续的优化建议，2查询最近2天的巡检记录分析最近趋势并进行总结')
    expect(attachments).toEqual([])
    expect(resume).toBeNull()
    expect(agentName).toBe('project')
    expect(projectId).toBeNull()
    expect(extras).toEqual({ referenced_servers: [{ name: 'biz-A', server_type: 'linux' }] })
    wrapper.unmount()
  })

  it('test_sse_stream_renders_text SSE message 事件逐段渲染到回答区', async () => {
    chatStreamMock.mockImplementation(async () => {
      readQueue.push(
        sse('data: {"type":"message","content":"## 一、问题分析"}\n\n'),
        sse('data: {"type":"message","content":"磁盘使用率偏高"}\n\n'),
        sse('data: {"type":"end"}\n\n'),
      )
      return fakeStream()
    })
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    const answer = wrapper.find('.detect-answer')
    expect(answer.html()).toContain('问题分析')
    expect(answer.html()).toContain('磁盘使用率偏高')
    wrapper.unmount()
  })

  it('test_http_error_shows_banner chatStream 抛 403 时显示错误横幅', async () => {
    const err = new Error("无权使用智能体 'project'")
    err.status = 403
    err.detail = "无权使用智能体 'project'"
    chatStreamMock.mockRejectedValue(err)
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    expect(wrapper.find('.detect-error').exists()).toBe(true)
    expect(wrapper.find('.detect-error').text()).toContain('无权使用智能体')
    wrapper.unmount()
  })

  it('test_unmount_aborts_stream unmount 时 triggerAbort + reader.cancel', async () => {
    // 流永不 done，保证 unmount 时 reader 仍存活
    chatStreamMock.mockImplementation(async () => ({
      getReader: () => ({
        read: () => new Promise(() => {}),
        cancel: cancelMock,
      }),
    }))
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    wrapper.unmount()
    expect(triggerAbortMock).toHaveBeenCalledTimes(1)
    expect(triggerAbortMock.mock.calls[0][0]).toMatch(/^ops-detect:1:/)
    expect(cancelMock).toHaveBeenCalled()
  })

  // -------- UI 契约（2026-08-17 新增） --------
  it('test_no_question_bubble UI 不渲染用户问题气泡（只输出答案）', async () => {
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    expect(wrapper.find('.detect-question').exists()).toBe(false)
    wrapper.unmount()
  })

  it('test_no_maximize_button UI 不渲染最大化按钮（仅关闭按钮）', async () => {
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    expect(wrapper.find('.win-control--max').exists()).toBe(false)
    expect(wrapper.find('.win-control--close').exists()).toBe(true)
    wrapper.unmount()
  })

  // -------- 加载占位（2026-08-17 新增） --------
  it('test_loading_placeholder_during_streaming_before_first_event 流式挂起时显示心跳占位', async () => {
    // reader.read 永不 resolve，模拟"流式发起但首段未到"
    chatStreamMock.mockImplementation(async () => ({
      getReader: () => ({
        read: () => new Promise(() => {}),
        cancel: cancelMock,
      }),
    }))
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    // 心跳占位存在且文案正确
    const empty = wrapper.find('.detect-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('正在分析服务器巡检数据')
    // 真实回答卡片与错误横幅均不渲染（互斥）
    expect(wrapper.find('.detect-answer-card').exists()).toBe(false)
    expect(wrapper.find('.detect-error').exists()).toBe(false)
    wrapper.unmount()
  })

  it('test_placeholder_hides_after_first_sse_event 首段 SSE 到达后占位让位给回答卡片', async () => {
    chatStreamMock.mockImplementation(async () => {
      readQueue.push(
        sse('data: {"type":"message","content":"hi"}\n\n'),
        sse('data: {"type":"end"}\n\n'),
      )
      return fakeStream()
    })
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    expect(wrapper.find('.detect-empty').exists()).toBe(false)
    expect(wrapper.find('.detect-answer-card').exists()).toBe(true)
    expect(wrapper.find('.detect-answer').text()).toContain('hi')
    wrapper.unmount()
  })

  it('test_error_banner_wins_over_placeholder 错误横幅优先级高于占位与答案', async () => {
    const err = new Error('网络错误')
    err.status = 500
    err.detail = '后端超时'
    chatStreamMock.mockRejectedValue(err)
    const wrapper = mount(OpsDetectChatWindow, { props: { win: baseWin, server: srv } })
    await flushPromises()
    expect(wrapper.find('.detect-error').exists()).toBe(true)
    expect(wrapper.find('.detect-error').text()).toContain('后端超时')
    expect(wrapper.find('.detect-empty').exists()).toBe(false)
    expect(wrapper.find('.detect-answer-card').exists()).toBe(false)
    wrapper.unmount()
  })
})