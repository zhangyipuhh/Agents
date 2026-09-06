<script setup>
/**
 * FeishuSettingsManager - 飞书设置管理组件（admin）
 *
 * 挂载位置（2026-09-03 新增）：与 EmailSettingsManager 对称,渲染在
 * 「消息设置」(messaging) 顶级 tab 下的 channel 子 tab 「飞书设置」(messaging.feishu) 内。
 * 菜单注册链路：messaging → messaging.feishu → messaging.feishu.{apps,policies,test}
 * 端点 ACL key 用 messaging.feishu.<sub>（详见 NotificationConfigService）
 *
 * 提供三个 Tab：
 * - 应用设置（apps）：飞书凭证组(多应用并存);每组含 app_id / app_secret /
 *   default_receive_id / default_receive_id_type / log_level / agent_name /
 *   receiver_username + 「设为默认应用」勾选
 * - 发送策略（policies）：从 channels 列表选择应用,加 target(群/用户) +
 *   选智能体(从 GET /api/notification/agents 下拉) + 模板字段
 * - 发送测试（test）：选 channel → 选 target → 输入内容 → POST /api/notification/send-test
 *
 * 安全设计：
 * - 凭证字段在 GET 接口中返回空字符串(脱敏),前端"密钥留空"表示不修改
 * - 飞书 WebSocket 多实例(session_id 加 channel_id 命名空间)在后台生效
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
  default_receive_id: '',
  default_receive_id_type: 'chat_id',
  log_level: 'INFO',
  agent_name: '',
  receiver_username: '',
  enabled: true,
  is_default: false,
})

// === 发送策略 Tab ===
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
  agent_name: '',
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
 * 加载智能体列表（target agent_name 下拉用）。
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
  channelForm.default_receive_id = ''
  channelForm.default_receive_id_type = 'chat_id'
  channelForm.log_level = 'INFO'
  channelForm.agent_name = ''
  channelForm.receiver_username = ''
  channelForm.enabled = true
  channelForm.is_default = false
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
    channelForm.default_receive_id = detail.config?.default_receive_id || ''
    channelForm.default_receive_id_type = detail.config?.default_receive_id_type || 'chat_id'
    channelForm.log_level = detail.config?.log_level || 'INFO'
    channelForm.agent_name = detail.config?.agent_name || ''
    channelForm.receiver_username = detail.config?.receiver_username || ''
    channelForm.enabled = detail.enabled !== false
    channelForm.is_default = detail.is_default === true
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
  if (!channelForm.agent_name.trim()) {
    channelError.value = 'agent_name 不能为空(WS 多实例需要)'
    return
  }
  if (!channelForm.receiver_username.trim()) {
    channelError.value = 'receiver_username 不能为空(WS 多实例需要)'
    return
  }
  isSavingChannel.value = true
  try {
    if (selectedChannel.value) {
      // 更新
      const updatePayload = {
        display_name: channelForm.display_name,
        enabled: channelForm.enabled,
        is_default: channelForm.is_default,
        config: {
          default_receive_id: channelForm.default_receive_id,
          default_receive_id_type: channelForm.default_receive_id_type,
          log_level: channelForm.log_level,
          agent_name: channelForm.agent_name,
          receiver_username: channelForm.receiver_username,
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
        is_default: channelForm.is_default,
        config: {
          app_id: channelForm.app_id,
          app_secret: channelForm.app_secret,
          default_receive_id: channelForm.default_receive_id,
          default_receive_id_type: channelForm.default_receive_id_type,
          log_level: channelForm.log_level,
          agent_name: channelForm.agent_name,
          receiver_username: channelForm.receiver_username,
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
  targetForm.agent_name = ''
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
  targetForm.agent_name = t.agent_name
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
  if (!targetForm.agent_name.trim()) {
    targetError.value = 'agent_name 不能为空'
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
        agent_name: targetForm.agent_name,
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
        agent_name: targetForm.agent_name,
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
  <div
    v-if="!hasAnyAccess"
    class="email-settings-empty"
    data-testid="feishu-settings-no-permission"
  >
    此功能对您未开放。如需使用请联系系统管理员调整菜单权限。
  </div>

  <section v-else class="email-settings-manager">
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
              <span v-if="c.is_default" class="badge default">默认</span>
              <span v-if="!c.enabled" class="badge disabled">已禁用</span>
            </span>
            <span class="policy-meta">{{ c.name }}</span>
          </button>
          <button
            class="primary-btn"
            type="button"
            data-testid="feishu-create-channel-btn"
            @click="startCreateChannel"
            style="margin-top: 12px; width: 100%;"
          >+ 新建应用</button>
        </div>

        <div class="policy-editor" v-if="isEditingChannel">
          <h4>{{ selectedChannel ? '编辑应用' : '新建应用' }}</h4>
          <form class="email-form form-grid" @submit.prevent="saveChannel">
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

            <div class="field-row full">
              <label class="field-label" for="feishu-default-receive-id">默认接收方 ID</label>
              <div class="field-control">
                <input id="feishu-default-receive-id" v-model="channelForm.default_receive_id" type="text"
                       placeholder="群 chat_id (oc_xxx) 或 用户 open_id (ou_xxx)" />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="feishu-default-receive-id-type">接收方类型</label>
              <div class="field-control">
                <select id="feishu-default-receive-id-type" v-model="channelForm.default_receive_id_type" class="form-input form-select">
                  <option value="chat_id">chat_id</option>
                  <option value="open_id">open_id</option>
                  <option value="user_id">user_id</option>
                  <option value="email">email</option>
                </select>
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

            <div class="field-row full">
              <label class="field-label" for="feishu-agent-name">路由 Agent *</label>
              <div class="field-control">
                <select id="feishu-agent-name" v-model="channelForm.agent_name" class="form-input form-select">
                  <option value="">-- 请选择智能体 --</option>
                  <option v-for="a in agents" :key="a.name" :value="a.name">{{ a.display_name }} ({{ a.name }})</option>
                </select>
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="feishu-receiver-username">接收账号 username *</label>
              <div class="field-control">
                <input id="feishu-receiver-username" v-model="channelForm.receiver_username" type="text"
                       placeholder="该应用产生的 session 归属到的系统用户名(如 admin)" />
              </div>
            </div>

            <label class="inline-field">
              <input v-model="channelForm.enabled" type="checkbox" data-testid="feishu-channel-enabled" />
              <span>启用此应用(WS 多实例仅监听 enabled 的应用)</span>
            </label>
            <label class="inline-field">
              <input v-model="channelForm.is_default" type="checkbox" data-testid="feishu-channel-is-default" />
              <span>设为默认应用(LLM 工具 send_feishu_message 使用)</span>
            </label>

            <div class="form-actions">
              <button class="primary-btn" type="submit" :disabled="isSavingChannel" data-testid="feishu-save-channel-btn">
                {{ isSavingChannel ? '保存中...' : '保存' }}
              </button>
              <button class="secondary-btn" type="button" :disabled="isTestingChannel || !selectedChannel"
                      data-testid="feishu-test-connection-btn" @click="testChannelConnection">
                {{ isTestingChannel ? '测试中...' : '测试连接' }}
              </button>
              <button class="secondary-btn" type="button" @click="cancelEditChannel">取消</button>
              <button v-if="selectedChannel" class="secondary-btn danger" type="button"
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
          <form class="email-form form-grid" @submit.prevent="saveTarget">
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

            <div class="field-row full">
              <label class="field-label" for="feishu-target-agent">绑定智能体 *</label>
              <div class="field-control">
                <select id="feishu-target-agent" v-model="targetForm.agent_name" class="form-input form-select">
                  <option value="">-- 请选择智能体 --</option>
                  <option v-for="a in agents" :key="a.name" :value="a.name">{{ a.display_name }} ({{ a.name }})</option>
                </select>
              </div>
            </div>

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
              <button v-if="selectedTarget" class="secondary-btn danger" type="button"
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

      <form class="email-form form-grid" @submit.prevent="sendTest">
        <div class="field-row">
          <label class="field-label" for="feishu-test-channel">应用 *</label>
          <div class="field-control">
            <select id="feishu-test-channel" v-model="testForm.channel_id" class="form-input form-select"
                    data-testid="feishu-test-channel-select" @change="loadTargets(testForm.channel_id)">
              <option :value="null">-- 请选择应用 --</option>
              <option v-for="c in channels" :key="c.id" :value="c.id">{{ c.display_name || c.name }}</option>
            </select>
          </div>
        </div>

        <div class="field-row">
          <label class="field-label" for="feishu-test-target">目标 *</label>
          <div class="field-control">
            <select id="feishu-test-target" v-model="testForm.target_id" class="form-input form-select"
                    data-testid="feishu-test-target-select" :disabled="!testForm.channel_id">
              <option :value="null">-- 请选择目标 --</option>
              <option v-for="t in filteredTestTargets" :key="t.id" :value="t.id">
                {{ t.name }} ({{ t.target_type }})
              </option>
            </select>
          </div>
        </div>

        <div class="field-row full">
          <label class="field-label" for="feishu-test-content">消息内容 *</label>
          <div class="field-control">
            <textarea id="feishu-test-content" v-model="testForm.content" rows="6"
                      placeholder="支持 Markdown(自动检测 → 飞书交互式卡片);普通文本走 msg_type=text"
                      data-testid="feishu-test-content-textarea"></textarea>
          </div>
        </div>

        <div class="form-actions">
          <button class="primary-btn" type="submit" :disabled="isSendingTest" data-testid="feishu-send-test-btn">
            {{ isSendingTest ? '发送中...' : '发送' }}
          </button>
        </div>
      </form>
    </section>
  </section>
</template>
