<template>
  <div class="mcp-server-manager">
    <div class="manager-header">
      <h3>MCP 服务器管理</h3>
      <button class="new-server-btn" @click="showNewForm">+ 新增服务器</button>
    </div>

    <div class="manager-body">
      <div class="server-list-panel">
        <div v-if="servers.length === 0" class="empty-state">
          暂无 MCP 服务器，点击上方按钮新增
        </div>
        <div
          v-for="server in servers"
          :key="server.name"
          class="server-item"
          :class="{ selected: selectedServer?.name === server.name }"
          @click="selectServer(server)"
        >
          <div class="server-item-header">
            <span class="server-name">{{ server.display_name || server.name }}</span>
            <label class="server-toggle-wrapper" @click.stop>
              <input
                type="checkbox"
                class="server-toggle"
                :checked="server.enabled"
                @change="onToggleServer(server, $event.target.checked, $event)"
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
          <div class="server-item-meta">
            <span class="server-type">{{ server.type }}</span>
            <span v-if="server.tags?.length" class="server-tags">
              {{ server.tags.join(', ') }}
            </span>
          </div>
        </div>
      </div>

      <div class="server-detail-panel">
        <div v-if="formVisible" class="server-form">
          <h4>{{ editingServer ? '编辑服务器' : '新增服务器' }}</h4>
          <div class="form-row">
            <label>名称（唯一标识）</label>
            <input v-model="formData.name" :disabled="!!editingServer" placeholder="amap" />
          </div>
          <div class="form-row">
            <label>显示名</label>
            <input v-model="formData.display_name" placeholder="高德地图" />
          </div>
          <div class="form-row">
            <label>类型</label>
            <select v-model="formData.type">
              <option value="sse">SSE</option>
              <option value="stdio">STDIO</option>
              <option value="http">HTTP</option>
            </select>
          </div>
          <div class="form-row" v-if="formData.type === 'sse' || formData.type === 'http'">
            <label>URL</label>
            <input v-model="formData.url" placeholder="http://10.20.8.178:1024/sse" />
          </div>
          <div class="form-row" v-if="formData.type === 'stdio'">
            <label>Command（JSON 数组）</label>
            <input v-model="commandText" placeholder='["node", "server.js"]' />
          </div>
          <div class="form-row">
            <label>Tags（逗号分隔）</label>
            <input v-model="tagsText" placeholder="map, geo" />
          </div>
          <div class="form-row">
            <label>Timeout（秒）</label>
            <input type="number" v-model.number="formData.timeout" />
          </div>
          <div class="form-row">
            <label>Read Timeout（秒）</label>
            <input type="number" v-model.number="formData.read_timeout" />
          </div>
          <div class="form-row">
            <label>Connect Timeout（秒）</label>
            <input type="number" v-model.number="formData.connect_timeout" />
          </div>
          <div class="form-row" v-if="formData.type === 'stdio'">
            <label>Args（JSON 数组）</label>
            <textarea v-model="argsText" rows="3" placeholder='["--port", "8080"]'></textarea>
          </div>
          <div class="form-row" v-if="formData.type === 'stdio'">
            <label>Env（JSON 对象）</label>
            <textarea v-model="envText" rows="3" placeholder='{"NODE_ENV": "production"}'></textarea>
          </div>
          <div class="form-row" v-if="formData.type === 'sse' || formData.type === 'http'">
            <label>Headers（JSON 对象）</label>
            <textarea v-model="headersText" rows="3" placeholder='{"Authorization": "Bearer xxx"}'></textarea>
          </div>
          <div class="form-row">
            <label>Tool Config（JSON）</label>
            <textarea v-model="toolConfigText" rows="6" placeholder='{"enable_injection": true, ...}'></textarea>
          </div>
          <div v-if="editingServer" class="form-row form-row-inline">
            <label>
              <input type="checkbox" v-model="progressReportingEnabled" />
              启用进度上报
            </label>
          </div>
          <div class="form-actions">
            <button class="save-btn" @click="saveServer">保存</button>
            <button class="cancel-btn" @click="hideForm">取消</button>
          </div>
        </div>

        <div v-else-if="selectedServer" class="server-detail">
          <h4>{{ selectedServer.display_name || selectedServer.name }}</h4>
          <div class="detail-row"><span>名称:</span> {{ selectedServer.name }}</div>
          <div class="detail-row"><span>类型:</span> {{ selectedServer.type }}</div>
          <div class="detail-row" v-if="selectedServer.url">
            <span>URL:</span> {{ selectedServer.url }}
          </div>
          <div class="detail-row" v-if="selectedServer.tags?.length">
            <span>Tags:</span> {{ selectedServer.tags.join(', ') }}
          </div>
          <div class="detail-row">
            <span>Connect Timeout:</span> {{ selectedServer.connect_timeout }}
          </div>
          <div class="detail-row" v-if="selectedServer.args?.length">
            <span>Args:</span> {{ JSON.stringify(selectedServer.args) }}
          </div>
          <div class="detail-row" v-if="selectedServer.env && Object.keys(selectedServer.env).length">
            <span>Env:</span> {{ JSON.stringify(selectedServer.env) }}
          </div>
          <div class="detail-row" v-if="selectedServer.headers && Object.keys(selectedServer.headers).length">
            <span>Headers:</span> {{ JSON.stringify(selectedServer.headers) }}
          </div>
          <div class="detail-row" v-if="selectedServer.tool_config">
            <span>Tool Config:</span> {{ JSON.stringify(selectedServer.tool_config) }}
          </div>
          <div class="detail-row">
            <span>进度上报:</span>
            <span :class="selectedServer.progress_reporting?.enabled ? 'status-on' : 'status-off'">
              {{ selectedServer.progress_reporting?.enabled ? '启用' : '禁用' }}
            </span>
          </div>
          <div class="detail-row">
            <span>状态:</span>
            <span :class="selectedServer.enabled ? 'status-on' : 'status-off'">
              {{ selectedServer.enabled ? '启用' : '禁用' }}
            </span>
          </div>

          <div class="detail-actions">
            <button class="edit-btn" @click="editServer(selectedServer)">编辑</button>
            <button class="delete-btn" @click="onDeleteServer(selectedServer)">删除</button>
          </div>

          <div class="methods-section">
            <div class="methods-header" @click="toggleMethods">
              <span
                class="methods-arrow"
                :class="{ expanded: methodsExpanded }"
              >▶</span>
              <h5>方法列表</h5>
              <button class="refresh-methods-btn" @click.stop="onRefreshMethods">
                刷新方法列表
              </button>
            </div>
            <div v-show="methodsExpanded">
              <div v-if="methods.length === 0" class="methods-empty">
                暂无方法，点击"刷新方法列表"拉取
              </div>
              <div v-for="m in methods" :key="m.method_name" class="method-item">
                <label class="method-toggle-wrapper">
                  <input
                    type="checkbox"
                    :checked="m.enabled"
                    @change="onToggleMethod(m, $event.target.checked, $event)"
                  />
                  <span>{{ m.method_name }}</span>
                </label>
                <span v-if="m.description" class="method-desc">{{ m.description }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="no-selection">
          请从左侧选择一个服务器查看详情
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  listMcpServers,
  createMcpServer,
  updateMcpServer,
  deleteMcpServer,
  toggleMcpServer,
  listMcpMethods,
  refreshMcpMethods,
  toggleMcpMethod,
} from '../utils/api.js'

const servers = ref([])
const selectedServer = ref(null)
const methods = ref([])
const methodsExpanded = ref(true)
const formVisible = ref(false)

/**
 * 切换方法列表的展开/折叠状态
 */
function toggleMethods() {
  methodsExpanded.value = !methodsExpanded.value
}
const editingServer = ref(null)
const commandText = ref('')
const tagsText = ref('')
const argsText = ref('[]')
const envText = ref('{}')
const headersText = ref('{}')
const progressReportingEnabled = ref(false)
const toolConfigText = ref(JSON.stringify({
  enable_injection: true,
  default_param_keys: [],
  hidden_param_keys: [],
  unwrap_result: false,
}, null, 2))

const formData = ref({
  name: '',
  display_name: '',
  type: 'sse',
  url: '',
  timeout: 5,
  read_timeout: 300,
  connect_timeout: 10,
})

onMounted(loadServers)

/**
 * 加载 MCP 服务器列表
 * @returns {Promise<void>} 无返回值；成功时更新 servers.value，失败时仅 console.error
 * @throws {Error} 内部捕获，不向上抛出
 */
async function loadServers() {
  try {
    servers.value = await listMcpServers()
  } catch (err) {
    console.error('加载 MCP 服务器列表失败:', err)
  }
}

/**
 * 选中指定服务器并加载其方法列表
 * @param {Object} server - 服务器对象（含 name 字段）
 * @returns {Promise<void>} 无返回值
 */
async function selectServer(server) {
  selectedServer.value = server
  formVisible.value = false
  try {
    methods.value = await listMcpMethods(server.name)
  } catch (err) {
    methods.value = []
    console.error('加载方法列表失败:', err)
  }
}

/**
 * 显示新增服务器表单，重置表单数据
 */
function showNewForm() {
  editingServer.value = null
  formData.value = {
    name: '',
    display_name: '',
    type: 'sse',
    url: '',
    timeout: 5,
    read_timeout: 300,
    connect_timeout: 10,
  }
  commandText.value = ''
  tagsText.value = ''
  argsText.value = '[]'
  envText.value = '{}'
  headersText.value = '{}'
  progressReportingEnabled.value = false
  toolConfigText.value = JSON.stringify({
    enable_injection: true,
    default_param_keys: [],
    hidden_param_keys: [],
    unwrap_result: false,
  }, null, 2)
  formVisible.value = true
}

/**
 * 显示编辑服务器表单，回填现有数据
 * @param {Object} server - 待编辑的服务器对象
 */
function editServer(server) {
  editingServer.value = server
  formData.value = {
    name: server.name,
    display_name: server.display_name || '',
    type: server.type,
    url: server.url || '',
    timeout: server.timeout || 5,
    read_timeout: server.read_timeout || 300,
    connect_timeout: server.connect_timeout || 10,
  }
  commandText.value = server.command ? JSON.stringify(server.command) : ''
  tagsText.value = (server.tags || []).join(', ')
  argsText.value = JSON.stringify(server.args || [])
  envText.value = JSON.stringify(server.env || {})
  headersText.value = JSON.stringify(server.headers || {})
  progressReportingEnabled.value = server.progress_reporting?.enabled || false
  toolConfigText.value = JSON.stringify(server.tool_config || {
    enable_injection: true,
    default_param_keys: [],
    hidden_param_keys: [],
    unwrap_result: false,
  }, null, 2)
  formVisible.value = true
}

/**
 * 隐藏表单并清空编辑状态
 */
function hideForm() {
  formVisible.value = false
  editingServer.value = null
}

/**
 * 保存服务器（新增或编辑）
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function saveServer() {
  try {
    const tags = tagsText.value
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)

    let parsedArgs = []
    let parsedEnv = {}
    let parsedHeaders = {}
    let parsedToolConfig = {}
    try {
      parsedArgs = argsText.value ? JSON.parse(argsText.value) : []
      parsedEnv = envText.value ? JSON.parse(envText.value) : {}
      parsedHeaders = headersText.value ? JSON.parse(headersText.value) : {}
      parsedToolConfig = toolConfigText.value ? JSON.parse(toolConfigText.value) : {}
    } catch (err) {
      alert('JSON 格式错误: ' + err.message)
      return
    }

    const payload = {
      ...formData.value,
      tags,
      command: formData.value.type === 'stdio' && commandText.value
        ? JSON.parse(commandText.value)
        : null,
      args: parsedArgs,
      env: parsedEnv,
      headers: parsedHeaders,
      tool_config: parsedToolConfig,
    }
    if (editingServer.value) {
      payload.progress_reporting = { enabled: progressReportingEnabled.value }
      await updateMcpServer(editingServer.value.name, payload)
    } else {
      await createMcpServer(payload)
    }
    hideForm()
    await loadServers()
    // C2 修复：保存后若 selectedServer 仍存在，从新列表中刷新引用
    if (selectedServer.value) {
      const refreshed = servers.value.find(s => s.name === selectedServer.value.name)
      if (refreshed) {
        selectedServer.value = refreshed
        methods.value = await listMcpMethods(refreshed.name).catch(() => [])
      } else {
        selectedServer.value = null
        methods.value = []
      }
    }
  } catch (err) {
    alert('保存失败: ' + err.message)
  }
}

/**
 * 删除指定服务器（含 confirm 确认）
 * @param {Object} server - 待删除的服务器对象
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 */
async function onDeleteServer(server) {
  if (!confirm(`确认删除服务器 "${server.name}"？`)) return
  try {
    await deleteMcpServer(server.name)
    selectedServer.value = null
    methods.value = []
    await loadServers()
  } catch (err) {
    alert('删除失败: ' + err.message)
  }
}

/**
 * 切换服务器启用状态
 * @param {Object} server - 服务器对象
 * @param {boolean} enabled - 目标启用状态
 * @param {Event} event - change 事件对象，用于失败时回滚 DOM
 * @returns {Promise<void>} 无返回值；失败时回滚 DOM 并 alert
 */
async function onToggleServer(server, enabled, event) {
  try {
    await toggleMcpServer(server.name, enabled)
    server.enabled = enabled
  } catch (err) {
    // I1 修复：API 失败时回滚 DOM checkbox 到原状态
    if (event && event.target) {
      event.target.checked = server.enabled
    }
    alert('切换失败: ' + err.message)
  }
}

/**
 * 刷新当前选中服务器的方法列表
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 */
async function onRefreshMethods() {
  if (!selectedServer.value) return
  try {
    await refreshMcpMethods(selectedServer.value.name)
    methods.value = await listMcpMethods(selectedServer.value.name)
  } catch (err) {
    alert('刷新失败: ' + err.message)
  }
}

/**
 * 切换单个方法的启用状态
 * @param {Object} method - 方法对象（含 method_name 字段）
 * @param {boolean} enabled - 目标启用状态
 * @param {Event} event - change 事件对象，用于失败时回滚 DOM
 * @returns {Promise<void>} 无返回值；失败时回滚 DOM 并 alert
 */
async function onToggleMethod(method, enabled, event) {
  try {
    await toggleMcpMethod(selectedServer.value.name, method.method_name, enabled)
    method.enabled = enabled
  } catch (err) {
    // I1 修复：API 失败时回滚 DOM checkbox 到原状态
    if (event && event.target) {
      event.target.checked = method.enabled
    }
    alert('切换失败: ' + err.message)
  }
}
</script>

<style scoped>
.mcp-server-manager {
  padding: 12px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.manager-header h3 {
  margin: 0;
  font-size: 16px;
}
.new-server-btn {
  padding: 6px 12px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.new-server-btn:hover {
  background: #1d4ed8;
}
.manager-body {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.server-list-panel {
  width: 240px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  padding: 8px;
}
.server-item {
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 4px;
  border: 1px solid transparent;
}
.server-item:hover {
  background: #f3f4f6;
}
.server-item.selected {
  background: #dbeafe;
  border-color: #2563eb;
}
.server-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.server-name {
  font-weight: 500;
}
.server-item-meta {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}
.server-type {
  background: #e5e7eb;
  padding: 1px 6px;
  border-radius: 2px;
  margin-right: 4px;
}
.server-toggle-wrapper {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}
.server-toggle-wrapper input {
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #ccc;
  border-radius: 20px;
  transition: 0.3s;
}
.server-toggle-wrapper input:checked + .toggle-slider {
  background: #2563eb;
}
.toggle-slider:before {
  position: absolute;
  content: '';
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background: white;
  border-radius: 50%;
  transition: 0.3s;
}
.server-toggle-wrapper input:checked + .toggle-slider:before {
  transform: translateX(16px);
}
.server-detail-panel {
  flex: 1;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  padding: 12px;
  overflow-y: auto;
}
.empty-state,
.no-selection {
  color: #9ca3af;
  text-align: center;
  padding: 24px;
}
.server-form h4,
.server-detail h4 {
  margin: 0 0 12px 0;
}
.form-row {
  margin-bottom: 8px;
}
.form-row label {
  display: block;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}
.form-row input,
.form-row select,
.form-row textarea {
  width: 100%;
  padding: 6px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  box-sizing: border-box;
  font-family: inherit;
}
.form-row textarea {
  resize: vertical;
}
.form-row-inline label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #374151;
  cursor: pointer;
}
.form-row-inline input[type="checkbox"] {
  width: auto;
}
.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.save-btn {
  padding: 6px 16px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.cancel-btn {
  padding: 6px 16px;
  background: #e5e7eb;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.detail-row {
  margin-bottom: 6px;
  font-size: 14px;
}
.detail-row span:first-child {
  color: #6b7280;
  display: inline-block;
  width: 60px;
}
.status-on {
  color: #16a34a;
}
.status-off {
  color: #dc2626;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin: 12px 0;
}
.edit-btn {
  padding: 4px 12px;
  background: #f59e0b;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.delete-btn {
  padding: 4px 12px;
  background: #dc2626;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.methods-section {
  margin-top: 16px;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
}
.methods-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.methods-header h5 {
  margin: 0;
  flex: 1;
}
.methods-arrow {
  font-size: 10px;
  color: #6b7280;
  transition: transform 0.2s;
  display: inline-block;
}
.methods-arrow.expanded {
  transform: rotate(90deg);
}
.refresh-methods-btn {
  padding: 4px 8px;
  background: #6b7280;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.methods-empty {
  color: #9ca3af;
  font-size: 13px;
  padding: 8px 0;
}
.method-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.method-toggle-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.method-desc {
  color: #6b7280;
  font-size: 12px;
}
</style>
