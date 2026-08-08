// -*- coding:utf-8 -*-
/**
 * AgentWorkspace FilePreviewModal 自动弹出 bug 验证测试（临时）
 *
 * 根因假设（R1）：chatWorkspace 是普通对象（非 reactive），
 * 模板里 ws.filePreviewOpen 在 AgentWorkspace 不被自动解包，
 * ref 对象传给 FilePreviewModal 的 isOpen prop（Boolean 类型），
 * 被强制转 true → 弹窗始终显示。
 *
 * 本测试用真实 chatWorkspace 普通对象 + mount AgentWorkspace，
 * 断言 FilePreviewModal 子组件接收到的 isOpen prop 实际值。
 * - 若 isOpen 是 true → 根因 R1 确认
 * - 若 isOpen 是 false → 根因 R1 排除，需查 R3（缓存/HMR）
 *
 * 修复后会转为正式回归测试（见 .trae/documents/file-preview-modal-auto-open-bug.md）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, reactive } from 'vue'
import AgentWorkspace from '../AgentWorkspace.vue'
import FilePreviewModal from '../../components/FilePreviewModal.vue'

/**
 * 构造一个「普通对象」形态的 chatWorkspace（与 App.vue 当前实现一致）
 * 关键：外层不调用 reactive() 包裹，内部所有状态是顶层 ref / reactive 对象
 */
function buildPlainChatWorkspace() {
  const messages = reactive([])
  const sessionId = reactive({ value: '' })
  const isStreaming = reactive({ value: false })
  const toolStopPending = ref(false)
  const currentAttachments = ref([])
  const approvalMode = ref(false)
  const approvalData = ref({ questions: [] })
  const currentProject = ref(null)
  const agentName = ref(null)
  const agentDisplayName = ref('')
  const allowedAgents = ref([])
  const sessionTitle = ref('')
  const queueStatus = ref({
    event: 'idle', waitingCount: 0, activeCount: 0,
    maxConcurrency: 0, position: 0, timestamp: 0
  })
  const subAgentDrawerVisible = ref(false)
  const currentSubAgent = ref(null)
  const sessionFileDrawerVisible = ref(false)
  const sessionFileTree = ref(null)
  const sessionFileDrawerLoading = ref(false)
  const sessionFileDrawerError = ref('')
  const filePreviewOpen = ref(false)             // ← 关键 ref，默认 false
  const filePreviewData = ref({                  // ← 嵌套 ref
    content: '', fileType: 'txt', fileName: '',
    loading: false, previewMode: 'text', fileUrl: ''
  })
  const dislikeDialog = ref({                    // ← 嵌套 ref 里的字段
    visible: false, messageId: '', sessionId: '',
    messageContent: '', aiReply: '', agentName: ''
  })

  return {
    messages, sessionId, isStreaming, toolStopPending,
    currentAttachments, approvalMode, approvalData,
    currentProject, agentName, agentDisplayName, allowedAgents,
    sessionTitle, queueStatus,
    subAgentDrawerVisible, currentSubAgent,
    sessionFileDrawerVisible, sessionFileTree,
    sessionFileDrawerLoading, sessionFileDrawerError,
    filePreviewOpen, filePreviewData, dislikeDialog,
    isAdmin: ref(false),
    canEditProject: ref(true),
    newSession: vi.fn(),
    handleSendMessage: vi.fn(),
    handleStopMessage: vi.fn(),
    handleApprovalSubmit: vi.fn(),
    handleApprovalCancel: vi.fn(),
    handleRegenerate: vi.fn(),
    handleLike: vi.fn(),
    handleDislike: vi.fn(),
    handleCopy: vi.fn(),
    handleOpenSessionFileDrawer: vi.fn(),
    handleCloseFilePreview: vi.fn(),
    handleAgentSwitched: vi.fn(),
    handleProjectSelectNone: vi.fn(),
    handleProjectPick: vi.fn(),
    handleProjectCreate: vi.fn(),
    openCreateProjectDialog: vi.fn(),
    openPickProjectDialog: vi.fn(),
    openSubAgentDrawer: vi.fn(),
    closeSubAgentDrawer: vi.fn(),
    handleTagSelect: vi.fn(),
    handleToolAction: vi.fn(),
    ensureSessionForFirstOp: vi.fn(),
    handleDislikeSubmitted: vi.fn(),
    setProjectLockedByUpload: vi.fn(),
  }
}

describe('AgentWorkspace 弹窗默认值验证（2026-08-08 bug 排查）', () => {
  beforeEach(() => {
    // stub 复杂的子组件，仅保留 FilePreviewModal 用于断言
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('R1 验证：chatWorkspace 为普通对象时，FilePreviewModal 的 isOpen prop 实际值', async () => {
    // 模拟 App.vue 当前的实现：chatWorkspace 是普通对象字面量（未用 reactive 包裹）
    const ws = buildPlainChatWorkspace()
    // 通过 provide 注入
    const { provide } = await import('vue')
    // 因为 AgentWorkspace 用 inject('chatWorkspace')，我们需要在 mount 时 provide
    const wrapper = mount(AgentWorkspace, {
      global: {
        provide: { chatWorkspace: ws },
        stubs: {
          ChatArea: true,
          InputBox: true,
          HumanApprovalBox: true,
          QueueStatusBanner: true,
          SessionFileDrawer: true,
          DislikeDialog: true,
          Teleport: true,  // 防止 FilePreviewModal Teleport 跑挂测试
          Transition: true,
        },
      },
    })
    await flushPromises()

    // 找到 FilePreviewModal 子组件（不通过 Teleport，因为我们 stub 了 Teleport）
    const modal = wrapper.findComponent(FilePreviewModal)
    expect(modal.exists()).toBe(true)

    const actualIsOpen = modal.props('isOpen')
    const actualContent = modal.props('content')
    const actualFileName = modal.props('fileName')

    // 控制台输出便于诊断
    // eslint-disable-next-line no-console
    console.log('[诊断] ws.filePreviewOpen =', ws.filePreviewOpen,
      '(type:', typeof ws.filePreviewOpen, ')')
    // eslint-disable-next-line no-console
    console.log('[诊断] ws.filePreviewData =', ws.filePreviewData,
      '(type:', typeof ws.filePreviewData, ')')
    // eslint-disable-next-line no-console
    console.log('[诊断] FilePreviewModal.props.isOpen =', actualIsOpen)
    // eslint-disable-next-line no-console
    console.log('[诊断] FilePreviewModal.props.content =', actualContent)
    // eslint-disable-next-line no-console
    console.log('[诊断] FilePreviewModal.props.fileName =', actualFileName)

    // 核心断言：初始状态下，所有弹窗/drawer/dialog 的 prop 都应该是 false/空
    expect(modal.props('isOpen')).toBe(false)
    expect(actualContent).toBe('')
  })

  it('R1 反向：chatWorkspace 改为 reactive() 包裹后，prop 自动解包', async () => {
    // 同样的状态，但用 reactive() 包裹外层 —— 模拟「方案 A Step 1」修复后
    const wsRaw = buildPlainChatWorkspace()
    const ws = reactive(wsRaw)
    const wrapper = mount(AgentWorkspace, {
      global: {
        provide: { chatWorkspace: ws },
        stubs: {
          ChatArea: true,
          InputBox: true,
          HumanApprovalBox: true,
          QueueStatusBanner: true,
          SessionFileDrawer: true,
          DislikeDialog: true,
          Teleport: true,
          Transition: true,
        },
      },
    })
    await flushPromises()

    const modal = wrapper.findComponent(FilePreviewModal)
    expect(modal.exists()).toBe(true)
    expect(modal.props('isOpen')).toBe(false)
    expect(modal.props('content')).toBe('')
  })

  it('handleSessionFileClick 调用后，isOpen 变 true（验证事件链）', async () => {
    const ws = reactive(buildPlainChatWorkspace())
    ws.handleSessionFileClick = vi.fn().mockImplementation(async (file) => {
      ws.filePreviewOpen = true
      ws.filePreviewData = {
        content: file?.content || 'test',
        fileType: 'txt',
        fileName: file?.name || 'test.txt',
        loading: false,
        previewMode: 'text',
        fileUrl: ''
      }
    })
    const wrapper = mount(AgentWorkspace, {
      global: {
        provide: { chatWorkspace: ws },
        stubs: {
          ChatArea: true,
          InputBox: true,
          HumanApprovalBox: true,
          QueueStatusBanner: true,
          SessionFileDrawer: true,
          DislikeDialog: true,
          Teleport: true,
          Transition: true,
        },
      },
    })
    await flushPromises()

    const modalBefore = wrapper.findComponent(FilePreviewModal)
    expect(modalBefore.props('isOpen')).toBe(false)

    // 模拟 SessionFileDrawer 的 file-click 事件
    await modalBefore.vm.$emit?.('close')  // noop
    await ws.handleSessionFileClick({ name: 'foo.txt', path: 'foo.txt', content: 'hello' })
    await flushPromises()

    // 重新查询（响应式更新后）
    const modalAfter = wrapper.findComponent(FilePreviewModal)
    expect(modalAfter.props('isOpen')).toBe(true)
    expect(modalAfter.props('fileName')).toBe('foo.txt')
  })
})