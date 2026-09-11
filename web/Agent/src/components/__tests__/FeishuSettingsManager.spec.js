// FeishuSettingsManager 单元测试(2026-09-03 新增,2026-09-07 风格独立化改造)
//
// 测试策略:沿用 EmailSettingsManager.spec.js 的源码静态契约风格,
// 验证 FeishuSettingsManager.vue 关键结构(data-testid / 内部 3 Tab /
// ACL 双重门 / 高度链填满 / 独立样式块等),不在浏览器中挂载真组件(避免 mock
// fetchNotificationChannels / createNotificationChannel 等 11 个 API)。
//
// 源码静态契约(防回归):
// - 文件存在
// - 3 个 tab id: TAB_APPS / TAB_POLICIES / TAB_TEST
// - 3 个 ACL menuId: messaging.feishu.{apps,policies,test}
// - props: visibleMenus (Array) + isAdmin (Boolean)
// - data-testid: feishu-tab-{apps,policies,test} / feishu-panel-{...}
// - 应用设置 Tab 有: name / app_id / app_secret / log_level / agent_name / enabled
// 2026-09-07：移除 default_receive_id / receiver_username / default_receive_id_type
// 2026-09-11：移除 is_default 字段（按 channel.config.agent_name 自动路由）
// - 发送策略 Tab 有: target_type / chat_id / chat_type / chat_name / agent_name / 模板字段
// - 发送测试 Tab 有: channel_id / target_id / content
// - 高度链填满: 独立的 .feishu-settings-manager scoped 样式(2026-09-07 起不再借用邮件 scoped)
// - 内部滚动契约:tabpanel flex 链 + .feishu-form 自滚动 + .policies-layout 解封
// - 2026-09-07: 模板移除 class="email-*",新增独立 .feishu-settings-manager / .feishu-form /
//   .feishu-settings-empty 类;内联 style="margin-top: 12px; width: 100%;" 迁入 .create-channel-btn;
//   "secondary-btn danger" 合并到 .danger-btn;test tab 表单 .field-row 改为 .form-field.full 单栏;
//   新增 <style scoped> 块镜像邮件样式 + 飞书独有 .badge.default / .badge.disabled 样式
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve as resolvePath } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolvePath(__dirname, '../FeishuSettingsManager.vue'),
  'utf-8',
)

describe('FeishuSettingsManager - 文件存在 + 模块结构', () => {
  it('组件文件存在且 <script setup> + <template> + 完整结构', () => {
    expect(source).toContain('<script setup>')
    expect(source).toContain('</script>')
    expect(source).toContain('<template>')
    expect(source).toContain('</template>')
  })

  it('2026-09-07 起组件含独立 <style scoped> 块（不再借用邮件 scoped 样式）', () => {
    expect(source).toContain('<style scoped>')
    expect(source).toContain('</style>')
  })

  it('导出 const TAB_APPS / TAB_POLICIES / TAB_TEST 三常量', () => {
    expect(source).toMatch(/const\s+TAB_APPS\s*=\s*['"]apps['"]/)
    expect(source).toMatch(/const\s+TAB_POLICIES\s*=\s*['"]policies['"]/)
    expect(source).toMatch(/const\s+TAB_TEST\s*=\s*['"]test['"]/)
  })

  it('TAB_MENU_IDS 包含 3 个 ACL key', () => {
    expect(source).toContain("messaging.feishu.apps")
    expect(source).toContain("messaging.feishu.policies")
    expect(source).toContain("messaging.feishu.test")
  })

  it('props 包含 visibleMenus (Array) + isAdmin (Boolean)', () => {
    expect(source).toContain('visibleMenus:')
    expect(source).toContain('isAdmin:')
    expect(source).toMatch(/defineProps\s*\(\s*\{/)
  })

  it('模板根标签是 <section class="feishu-settings-manager">（2026-09-07 重命名）', () => {
    expect(source).toContain('class="feishu-settings-manager"')
  })

  it('2026-09-07 起模板不再出现 email-* 类名(空态 / 表单 / 根容器全部 feishu- 前缀)', () => {
    expect(source).not.toMatch(/class="email-/)
    expect(source).not.toMatch(/class="email-form/)
  })

  it('高度链填满契约(独立 scoped 样式,2026-09-07 起)', () => {
    expect(source).toContain('feishu-settings-manager')
    expect(source).toContain('role="tabpanel"')
    expect(source).toContain('feishu-form')
  })
})

describe('FeishuSettingsManager - 应用设置 Tab(apps)', () => {
  it('应用设置 panel data-testid 存在', () => {
    expect(source).toContain('feishu-panel-apps')
  })

  it('应用设置表单字段:name / app_id / app_secret / log_level / agent_name / enabled（2026-09-07 移除 default_receive_id* / receiver_username）', () => {
    expect(source).toContain('feishu-channel-name')
    expect(source).toContain('feishu-app-id')
    expect(source).toContain('feishu-app-secret')
    expect(source).toContain('feishu-log-level')
    expect(source).toContain('feishu-channel-agent')  // 实际 id（template 用 v-model="channelForm.agent_name"）
    // 2026-09-07：channel 已废弃 default_receive_id / receiver_username / default_receive_id_type
    expect(source).not.toContain('feishu-default-receive-id')
    expect(source).not.toContain('feishu-receiver-username')
  })

  it('包含 enabled 复选框（2026-09-11 移除 is_default）', () => {
    expect(source).toContain('feishu-channel-enabled')
    // 2026-09-11：is_default 复选框已清理（按 channel.config.agent_name 自动路由）
    expect(source).not.toContain('feishu-channel-is-default')
  })

  it('保存/测试连接/删除 按钮 data-testid 存在', () => {
    expect(source).toContain('feishu-save-channel-btn')
    expect(source).toContain('feishu-test-connection-btn')
    expect(source).toContain('feishu-create-channel-btn')
  })
})

describe('FeishuSettingsManager - 发送策略 Tab(policies)', () => {
  it('发送策略 panel data-testid 存在', () => {
    expect(source).toContain('feishu-panel-policies')
  })

  it('target 表单字段:name / target_type / chat_id / chat_type / chat_name + 模板字段', () => {
    // 2026-09-07 第二轮:target 不再绑 agent_name（前端 UI 仍保留 target_type 与模板字段;
    // 后续需清理 target 模板字段,见项目记忆 TODO）
    expect(source).toContain('feishu-target-name')
    expect(source).toContain('feishu-target-type')
    expect(source).toContain('feishu-chat-id')
    expect(source).toContain('feishu-chat-type')
    expect(source).toContain('feishu-chat-name')
    expect(source).toContain('feishu-target-subject-template')
    expect(source).toContain('feishu-target-body-template')
    expect(source).toContain('feishu-target-enabled')
    // 2026-09-07 第二轮：target 不绑 agent_name
    expect(source).not.toContain('feishu-target-agent')
  })

  it('target 保存按钮 + 应用切换器', () => {
    expect(source).toContain('feishu-save-target-btn')
    expect(source).toContain('feishu-policy-channel-select')
    expect(source).toContain('feishu-create-target-btn')
  })

  it('policies-layout 解封 + policy-editor / policy-list 样式', () => {
    expect(source).toContain('policies-layout')
    expect(source).toContain('policies-list')
    expect(source).toContain('policy-editor')
    expect(source).toContain('policy-item')
  })
})

describe('FeishuSettingsManager - 发送测试 Tab(test)', () => {
  it('发送测试 panel data-testid 存在', () => {
    expect(source).toContain('feishu-panel-test')
  })

  it('test 表单字段:channel_id / target_id / content', () => {
    expect(source).toContain('feishu-test-channel-select')
    expect(source).toContain('feishu-test-target-select')
    expect(source).toContain('feishu-test-content-textarea')
  })

  it('发送按钮 data-testid', () => {
    expect(source).toContain('feishu-send-test-btn')
  })
})

describe('FeishuSettingsManager - API 调用契约', () => {
  it('从 utils/api.js 导入 11 个通知 API 函数', () => {
    expect(source).toContain("from '../utils/api.js'")
    expect(source).toContain('fetchNotificationChannels')
    expect(source).toContain('fetchNotificationChannel')
    expect(source).toContain('createNotificationChannel')
    expect(source).toContain('updateNotificationChannel')
    expect(source).toContain('deleteNotificationChannel')
    expect(source).toContain('testNotificationChannelConnection')
    expect(source).toContain('fetchNotificationTargets')
    expect(source).toContain('createNotificationTarget')
    expect(source).toContain('updateNotificationTarget')
    expect(source).toContain('deleteNotificationTarget')
    expect(source).toContain('fetchNotificationAgents')
    expect(source).toContain('sendNotificationTest')
  })

  it('loadChannels() 在 onMounted 调用', () => {
    expect(source).toContain('loadChannels()')
    expect(source).toContain('onMounted')
  })

  it('loadAgents() 在 onMounted 调用', () => {
    expect(source).toContain('loadAgents()')
  })
})

describe('FeishuSettingsManager - 安全设计契约', () => {
  it('应用密钥显示契约:detail 不显示已保存密钥', () => {
    expect(source).toContain("channelForm.app_id = ''")
    expect(source).toContain("channelForm.app_secret = ''")
  })

  it('更新 channel 时 keep_existing_secret=true(留空不修改)', () => {
    expect(source).toContain('keep_existing_secret: true')
  })

  it('config.app_id / app_secret 留空 → 不覆盖', () => {
    // 注释中已说明 + 代码逻辑
    expect(source).toMatch(/if\s*\(channelForm\.app_id\.trim\(\)\)\s*updatePayload\.config\.app_id/)
    expect(source).toMatch(/if\s*\(channelForm\.app_secret\.trim\(\)\)\s*updatePayload\.config\.app_secret/)
  })

  it('agent_name 必填校验（2026-09-07 移除 receiver_username 必填）', () => {
    // 实际文案：'路由 Agent 不能为空（应用必须绑定一个智能体）'
    expect(source).toContain("路由 Agent 不能为空")
    expect(source).not.toContain("receiver_username 不能为空")
  })
})

describe('FeishuSettingsManager - 风格独立化(2026-09-07 落地)', () => {
  it('独立 <style scoped> 块存在 + 镜像邮件视觉规格的关键类名都在', () => {
    expect(source).toContain('<style scoped>')
    expect(source).toContain('.feishu-settings-manager')
    expect(source).toContain('.feishu-settings-empty')
    expect(source).toContain('.feishu-form')
    // 通用类(tab/btn/alert/policies-layout 等)镜像邮件
    expect(source).toContain('.tab.active')
    expect(source).toContain('.primary-btn')
    expect(source).toContain('.secondary-btn')
    expect(source).toContain('.danger-btn')
    expect(source).toContain('.alert.error')
    expect(source).toContain('.alert.success')
    expect(source).toContain('.policies-layout')
    expect(source).toContain('.policy-item.active')
    expect(source).toContain('.policy-editor')
    expect(source).toContain('.form-grid')
    expect(source).toContain('.field-row')
    expect(source).toContain('box-shadow: 0 0 0 3px')
  })

  it('飞书独有样式: 默认 / 禁用徽章 + 新建应用按钮', () => {
    expect(source).toContain('.badge')
    expect(source).toContain('.badge.default')
    expect(source).toContain('.badge.disabled')
    expect(source).toContain('.create-channel-btn')
  })

  it('模板不再含内联 style="margin-top: 12px; width: 100%;"(已迁入 .create-channel-btn)', () => {
    expect(source).not.toMatch(/style="margin-top:\s*12px;\s*width:\s*100%;/)
    expect(source).toContain('create-channel-btn')
  })

  it('删除按钮从 "secondary-btn danger" 合并到 .danger-btn', () => {
    expect(source).not.toContain('secondary-btn danger')
    // 两个删除按钮(应用/目标)都使用 danger-btn
    const dangerBtnCount = (source.match(/class="danger-btn"/g) || []).length
    expect(dangerBtnCount).toBeGreaterThanOrEqual(2)
  })

  it('test tab 表单使用 .form-field.full 单栏结构(与邮件发送测试一致)', () => {
    // 三个字段全部包在 form-field full label 中
    expect(source).toMatch(/class="form-field full"[\s\S]*?feishu-test-channel/)
    expect(source).toMatch(/class="form-field full"[\s\S]*?feishu-test-target/)
    expect(source).toMatch(/class="form-field full"[\s\S]*?feishu-test-content/)
  })
})
