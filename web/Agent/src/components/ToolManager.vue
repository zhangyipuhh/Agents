<template>
  <!-- 工具管理主容器：左侧按分类分组的已注册工具列表，右侧详情/扫描结果面板 -->
  <div class="tool-manager">
    <!-- 顶部头部：标题 + 操作按钮 -->
    <div class="manager-header">
      <h3>工具管理</h3>
      <div class="header-actions">
        <button class="header-btn btn-scan" :disabled="scanning" @click="onScanTools">
          <span v-if="scanning" class="btn-loading-dot"></span>
          {{ scanning ? '扫描中...' : '扫描未注册工具' }}
        </button>
        <button class="header-btn btn-refresh" :disabled="loading" @click="loadTools">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="manager-body">
      <!-- 左侧：已注册工具列表（按 category 分组） -->
      <div class="tool-list-panel">
        <div v-if="loading && tools.length === 0" class="empty-state">
          加载中...
        </div>
        <div v-else-if="groupedTools.length === 0" class="empty-state">
          暂无已注册工具
        </div>
        <!-- 按 category 分组渲染 -->
        <div
          v-for="group in groupedTools"
          :key="group.category"
          class="category-group"
        >
          <div class="category-header" @click="toggleCategory(group.category)">
            <span class="category-arrow" :class="{ expanded: expandedCategories.has(group.category) }">
              ▶
            </span>
            <span class="category-name">{{ group.category }}</span>
            <span class="category-count">{{ group.tools.length }}</span>
          </div>
          <div v-show="expandedCategories.has(group.category)" class="category-tools">
            <div
              v-for="tool in group.tools"
              :key="tool.name"
              class="tool-item"
              :class="{ selected: selectedTool?.name === tool.name }"
              @click="selectTool(tool)"
            >
              <div class="tool-item-header">
                <span class="tool-name">{{ tool.display_name || formatToolName(tool) }}</span>
                <label class="tool-toggle-wrapper" @click.stop>
                  <input
                    type="checkbox"
                    class="tool-toggle"
                    :checked="tool.enabled"
                    @change="onToggleTool(tool, $event.target.checked, $event)"
                  />
                  <span class="toggle-slider"></span>
                </label>
              </div>
              <div class="tool-item-meta">
                <span class="tool-name-id">{{ formatToolName(tool) }}</span>
                <span v-if="!tool.enabled" class="tool-disabled-tag">已禁用</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：详情/扫描结果面板 -->
      <div class="tool-detail-panel">
        <!-- 扫描结果视图 -->
        <div v-if="viewMode === 'scan'" class="scan-result">
          <div class="scan-header">
            <h4>未注册工具扫描结果</h4>
            <button class="detail-btn btn-back" @click="exitScanView">返回</button>
          </div>
          <div v-if="unregisteredTools.length === 0" class="empty-state">
            未发现未注册工具
          </div>
          <div
            v-for="item in unregisteredTools"
            :key="item.name"
            class="unregistered-item"
          >
            <div class="unregistered-info">
              <div class="unregistered-name">{{ item.name }}</div>
              <div class="unregistered-path">{{ item.file_path }}</div>
              <div v-if="item.function_description" class="unregistered-desc">
                {{ item.function_description }}
              </div>
            </div>
            <button class="detail-btn btn-register" @click="openRegisterForm(item)">
              注册
            </button>
          </div>
        </div>

        <!-- 工具详情视图 -->
        <div v-else-if="selectedTool" class="tool-detail">
          <h4>{{ selectedTool.display_name || selectedTool.name }}</h4>
          <div class="detail-row"><span>名称:</span> {{ selectedTool.name }}</div>
          <div class="detail-row"><span>分类:</span> {{ selectedTool.category }}</div>
          <div class="detail-row" v-if="selectedTool.display_name">
            <span>展示名:</span> {{ selectedTool.display_name }}
          </div>
          <div class="detail-row" v-if="selectedTool.description">
            <span>描述:</span> {{ selectedTool.description }}
          </div>
          <div class="detail-row" v-if="selectedTool.module_path">
            <span>模块路径:</span> {{ selectedTool.module_path }}
          </div>
          <div class="detail-row" v-if="selectedTool.file_path">
            <span>文件路径:</span> {{ selectedTool.file_path }}
          </div>
          <div class="detail-row" v-if="selectedTool.return_description">
            <span>返回值:</span> {{ selectedTool.return_description }}
          </div>
          <div class="detail-row" v-if="selectedTool.function_description">
            <span>函数描述:</span>
            <pre class="detail-pre">{{ selectedTool.function_description }}</pre>
          </div>
          <div class="detail-row" v-if="selectedTool.args_schema && Object.keys(selectedTool.args_schema).length">
            <span>参数 Schema:</span>
            <pre class="detail-pre">{{ JSON.stringify(selectedTool.args_schema, null, 2) }}</pre>
          </div>
          <div class="detail-row">
            <span>状态:</span>
            <span :class="selectedTool.enabled ? 'status-on' : 'status-off'">
              {{ selectedTool.enabled ? '启用' : '禁用' }}
            </span>
          </div>

          <div class="detail-actions">
            <button class="detail-btn btn-toggle" @click="onToggleTool(selectedTool, !selectedTool.enabled, $event)">
              {{ selectedTool.enabled ? '禁用' : '启用' }}
            </button>
            <button class="detail-btn btn-delete" @click="onDeleteTool(selectedTool)">删除</button>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="no-selection">
          请从左侧选择一个工具查看详情，或点击"扫描未注册工具"
        </div>
      </div>
    </div>

    <!-- 注册新工具弹窗 -->
    <Transition name="dialog-fade">
      <div v-if="registerFormVisible" class="register-overlay" @click="closeRegisterForm">
        <div class="register-card" @click.stop>
          <div class="register-header">
            <h3>注册新工具</h3>
            <button class="register-close" @click="closeRegisterForm" aria-label="关闭">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5l10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          </div>
          <div class="register-body">
            <!-- 只读：自动解析的字段 -->
            <div class="form-group">
              <label class="form-label">名称（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.name" readonly />
            </div>
            <div class="form-group">
              <label class="form-label">模块路径（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.module_path" readonly />
            </div>
            <div class="form-group">
              <label class="form-label">文件路径（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.file_path" readonly />
            </div>
            <div class="form-group" v-if="registerData.function_description">
              <label class="form-label">函数描述（自动解析）</label>
              <textarea class="form-input readonly-input" :value="registerData.function_description" rows="3" readonly></textarea>
            </div>
            <div class="form-group" v-if="registerData.return_description">
              <label class="form-label">返回值描述（自动解析）</label>
              <input class="form-input readonly-input" :value="registerData.return_description" readonly />
            </div>
            <div class="form-group" v-if="registerData.args_schema && Object.keys(registerData.args_schema).length">
              <label class="form-label">参数 Schema（自动解析）</label>
              <textarea class="form-input readonly-input" :value="JSON.stringify(registerData.args_schema, null, 2)" rows="4" readonly></textarea>
            </div>

            <div class="form-divider"></div>

            <!-- 可编辑：需补充的字段 -->
            <div class="form-group">
              <label class="form-label">展示名称</label>
              <input
                v-model="registerData.display_name"
                class="form-input"
                placeholder="请输入展示名称（可选）"
              />
            </div>
            <div class="form-group">
              <label class="form-label">分类 <span class="required-mark">*</span></label>
              <input
                v-model="registerData.category"
                class="form-input"
                placeholder="如 filesystem / sandbox / mcp / map"
              />
            </div>
            <div class="form-group">
              <label class="form-label">描述</label>
              <textarea
                v-model="registerData.description"
                class="form-input"
                rows="3"
                placeholder="请输入工具描述"
              ></textarea>
            </div>
            <div class="form-group">
              <label class="form-label">
                <input type="checkbox" v-model="registerData.enabled" />
                启用工具
              </label>
            </div>

            <div v-if="registerError" class="error-message">{{ registerError }}</div>
            <div class="form-actions">
              <button class="detail-btn btn-back" @click="closeRegisterForm" :disabled="registering">取消</button>
              <button class="detail-btn btn-submit" :disabled="registering" @click="submitRegister">
                <span v-if="registering" class="btn-loading-dot"></span>
                {{ registering ? '注册中...' : '注册' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
/**
 * ToolManager - 工具管理组件
 *
 * 提供工具注册中心的完整管理界面（admin 权限）：
 * - 已注册工具列表，按 category 分组展示（可折叠）
 * - 扫描未注册工具文件（POST /api/admin/tools/scan）
 * - 注册新工具弹窗（从扫描结果选择，补充 description + category 后提交）
 * - 启用/禁用工具 toggle（PUT /api/admin/tools/{name}/enabled）
 * - 删除工具（DELETE /api/admin/tools/{name}，带 confirm 确认）
 *
 * 数据加载由组件自管理（onMounted 触发 listTools），
 * 在 UserSettingsDialog 中通过 v-show 始终挂载，切换 Tab 时仅 display 切换。
 */
import { ref, computed, onMounted } from 'vue'
import {
  listTools,
  listUnregisteredTools,
  registerTool,
  deleteTool,
  setToolEnabled,
  scanTools,
} from '../utils/api.js'

/** @type {import('vue').Ref<Array>} 已注册工具列表 */
const tools = ref([])

/** @type {import('vue').Ref<Object|null>} 当前选中的工具 */
const selectedTool = ref(null)

/** @type {import('vue').Ref<Array>} 未注册工具扫描结果 */
const unregisteredTools = ref([])

/** @type {import('vue').Ref<boolean>} 列表加载中 */
const loading = ref(false)

/** @type {import('vue').Ref<boolean>} 扫描中 */
const scanning = ref(false)

/** @type {import('vue').Ref<'detail'|'scan'>} 右侧面板视图模式 */
const viewMode = ref('detail')

/**
 * 提取工具的"文件名.函数名"展示形式
 * 从 tool.file_path 中取最后一个 / 或 \ 之后的文件名，去掉 .py 后缀
 * 拼接为 "BaseTools.get_current_time" 格式，便于用户识别工具来源
 * @param {Object} tool - 工具对象（含 file_path 和 name 字段）
 * @returns {string} "文件名.函数名" 或仅 "函数名"（当 file_path 为空时）
 */
function formatToolName(tool) {
  if (!tool || !tool.name) return ''
  const filePath = tool.file_path || ''
  if (!filePath) return tool.name
  const parts = filePath.split(/[/\\]/)
  const fileName = parts[parts.length - 1] || ''
  const baseName = fileName.replace(/\.py$/i, '')
  return baseName ? `${baseName}.${tool.name}` : tool.name
}

/** @type {import('vue').Ref<Set<string>>} 已展开的分类集合 */
const expandedCategories = ref(new Set())

/** @type {import('vue').Ref<boolean>} 注册弹窗是否可见 */
const registerFormVisible = ref(false)

/** @type {import('vue').Ref<boolean>} 注册提交中 */
const registering = ref(false)

/** @type {import('vue').Ref<string>} 注册错误信息 */
const registerError = ref('')

/** 注册表单数据（含自动解析的只读字段 + 可编辑字段） */
const registerData = ref({
  name: '',
  module_path: '',
  file_path: '',
  function_description: '',
  return_description: '',
  args_schema: {},
  display_name: '',
  category: '',
  description: '',
  enabled: true,
})

/**
 * 按 category 分组的工具列表（计算属性）
 * @returns {Array<{category: string, tools: Array}>} 分组后的工具列表
 */
const groupedTools = computed(() => {
  const map = new Map()
  for (const tool of tools.value) {
    const category = tool.category || '未分类'
    if (!map.has(category)) {
      map.set(category, [])
    }
    map.get(category).push(tool)
  }
  // 转为数组并按 category 名称排序
  return Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([category, toolList]) => ({
      category,
      tools: toolList.sort((a, b) => (a.name || '').localeCompare(b.name || '')),
    }))
})

onMounted(loadTools)

/**
 * 加载已注册工具列表
 * 首次加载时自动展开所有分类
 * @returns {Promise<void>} 无返回值；成功时更新 tools.value，失败时仅 console.error
 * @throws {Error} 内部捕获，不向上抛出
 */
async function loadTools() {
  loading.value = true
  try {
    const data = await listTools()
    tools.value = Array.isArray(data) ? data : []
    // 首次加载自动展开所有分类
    if (expandedCategories.value.size === 0 && groupedTools.value.length > 0) {
      expandedCategories.value = new Set(groupedTools.value.map(g => g.category))
    }
  } catch (err) {
    console.error('加载工具列表失败:', err)
    tools.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 切换分类的展开/折叠状态
 * @param {string} category - 分类名称
 */
function toggleCategory(category) {
  const next = new Set(expandedCategories.value)
  if (next.has(category)) {
    next.delete(category)
  } else {
    next.add(category)
  }
  expandedCategories.value = next
}

/**
 * 选中工具并切换到详情视图
 * @param {Object} tool - 工具对象
 */
function selectTool(tool) {
  selectedTool.value = tool
  viewMode.value = 'detail'
}

/**
 * 扫描未注册工具并切换到扫描结果视图
 * 优先调用 scanTools（POST 语义），失败时降级到 listUnregisteredTools（GET）
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function onScanTools() {
  scanning.value = true
  try {
    let data
    try {
      data = await scanTools()
    } catch {
      // POST 失败时降级到 GET
      data = await listUnregisteredTools()
    }
    unregisteredTools.value = Array.isArray(data) ? data : []
    viewMode.value = 'scan'
    selectedTool.value = null
  } catch (err) {
    alert('扫描未注册工具失败: ' + err.message)
  } finally {
    scanning.value = false
  }
}

/**
 * 退出扫描结果视图，返回详情视图
 */
function exitScanView() {
  viewMode.value = 'detail'
}

/**
 * 打开注册新工具弹窗，回填自动解析的只读字段
 * @param {Object} unregisteredItem - 扫描结果中的未注册工具项
 */
function openRegisterForm(unregisteredItem) {
  registerData.value = {
    name: unregisteredItem.name || '',
    module_path: unregisteredItem.module_path || '',
    file_path: unregisteredItem.file_path || '',
    function_description: unregisteredItem.function_description || '',
    return_description: unregisteredItem.return_description || '',
    args_schema: unregisteredItem.args_schema || {},
    display_name: '',
    category: '',
    description: '',
    enabled: true,
  }
  registerError.value = ''
  registerFormVisible.value = true
}

/**
 * 关闭注册弹窗并重置状态
 */
function closeRegisterForm() {
  registerFormVisible.value = false
  registerError.value = ''
}

/**
 * 提交注册新工具
 * 校验 category 必填后调用 registerTool，成功后刷新列表并关闭弹窗
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function submitRegister() {
  // 校验必填字段
  if (!registerData.value.category.trim()) {
    registerError.value = '请输入工具分类'
    return
  }
  if (!registerData.value.name) {
    registerError.value = '工具名称缺失'
    return
  }

  registering.value = true
  registerError.value = ''
  try {
    const payload = {
      name: registerData.value.name,
      display_name: registerData.value.display_name.trim() || null,
      category: registerData.value.category.trim(),
      description: registerData.value.description.trim() || null,
      module_path: registerData.value.module_path,
      file_path: registerData.value.file_path,
      args_schema: registerData.value.args_schema || {},
      return_description: registerData.value.return_description || null,
      function_description: registerData.value.function_description || null,
      enabled: registerData.value.enabled,
      sort_order: 0,
    }
    await registerTool(payload)
    closeRegisterForm()
    await loadTools()
    // 从扫描结果中移除已注册项
    unregisteredTools.value = unregisteredTools.value.filter(
      item => item.name !== payload.name
    )
  } catch (err) {
    registerError.value = err.message || '注册失败'
  } finally {
    registering.value = false
  }
}

/**
 * 切换工具启用状态
 * API 失败时回滚 DOM checkbox 到原状态
 * @param {Object} tool - 工具对象
 * @param {boolean} enabled - 目标启用状态
 * @param {Event} event - change/click 事件对象，用于失败时回滚 DOM
 * @returns {Promise<void>} 无返回值；失败时回滚 DOM 并 alert
 * @throws {Error} 内部捕获，不向上抛出
 */
async function onToggleTool(tool, enabled, event) {
  try {
    await setToolEnabled(tool.name, enabled)
    tool.enabled = enabled
  } catch (err) {
    // API 失败时回滚 DOM checkbox 到原状态
    if (event && event.target && event.target.type === 'checkbox') {
      event.target.checked = tool.enabled
    }
    alert('切换失败: ' + err.message)
  }
}

/**
 * 删除工具（含 confirm 确认）
 * @param {Object} tool - 待删除的工具对象
 * @returns {Promise<void>} 无返回值；失败时 alert 提示
 * @throws {Error} 内部捕获，不向上抛出
 */
async function onDeleteTool(tool) {
  if (!confirm(`确认删除工具 "${tool.name}"？此操作不可恢复。`)) return
  try {
    await deleteTool(tool.name)
    selectedTool.value = null
    await loadTools()
  } catch (err) {
    alert('删除失败: ' + err.message)
  }
}
</script>

<style scoped>
/* 主容器 */
.tool-manager {
  padding: var(--space-md);
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 顶部头部 */
.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.manager-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.header-actions {
  display: flex;
  gap: var(--space-sm);
}

.header-btn {
  padding: 6px 14px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.header-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.btn-scan {
  background-color: var(--color-accent);
}

.btn-scan:hover:not(:disabled) {
  background-color: var(--color-accent-hover);
}

.btn-refresh {
  background-color: var(--color-bg-active);
  color: var(--color-text-primary);
}

.btn-refresh:hover:not(:disabled) {
  background-color: var(--color-border);
}

/* 主体左右分栏 */
.manager-body {
  display: flex;
  gap: var(--space-md);
  flex: 1;
  min-height: 0;
}

/* 左侧工具列表面板 */
.tool-list-panel {
  width: 260px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-sm);
  background-color: var(--color-bg-secondary);
}

.empty-state,
.no-selection {
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-xl);
  font-size: var(--font-size-sm);
}

/* 分类分组 */
.category-group {
  margin-bottom: var(--space-sm);
}

.category-header {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  cursor: pointer;
  border-radius: var(--radius-sm);
  user-select: none;
  transition: var(--transition-colors);
}

.category-header:hover {
  background-color: var(--color-bg-hover);
}

.category-arrow {
  font-size: 10px;
  color: var(--color-text-muted);
  transition: var(--transition-transform);
  display: inline-block;
}

.category-arrow.expanded {
  transform: rotate(90deg);
}

.category-name {
  flex: 1;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.category-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background-color: var(--color-bg-active);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.category-tools {
  margin-top: var(--space-xs);
}

/* 工具项 */
.tool-item {
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 2px;
  border: 1px solid transparent;
  transition: var(--transition-colors);
}

.tool-item:hover {
  background-color: var(--color-bg-hover);
}

.tool-item.selected {
  background-color: var(--color-accent-light);
  border-color: var(--color-accent);
}

.tool-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tool-name {
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.tool-item-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.tool-name-id {
  font-family: monospace;
}

.tool-disabled-tag {
  background-color: var(--color-tag-beta);
  color: var(--color-tag-beta-text);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-size: 10px;
}

/* toggle 开关（复用 McpServerManager 样式，改用 CSS 变量） */
.tool-toggle-wrapper {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}

.tool-toggle-wrapper input {
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
  background-color: var(--color-border);
  border-radius: 20px;
  transition: var(--transition-colors);
}

.tool-toggle-wrapper input:checked + .toggle-slider {
  background-color: var(--color-accent);
}

.toggle-slider:before {
  position: absolute;
  content: '';
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background-color: var(--color-text-inverse);
  border-radius: 50%;
  transition: var(--transition-transform);
}

.tool-toggle-wrapper input:checked + .toggle-slider:before {
  transform: translateX(16px);
}

/* 右侧详情面板 */
.tool-detail-panel {
  flex: 1;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  overflow-y: auto;
  background-color: var(--color-bg-primary);
}

.tool-detail h4,
.scan-result h4 {
  margin: 0 0 var(--space-md) 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

/* 详情行 */
.detail-row {
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
}

.detail-row span:first-child {
  color: var(--color-text-muted);
  display: inline-block;
  min-width: 80px;
  flex-shrink: 0;
}

.detail-pre {
  margin: 0;
  flex: 1;
  padding: var(--space-sm);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: monospace;
  font-size: var(--font-size-xs);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow-y: auto;
  color: var(--color-text-primary);
}

.status-on {
  color: var(--color-success);
  font-weight: var(--font-weight-medium);
}

.status-off {
  color: var(--color-error);
  font-weight: var(--font-weight-medium);
}

/* 详情操作按钮 */
.detail-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.detail-btn {
  padding: 6px 16px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
}

.btn-toggle {
  background-color: var(--color-tag-beta);
  color: var(--color-tag-beta-text);
}

.btn-toggle:hover {
  background-color: var(--color-warning);
  color: var(--color-text-inverse);
}

.btn-delete {
  background-color: #FEE2E2;
  color: #DC2626;
}

.btn-delete:hover {
  background-color: #FECACA;
}

.btn-back {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}

.btn-back:hover {
  background-color: #D6E4F5;
}

/* 扫描结果 */
.scan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.unregistered-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-sm);
  background-color: var(--color-bg-secondary);
}

.unregistered-info {
  flex: 1;
  min-width: 0;
}

.unregistered-name {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-family: monospace;
}

.unregistered-path {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
  word-break: break-all;
}

.unregistered-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-xs);
  white-space: pre-wrap;
}

.btn-register {
  background-color: var(--color-accent);
  color: var(--color-text-inverse);
  flex-shrink: 0;
}

.btn-register:hover {
  background-color: var(--color-accent-hover);
}

/* 注册弹窗 */
.register-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 2100;
  background-color: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl);
}

.register-card {
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.register-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.register-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.register-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  transition: var(--transition-colors);
  background: none;
  border: none;
  cursor: pointer;
}

.register-close:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.register-body {
  padding: var(--space-lg);
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: var(--space-md);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.required-mark {
  color: var(--color-error);
}

.form-input {
  width: 100%;
  padding: 8px var(--space-sm);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors), var(--transition-shadow);
  box-sizing: border-box;
  font-family: inherit;
}

.form-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-light);
  background-color: var(--color-bg-primary);
  outline: none;
}

.form-input::placeholder {
  color: var(--color-text-muted);
}

textarea.form-input {
  resize: vertical;
  font-family: monospace;
}

.readonly-input {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: not-allowed;
}

.form-divider {
  height: 1px;
  background-color: var(--color-border);
  margin: var(--space-md) 0;
}

.error-message {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--color-error);
  background-color: #FEF2F2;
  border-radius: var(--radius-sm);
  border: 1px solid #FECACA;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.btn-submit {
  background-color: var(--color-accent);
  color: var(--color-text-inverse);
  min-width: 100px;
  justify-content: center;
}

.btn-submit:hover:not(:disabled) {
  background-color: var(--color-accent-hover);
}

.btn-submit:disabled,
.detail-btn:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

/* 加载小圆点 */
.btn-loading-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: tool-spin 0.6s linear infinite;
}

/* 弹窗过渡动画 */
.dialog-fade-enter-active {
  transition: opacity 0.25s ease;
}

.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-active .register-card {
  animation: tool-scale-in 0.25s ease;
}

.dialog-fade-leave-active .register-card {
  animation: tool-scale-out 0.2s ease;
}

@keyframes tool-scale-in {
  from {
    transform: scale(0.95);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes tool-scale-out {
  from {
    transform: scale(1);
    opacity: 1;
  }
  to {
    transform: scale(0.95);
    opacity: 0;
  }
}

@keyframes tool-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
