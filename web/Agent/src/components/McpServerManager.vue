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
                @change="onToggleServer(server, $event.target.checked)"
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
            <div class="methods-header">
              <h5>方法列表</h5>
              <button class="refresh-methods-btn" @click="onRefreshMethods">
                刷新方法列表
              </button>
            </div>
            <div v-if="methods.length === 0" class="methods-empty">
              暂无方法，点击"刷新方法列表"拉取
            </div>
            <div v-for="m in methods" :key="m.method_name" class="method-item">
              <label class="method-toggle-wrapper">
                <input
                  type="checkbox"
                  :checked="m.enabled"
                  @change="onToggleMethod(m, $event.target.checked)"
                />
                <span>{{ m.method_name }}</span>
              </label>
              <span v-if="m.description" class="method-desc">{{ m.description }}</span>
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
const formVisible = ref(false)
const editingServer = ref(null)
const commandText = ref('')
const tagsText = ref('')

const formData = ref({
  name: '',
  display_name: '',
  type: 'sse',
  url: '',
  timeout: 5,
  read_timeout: 300,
})

onMounted(loadServers)

async function loadServers() {
  try {
    servers.value = await listMcpServers()
  } catch (err) {
    console.error('加载 MCP 服务器列表失败:', err)
  }
}

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

function showNewForm() {
  editingServer.value = null
  formData.value = {
    name: '',
    display_name: '',
    type: 'sse',
    url: '',
    timeout: 5,
    read_timeout: 300,
  }
  commandText.value = ''
  tagsText.value = ''
  formVisible.value = true
}

function editServer(server) {
  editingServer.value = server
  formData.value = {
    name: server.name,
    display_name: server.display_name || '',
    type: server.type,
    url: server.url || '',
    timeout: server.timeout || 5,
    read_timeout: server.read_timeout || 300,
  }
  commandText.value = server.command ? JSON.stringify(server.command) : ''
  tagsText.value = (server.tags || []).join(', ')
  formVisible.value = true
}

function hideForm() {
  formVisible.value = false
  editingServer.value = null
}

async function saveServer() {
  const tags = tagsText.value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
  const payload = {
    ...formData.value,
    tags,
    command: formData.value.type === 'stdio' && commandText.value
      ? JSON.parse(commandText.value)
      : null,
  }
  try {
    if (editingServer.value) {
      await updateMcpServer(editingServer.value.name, payload)
    } else {
      await createMcpServer(payload)
    }
    hideForm()
    await loadServers()
  } catch (err) {
    alert('保存失败: ' + err.message)
  }
}

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

async function onToggleServer(server, enabled) {
  try {
    await toggleMcpServer(server.name, enabled)
    server.enabled = enabled
  } catch (err) {
    alert('切换失败: ' + err.message)
  }
}

async function onRefreshMethods() {
  if (!selectedServer.value) return
  try {
    await refreshMcpMethods(selectedServer.value.name)
    methods.value = await listMcpMethods(selectedServer.value.name)
  } catch (err) {
    alert('刷新失败: ' + err.message)
  }
}

async function onToggleMethod(method, enabled) {
  try {
    await toggleMcpMethod(selectedServer.value.name, method.method_name, enabled)
    method.enabled = enabled
  } catch (err) {
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
.form-row select {
  width: 100%;
  padding: 6px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  box-sizing: border-box;
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
  justify-content: space-between;
  align-items: center;
}
.methods-header h5 {
  margin: 0;
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
