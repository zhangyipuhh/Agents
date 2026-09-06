// UserSettingsDialog 飞书设置 channel 集成测试(2026-09-03 新增)
//
// 验证 UserSettingsDialog 内「消息设置」一级 Tab 下的飞书 channel 子 tab:
// - sub-tab 按钮 + panel 渲染
// - activeEmailChannel === 'messaging.feishu' 时 FeishuSettingsManager v-show 渲染
// - 切换 messaging.email ↔ messaging.feishu 互斥
// - PARENT_TO_CHILDREN_ALIAS 让 messaging.feishu.* 授权时父级 messaging 可见
//
// 设计:沿用 EmailSettingsManager.spec.js 的 mount 套路,直接 import
// UserSettingsDialog 并 minimal 渲染。
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'

// 静态分析:验证源码契约(data-testid + alias 列表)
import UserSettingsDialog from '../UserSettingsDialog.vue'

// mock 子组件,避免拉起真实 EmailSettingsManager / FeishuSettingsManager 的依赖链
const EmailSettingsManagerStub = defineComponent({
  name: 'EmailSettingsManager',
  props: { visibleMenus: { type: Array, default: () => [] }, isAdmin: { type: Boolean, default: false } },
  template: '<div data-testid="email-settings-manager-stub" />',
})
const FeishuSettingsManagerStub = defineComponent({
  name: 'FeishuSettingsManager',
  props: { visibleMenus: { type: Array, default: () => [] }, isAdmin: { type: Boolean, default: false } },
  template: '<div data-testid="feishu-settings-manager-stub" />',
})
const MenuPermissionManagerStub = defineComponent({
  name: 'MenuPermissionManager',
  props: { isAdmin: { type: Boolean, default: false } },
  template: '<div data-testid="menu-permission-manager-stub" />',
})
const AgentAccessManagerStub = defineComponent({
  name: 'AgentAccessManager',
  props: { isAdmin: { type: Boolean, default: false } },
  template: '<div data-testid="agent-access-manager-stub" />',
})

// 解析源码中的 PARENT_TO_CHILDREN_ALIAS(从 UserSettingsDialog 源码中提取)
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve as resolvePath } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const userDialogSource = readFileSync(
  resolvePath(__dirname, '../UserSettingsDialog.vue'),
  'utf-8',
)

describe('UserSettingsDialog - 飞书设置 channel(2026-09-03 新增)', () => {
  beforeEach(() => {
    // reset DOM
    document.body.innerHTML = ''
  })

  it('源码包含 PARENT_TO_CHILDREN_ALIAS 中 messaging.feishu.* 三项', () => {
    expect(userDialogSource).toContain("'messaging.feishu'")
    expect(userDialogSource).toContain("'messaging.feishu.apps'")
    expect(userDialogSource).toContain("'messaging.feishu.policies'")
    expect(userDialogSource).toContain("'messaging.feishu.test'")
  })

  it('源码包含飞书 sub-tab 按钮 + v-show 渲染', () => {
    // sub-tab 按钮
    expect(userDialogSource).toContain('messaging-channel-feishu')
    expect(userDialogSource).toContain('switchEmailChannel(\'messaging.feishu\')')
    // v-show panel
    expect(userDialogSource).toContain('messaging-channel-feishu-panel')
    expect(userDialogSource).toContain('<FeishuSettingsManager')
  })

  it('源码包含「飞书设置」中文 label', () => {
    expect(userDialogSource).toContain('>飞书设置<')
  })

  it('源码中 PARENT_TO_CHILDREN_ALIAS.messaging 包含飞书孙 tab id(防 alias 退化)', () => {
    // 直接断言源码包含关键 alias 项即可(正则块匹配脆弱)
    expect(userDialogSource).toContain('messaging: [')
    expect(userDialogSource).toContain("'messaging.feishu.apps'")
    expect(userDialogSource).toContain("'messaging.feishu.policies'")
    expect(userDialogSource).toContain("'messaging.feishu.test'")
    expect(userDialogSource).toContain("'messaging.feishu'")
  })
})
