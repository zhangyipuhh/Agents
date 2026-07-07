/**
 * InputBox 上传文件锁定事件测试（2026-07-06 新增）
 *
 * 覆盖：
 *   1. 文件上传成功后 emit project-lock-change(true)
 *   2. 删除所有成功上传的文件后 emit project-lock-change(false)
 *   3. ensureSession 回调被传入当前 projectId
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InputBox from '../InputBox.vue'

beforeAll(() => {
  if (typeof window !== 'undefined' && !window.alert) {
    window.alert = () => {}
  }
})

vi.mock('../../utils/api.js', () => ({
  uploadFileInChunks: vi.fn(() =>
    Promise.resolve({
      files: [{ filename: 'test.txt', stored_path: '/tmp/test.md', file_type: 'md' }]
    })
  ),
  formatFileSize: vi.fn((size) => `${size} bytes`),
  getFileExtension: vi.fn((name) => {
    const parts = name.split('.')
    return parts.length > 1 ? parts.pop() : ''
  }),
  refreshToken: vi.fn(() => Promise.resolve('fake-token')),
  fetchAgentList: vi.fn(() => Promise.resolve([])),
  deleteAttachments: vi.fn(() => Promise.resolve())
}))

describe('InputBox 上传文件 project-lock-change 事件（2026-07-06 新增）', () => {
  it('test_inputbox_emits_project_lock_change_true_on_upload_success 上传成功后 emit project-lock-change(true)', async () => {
    const ensureSession = vi.fn(() => Promise.resolve('sid_upload_001'))
    const wrapper = mount(InputBox, {
      props: {
        sessionId: '',
        isStreaming: false,
        currentProject: null,
        ensureSession
      }
    })
    await flushPromises()

    // 初始不应 emit
    expect(wrapper.emitted('project-lock-change')).toBeFalsy()

    const fileItem = {
      id: 'f1',
      file: new File(['content'], 'test.txt', { type: 'text/plain' }),
      name: 'test.txt',
      size: 7,
      type: 'text/plain',
      extension: 'txt',
      status: 'pending',
      progress: 0,
      uploadResult: null,
      errorMsg: '',
      cancelFn: null
    }

    // startUpload 内部通过 selectedFiles 查找当前文件项，需先加入列表
    wrapper.vm.selectedFiles.push(fileItem)
    wrapper.vm.startUpload(fileItem)
    await flushPromises()

    expect(wrapper.emitted('project-lock-change')).toBeTruthy()
    expect(wrapper.emitted('project-lock-change')[0]).toEqual([true])
  })

  it('test_inputbox_ensure_session_receives_current_project_id 上传时 ensureSession 携带当前项目 ID', async () => {
    const ensureSession = vi.fn(() => Promise.resolve('sid_upload_002'))
    const wrapper = mount(InputBox, {
      props: {
        sessionId: '',
        isStreaming: false,
        currentProject: { id: 42, name: '测试项目', uuid: 'proj-uuid' },
        ensureSession
      }
    })
    await flushPromises()

    const fileItem = {
      id: 'f2',
      file: new File(['content'], 'test.txt', { type: 'text/plain' }),
      name: 'test.txt',
      size: 7,
      type: 'text/plain',
      extension: 'txt',
      status: 'pending',
      progress: 0,
      uploadResult: null,
      errorMsg: '',
      cancelFn: null
    }

    wrapper.vm.startUpload(fileItem)
    await flushPromises()

    expect(ensureSession).toHaveBeenCalledWith(42)
  })

  it('test_inputbox_emits_project_lock_change_false_on_remove_all_success 删除所有成功文件后 emit project-lock-change(false)', async () => {
    const wrapper = mount(InputBox, {
      props: {
        sessionId: 'sid_remove_001',
        isStreaming: false,
        currentProject: null
      }
    })
    await flushPromises()

    // 直接注入一个成功文件
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

    // 触发删除
    wrapper.vm.removeFile(fileItem)
    await flushPromises()

    expect(wrapper.emitted('project-lock-change')).toBeTruthy()
    expect(wrapper.emitted('project-lock-change')[0]).toEqual([false])
  })
})
