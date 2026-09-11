<script setup>
/**
 * FeishuSettingsManager - 飞书设置管理组件（admin）
 *
 * 挂载位置（2026-09-03 新增，2026-09-07 第二轮修正）：与 EmailSettingsManager 对称,渲染在
 * 「消息设置」(messaging) 顶级 tab 下的 channel 子 tab 「飞书设置」(messaging.feishu) 内。
 * 菜单注册链路：messaging → messaging.feishu → messaging.feishu.{apps,policies,test}
 * 端点 ACL key 用 messaging.feishu.<sub>（详见 NotificationConfigService）
 *
 * 提供三个 Tab：
 * - 应用设置（apps）：飞书凭证组(多应用并存);每组含 app_id / app_secret / log_level /
 *   agent_name（应用绑定的智能体，必填）。2026-09-11 移除「设为默认应用」勾选——
 *   send_feishu_message 按 channel.config.agent_name 自动路由，不需要全局默认概念
 * - 发送策略（policies）：从 channels 列表选择应用,加 target(群 chat_id / chat_type / chat_name)
 *   + 模板字段（智能体由所属 channel 继承，不在 target 层重复设置）
 * - 发送测试（test）：选 channel → 选 target → 输入内容 → POST /api/notification/send-test
 *   发送交互式卡片到目标群
 *
 * 安全设计：
 * - 凭证字段在 GET 接口中返回空字符串(脱敏),前端"密钥留空"表示不修改
 * - 飞书 WebSocket 多实例(session_id 加 channel_id 命名空间)在后台生效
 * - 每个 channel 实例绑定的智能体从 channel.config.agent_name 派生
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  fetchNotificationChannels,
  fetchNotificationChannel,
  createNotificationChannel,
  updateNotificationChannel,
  deleteNotificationChannel,
  testNotificationChannelConnection,
  fetchNotificationTargets,
  createNotificationTarget,
  updateNotificationTarget,
  deleteNotificationTarget,
  fetchNotificationAgents,
  sendNotificationTest,
} from '../utils/api.js'

const TAB_APPS = 'apps'
const TAB_POLICIES = 'policies'
const TAB_TEST = 'test'

// 2026-09-03 ACL 双重门：tab 与后端 MENU_CATALOG 的子菜单 id 对齐
const TAB_MENU_IDS = {
  [TAB_APPS]: 'messaging.feishu.apps',
  [TAB_POLICIES]: 'messaging.feishu.policies',
  [TAB_TEST]: 'messaging.feishu.test',
}

// 全部 tab 元数据（label 由父组件 props.visibleMenus 过滤后渲染）
const ALL_TABS = [
  { id: TAB_APPS, label: '应用设置', menuId: TAB_MENU_IDS[TAB_APPS] },
  { id: TAB_POLICIES, label: '发送策略', menuId: TAB_MENU_IDS[TAB_POLICIES] },
  { id: TAB_TEST, label: '发送测试', menuId: TAB_MENU_IDS[TAB_TEST] },
]

const activeTab = ref(TAB_APPS)

// === 应用设置 Tab ===
// 2026-09-07 第二轮：channel = 飞书应用凭证 + 该应用绑定的智能体（agent_name 必填）
// - default_receive_id / default_receive_id_type 已迁出 channel（由 target.config 接管）
// - receiver_username 仍可在 channel 中配置（不强制，可由 settings.feishu_ws_receiver_username 兜底）
const channels = ref([])
const selectedChannel = ref(null)
const isEditingChannel = ref(false)
const isSavingChannel = ref(false)
const isTestingChannel = ref(false)
const channelMessage = ref('')
const channelError = ref('')
const channelForm = reactive({
  name: '',
  display_name: '',
  app_id: '',       // 明文（前端用），后端 Fernet 加密
  app_secret: '',   // 明文（前端用），后端 Fernet 加密
  log_level: 'INFO',
  agent_name: '',   // 2026-09-07 第二轮：飞书应用绑定的目标智能体（必填）
  enabled: true,
  // 2026-09-11：移除 is_default 字段。send_feishu_message 按 channel.config.agent_name
  // 自动路由（FeishuEndpointResolver），不再需要「设为默认应用」复选框，避免误导。
})

// === 发送策略 Tab ===
// 2026-09-07 第二轮：target 仅管接收方（chat_id / chat_type / chat_name）；
// agent_name 已迁出（智能体绑定收口在 channel 层）
const targets = ref([])
const selectedTarget = ref(null)
const isEditingTarget = ref(false)
const isSavingTarget = ref(false)
const targetMessage = ref('')
const targetError = ref('')
const agents = ref([])
const targetForm = reactive({
  channel_id: null,
  target_type: 'feishu.chat',
  name: '',
  config: {
    chat_id: '',
    chat_type: 'chat_id',
    chat_name: '',
  },
  subject_template: '',
  body_template: '',
  enabled: true,
})

// === 发送测试 Tab ===
const testForm = reactive({
  channel_id: null,
  target_id: null,
  content: '',
})
const isSendingTest = ref(false)
const testMessage = ref('')
const testError = ref('')

// === Props ===
const props = defineProps({
  visibleMenus: {
    type: Array,
    default: () => []
  },
  isAdmin: {
    type: Boolean,
    default: false
  }
})

const visibleSet = computed(() => new Set(props.visibleMenus || []))

const availableTabs = computed(() => {
  if (props.isAdmin) return ALL_TABS
  return ALL_TABS.filter(t => visibleSet.value.has(t.menuId))
})

const hasAnyAccess = computed(() => props.isAdmin || availableTabs.value.length > 0)

/**
 * 切换 Tab。
 * @param {string} tabId - Tab 标识。
 */
function switchTab(tabId) {
  if (activeTab.value === tabId) return
  activeTab.value = tabId
}

/**
 * 加载 channels 列表。
 */
async function loadChannels() {
  channelError.value = ''
  try {
    channels.value = await fetchNotificationChannels('feishu')
  } catch (err) {
    channelError.value = err.message
  }
}

/**
 * 加载智能体列表（channelForm.agent_name select 下拉用）。
 */
async function loadAgents() {
  try {
    agents.value = await fetchNotificationAgents()
  } catch (err) {
    console.warn('[FeishuSettingsManager] 加载智能体列表失败:', err.message)
  }
}

/**
 * 加载某 channel 下的 targets。
 * @param {number} channelId - 渠道 ID。
 */
async function loadTargets(channelId) {
  targetError.value = ''
  if (!channelId) {
    targets.value = []
    return
  }
  try {
    targets.value = await fetchNotificationTargets(channelId)
  } catch (err) {
    targetError.value = err.message
  }
}

/**
 * 开始新建 channel。
 */
function startCreateChannel() {
  selectedChannel.value = null
  isEditingChannel.value = true
  channelForm.name = ''
  channelForm.display_name = ''
  channelForm.app_id = ''
  channelForm.app_secret = ''
  channelForm.log_level = 'INFO'
  channelForm.agent_name = ''
  channelForm.enabled = true
  channelMessage.value = ''
  channelError.value = ''
}

/**
 * 选中已有 channel 进行编辑（拉取最新 detail,内部仍含加密字段为空串）。
 * @param {Object} ch - channel 对象。
 */
async function selectChannel(ch) {
  selectedChannel.value = ch
  isEditingChannel.value = true
  try {
    const detail = await fetchNotificationChannel(ch.id)
    channelForm.name = detail.name
    channelForm.display_name = detail.display_name || ''
    channelForm.app_id = ''  // 永远不显示已保存的密钥
    channelForm.app_secret = ''
    // 2026-09-07 第二轮：重新从 channel.config 读 agent_name
    channelForm.log_level = detail.config?.log_level || 'INFO'
    channelForm.agent_name = detail.config?.agent_name || ''
    channelForm.enabled = detail.enabled !== false
  } catch (err) {
    channelError.value = err.message
  }
  channelMessage.value = ''
  channelError.value = ''
}

/**
 * 保存 channel（新建或更新）。
 */
async function saveChannel() {
  channelError.value = ''
  channelMessage.value = ''
  if (!channelForm.name.trim()) {
    channelError.value = '应用名称不能为空'
    return
  }
  if (!selectedChannel.value) {
    // 新建：必填密钥
    if (!channelForm.app_id.trim() || !channelForm.app_secret.trim()) {
      channelError.value = '新建应用必须填写 App ID 与 App Secret'
      return
    }
  }
  // 2026-09-07 第二轮：channel 必填 agent_name（应用绑智能体）
  if (!channelForm.agent_name.trim()) {
    channelError.value = '路由 Agent 不能为空（应用必须绑定一个智能体）'
    return
  }
  isSavingChannel.value = true
  try {
    if (selectedChannel.value) {
      // 更新
      const updatePayload = {
        display_name: channelForm.display_name,
        enabled: channelForm.enabled,
        config: {
          log_level: channelForm.log_level,
          agent_name: channelForm.agent_name,
        },
        keep_existing_secret: true,
      }
      // 留空 → 不修改；非空 → 覆盖
      if (channelForm.app_id.trim()) updatePayload.config.app_id = channelForm.app_id
      if (channelForm.app_secret.trim()) updatePayload.config.app_secret = channelForm.app_secret
      await updateNotificationChannel(selectedChannel.value.id, updatePayload)
      channelMessage.value = '应用已更新'
    } else {
      // 新建
      await createNotificationChannel({
        channel_type: 'feishu',
        name: channelForm.name,
        display_name: channelForm.display_name,
        enabled: channelForm.enabled,
        config: {
          app_id: channelForm.app_id,
          app_secret: channelForm.app_secret,
          log_level: channelForm.log_level,
          agent_name: channelForm.agent_name,
        },
      })
      channelMessage.value = '应用已创建'
    }
    await loadChannels()
    cancelEditChannel()
  } catch (err) {
    channelError.value = err.message
  } finally {
    isSavingChannel.value = false
  }
}

/**
 * 取消编辑 channel。
 */
function cancelEditChannel() {
  isEditingChannel.value = false
  selectedChannel.value = null
}

/**
 * 删除 channel。
 * @param {Object} ch - channel 对象。
 */
async function removeChannel(ch) {
  if (!confirm(`确认删除应用「${ch.name}」？所有关联的 target 也会被级联删除。`)) return
  channelError.value = ''
  try {
    await deleteNotificationChannel(ch.id)
    channelMessage.value = '应用已删除'
    if (selectedChannel.value && selectedChannel.value.id === ch.id) {
      cancelEditChannel()
    }
    await loadChannels()
  } catch (err) {
    channelError.value = err.message
  }
}

/**
 * 测试 channel 凭证。
 */
async function testChannelConnection() {
  channelError.value = ''
  channelMessage.value = ''
  if (!selectedChannel.value) {
    channelError.value = '请先选中一个应用'
    return
  }
  isTestingChannel.value = true
  try {
    const result = await testNotificationChannelConnection(selectedChannel.value.id)
    if (result.success) {
      channelMessage.value = result.message || '凭证有效'
    } else {
      channelError.value = result.message || '凭证无效'
    }
  } catch (err) {
    channelError.value = err.message
  } finally {
    isTestingChannel.value = false
  }
}

// === Target CRUD ===

/**
 * 开始新建 target。
 */
function startCreateTarget() {
  selectedTarget.value = null
  isEditingTarget.value = true
  targetForm.channel_id = selectedChannel.value?.id || channels.value[0]?.id || null
  targetForm.target_type = 'feishu.chat'
  targetForm.name = ''
  targetForm.config = { chat_id: '', chat_type: 'chat_id', chat_name: '' }
  // 2026-09-07 第二轮：target 不再绑 agent_name
  targetForm.subject_template = ''
  targetForm.body_template = ''
  targetForm.enabled = true
  targetMessage.value = ''
  targetError.value = ''
}

/**
 * 选中已有 target 进行编辑。
 * @param {Object} t - target 对象。
 */
function selectTarget(t) {
  selectedTarget.value = t
  isEditingTarget.value = true
  targetForm.channel_id = t.channel_id
  targetForm.target_type = t.target_type
  targetForm.name = t.name
  targetForm.config = {
    chat_id: t.config?.chat_id || '',
    chat_type: t.config?.chat_type || 'chat_id',
    chat_name: t.config?.chat_name || '',
  }
  // 2026-09-07 第二轮：target 不再绑 agent_name（仍展示 channel 绑定的智能体）
  targetForm.subject_template = t.subject_template || ''
  targetForm.body_template = t.body_template || ''
  targetForm.enabled = t.enabled !== false
  targetMessage.value = ''
  targetError.value = ''
}

/**
 * 保存 target。
 */
async function saveTarget() {
  targetError.value = ''
  targetMessage.value = ''
  if (!targetForm.channel_id) {
    targetError.value = '请先选择应用'
    return
  }
  if (!targetForm.name.trim()) {
    targetError.value = '目标名称不能为空'
    return
  }
  if (!targetForm.config.chat_id.trim()) {
    targetError.value = 'chat_id 不能为空'
    return
  }
  isSavingTarget.value = true
  try {
    if (selectedTarget.value) {
      await updateNotificationTarget(selectedTarget.value.id, {
        target_type: targetForm.target_type,
        name: targetForm.name,
        config: targetForm.config,
        subject_template: targetForm.subject_template,
        body_template: targetForm.body_template,
        enabled: targetForm.enabled,
      })
      targetMessage.value = '目标已更新'
    } else {
      await createNotificationTarget(targetForm.channel_id, {
        target_type: targetForm.target_type,
        name: targetForm.name,
        config: targetForm.config,
        subject_template: targetForm.subject_template,
        body_template: targetForm.body_template,
        enabled: targetForm.enabled,
      })
      targetMessage.value = '目标已创建'
    }
    await loadTargets(targetForm.channel_id)
    cancelEditTarget()
  } catch (err) {
    targetError.value = err.message
  } finally {
    isSavingTarget.value = false
  }
}

/**
 * 取消编辑 target。
 */
function cancelEditTarget() {
  isEditingTarget.value = false
  selectedTarget.value = null
}

/**
 * 删除 target。
 * @param {Object} t - target 对象。
 */
async function removeTarget(t) {
  if (!confirm(`确认删除目标「${t.name}」？`)) return
  targetError.value = ''
  try {
    await deleteNotificationTarget(t.id)
    targetMessage.value = '目标已删除'
    if (selectedTarget.value && selectedTarget.value.id === t.id) {
      cancelEditTarget()
    }
    await loadTargets(t.channel_id)
  } catch (err) {
    targetError.value = err.message
  }
}

// === Test send ===

const filteredTestTargets = computed(() => {
  if (!testForm.channel_id) return []
  return targets.value.filter(t => t.channel_id === testForm.channel_id)
})

/**
 * 发送测试消息。
 */
async function sendTest() {
  testError.value = ''
  testMessage.value = ''
  if (!testForm.target_id) {
    testError.value = '请选择目标'
    return
  }
  if (!testForm.content.trim()) {
    testError.value = '消息内容不能为空'
    return
  }
  isSendingTest.value = true
  try {
    const result = await sendNotificationTest({
      target_id: testForm.target_id,
      channel_type: 'feishu',
      content: testForm.content,
    })
    if (result.success) {
      testMessage.value = `发送成功！message_id=${result.message_id || '(无)'};agent 回复依赖 WS 是否对该 channel 监听`
    } else {
      testError.value = result.error || '发送失败'
    }
  } catch (err) {
    testError.value = err.message
  } finally {
    isSendingTest.value = false
  }
}

onMounted(async () => {
  if (!hasAnyAccess.value) {
    console.warn('[FeishuSettingsManager] 用户未被授权任何 feishu-settings 子 tab,已跳过数据加载')
    return
  }
  // activeTab 默认值:第一个被授权的 tab
  if (availableTabs.value.length > 0 && !availableTabs.value.find(t => t.id === activeTab.value)) {
    activeTab.value = availableTabs.value[0].id
  }
  // 按 tab 授权加载数据
  const tasks = []
  const hasApps = props.isAdmin || visibleSet.value.has(TAB_MENU_IDS[TAB_APPS])
  const hasPolicies = props.isAdmin || visibleSet.value.has(TAB_MENU_IDS[TAB_POLICIES])
  const hasTest = props.isAdmin || visibleSet.value.has(TAB_MENU_IDS[TAB_TEST])
  if (hasApps || hasPolicies || hasTest) {
    tasks.push(loadChannels())
  }
  if (hasPolicies || hasTest) {
    tasks.push(loadAgents())
  }
  if (tasks.length === 0) return
  await Promise.all(tasks)
  // 若 policies 授权且已有 channel,自动加载第一个 channel 的 targets
  if (hasPolicies && channels.value.length > 0) {
    const firstChannel = channels.value[0]
    selectedChannel.value = firstChannel
    await loadTargets(firstChannel.id)
  }
})

// 切换 channel 时自动重新加载 targets(policies tab)
watch(() => selectedChannel.value, (newCh, oldCh) => {
  if (newCh && (!oldCh || newCh.id !== oldCh.id)) {
    loadTargets(newCh.id)
  }
})
</script>

<template>
  <div class="feishu-settings-wrapper">
    <section v-if="!hasAnyAccess" class="feishu-settings-empty" data-testid="feishu-settings-no-permission">
      此功能对您未开放。如需使用请联系系统管理员调整菜单权限。
    </section>

    <section v-else class="feishu-settings-manager">
    <div
      class="tablist"
      role="tablist"
      aria-label="飞书设置管理"
    >
      <button
        v-for="tab in availableTabs"
        :key="tab.id"
        type="button"
        role="tab"
        :id="`feishu-tab-${tab.id}`"
        :aria-controls="`feishu-panel-${tab.id}`"
        :aria-selected="activeTab === tab.id ? 'true' : 'false'"
        :tabindex="activeTab === tab.id ? 0 : -1"
        :class="['tab', { active: activeTab === tab.id }]"
        :data-testid="`feishu-tab-${tab.id}`"
        @click="switchTab(tab.id)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 应用设置 Tab -->
    <section
      v-if="activeTab === TAB_APPS"
      :id="`feishu-panel-${TAB_APPS}`"
      role="tabpanel"
      aria-labelledby="feishu-tab-apps"
      data-testid="feishu-panel-apps"
    >
      <div v-if="channelError" class="alert error">{{ channelError }}</div>
      <div v-if="channelMessage" class="alert success">{{ channelMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>飞书应用配置</h3>
          <p>
            每个应用对应一组飞书凭证(企业可创建多个应用分别接入不同群组)。
            WS 多实例:每个 enabled 应用启动独立监听进程,绑定不同 agent。
            密钥字段留空表示不修改原密钥。
          </p>
        </div>
      </header>

      <div class="policies-layout">
        <div class="policies-list">
          <div v-if="!channels.length" class="empty-state">暂无应用</div>
          <button
            v-for="c in channels"
            :key="c.id"
            class="policy-item"
            :class="{ active: selectedChannel && selectedChannel.id === c.id }"
            type="button"
            @click="selectChannel(c)"
          >
            <span class="policy-name">
              {{ c.display_name || c.name }}
              <span v-if="!c.enabled" class="badge disabled">已禁用</span>
            </span>
            <span class="policy-meta">{{ c.name }}</span>
          </button>
          <button
            class="primary-btn create-channel-btn"
            type="button"
            data-testid="feishu-create-channel-btn"
            @click="startCreateChannel"
          >+ 新建应用</button>
        </div>

        <div class="policy-editor" v-if="isEditingChannel">
          <h4>{{ selectedChannel ? '编辑应用' : '新建应用' }}</h4>
          <form class="feishu-form form-grid" @submit.prevent="saveChannel">
            <div class="field-row full">
              <label class="field-label" for="feishu-channel-name">应用名称 *</label>
              <div class="field-control">
                <input id="feishu-channel-name" v-model="channelForm.name" type="text"
                       placeholder="如：运维告警通知群" :disabled="!!selectedChannel" />
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="feishu-channel-display-name">显示名称</label>
              <div class="field-control">
                <input id="feishu-channel-display-name" v-model="channelForm.display_name" type="text"
                       placeholder="可选, 用于 UI 展示" />
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="feishu-app-id">App ID {{ selectedChannel ? '(留空不修改)' : '*' }}</label>
              <div class="field-control">
                <input id="feishu-app-id" v-model="channelForm.app_id" type="text"
                       placeholder="cli_xxx" :autocomplete="'off'" />
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="feishu-app-secret">App Secret {{ selectedChannel ? '(留空不修改)' : '*' }}</label>
              <div class="field-control">
                <input id="feishu-app-secret" v-model="channelForm.app_secret" type="password"
                       placeholder="飞书应用 App Secret" :autocomplete="'new-password'" />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="feishu-log-level">日志级别</label>
              <div class="field-control">
                <select id="feishu-log-level" v-model="channelForm.log_level" class="form-input form-select">
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
              </div>
            </div>

            <!-- 2026-09-07 第二轮：channel 重新绑智能体——每个飞书应用绑定一个目标智能体 -->
            <div class="field-row full">
              <label class="field-label" for="feishu-channel-agent">路由 Agent *</label>
              <div class="field-control">
                <select id="feishu-channel-agent" v-model="channelForm.agent_name" class="form-input form-select"
                        data-testid="feishu-channel-agent-select">
                  <option value="">-- 请选择智能体 --</option>
                  <option v-for="a in agents" :key="a.name" :value="a.name">{{ a.display_name }} ({{ a.name }})</option>
                </select>
              </div>
            </div>

            <label class="inline-field">
              <input v-model="channelForm.enabled" type="checkbox" data-testid="feishu-channel-enabled" />
              <span>启用此应用(WS 多实例仅监听 enabled 的应用)</span>
            </label>
            <!-- 2026-09-11：移除「设为默认应用」复选框。send_feishu_message 按 channel.config.agent_name 自动路由。 -->

            <div class="form-actions">
              <button class="primary-btn" type="submit" :disabled="isSavingChannel" data-testid="feishu-save-channel-btn">
                {{ isSavingChannel ? '保存中...' : '保存' }}
              </button>
              <button class="secondary-btn" type="button" :disabled="isTestingChannel || !selectedChannel"
                      data-testid="feishu-test-connection-btn" @click="testChannelConnection">
                {{ isTestingChannel ? '测试中...' : '测试连接' }}
              </button>
              <button class="secondary-btn" type="button" @click="cancelEditChannel">取消</button>
              <button v-if="selectedChannel" class="danger-btn" type="button"
                      @click="removeChannel(selectedChannel)">删除应用</button>
            </div>
          </form>
        </div>
      </div>
    </section>

    <!-- 发送策略 Tab -->
    <section
      v-else-if="activeTab === TAB_POLICIES"
      :id="`feishu-panel-${TAB_POLICIES}`"
      role="tabpanel"
      aria-labelledby="feishu-tab-policies"
      data-testid="feishu-panel-policies"
    >
      <div v-if="targetError" class="alert error">{{ targetError }}</div>
      <div v-if="targetMessage" class="alert success">{{ targetMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>飞书发送策略</h3>
          <p>每条策略 = 应用 × 群/用户 × 智能体;通过「应用设置」Tab 选中应用后,在此添加目标。</p>
        </div>
        <div class="actions">
          <select v-model="selectedChannel" class="form-input form-select" data-testid="feishu-policy-channel-select">
            <option :value="null">-- 请选择应用 --</option>
            <option v-for="c in channels" :key="c.id" :value="c">{{ c.display_name || c.name }}</option>
          </select>
          <button class="primary-btn" type="button" data-testid="feishu-create-target-btn"
                  :disabled="!selectedChannel" @click="startCreateTarget">新建目标</button>
        </div>
      </header>

      <div class="policies-layout">
        <div class="policies-list">
          <div v-if="!selectedChannel" class="empty-state">请先在「应用设置」Tab 选中一个应用</div>
          <div v-else-if="!targets.length" class="empty-state">该应用下暂无目标</div>
          <button
            v-for="t in targets"
            :key="t.id"
            class="policy-item"
            :class="{ active: selectedTarget && selectedTarget.id === t.id }"
            type="button"
            @click="selectTarget(t)"
          >
            <span class="policy-name">
              {{ t.name }}
              <span v-if="!t.enabled" class="badge disabled">已禁用</span>
            </span>
            <span class="policy-meta">{{ t.target_type }} · {{ t.agent_name }}</span>
          </button>
        </div>

        <div class="policy-editor" v-if="isEditingTarget">
          <h4>{{ selectedTarget ? '编辑目标' : '新建目标' }}</h4>
          <form class="feishu-form form-grid" @submit.prevent="saveTarget">
            <div class="field-row full">
              <label class="field-label" for="feishu-target-name">目标名称 *</label>
              <div class="field-control">
                <input id="feishu-target-name" v-model="targetForm.name" type="text"
                       placeholder="如：运维告警群" />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="feishu-target-type">目标类型</label>
              <div class="field-control">
                <select id="feishu-target-type" v-model="targetForm.target_type" class="form-input form-select">
                  <option value="feishu.chat">飞书群 chat</option>
                  <option value="feishu.user">飞书用户</option>
                </select>
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="feishu-chat-id">Chat ID *</label>
              <div class="field-control">
                <input id="feishu-chat-id" v-model="targetForm.config.chat_id" type="text"
                       placeholder="群 chat_id (oc_xxx) 或 用户 open_id (ou_xxx)" />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="feishu-chat-type">接收方类型</label>
              <div class="field-control">
                <select id="feishu-chat-type" v-model="targetForm.config.chat_type" class="form-input form-select">
                  <option value="chat_id">chat_id</option>
                  <option value="open_id">open_id</option>
                  <option value="user_id">user_id</option>
                  <option value="email">email</option>
                </select>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="feishu-chat-name">群名称(备注)</label>
              <div class="field-control">
                <input id="feishu-chat-name" v-model="targetForm.config.chat_name" type="text"
                       placeholder="可选, 仅用于 UI 展示" />
              </div>
            </div>

            <!-- 2026-09-07 第二轮：target 不再绑智能体；智能体在「应用设置」Tab 的 channel.config.agent_name -->
            <div class="field-row full">
              <label class="field-label" for="feishu-target-subject-template">主题模板</label>
              <div class="field-control">
                <input id="feishu-target-subject-template" v-model="targetForm.subject_template" type="text"
                       placeholder="留空使用默认" />
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="feishu-target-body-template">正文模板</label>
              <div class="field-control">
                <textarea id="feishu-target-body-template" v-model="targetForm.body_template" rows="4"
                          placeholder="留空使用默认"></textarea>
              </div>
            </div>

            <label class="inline-field">
              <input v-model="targetForm.enabled" type="checkbox" data-testid="feishu-target-enabled" />
              <span>启用此目标</span>
            </label>

            <div class="form-actions">
              <button class="primary-btn" type="submit" :disabled="isSavingTarget" data-testid="feishu-save-target-btn">
                {{ isSavingTarget ? '保存中...' : '保存目标' }}
              </button>
              <button class="secondary-btn" type="button" @click="cancelEditTarget">取消</button>
              <button v-if="selectedTarget" class="danger-btn" type="button"
                      @click="removeTarget(selectedTarget)">删除目标</button>
            </div>
          </form>
        </div>
      </div>
    </section>

    <!-- 发送测试 Tab -->
    <section
      v-else-if="activeTab === TAB_TEST"
      :id="`feishu-panel-${TAB_TEST}`"
      role="tabpanel"
      aria-labelledby="feishu-tab-test"
      data-testid="feishu-panel-test"
    >
      <div v-if="testError" class="alert error">{{ testError }}</div>
      <div v-if="testMessage" class="alert success">{{ testMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>飞书发送测试</h3>
          <p>向飞书群发送测试消息;若该应用 WS 已启用,绑定的智能体收到群消息后会自动回复。</p>
        </div>
      </header>

      <form class="feishu-form" @submit.prevent="sendTest">
        <label class="form-field full">
          <span>应用 *</span>
          <select id="feishu-test-channel" v-model="testForm.channel_id" class="form-input form-select"
                  data-testid="feishu-test-channel-select" @change="loadTargets(testForm.channel_id)">
            <option :value="null">-- 请选择应用 --</option>
            <option v-for="c in channels" :key="c.id" :value="c.id">{{ c.display_name || c.name }}</option>
          </select>
        </label>

        <label class="form-field full">
          <span>目标 *</span>
          <select id="feishu-test-target" v-model="testForm.target_id" class="form-input form-select"
                  data-testid="feishu-test-target-select" :disabled="!testForm.channel_id">
            <option :value="null">-- 请选择目标 --</option>
            <option v-for="t in filteredTestTargets" :key="t.id" :value="t.id">
              {{ t.name }} ({{ t.target_type }})
            </option>
          </select>
        </label>

        <label class="form-field full">
          <span>消息内容 *</span>
          <textarea id="feishu-test-content" v-model="testForm.content" rows="6"
                    placeholder="支持 Markdown(自动检测 → 飞书交互式卡片);普通文本走 msg_type=text"
                    data-testid="feishu-test-content-textarea"></textarea>
        </label>

        <div class="form-actions">
          <button class="primary-btn" type="submit" :disabled="isSendingTest" data-testid="feishu-send-test-btn">
            {{ isSendingTest ? '发送中...' : '发送' }}
          </button>
        </div>
      </form>
    </section>
    </section>
  </div>
</template>

<style scoped>
/* FeishuSettingsManager 样式块（2026-09-07 新增）
 *
 * 历史：组件模板一直复用 EmailSettingsManager.vue 的 scoped 类名（email-form /
 *   policies-layout / policy-editor / primary-btn 等），但 Vue scoped CSS 只对
 *   带 data-v-xxx 属性选择器的元素生效——本组件元素没有邮件组件的 hash,
 *   导致大量样式（tab 下划线/alert 配色/grid 布局/policy-item 选中态/badge/chip/
 *   focus 光晕等）实际从未生效，仅靠浏览器默认样式呈现"看起来差不多"的假象。
 *
 * 修复：把飞书组件的根容器/表单/empty 状态重命名为 feishu-* 前缀（避免与邮件组件
 *   scoped 样式名耦合），并为本组件添加自己的 <style scoped> 块逐字镜像
 *   EmailSettingsManager 的视觉规格，确保两个管理面板风格完全一致。
 *   通用类（tab/btn/alert/policies-layout 等）保持原名以便未来其他通知渠道复用。
 */

.feishu-settings-empty {
  padding: 16px;
  color: #6b7280;
  text-align: center;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}

.feishu-settings-manager {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

/* tabpanel flex 链：让三个 tabpanel 沿根 section 的 flex 列铺满剩余高度，
   外框始终贴满可视区，超长内容由 panel 内部自滚动 */
.feishu-settings-manager > section[role="tabpanel"] {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.tablist {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
  padding-bottom: 0;
}

.tab {
  border: 0;
  background: transparent;
  padding: 8px 14px;
  cursor: pointer;
  color: #6b7280;
  font-size: var(--font-size-base);
  border-bottom: 2px solid transparent;
  border-radius: 0;
}

.tab.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
  font-weight: 600;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0; /* 防止 tabpanel flex 链把头部压缩成 0 */
}

.detail-header h3 {
  margin: 0;
  color: #111827;
  font-size: 18px;
}

.detail-header p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.feishu-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  flex: 1;             /* 吃光 tabpanel 高度 */
  min-height: 0;       /* 解封 flex 链断点 */
  overflow-y: auto;    /* 长表单内部自滚动 */
  align-content: start;/* Grid 行靠顶对齐，避免外层 .tab-fill-wrapper 高度拉大时 Grid 默认 stretch 把行间空白撑开 */
}

/* test tab 单栏（与邮件发送测试一致）：仅一列，避免 .form-grid 强制两栏 */
.feishu-form:not(.form-grid) {
  grid-template-columns: minmax(0, 1fr);
}

.form-field,
.inline-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #374151;
  font-size: 13px;
}

.inline-field {
  flex-direction: row;
  align-items: center;
  gap: 4px;
  justify-self: start;
}

.inline-field input[type="checkbox"] {
  width: auto;
  flex: 0 0 auto;
  margin: 0;
}

.inline-field span {
  white-space: nowrap;
}

.form-field.full,
.form-actions {
  grid-column: 1 / -1;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 14px;
  color: #111827;
  background: #ffffff;
}

textarea {
  resize: vertical;
}

input[type="number"] {
  width: auto;
  min-width: 80px;
}

.actions,
.form-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.primary-btn,
.secondary-btn,
.danger-btn {
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-weight: 600;
}

.primary-btn {
  color: #ffffff;
  background: #2563eb;
}

.primary-btn:disabled,
.primary-btn[disabled] {
  background: #93c5fd;
  cursor: not-allowed;
}

.secondary-btn {
  color: #1f2937;
  background: #e5e7eb;
}

.secondary-btn:disabled,
.secondary-btn[disabled] {
  cursor: not-allowed;
  opacity: 0.6;
}

.danger-btn {
  color: #ffffff;
  background: #dc2626;
}

.alert {
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
}

.alert.error {
  color: #991b1b;
  background: #fee2e2;
}

.alert.success {
  color: #065f46;
  background: #d1fae5;
}

.empty-state {
  color: #6b7280;
  padding: 16px;
  text-align: center;
}

.policies-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.policies-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  min-height: 0;
}

.policy-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
}

.policy-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.policy-name {
  color: #111827;
  font-weight: 600;
}

.policy-meta {
  color: #6b7280;
  font-size: 12px;
}

.policy-editor {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px;
  overflow-y: auto;
  min-height: 0;
  flex: 1;
}

.policy-editor h4 {
  margin: 0 0 12px;
  color: #111827;
  font-size: 15px;
}

/* —— 策略编辑表单两栏（field-row + label + control） —— */
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 20px;
}

.field-row {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: start;
  gap: 10px;
}

.field-row.full {
  grid-column: 1 / -1;
}

.field-label {
  font-size: 13px;
  color: #374151;
  font-weight: 600;
  line-height: 1.5;
  padding-top: 10px;
  text-align: left;
  white-space: nowrap;
}

.field-control {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.form-actions-row {
  margin-top: 4px;
}

input:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

/* —— 飞书独有：默认应用 / 禁用徽章 —— */
.badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  vertical-align: middle;
}

.badge.default {
  background: #dbeafe;
  color: #1e40af;
  border: 1px solid #bfdbfe;
}

.badge.disabled {
  background: #f3f4f6;
  color: #6b7280;
  border: 1px solid #e5e7eb;
}

/* —— 飞书独有：左侧「新建应用」按钮占满宽度 —— */
.create-channel-btn {
  margin-top: 12px;
  width: 100%;
}
</style>
