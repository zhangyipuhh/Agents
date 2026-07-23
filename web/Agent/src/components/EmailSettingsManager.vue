<script setup>
/**
 * EmailSettingsManager - 邮件设置管理组件（admin）
 *
 * 提供三个 Tab：
 * - 服务器配置（SMTP 主机 / 端口 / SSL / 账号 / 授权码 / 发件人显示名）
 * - 发送策略（从已注册且邮箱非空用户中挑选收件人，组成策略）
 * - 测试发送（multipart/form-data，支持本地附件上传）
 *
 * 安全设计：
 * - SMTP 密码字段在 GET 接口中返回空字符串，前端"密码留空"表示不修改原密码。
 * - 发送测试邮件使用 multipart/form-data 以支持附件上传。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import {
  fetchEmailServerConfig,
  updateEmailServerConfig,
  testEmailServerConfig,
  fetchEmailableUsers,
  fetchEmailPolicies,
  createEmailPolicy,
  updateEmailPolicy,
  deleteEmailPolicy,
  sendTestEmail,
} from '../utils/api.js'

const TAB_SERVER = 'server'
const TAB_POLICIES = 'policies'
const TAB_TEST = 'test'

// 2026-07-23 ACL 双重门：tab 与后端 MENU_CATALOG 的子菜单 id 对齐
const TAB_MENU_IDS = {
  [TAB_SERVER]: 'task-scheduler.email-settings.server',
  [TAB_POLICIES]: 'task-scheduler.email-settings.policies',
  [TAB_TEST]: 'task-scheduler.email-settings.test',
}

// 全部 tab 元数据（label 由父组件 props.visibleMenus 过滤后渲染）
const ALL_TABS = [
  { id: TAB_SERVER, label: '服务器配置', menuId: TAB_MENU_IDS[TAB_SERVER] },
  { id: TAB_POLICIES, label: '发送策略', menuId: TAB_MENU_IDS[TAB_POLICIES] },
  { id: TAB_TEST, label: '测试发送', menuId: TAB_MENU_IDS[TAB_TEST] },
]

const activeTab = ref(TAB_SERVER)

// 服务器配置状态
const serverConfig = reactive({
  host: 'smtp.qq.com',
  port: 465,
  use_ssl: true,
  username: '',
  password: '',
  sender_name: '',
  enabled: true,
  // 2026-07-18 新增：企业邮箱兼容字段（方案 Z）
  force_plain: false,
  verify_ssl: true,
})
// 高级选项折叠面板展开状态（默认收起，避免新手误操作）
const showAdvancedOptions = ref(false)
const isSavingServer = ref(false)
const isTestingConnection = ref(false)
const serverMessage = ref('')
const serverError = ref('')

// 发送策略状态
const policies = ref([])
const emailableUsers = ref([])
const selectedPolicy = ref(null)
const isEditingPolicy = ref(false)
const isSavingPolicy = ref(false)
const policyForm = reactive({
  name: '',
  description: '',
  recipient_user_ids: [],
  subject_template: '',
  body_template: '',
})
const policyError = ref('')
const policyMessage = ref('')
const recipientKeyword = ref('')

// 测试发送状态
const testForm = reactive({
  to: '',
  cc: '',
  subject: '',
  body: '',
})
const testFiles = ref([])
const isSendingTest = ref(false)
const testMessage = ref('')
const testError = ref('')

/**
 * 切换 Tab。
 * @param {string} tabId - Tab 标识。
 */
function switchTab(tabId) {
  if (activeTab.value === tabId) return
  activeTab.value = tabId
}

/**
 * 加载 SMTP 服务器配置。
 */
async function loadServerConfig() {
  serverError.value = ''
  try {
    const data = await fetchEmailServerConfig()
    if (data) {
      serverConfig.host = data.host || 'smtp.qq.com'
      serverConfig.port = data.port || 465
      serverConfig.use_ssl = data.use_ssl !== false
      serverConfig.username = data.username || ''
      serverConfig.password = '' // 永远不显示已保存的密码
      serverConfig.sender_name = data.sender_name || ''
      serverConfig.enabled = data.enabled !== false
      // 2026-07-18 新增：企业邮箱兼容字段（后端缺省 false/true）
      serverConfig.force_plain = data.force_plain === true
      serverConfig.verify_ssl = data.verify_ssl !== false
    }
  } catch (err) {
    serverError.value = err.message
  }
}

/**
 * 保存 SMTP 服务器配置。
 */
async function saveServerConfig() {
  serverError.value = ''
  serverMessage.value = ''
  if (!serverConfig.host || !serverConfig.username) {
    serverError.value = 'SMTP 主机和账号不能为空'
    return
  }
  isSavingServer.value = true
  try {
    await updateEmailServerConfig({
      host: serverConfig.host,
      port: Number(serverConfig.port),
      use_ssl: serverConfig.use_ssl,
      username: serverConfig.username,
      password: serverConfig.password, // 空字符串表示不修改
      sender_name: serverConfig.sender_name,
      enabled: serverConfig.enabled,
      // 2026-07-18 新增：企业邮箱兼容字段
      force_plain: serverConfig.force_plain,
      verify_ssl: serverConfig.verify_ssl,
    })
    serverMessage.value = 'SMTP 配置已保存'
    serverConfig.password = '' // 清空密码框
  } catch (err) {
    serverError.value = err.message
  } finally {
    isSavingServer.value = false
  }
}

/**
 * 测试 SMTP 连接（不发送邮件）。
 */
async function testConnection() {
  serverError.value = ''
  serverMessage.value = ''
  if (!serverConfig.host || !serverConfig.username) {
    serverError.value = 'SMTP 主机和账号不能为空'
    return
  }
  isTestingConnection.value = true
  try {
    const result = await testEmailServerConfig({
      host: serverConfig.host,
      port: Number(serverConfig.port),
      use_ssl: serverConfig.use_ssl,
      username: serverConfig.username,
      password: serverConfig.password,
      // 2026-07-18 新增：企业邮箱兼容字段
      force_plain: serverConfig.force_plain,
      verify_ssl: serverConfig.verify_ssl,
    })
    if (result.success) {
      serverMessage.value = result.message || '连接成功'
    } else {
      serverError.value = result.message || '连接失败'
    }
  } catch (err) {
    serverError.value = err.message
  } finally {
    isTestingConnection.value = false
  }
}

/**
 * 加载已注册且邮箱非空的用户列表。
 */
async function loadEmailableUsers() {
  try {
    emailableUsers.value = await fetchEmailableUsers()
  } catch (err) {
    policyError.value = err.message
  }
}

/**
 * 加载策略列表。
 */
async function loadPolicies() {
  policyError.value = ''
  try {
    policies.value = await fetchEmailPolicies()
  } catch (err) {
    policyError.value = err.message
  }
}

/**
 * 开始新建策略。
 */
function startCreatePolicy() {
  selectedPolicy.value = null
  isEditingPolicy.value = true
  policyForm.name = ''
  policyForm.description = ''
  policyForm.recipient_user_ids = []
  policyForm.subject_template = ''
  policyForm.body_template = ''
  recipientKeyword.value = ''
  policyError.value = ''
  policyMessage.value = ''
}

/**
 * 选中已有策略进行编辑。
 * @param {Object} policy - 策略对象。
 */
function selectPolicy(policy) {
  selectedPolicy.value = policy
  isEditingPolicy.value = true
  policyForm.name = policy.name
  policyForm.description = policy.description || ''
  policyForm.recipient_user_ids = [...(policy.recipient_user_ids || [])]
  policyForm.subject_template = policy.subject_template || ''
  policyForm.body_template = policy.body_template || ''
  recipientKeyword.value = ''
  policyError.value = ''
  policyMessage.value = ''
}

/**
 * 取消编辑策略。
 */
function cancelEditPolicy() {
  isEditingPolicy.value = false
  selectedPolicy.value = null
  policyForm.name = ''
  policyForm.description = ''
  policyForm.recipient_user_ids = []
  policyForm.subject_template = ''
  policyForm.body_template = ''
  recipientKeyword.value = ''
}

/**
 * 按搜索关键词过滤后的可选用户列表。
 * @returns {Array<Object>} 过滤后的用户列表。
 */
const filteredEmailableUsers = computed(() => {
  const kw = recipientKeyword.value.trim().toLowerCase()
  if (!kw) return emailableUsers.value
  return emailableUsers.value.filter(
    (u) =>
      (u.real_name || '').toLowerCase().includes(kw) ||
      (u.username || '').toLowerCase().includes(kw) ||
      (u.email || '').toLowerCase().includes(kw),
  )
})

/**
 * 当前已选中的收件人（含姓名 / 邮箱）列表，用于顶部 chip 展示。
 * @returns {Array<Object>} 已选用户对象列表。
 */
const selectedRecipientChips = computed(() =>
  emailableUsers.value.filter((u) => policyForm.recipient_user_ids.includes(u.id)),
)

/**
 * 已选收件人数量。
 * @returns {number} 已选人数。
 */
const selectedCount = computed(() => selectedRecipientChips.value.length)

/**
 * 全选当前过滤结果中的所有用户。
 */
function selectAllRecipients() {
  policyForm.recipient_user_ids = filteredEmailableUsers.value.map((u) => u.id)
}

/**
 * 清空当前已选收件人。
 */
function clearRecipients() {
  policyForm.recipient_user_ids = []
}

/**
 * 切换某用户的选中状态（用于 chip 上的移除按钮）。
 * @param {number} id - 用户 ID。
 */
function toggleRecipient(id) {
  const set = new Set(policyForm.recipient_user_ids)
  if (set.has(id)) {
    set.delete(id)
  } else {
    set.add(id)
  }
  policyForm.recipient_user_ids = Array.from(set)
}

/**
 * 保存策略（新建或更新）。
 */
async function savePolicy() {
  policyError.value = ''
  policyMessage.value = ''
  if (!policyForm.name.trim()) {
    policyError.value = '策略名称不能为空'
    return
  }
  if (!policyForm.recipient_user_ids.length) {
    policyError.value = '请至少选择一个收件人'
    return
  }
  isSavingPolicy.value = true
  try {
    if (selectedPolicy.value) {
      await updateEmailPolicy(selectedPolicy.value.id, {
        name: policyForm.name,
        description: policyForm.description,
        recipient_user_ids: policyForm.recipient_user_ids,
        subject_template: policyForm.subject_template,
        body_template: policyForm.body_template,
      })
      policyMessage.value = '策略已更新'
    } else {
      await createEmailPolicy({
        name: policyForm.name,
        description: policyForm.description,
        recipient_user_ids: policyForm.recipient_user_ids,
        subject_template: policyForm.subject_template,
        body_template: policyForm.body_template,
      })
      policyMessage.value = '策略已创建'
    }
    await loadPolicies()
    cancelEditPolicy()
  } catch (err) {
    policyError.value = err.message
  } finally {
    isSavingPolicy.value = false
  }
}

/**
 * 删除策略。
 * @param {Object} policy - 策略对象。
 */
async function removePolicy(policy) {
  if (!confirm(`确认删除策略「${policy.name}」？`)) return
  policyError.value = ''
  try {
    await deleteEmailPolicy(policy.id)
    policyMessage.value = '策略已删除'
    if (selectedPolicy.value && selectedPolicy.value.id === policy.id) {
      cancelEditPolicy()
    }
    await loadPolicies()
  } catch (err) {
    policyError.value = err.message
  }
}

/**
 * 处理附件选择。
 * @param {Event} event - input change 事件。
 */
function handleFileChange(event) {
  testFiles.value = Array.from(event.target.files || [])
}

/**
 * 发送测试邮件。
 */
async function sendTest() {
  testError.value = ''
  testMessage.value = ''
  if (!testForm.to.trim() || !testForm.subject.trim() || !testForm.body.trim()) {
    testError.value = '收件人、主题和正文不能为空'
    return
  }
  isSendingTest.value = true
  try {
    const formData = new FormData()
    formData.append('to', testForm.to)
    formData.append('cc', testForm.cc)
    formData.append('subject', testForm.subject)
    formData.append('body', testForm.body)
    for (const file of testFiles.value) {
      formData.append('files', file, file.name)
    }
    const result = await sendTestEmail(formData)
    testMessage.value = `发送成功！共发送给 ${result.sent_to.length} 个收件人（SMTP 已接收；若对方未收到，请检查对方垃圾箱 / 网关隔离区）`
  } catch (err) {
    testError.value = err.message
  } finally {
    isSendingTest.value = false
  }
}

// === Props ===
/**
 * 2026-07-23 改造：组件 props。
 * - visibleMenus（ACL）：父组件传入当前用户的可见菜单列表。子 tab 按 ACL 过滤。
 * - isAdmin：兼容 hint，admin 直通；保留供旧测试。
 */
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

/**
 * 计算可用的子 tab：admin 全量；普通用户按 ACL 过滤
 */
const availableTabs = computed(() => {
  if (props.isAdmin) return ALL_TABS
  return ALL_TABS.filter(t => visibleSet.value.has(t.menuId))
})

/** 是否有任何 tab 可访问 */
const hasAnyAccess = computed(() => props.isAdmin || availableTabs.value.length > 0)

onMounted(async () => {
  // 2026-07-23 修复：fail-safe 兜底，但只对没有任何 tab 授权的情况 skip
  if (!hasAnyAccess.value) {
    console.warn('[EmailSettingsManager] 用户未被授权任何 email-settings 子 tab，已跳过数据加载')
    return
  }
  // activeTab 默认值：第一个被授权的 tab（避免默认 'server' 但没授权）
  if (availableTabs.value.length > 0 && !availableTabs.value.find(t => t.id === activeTab.value)) {
    activeTab.value = availableTabs.value[0].id
  }
  // 按 tab 授权加载数据：只调被授权对应 backend 的 fetch
  // - server tab (server-config + emailable-users) 只在授权 server 时加载
  // - policies tab (policies + emailable-users) 只在授权 policies 时加载
  // - emailable-users 是 server 与 policies 共用的辅助数据，跟着任一授权走即可
  const tasks = []
  const hasServer = visibleSet.value.has(TAB_MENU_IDS[TAB_SERVER])
  const hasPolicies = visibleSet.value.has(TAB_MENU_IDS[TAB_POLICIES])
  // 服务端 isAdmin：visibleSet 里没有 menu_id 时，仍按 isAdmin 决定
  const canServer = props.isAdmin || hasServer
  const canPolicies = props.isAdmin || hasPolicies

  if (canServer || canPolicies) {
    tasks.push(loadEmailableUsers())
  }
  if (canServer) {
    tasks.push(loadServerConfig())
  }
  if (canPolicies) {
    tasks.push(loadPolicies())
  }
  if (tasks.length === 0) {
    return
  }
  await Promise.all(tasks)
})
</script>

<template>
  <!-- 2026-07-23 ACL 双重门：用户未被授权任何 tab 时显示提示 -->
  <div
    v-if="!hasAnyAccess"
    class="email-settings-empty"
    data-testid="email-settings-no-permission"
  >
    此功能对您未开放。如需使用请联系系统管理员调整菜单权限。
  </div>

  <section v-else class="email-settings-manager">
    <div
      class="tablist"
      role="tablist"
      aria-label="邮件设置管理"
    >
      <button
        v-for="tab in availableTabs"
        :key="tab.id"
        type="button"
        role="tab"
        :id="`email-tab-${tab.id}`"
        :aria-controls="`email-panel-${tab.id}`"
        :aria-selected="activeTab === tab.id ? 'true' : 'false'"
        :tabindex="activeTab === tab.id ? 0 : -1"
        :class="['tab', { active: activeTab === tab.id }]"
        :data-testid="`email-tab-${tab.id}`"
        @click="switchTab(tab.id)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 服务器配置 Tab -->
    <section
      v-if="activeTab === TAB_SERVER"
      :id="`email-panel-${TAB_SERVER}`"
      role="tabpanel"
      aria-labelledby="email-tab-server"
      data-testid="email-panel-server"
    >
      <div v-if="serverError" class="alert error">{{ serverError }}</div>
      <div v-if="serverMessage" class="alert success">{{ serverMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>SMTP 服务器配置</h3>
          <p>
            配置 QQ 邮箱 SMTP：SSL(465) 或 STARTTLS(587) 二选一（QQ 官方推荐 587）。
            若 465 报「SSL 握手失败」「服务器主动断开」，请取消勾选改用 587；
            若账号是企业邮箱，请把主机从 <code>smtp.qq.com</code> 改为
            <code>smtp.exmail.qq.com</code>。密码留空表示不修改原密码。
          </p>
        </div>
      </header>

      <form class="email-form" @submit.prevent="saveServerConfig">
        <label class="form-field">
          <span>SMTP 主机 *</span>
          <input v-model="serverConfig.host" type="text" placeholder="smtp.qq.com" />
        </label>
        <label class="form-field">
          <span>SMTP 端口 *</span>
          <input v-model.number="serverConfig.port" type="number" min="1" max="65535" placeholder="465" />
        </label>
        <label class="form-field">
          <span>登录账号 *</span>
          <input v-model="serverConfig.username" type="text" placeholder="发件邮箱地址" />
        </label>
        <label class="form-field">
          <span>发件人显示名</span>
          <input v-model="serverConfig.sender_name" type="text" placeholder="如：管理员" />
        </label>
        <label class="form-field full">
          <span>密码 / 授权码</span>
          <input v-model="serverConfig.password" type="password" placeholder="留空表示不修改原密码" />
        </label>
        <label class="inline-field">
          <input v-model="serverConfig.use_ssl" type="checkbox" />
          <span>使用 SMTP_SSL（取消则走 STARTTLS，推荐 587）</span>
        </label>
        <label class="inline-field">
          <input v-model="serverConfig.enabled" type="checkbox" />
          <span>启用此配置</span>
        </label>

        <!-- 2026-07-18 新增：高级选项（企业邮箱兼容） -->
        <div class="advanced-section">
          <button
            type="button"
            class="advanced-toggle"
            :aria-expanded="showAdvancedOptions ? 'true' : 'false'"
            data-testid="email-advanced-toggle"
            @click="showAdvancedOptions = !showAdvancedOptions"
          >
            <span>{{ showAdvancedOptions ? '▼' : '▶' }}</span>
            <span>高级选项（企业邮箱兼容）</span>
          </button>
          <div v-if="showAdvancedOptions" class="advanced-body">
            <p class="advanced-hint">
              仅当 SMTP 协议兼容性异常时报「SSL 握手失败」或「网络层超时」时勾选。
              普通邮箱（QQ/163/Gmail）保持默认即可。
            </p>
            <label class="inline-field">
              <input
                v-model="serverConfig.force_plain"
                type="checkbox"
                data-testid="email-force-plain"
              />
              <span>强制明文 SMTP（跳过 STARTTLS）</span>
            </label>
            <label class="inline-field">
              <input
                v-model="serverConfig.verify_ssl"
                type="checkbox"
                data-testid="email-verify-ssl"
              />
              <span>校验 TLS 证书（取消则跳过证书校验）</span>
            </label>
          </div>
        </div>
        <div class="form-actions">
          <button class="primary-btn" type="submit" :disabled="isSavingServer">
            {{ isSavingServer ? '保存中...' : '保存配置' }}
          </button>
          <button class="secondary-btn" type="button" :disabled="isTestingConnection" @click="testConnection">
            {{ isTestingConnection ? '测试中...' : '测试连接' }}
          </button>
        </div>
      </form>
    </section>

    <!-- 发送策略 Tab -->
    <section
      v-else-if="activeTab === TAB_POLICIES"
      :id="`email-panel-${TAB_POLICIES}`"
      role="tabpanel"
      aria-labelledby="email-tab-policies"
      data-testid="email-panel-policies"
    >
      <div v-if="policyError" class="alert error">{{ policyError }}</div>
      <div v-if="policyMessage" class="alert success">{{ policyMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>邮件发送策略</h3>
          <p>策略仅包含收件人集合；收件人必须为已注册且邮箱非空的用户。</p>
        </div>
        <div class="actions">
          <button class="primary-btn" type="button" @click="startCreatePolicy">新建策略</button>
        </div>
      </header>

      <div class="policies-layout">
        <div class="policies-list">
          <div v-if="!policies.length" class="empty-state">暂无策略</div>
          <button
            v-for="p in policies"
            :key="p.id"
            class="policy-item"
            :class="{ active: selectedPolicy && selectedPolicy.id === p.id }"
            type="button"
            @click="selectPolicy(p)"
          >
            <span class="policy-name">{{ p.name }}</span>
            <span class="policy-meta">{{ (p.recipient_user_ids || []).length }} 个收件人</span>
          </button>
        </div>

        <div class="policy-editor" v-if="isEditingPolicy">
          <h4>{{ selectedPolicy ? '编辑策略' : '新建策略' }}</h4>
          <form class="email-form form-grid" @submit.prevent="savePolicy">
            <div class="field-row full">
              <label class="field-label" for="policy-name">策略名称 *</label>
              <div class="field-control">
                <input
                  id="policy-name"
                  v-model="policyForm.name"
                  type="text"
                  placeholder="例如：运维告警通知"
                />
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="policy-desc">策略描述</label>
              <div class="field-control">
                <textarea
                  id="policy-desc"
                  v-model="policyForm.description"
                  rows="2"
                  placeholder="可选"
                ></textarea>
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="policy-subject-template">主题模板</label>
              <div class="field-control">
                <input
                  id="policy-subject-template"
                  v-model="policyForm.subject_template"
                  type="text"
                  data-testid="policy-subject-template"
                  placeholder="留空使用策略名称作为主题。支持 {{schedule_name}} {{run_id}} {{timestamp|%Y%m%d%H%M}} 等占位符"
                />
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label" for="policy-body-template">正文模板</label>
              <div class="field-control">
                <textarea
                  id="policy-body-template"
                  v-model="policyForm.body_template"
                  rows="6"
                  data-testid="policy-body-template"
                  placeholder="可选。支持占位符：{{schedule_name}} {{script_name}} {{script_output}} {{attachment_paths}} {{run_id}} {{started_at}} {{trigger_type}} {{finished_at}} {{timestamp|%Y-%m-%d %H:%M}}"
                ></textarea>
              </div>
            </div>

            <div class="field-row full">
              <label class="field-label">收件人 *</label>
              <div class="field-control">
                <div class="recipient-panel">
                  <div class="recipient-panel__toolbar">
                    <input
                      v-model="recipientKeyword"
                      type="search"
                      class="recipient-search"
                      placeholder="搜索姓名/邮箱…"
                      aria-label="搜索收件人"
                    />
                    <div class="recipient-toolbar__actions">
                      <button type="button" class="link-btn" @click="selectAllRecipients">
                        全选
                      </button>
                      <span class="divider"></span>
                      <button type="button" class="link-btn" @click="clearRecipients">
                        清空
                      </button>
                    </div>
                    <div class="recipient-counter" :class="{ active: selectedCount > 0 }">
                      已选 <strong>{{ selectedCount }}</strong> /
                      {{ filteredEmailableUsers.length }}
                    </div>
                  </div>

                  <div v-if="filteredEmailableUsers.length" class="recipient-list">
                    <label
                      v-for="u in filteredEmailableUsers"
                      :key="u.id"
                      class="recipient-item"
                    >
                      <input
                        type="checkbox"
                        :value="u.id"
                        v-model="policyForm.recipient_user_ids"
                      />
                      <span class="recipient-name">{{ u.real_name || u.username }}</span>
                      <span class="recipient-email">{{ u.email }}</span>
                    </label>
                  </div>
                  <div v-else-if="emailableUsers.length" class="empty-state">
                    没有匹配「{{ recipientKeyword }}」的用户
                  </div>
                  <div v-else class="empty-state">暂无可选用户（所有用户邮箱为空）</div>

                  <div
                    v-if="selectedRecipientChips.length"
                    class="recipient-chips"
                    aria-label="已选收件人"
                  >
                    <span
                      v-for="u in selectedRecipientChips"
                      :key="u.id"
                      class="chip"
                    >
                      {{ u.real_name || u.username }}
                      <button
                        type="button"
                        class="chip-remove"
                        :aria-label="`移除 ${u.real_name || u.username}`"
                        @click="toggleRecipient(u.id)"
                      >
                        ×
                      </button>
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div class="field-row full form-actions-row">
              <div class="field-label"></div>
              <div class="field-control form-actions">
                <button class="primary-btn" type="submit" :disabled="isSavingPolicy">
                  {{ isSavingPolicy ? '保存中...' : '保存策略' }}
                </button>
                <button class="secondary-btn" type="button" @click="cancelEditPolicy">
                  取消
                </button>
                <button
                  v-if="selectedPolicy"
                  class="danger-btn"
                  type="button"
                  @click="removePolicy(selectedPolicy)"
                >
                  删除
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </section>

    <!-- 测试发送 Tab -->
    <section
      v-else-if="activeTab === TAB_TEST"
      :id="`email-panel-${TAB_TEST}`"
      role="tabpanel"
      aria-labelledby="email-tab-test"
      data-testid="email-panel-test"
    >
      <div v-if="testError" class="alert error">{{ testError }}</div>
      <div v-if="testMessage" class="alert success">{{ testMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>发送测试邮件</h3>
          <p>
            使用当前已保存的 SMTP 配置发送；附件从本地浏览器上传。
            「发送成功」仅代表 SMTP 服务器已接收（250 OK），不代表对方邮箱已投递；
            跨域发送（如 QQ/foxmail → 企业邮箱）可能被对方反垃圾网关静默丢弃，
            未收到时请检查对方垃圾箱 / 网关隔离区，或改用与收件人同域的 SMTP 服务器。
          </p>
        </div>
      </header>

      <form class="email-form" @submit.prevent="sendTest">
        <label class="form-field full">
          <span>收件人 * (多个用逗号分隔)</span>
          <input v-model="testForm.to" type="text" placeholder="a@example.com, b@example.com" />
        </label>
        <label class="form-field full">
          <span>抄送 (多个用逗号分隔)</span>
          <input v-model="testForm.cc" type="text" placeholder="可选" />
        </label>
        <label class="form-field full">
          <span>主题 *</span>
          <input v-model="testForm.subject" type="text" placeholder="邮件主题" />
        </label>
        <label class="form-field full">
          <span>正文 *</span>
          <textarea v-model="testForm.body" rows="6" placeholder="邮件正文"></textarea>
        </label>
        <label class="form-field full">
          <span>附件 (可多选)</span>
          <input
            type="file"
            multiple
            @change="handleFileChange"
            data-testid="email-test-attachment"
          />
          <div v-if="testFiles.length" class="attachment-list">
            已选 {{ testFiles.length }} 个文件：
            <span v-for="(f, i) in testFiles" :key="i">{{ f.name }}{{ i < testFiles.length - 1 ? ', ' : '' }}</span>
          </div>
        </label>
        <div class="form-actions">
          <button class="primary-btn" type="submit" :disabled="isSendingTest">
            {{ isSendingTest ? '发送中...' : '发送测试邮件' }}
          </button>
        </div>
      </form>
    </section>
  </section>
</template>

<style scoped>
.email-settings-manager {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 18px;
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
  font-size: 14px;
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

.email-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
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

input[type="file"] {
  padding: 6px;
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
}

.policies-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
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

/* 2026-07-18 新增：高级选项折叠面板（企业邮箱兼容） */
.advanced-section {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
  padding: 8px 12px;
}
.advanced-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: #374151;
  font-size: 13px;
  padding: 4px 0;
}
.advanced-toggle:hover {
  color: #2563eb;
}
.advanced-body {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.advanced-hint {
  color: #6b7280;
  font-size: 12px;
  margin: 0 0 6px;
  line-height: 1.5;
}

.policy-editor {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px;
}

.policy-editor h4 {
  margin: 0 0 12px;
  color: #111827;
  font-size: 15px;
}

.recipient-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 240px;
  overflow-y: auto;
  padding: 6px 8px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.recipient-item {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.recipient-item:hover {
  background: #f3f4f6;
}

.recipient-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin: 0;
}

.recipient-name {
  color: #111827;
  font-weight: 500;
}

.recipient-email {
  color: #6b7280;
  font-size: 12px;
}

/* —— 收件人面板（带头部 / 工具栏 / 已选 chip） —— */
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

.recipient-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 10px;
}

.recipient-panel__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.recipient-search {
  flex: 1 1 200px;
  min-width: 160px;
  height: 32px;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 13px;
  background: #ffffff;
  color: #111827;
}

.recipient-search:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.recipient-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.link-btn {
  background: none;
  border: 0;
  color: #2563eb;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
}

.link-btn:hover {
  text-decoration: underline;
  background: #eff6ff;
}

.divider {
  width: 1px;
  height: 14px;
  background: #e5e7eb;
}

.recipient-counter {
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
  padding: 4px 10px;
  background: #f3f4f6;
  border-radius: 999px;
}

.recipient-counter.active {
  color: #1e3a8a;
  background: #dbeafe;
  font-weight: 600;
}

.recipient-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px dashed #e5e7eb;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: #eff6ff;
  color: #1e40af;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  font-size: 12px;
}

.chip-remove {
  background: none;
  border: 0;
  color: #1e40af;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}

.chip-remove:hover {
  color: #dc2626;
}

.attachment-list {
  margin-top: 6px;
  color: #4b5563;
  font-size: 12px;
}
</style>
