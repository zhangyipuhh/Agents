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
import { onMounted, reactive, ref } from 'vue'
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

const TAB_LABELS = [
  { id: TAB_SERVER, label: '服务器配置' },
  { id: TAB_POLICIES, label: '发送策略' },
  { id: TAB_TEST, label: '测试发送' },
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
})
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
})
const policyError = ref('')
const policyMessage = ref('')

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
      })
      policyMessage.value = '策略已更新'
    } else {
      await createEmailPolicy({
        name: policyForm.name,
        description: policyForm.description,
        recipient_user_ids: policyForm.recipient_user_ids,
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
    testMessage.value = `发送成功！共发送给 ${result.sent_to.length} 个收件人`
  } catch (err) {
    testError.value = err.message
  } finally {
    isSendingTest.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    loadServerConfig(),
    loadEmailableUsers(),
    loadPolicies(),
  ])
})
</script>

<template>
  <section class="email-settings-manager">
    <div
      class="tablist"
      role="tablist"
      aria-label="邮件设置管理"
    >
      <button
        v-for="tab in TAB_LABELS"
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
          <p>配置 QQ 邮箱 SMTP_SSL（465）+ 授权码；密码留空表示不修改原密码。</p>
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
        <label class="inline-field">
          <input v-model="serverConfig.use_ssl" type="checkbox" />
          <span>使用 SMTP_SSL（取消则走 STARTTLS）</span>
        </label>
        <label class="form-field">
          <span>登录账号 *</span>
          <input v-model="serverConfig.username" type="text" placeholder="发件邮箱地址" />
        </label>
        <label class="form-field">
          <span>密码 / 授权码</span>
          <input v-model="serverConfig.password" type="password" placeholder="留空表示不修改原密码" />
        </label>
        <label class="form-field">
          <span>发件人显示名</span>
          <input v-model="serverConfig.sender_name" type="text" placeholder="如：管理员" />
        </label>
        <label class="inline-field">
          <input v-model="serverConfig.enabled" type="checkbox" />
          <span>启用此配置</span>
        </label>
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
          <form class="email-form" @submit.prevent="savePolicy">
            <label class="form-field">
              <span>策略名称 *</span>
              <input v-model="policyForm.name" type="text" placeholder="例如：运维告警通知" />
            </label>
            <label class="form-field full">
              <span>策略描述</span>
              <textarea v-model="policyForm.description" rows="2" placeholder="可选"></textarea>
            </label>
            <div class="form-field full">
              <span>收件人 *</span>
              <div class="recipient-list">
                <label
                  v-for="u in emailableUsers"
                  :key="u.id"
                  class="recipient-item"
                >
                  <input
                    type="checkbox"
                    :value="u.id"
                    v-model="policyForm.recipient_user_ids"
                  />
                  <span>{{ u.real_name || u.username }} ({{ u.email }})</span>
                </label>
              </div>
              <div v-if="!emailableUsers.length" class="empty-state">
                暂无可选用户（所有用户邮箱为空）
              </div>
            </div>
            <div class="form-actions">
              <button class="primary-btn" type="submit" :disabled="isSavingPolicy">
                {{ isSavingPolicy ? '保存中...' : '保存策略' }}
              </button>
              <button class="secondary-btn" type="button" @click="cancelEditPolicy">取消</button>
              <button
                v-if="selectedPolicy"
                class="danger-btn"
                type="button"
                @click="removePolicy(selectedPolicy)"
              >
                删除
              </button>
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
          <p>使用当前已保存的 SMTP 配置发送；附件从本地浏览器上传。</p>
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
  gap: 6px;
  max-height: 240px;
  overflow-y: auto;
  padding: 8px;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
}

.recipient-item {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.recipient-item input[type="checkbox"] {
  width: auto;
}

.attachment-list {
  margin-top: 6px;
  color: #4b5563;
  font-size: 12px;
}
</style>
