/**
 * InputBox 上传文件与发送流程测试（2026-07-07 改造）
 *
 * 覆盖新行为：
 *   1. 选择文件后仅本地记录，不上传、不创建 session，并立即锁定项目选择器。
 *   2. 必须有文本才能发送；仅选文件时发送按钮不触发任何上传/会话操作。
 *   3. 发送时携带当前 projectId 创建 session，再统一上传文件，最后 emit send。
 *   4. 删除所有文件后解除项目选择器锁定。
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

const mockUploadResult = {
  files: [{ filename: 'test.txt', stored_path: '/tmp/test.md', file_type: 'md' }]
}

vi.mock('../../utils/api.js', () => ({
  uploadFileInChunks: vi.fn(() => Promise.resolve(mockUploadResult)),
  formatFileSize: vi.fn((size) => `${size} bytes`),
  getFileExtension: vi.fn((name) => {
    const parts = name.split('.')
    return parts.length > 1 ? parts.pop() : ''
  }),
  refreshToken: vi.fn(() => Promise.resolve('fake-token')),
  fetchAgentList: vi.fn(() => Promise.resolve([])),
  deleteAttachments: vi.fn(() => Promise.resolve())
}))

describe('InputBox 文件上传与项目锁定（2026-07-07 改造）', () => {
  it('test_inputbox_locks_project_on_file_select 选择文件后立即锁定项目选择器', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: '',
        isStreaming: false,
        currentProject: null,
        ensureSession: vi.fn(() => Promise.resolve('sid_select_001'))
      }
    })
    await flushPromises()

    expect(wrapper.emitted('project-lock-change')).toBeFalsy()

    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    wrapper.vm.addFiles([file])
    await flushPromises()

    expect(wrapper.emitted('project-lock-change')).toBeTruthy()
    expect(wrapper.emitted('project-lock-change')[0]).toEqual([true])
  })

  it('test_inputbox_cannot_send_files_only 仅选文件无文本时不触发会话或上传', async () => {
    const ensureSession = vi.fn(() => Promise.resolve('sid_no_send'))
    const wrapper = mount(InputBox, {
      props: {
        sessionId: '',
        isStreaming: false,
        currentProject: null,
        ensureSession
      }
    })
    await flushPromises()

    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    wrapper.vm.addFiles([file])
    await flushPromises()

    // 无文本时 canSend 应为 false，handleSend 直接返回
    expect(wrapper.vm.canSend).toBe(false)
    wrapper.vm.handleSend()
    await flushPromises()

    expect(ensureSession).not.toHaveBeenCalled()
    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('test_inputbox_uploads_on_send_with_text_and_files 有文本+文件时发送才上传并 emit send', async () => {
    const ensureSession = vi.fn(() => Promise.resolve('sid_send_001'))
    const wrapper = mount(InputBox, {
      props: {
        sessionId: '',
        isStreaming: false,
        currentProject: null,
        ensureSession
      }
    })
    await flushPromises()

    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    wrapper.vm.addFiles([file])
    wrapper.vm.inputValue = '测试发送'
    await flushPromises()

    wrapper.vm.handleSend()
    await flushPromises()

    expect(ensureSession).toHaveBeenCalled()
    expect(wrapper.emitted('send')).toBeTruthy()
    const [sendText, sendFiles] = wrapper.emitted('send')[0]
    expect(sendText).toBe('测试发送')
    expect(sendFiles).toHaveLength(1)
    expect(sendFiles[0].original_name).toBe('test.txt')
  })

  it('test_inputbox_ensure_session_receives_current_project_id 发送时 ensureSession 携带当前项目 ID', async () => {
    const ensureSession = vi.fn(() => Promise.resolve('sid_proj_001'))
    const wrapper = mount(InputBox, {
      props: {
        sessionId: '',
        isStreaming: false,
        currentProject: { id: 42, name: '测试项目', uuid: 'proj-uuid' },
        ensureSession
      }
    })
    await flushPromises()

    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    wrapper.vm.addFiles([file])
    wrapper.vm.inputValue = '带项目发送'
    await flushPromises()

    wrapper.vm.handleSend()
    await flushPromises()

    expect(ensureSession).toHaveBeenCalledWith(42)
  })

  it('test_inputbox_unlocks_project_on_remove_all 删除所有文件后解除项目选择器锁定', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_remove_001',
        isStreaming: false,
        currentProject: null
      }
    })
    await flushPromises()

    const fileItem = {
      id: 'f3',
      file: new File(['c'], 'a.txt', { type: 'text/plain' }),
      name: 'a.txt',
      size: 1,
      type: 'text/plain',
      extension: 'txt',
      status: 'success',
      progress: 100,
      uploadResult: { filename: 'a.txt', stored_path: '/tmp/a.md', file_type: 'md' },
      errorMsg: '',
      cancelFn: null
    }
    wrapper.vm.selectedFiles.push(fileItem)
    await flushPromises()

    wrapper.vm.removeFile(fileItem)
    await flushPromises()

    const events = wrapper.emitted('project-lock-change')
    expect(events).toBeTruthy()
    expect(events[events.length - 1]).toEqual([false])
  })
})
