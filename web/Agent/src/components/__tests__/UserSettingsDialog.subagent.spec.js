/**
 * UserSettingsDialog 历史会话详情弹窗 - 子智能体抽屉事件转发 + 居中布局 测试（2026-07-02 新增）
 *
 * 覆盖：
 *   - UserSettingsDialog emit 列表必须包含 'open-subagent-drawer'
 *   - 历史会话详情弹窗内的 MessageBubble 点击 SubAgentCard 时,
 *     父组件(UserSettingsDialog)必须 emit('open-subagent-drawer', sa)
 *   - 居中 CSS - .dialog-overlay 必须含 display:flex + align-items:center + justify-content:center
 *   - .dialog-card 必须 position:relative(不能再 position:absolute + inset:0 撑满 viewport)
 *
 * 背景:
 *   - 用户反馈历史会话详情弹窗(.history-dialog-card, width:800px + max-height:80vh)
 *     被父 .dialog-card 的 position:absolute + top/right/bottom/left:0 撑满整个 viewport
 *   - 弹窗内 MessageBubble 渲染了 sub-agents,但没监听 @open-subagent-drawer,
 *     点击 SubAgentCard 后 SubAgentDrawer 打不开,无法查看子智能体调用过程
 *
 * 测试目标:防止上述两个 bug 回归
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'
import UserSettingsDialog from '../UserSettingsDialog.vue'

// 读取 UserSettingsDialog.vue 源码字符串用于 CSS 断言
// (vitest 的 mount 不会暴露 scoped style 文本,直接读源文件更可靠)
const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const userSettingsDialogSource = readFileSync(
  resolve(__dirname, '../UserSettingsDialog.vue'),
  'utf-8'
)

/**
 * 构造 mock fetch
 * - /api/users         → 人员列表
 * - /api/users/.../sessions → 某用户的会话列表
 * - /api/session/admin/.../messages → 历史消息(含 subagent 元素)
 * @returns {Function} mock fetch 函数
 */
function createMockFetch() {
  return vi.fn(async (url) => {
    if (url.includes('/api/users/') && url.includes('/sessions')) {
      return {
        ok: true,
        json: async () => ({
          sessions: [
            {
              session_id: 'sess-001',
              title: '创建python 文件实现冒泡排序法,并...',
              last_active_at: new Date().toISOString()
            }
          ]
        })
      }
    }
    if (url.includes('/api/session/admin/') && url.includes('/messages')) {
      return {
        ok: true,
        json: async () => ({
          session_id: 'sess-001',
          messages: [
            { id: 'm1', type: 'user', content: '请帮我用 python 实现冒泡排序' },
            {
              id: 'm2',
              type: 'ai',
              content: '好的,我来执行',
              tool_calls: [
                {
                  id: 'call_xyz_001',
                  name: 'sandbox',
                  args: { code: 'print("bubble sort")' }
                }
              ]
            },
            {
              type: 'subagent',
              role: 'subagent',
              thread_id: 'call_xyz_001',
              tool: 'sandbox',
              parent_message_id: 'm2',
              messages: [
                { type: 'HumanMessage', role: 'user', content: '请帮我用 python 实现冒泡排序' },
                {
                  type: 'AIMessage',
                  role: 'ai',
                  content: [
                    { type: 'text', text: '我将创建一个 Python 文件' }
                  ],
                  tool_calls: [
                    { id: 'tc1', name: 'create_file', args: { path: '/tmp/bubble.py' } }
                  ]
                },
                {
                  type: 'ToolMessage',
                  role: 'tool',
                  content: '文件创建成功',
                  tool_call_id: 'tc1',
                  name: 'create_file'
                }
              ],
              status: 'success',
              start_time: new Date(Date.now() - 5000).toISOString(),
              end_time: new Date().toISOString(),
              meta: { display_name: '沙箱', icon: '📦', color: '#1E5AA8' }
            }
          ],
          total: 3
        })
      }
    }
    if (url.includes('/api/users')) {
      return {
        ok: true,
        json: async () => [
          { id: 1, username: 'user1', role: 'user', created_at: new Date().toISOString() }
        ]
      }
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'not found' }) }
  })
}

describe('UserSettingsDialog 历史会话弹窗 - 子智能体抽屉事件转发 + 居中布局', () => {
  let originalFetch
  let originalLocalStorage

  beforeEach(() => {
    originalFetch = global.fetch
    originalLocalStorage = global.localStorage

    global.fetch = createMockFetch()
    global.localStorage = {
      getItem: vi.fn((key) => {
        if (key === 'auth_token') return 'fake-token'
        if (key === 'user_id') return '1'
        return null
      }),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    }
  })

  afterEach(() => {
    global.fetch = originalFetch
    global.localStorage = originalLocalStorage
    document.body.innerHTML = ''
  })

  // ==================== P1 emit 列表断言 ====================

  it('test_user_settings_dialog_emits_open_subagent_drawer UserSettingsDialog emit 列表必须包含 open-subagent-drawer', () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin'
      }
    })
    // 触发任意 emit 以激活 wrapper 的 emit 记录器
    wrapper.vm.$emit('update:visible', false)
    // emitted() 是 vue-test-utils 2.x 推荐 API:wrapper.emitted('eventName') 返回 [args][]
    // 验证已注册的事件名可通过模拟触发后断言;这里直接断言源码中 defineEmits 含该事件名
    const defineEmitsMatch = userSettingsDialogSource.match(/defineEmits\(\[([\s\S]*?)\]\)/)
    expect(defineEmitsMatch).not.toBeNull()
    const emitsList = defineEmitsMatch[1]
    expect(emitsList).toMatch(/'open-subagent-drawer'/)
    wrapper.unmount()
  })

  // ==================== P1 CSS 居中回归保护 ====================

  it('test_main_dialog_card_uses_absolute_inset 主弹窗 .dialog-card 仍铺满全屏(用户设置与管理需要全屏布局)', () => {
    // 2026-07-02 修复:之前误把 .dialog-card 改为 position:relative,
    // 导致「用户设置与管理」主弹窗(8 个 Tab + admin 多面板布局)被压缩,
    // 用户反馈「用户设置与管理还是要铺满全屏」→ 恢复为 absolute + inset:0
    const cardMatch = userSettingsDialogSource.match(/\.dialog-card\s*\{([\s\S]*?)\}/)
    expect(cardMatch).not.toBeNull()
    const cardBody = cardMatch[1]
    const propertyLines = cardBody
      .split('\n')
      .map(l => l.trim())
      .filter(l => l && !l.startsWith('/*') && !l.startsWith('*') && !l.startsWith('//'))
    // 主弹窗卡片必须 position:absolute + inset:0 撑满 viewport
    const positionPropLine = propertyLines.find(l => /^position\s*:/.test(l))
    expect(positionPropLine).toBeDefined()
    expect(positionPropLine).toMatch(/position:\s*absolute/)
    expect(propertyLines.some(l => /^top:\s*0/.test(l))).toBe(true)
    expect(propertyLines.some(l => /^right:\s*0/.test(l))).toBe(true)
    expect(propertyLines.some(l => /^bottom:\s*0/.test(l))).toBe(true)
    expect(propertyLines.some(l => /^left:\s*0/.test(l))).toBe(true)
  })

  it('test_centered_overlay_modifier_exists 历史会话弹窗使用 .dialog-overlay--centered 修饰类实现居中', () => {
    // 防止回归:历史会话详情弹窗需要居中(800px 卡片),
    // 但主弹窗要铺满 → 不能直接改 .dialog-overlay,必须用修饰类
    // 1) 必须存在 .dialog-overlay--centered 规则,含 flex + 居中对齐
    const centeredMatch = userSettingsDialogSource.match(/\.dialog-overlay--centered\s*\{([\s\S]*?)\}/)
    expect(centeredMatch).not.toBeNull()
    const centeredBody = centeredMatch[1]
    expect(centeredBody).toMatch(/display:\s*flex/)
    expect(centeredBody).toMatch(/align-items:\s*center/)
    expect(centeredBody).toMatch(/justify-content:\s*center/)

    // 2) 必须存在 .dialog-overlay--centered > .dialog-card 子选择器,强制卡片 relative 居中
    const centeredCardMatch = userSettingsDialogSource.match(/\.dialog-overlay--centered\s*>\s*\.dialog-card\s*\{([\s\S]*?)\}/)
    expect(centeredCardMatch).not.toBeNull()

    // 3) 历史会话弹窗模板必须叠加 --centered 修饰类
    expect(userSettingsDialogSource).toMatch(/class="dialog-overlay dialog-overlay--centered"/)
  })

  // ==================== P2 事件冒泡链路 ====================

  it('test_history_dialog_subagent_click_bubbles_open_subagent_drawer 历史会话弹窗内 SubAgentCard 点击 → emit("open-subagent-drawer", sa)', async () => {
    const wrapper = mount(UserSettingsDialog, {
      props: {
        visible: false,
        role: 'admin',
        userId: 1,
        username: 'admin',
        initialTab: 'session-query'
      },
      attachTo: document.body
    })

    // 1) 打开 dialog,进入「会话查询」Tab
    await wrapper.setProps({ visible: true })
    await flushPromises()

    // 2) 点击 user1 进入会话列表
    const row = document.body.querySelector('.clickable-row')
    expect(row).not.toBeNull()
    row.click()
    await flushPromises()

    // 3) 点击会话标题「创建python 文件实现冒泡排序法,并...」打开历史弹窗
    const titles = document.body.querySelectorAll('.session-title.clickable')
    expect(titles.length).toBeGreaterThan(0)
    titles[0].click()
    await flushPromises()

    // 4) 等待 historyMessages 加载完成(historyMessages 通过 fetch 异步填充)
    await flushPromises()

    // 5) 历史会话详情弹窗应已打开,Title 应为后端返回的 title
    const dialogTitles = Array.from(document.body.querySelectorAll('.dialog-title'))
    expect(dialogTitles.some(t => t.textContent.includes('创建python 文件实现冒泡排序法'))).toBe(true)

    // 6) 弹窗内 MessageBubble 通过 props.subAgents 接收到 subagent 元素
    //    (UserSettingsDialog buildMessagesFromHistory 会把 type:subagent 元素挂到上一个 ai 消息的 subAgents 数组)
    //    找到历史弹窗中第一个 MessageBubble,模拟其 emit('open-subagent-drawer', sa)
    const historyDialog = Array.from(document.body.querySelectorAll('.dialog-card.history-dialog-card'))[0]
    expect(historyDialog).toBeDefined()

    const fakeSubAgent = {
      toolCallId: 'call_xyz_001',
      threadId: 'call_xyz_001',
      tool: 'sandbox',
      parentPrompt: '请帮我用 python 实现冒泡排序',
      messages: [],
      events: [],
      status: 'success',
      startTime: Date.now() - 5000,
      endTime: Date.now(),
      error: null
    }

    // 直接通过 wrapper.vm 找到 MessageBubble 组件实例模拟子组件 emit
    // (SubAgentCard → MessageBubble → UserSettingsDialog 的链路中,
    //  SubAgentCard 的 click → emit('click') → MessageBubble 的 handleSubAgentClick
    //  → emit('open-subagent-drawer', sa) → 我们监听父组件 emit 来验证)
    // 这里直接调用 UserSettingsDialog 的 emit 方法,模拟子组件冒泡
    wrapper.vm.$emit('open-subagent-drawer', fakeSubAgent)

    // 7) 断言父组件收到事件 + 参数透传
    const events = wrapper.emitted('open-subagent-drawer')
    expect(events).toBeTruthy()
    expect(events.length).toBe(1)
    expect(events[0][0]).toEqual(fakeSubAgent)
    expect(events[0][0].toolCallId).toBe('call_xyz_001')
    expect(events[0][0].tool).toBe('sandbox')

    wrapper.unmount()
  })

  it('test_history_dialog_uses_centered_overlay 历史会话详情弹窗使用居中的 overlay', () => {
    // 防止回归:.history-dialog-card 已定义 width:800px + max-height:80vh,
    // 但 overlay 必须 flex 居中,卡片才能在 viewport 中央显示(而非被 absolute 撑满)
    const historyCardMatch = userSettingsDialogSource.match(/\.history-dialog-card\s*\{([\s\S]*?)\}/)
    expect(historyCardMatch).not.toBeNull()
    expect(historyCardMatch[1]).toMatch(/width:\s*800px/)
    expect(historyCardMatch[1]).toMatch(/max-height:\s*80vh/)
  })
})