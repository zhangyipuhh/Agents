<script setup>
/**
 * ApiConfigManager - API 接口配置管理组件（admin）
 *
 * 左右布局：左侧为「文件夹 / 接口」树（支持搜索、新建、inline 重命名、删除、展开折叠），
 * 右侧为选中接口节点的请求配置区（method + URL + Params / Body / Headers / Mock 子 Tab），
 * 支持保存配置、发送真实请求并展示断言校验结果与最近发送历史。
 *
 * 后端契约：/api/admin/api-configs（见 utils/api.js 中 fetchApiConfigTree 等封装）。
 */
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import {
  fetchApiConfigTree,
  createApiConfigNode,
  updateApiConfigNode,
  deleteApiConfigNode,
  fetchApiConfig,
  saveApiConfig,
  sendApiConfig,
  fetchApiConfigRuns,
} from '../utils/api.js'

// ---------- 子 Tab 常量 ----------
const SUB_TAB_PARAMS = 'params'
const SUB_TAB_BODY = 'body'
const SUB_TAB_HEADERS = 'headers'
const SUB_TAB_MOCK = 'mock'

const SUB_TABS = [
  { id: SUB_TAB_PARAMS, label: 'Params' },
  { id: SUB_TAB_BODY, label: 'Body' },
  { id: SUB_TAB_HEADERS, label: 'Headers' },
  { id: SUB_TAB_MOCK, label: 'Mock' },
]

// Body 类型枚举（与后端 body_type 字段一致）
const BODY_TYPES = [
  { value: 'none', label: 'none' },
  { value: 'form-data', label: 'form-data' },
  { value: 'x-www-form-urlencoded', label: 'x-www-form-urlencoded' },
  { value: 'json', label: 'JSON' },
  { value: 'xml', label: 'XML' },
  { value: 'text', label: 'Text' },
]

// Mock 断言规则类型
const EXPECTATION_TYPES = [
  { value: 'status_code', label: '状态码等于' },
  { value: 'body_contains', label: '响应体包含' },
  { value: 'json_field', label: 'JSON字段' },
]

// Headers 参数名常用建议（datalist）
const HEADER_SUGGESTIONS = [
  'Content-Type',
  'Authorization',
  'Accept',
  'Accept-Encoding',
  'Accept-Language',
  'User-Agent',
  'Cache-Control',
  'Cookie',
  'Origin',
  'Referer',
  'X-Requested-With',
  'X-API-Key',
]

// 响应体预览最大字符数，超出截断并提示
const RESPONSE_PREVIEW_LIMIT = 5000

// ---------- 树状态 ----------
const nodes = ref([])
const expandedIds = ref(new Set())
const searchKeyword = ref('')
const selectedNodeId = ref(null)
const renamingId = ref(null)
const renamingValue = ref('')
const isLoadingTree = ref(false)
const treeError = ref('')
const treeMessage = ref('')

// ---------- 配置区状态 ----------
const config = reactive({
  method: 'POST',
  url: '',
  params: [],
  headers: [],
  body_type: 'none',
  body_content: '',
  form_fields: [],
  expectations: [],
})
const activeSubTab = ref(SUB_TAB_PARAMS)
const isLoadingConfig = ref(false)
const isSaving = ref(false)
const isSending = ref(false)
const isDirty = ref(false)
const detailError = ref('')
const detailMessage = ref('')
const sendResult = ref(null)
const runs = ref([])

// 接口节点 method 徽标缓存：{ [nodeId]: 'POST'|'PUT' }
const methodCache = reactive({})

// loadConfig 赋值期间置 true，避免 watch 把后端回填误判为用户编辑
let suppressDirtyWatch = false

/**
 * 把平铺节点列表组装为嵌套树（children 按 sort_order 升序）。
 * @returns {Array<Object>} 根节点列表（每个节点含 children 数组）
 */
const tree = computed(() => {
  const map = new Map()
  nodes.value.forEach((n) => map.set(n.id, { ...n, children: [] }))
  const roots = []
  map.forEach((n) => {
    if (n.parent_id != null && map.has(n.parent_id)) {
      map.get(n.parent_id).children.push(n)
    } else {
      roots.push(n)
    }
  })
  const sortRecursive = (list) => {
    list.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    list.forEach((n) => sortRecursive(n.children))
  }
  sortRecursive(roots)
  return roots
})

/**
 * 判断节点自身或其任一后代名称是否命中搜索关键词。
 * @param {Object} node - 树节点（含 children）
 * @param {string} kw - 小写关键词
 * @returns {boolean} 是否命中
 */
function subtreeMatches(node, kw) {
  if ((node.name || '').toLowerCase().includes(kw)) return true
  return node.children.some((c) => subtreeMatches(c, kw))
}

/**
 * 当前可见的扁平化节点列表（含缩进深度）。
 * 无搜索词时按 expandedIds 展开；有搜索词时强制全部展开，
 * 并显示「命中节点 + 其祖先 + 命中文件夹的全部后代」。
 * @returns {Array<{node: Object, depth: number}>} 可见节点列表
 */
const visibleNodes = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  const out = []
  const walk = (list, depth, ancestorMatched) => {
    for (const n of list) {
      if (kw && !ancestorMatched && !subtreeMatches(n, kw)) continue
      out.push({ node: n, depth })
      const expanded = kw ? true : expandedIds.value.has(n.id)
      if (n.children.length && expanded) {
        const selfMatched = kw && (n.name || '').toLowerCase().includes(kw)
        walk(n.children, depth + 1, ancestorMatched || selfMatched)
      }
    }
  }
  walk(tree.value, 0, false)
  return out
})

/**
 * 当前选中的节点对象（可能为文件夹或接口）。
 * @returns {Object|null} 节点对象
 */
const selectedNode = computed(() => nodes.value.find((n) => n.id === selectedNodeId.value) || null)

/**
 * 发送结果中的响应体预览（超长截断）。
 * @returns {{text: string, truncated: boolean}} 预览文本与是否被截断
 */
const responsePreview = computed(() => {
  const body = sendResult.value?.response_body ?? ''
  const text = typeof body === 'string' ? body : JSON.stringify(body, null, 2)
  if (text.length > RESPONSE_PREVIEW_LIMIT) {
    return { text: text.slice(0, RESPONSE_PREVIEW_LIMIT), truncated: true }
  }
  return { text, truncated: false }
})

// 配置任意字段变化 → 标记未保存（加载回填期间除外）
watch(
  config,
  () => {
    if (!suppressDirtyWatch) isDirty.value = true
  },
  { deep: true },
)

/**
 * 加载节点树，默认展开全部文件夹；
 * 随后后台静默拉取各接口节点配置以填充 method 徽标缓存（失败忽略）。
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时写入 treeError
 */
async function loadTree() {
  isLoadingTree.value = true
  treeError.value = ''
  try {
    const data = await fetchApiConfigTree()
    nodes.value = Array.isArray(data?.nodes) ? data.nodes : []
    expandedIds.value = new Set(nodes.value.filter((n) => n.node_type === 'folder').map((n) => n.id))
    // 后台填充 method 徽标缓存（fire-and-forget，单个失败不影响整体）
    const apiNodes = nodes.value.filter((n) => n.node_type === 'api')
    Promise.allSettled(
      apiNodes.map((n) =>
        fetchApiConfig(n.id).then((d) => {
          if (d && d.method) methodCache[n.id] = d.method
        }),
      ),
    )
  } catch (err) {
    treeError.value = err.message || '加载 API 配置树失败'
  } finally {
    isLoadingTree.value = false
  }
}

/**
 * 切换文件夹展开 / 折叠。
 * @param {number} id - 文件夹节点 ID
 * @returns {void}
 */
function toggleExpand(id) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

/**
 * 点击树节点：文件夹 → 选中并切换展开；接口 → 选中并加载配置。
 * @param {Object} node - 被点击的节点
 * @returns {Promise<void>} 无返回值
 */
async function onNodeClick(node) {
  if (node.node_type === 'folder') {
    selectedNodeId.value = node.id
    toggleExpand(node.id)
    return
  }
  if (selectedNodeId.value === node.id) return
  selectedNodeId.value = node.id
  activeSubTab.value = SUB_TAB_PARAMS
  sendResult.value = null
  await loadConfig(node.id)
}

/**
 * 加载接口节点的请求配置并回填表单（回填期间抑制 dirty 监听）。
 * @param {number} nodeId - 接口节点 ID
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时写入 detailError
 */
async function loadConfig(nodeId) {
  isLoadingConfig.value = true
  detailError.value = ''
  detailMessage.value = ''
  try {
    const data = await fetchApiConfig(nodeId)
    suppressDirtyWatch = true
    config.method = data.method || 'POST'
    config.url = data.url || ''
    config.params = (data.params || []).map((p) => ({
      name: p.name || '',
      value: p.value ?? '',
      description: p.description || '',
    }))
    config.headers = (data.headers || []).map((h) => ({
      name: h.name || '',
      value: h.value ?? '',
      description: h.description || '',
    }))
    config.body_type = data.body_type || 'none'
    config.body_content = data.body_content || ''
    config.form_fields = (data.form_fields || []).map((f) => ({
      name: f.name || '',
      value: f.value ?? '',
      description: f.description || '',
    }))
    config.expectations = (data.expectations || []).map((e) => ({
      type: e.type || 'status_code',
      operator: e.operator || 'eq',
      value: e.value ?? '',
      path: e.path || '',
    }))
    methodCache[nodeId] = config.method
    await nextTick()
    suppressDirtyWatch = false
    isDirty.value = false
  } catch (err) {
    suppressDirtyWatch = false
    detailError.value = err.message || '加载 API 配置失败'
  } finally {
    isLoadingConfig.value = false
  }
  // 发送历史独立于配置加载，失败静默
  try {
    const data = await fetchApiConfigRuns(nodeId, 20)
    runs.value = Array.isArray(data?.runs) ? data.runs : []
  } catch {
    runs.value = []
  }
}

/**
 * 新建节点（文件夹或接口），创建在选中文件夹下（未选中时创建在根）。
 * 创建成功后自动进入 inline 重命名。
 * @param {'folder'|'api'} nodeType - 节点类型
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时写入 treeError
 */
async function createNode(nodeType) {
  treeError.value = ''
  treeMessage.value = ''
  let parentId = null
  const sel = selectedNode.value
  if (sel) parentId = sel.node_type === 'folder' ? sel.id : sel.parent_id ?? null
  try {
    const created = await createApiConfigNode(
      parentId,
      nodeType,
      nodeType === 'folder' ? '新建文件夹' : '新建接口',
    )
    nodes.value.push(created)
    if (parentId != null) {
      const next = new Set(expandedIds.value)
      next.add(parentId)
      expandedIds.value = next
    }
    startRename(created)
  } catch (err) {
    treeError.value = err.message || '新建节点失败'
  }
}

/**
 * 进入 inline 重命名。
 * @param {Object} node - 目标节点
 * @returns {void}
 */
function startRename(node) {
  renamingId.value = node.id
  renamingValue.value = node.name
}

/**
 * 取消 inline 重命名。
 * @returns {void}
 */
function cancelRename() {
  renamingId.value = null
  renamingValue.value = ''
}

/**
 * 提交 inline 重命名（空名称视为取消）。
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时写入 treeError
 */
async function submitRename() {
  const id = renamingId.value
  const name = renamingValue.value.trim()
  if (!id) return
  if (!name) {
    cancelRename()
    return
  }
  treeError.value = ''
  try {
    await updateApiConfigNode(id, { name })
    const target = nodes.value.find((n) => n.id === id)
    if (target) target.name = name
    cancelRename()
  } catch (err) {
    treeError.value = err.message || '重命名失败'
  }
}

/**
 * 删除节点（需用户确认）。非空文件夹后端返回 400，错误消息原样展示。
 * @param {Object} node - 目标节点
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时写入 treeError
 */
async function removeNode(node) {
  if (!confirm(`确认删除「${node.name}」？`)) return
  treeError.value = ''
  treeMessage.value = ''
  try {
    await deleteApiConfigNode(node.id)
    nodes.value = nodes.value.filter((n) => n.id !== node.id)
    if (selectedNodeId.value === node.id) {
      selectedNodeId.value = null
      sendResult.value = null
      runs.value = []
      isDirty.value = false
    }
    treeMessage.value = '节点已删除'
  } catch (err) {
    treeError.value = err.message || '删除失败'
  }
}

/**
 * 切换右侧配置子 Tab。
 * @param {string} tabId - SUB_TAB_PARAMS / SUB_TAB_BODY / SUB_TAB_HEADERS / SUB_TAB_MOCK
 * @returns {void}
 */
function switchSubTab(tabId) {
  if (activeSubTab.value === tabId) return
  activeSubTab.value = tabId
}

/**
 * 添加一行 key-value 记录（Params / Headers / form 字段共用）。
 * @param {Array} list - 目标数组（config.params / config.headers / config.form_fields）
 * @returns {void}
 */
function addRow(list) {
  list.push({ name: '', value: '', description: '' })
}

/**
 * 删除一行 key-value 记录。
 * @param {Array} list - 目标数组
 * @param {number} index - 行下标
 * @returns {void}
 */
function removeRow(list, index) {
  list.splice(index, 1)
}

/**
 * 添加一条 Mock 断言规则（默认状态码等于 200）。
 * @returns {void}
 */
function addExpectation() {
  config.expectations.push({ type: 'status_code', operator: 'eq', value: 200, path: '' })
}

/**
 * 删除一条 Mock 断言规则。
 * @param {number} index - 规则下标
 * @returns {void}
 */
function removeExpectation(index) {
  config.expectations.splice(index, 1)
}

/**
 * 切换 Body 类型。
 * @param {string} type - BODY_TYPES 中的 value
 * @returns {void}
 */
function setBodyType(type) {
  config.body_type = type
}

/**
 * 把表单中的 expectations 规范化为后端契约结构：
 * - status_code：value 转数字，operator 固定 eq
 * - body_contains：仅保留 value 字符串
 * - json_field：保留 path + operator；operator=exists 时省略 value
 * @returns {Array<Object>} 规范化后的断言规则列表
 */
function normalizeExpectations() {
  return config.expectations.map((e) => {
    if (e.type === 'status_code') {
      return { type: 'status_code', operator: 'eq', value: Number(e.value) }
    }
    if (e.type === 'body_contains') {
      return { type: 'body_contains', value: String(e.value ?? '') }
    }
    const rule = { type: 'json_field', path: e.path || '', operator: e.operator || 'exists' }
    if (rule.operator !== 'exists') rule.value = e.value
    return rule
  })
}

/**
 * 保存当前接口节点的完整配置（全量 upsert）。
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时写入 detailError
 */
async function saveConfig() {
  if (!selectedNodeId.value) return
  detailError.value = ''
  detailMessage.value = ''
  isSaving.value = true
  try {
    await saveApiConfig(selectedNodeId.value, {
      method: config.method,
      url: config.url,
      params: config.params.filter((p) => p.name),
      headers: config.headers.filter((h) => h.name),
      body_type: config.body_type,
      body_content: config.body_content,
      form_fields: config.form_fields.filter((f) => f.name),
      expectations: normalizeExpectations(),
    })
    methodCache[selectedNodeId.value] = config.method
    isDirty.value = false
    detailMessage.value = '配置已保存'
  } catch (err) {
    detailError.value = err.message || '保存配置失败'
  } finally {
    isSaving.value = false
  }
}

/**
 * 发送当前接口节点请求（后端按已保存配置发起真实 HTTP 调用）。
 * 发送成功后刷新发送历史。
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 不向外抛出，失败时以 error_message 形式展示在结果区
 */
async function sendRequest() {
  if (!selectedNodeId.value) return
  isSending.value = true
  sendResult.value = null
  detailError.value = ''
  try {
    sendResult.value = await sendApiConfig(selectedNodeId.value)
  } catch (err) {
    sendResult.value = {
      http_status: null,
      duration_ms: null,
      response_body: '',
      check_passed: false,
      assertion_results: [],
      error_message: err.message || '发送请求失败',
    }
  } finally {
    isSending.value = false
  }
  try {
    const data = await fetchApiConfigRuns(selectedNodeId.value, 20)
    runs.value = Array.isArray(data?.runs) ? data.runs : []
  } catch {
    // 历史刷新失败静默
  }
}

onMounted(loadTree)
</script>

<template>
  <section class="api-config-manager">
    <div class="acm-layout">
      <!-- 左侧：节点树 -->
      <aside class="acm-sidebar">
        <div class="acm-toolbar">
          <input
            v-model="searchKeyword"
            type="search"
            class="acm-search"
            placeholder="搜索名称…"
            aria-label="搜索节点"
            data-testid="api-tree-search"
          />
          <div class="acm-toolbar-actions">
            <button type="button" class="secondary-btn" data-testid="api-new-folder" @click="createNode('folder')">
              新建文件夹
            </button>
            <button type="button" class="primary-btn" data-testid="api-new-api" @click="createNode('api')">
              新建接口
            </button>
          </div>
        </div>

        <div v-if="treeError" class="alert error" role="alert" data-testid="api-tree-error">{{ treeError }}</div>
        <div v-if="treeMessage" class="alert success" data-testid="api-tree-message">{{ treeMessage }}</div>

        <div v-if="isLoadingTree" class="empty-state">正在加载节点树...</div>
        <div v-else-if="!visibleNodes.length" class="empty-state" data-testid="api-tree-empty">
          {{ searchKeyword ? '没有匹配的节点' : '暂无节点，点击「新建文件夹 / 新建接口」开始' }}
        </div>

        <div v-else class="acm-tree" data-testid="api-tree">
          <div
            v-for="{ node, depth } in visibleNodes"
            :key="node.id"
            class="tree-node"
            :class="{ active: selectedNodeId === node.id }"
            :style="{ paddingLeft: `${depth * 16 + 8}px` }"
            :data-testid="`tree-node-${node.id}`"
            role="button"
            tabindex="0"
            @click="onNodeClick(node)"
            @keydown.enter="onNodeClick(node)"
          >
            <template v-if="node.node_type === 'folder'">
              <span class="folder-arrow">{{ expandedIds.has(node.id) || searchKeyword ? '▾' : '▸' }}</span>
              <svg class="folder-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
              </svg>
            </template>
            <span
              v-else
              class="method-badge"
              :class="(methodCache[node.id] || 'POST') === 'PUT' ? 'method-put' : 'method-post'"
            >
              {{ methodCache[node.id] || 'POST' }}
            </span>

            <input
              v-if="renamingId === node.id"
              v-model="renamingValue"
              type="text"
              class="rename-input"
              data-testid="rename-input"
              @click.stop
              @keydown.enter.prevent="submitRename"
              @keydown.esc.prevent="cancelRename"
              @blur="submitRename"
            />
            <span v-else class="node-name" :title="node.name">{{ node.name }}</span>

            <span class="node-actions">
              <button
                type="button"
                class="icon-btn"
                :aria-label="`重命名 ${node.name}`"
                :data-testid="`node-rename-${node.id}`"
                @click.stop="startRename(node)"
              >
                ✎
              </button>
              <button
                type="button"
                class="icon-btn danger"
                :aria-label="`删除 ${node.name}`"
                :data-testid="`node-delete-${node.id}`"
                @click.stop="removeNode(node)"
              >
                ×
              </button>
            </span>
          </div>
        </div>
      </aside>

      <!-- 右侧：配置区 -->
      <main class="acm-detail">
        <div
          v-if="!selectedNode || selectedNode.node_type !== 'api'"
          class="empty-state detail-empty"
          data-testid="api-detail-empty"
        >
          请选择左侧的接口节点进行配置；文件夹节点仅用于分组。
        </div>

        <template v-else>
          <div v-if="detailError" class="alert error" role="alert" data-testid="api-detail-error">{{ detailError }}</div>
          <div v-if="detailMessage" class="alert success" data-testid="api-detail-message">{{ detailMessage }}</div>

          <!-- 顶部行：method + URL + 发送 + 保存 -->
          <div class="request-line">
            <select v-model="config.method" class="method-select" data-testid="api-method" aria-label="请求方法">
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
            </select>
            <input
              v-model="config.url"
              type="text"
              class="url-input"
              placeholder="https://api.example.com/path"
              data-testid="api-url"
              aria-label="请求 URL"
            />
            <button
              type="button"
              class="primary-btn"
              data-testid="api-send-btn"
              :disabled="isSending || isLoadingConfig"
              @click="sendRequest"
            >
              {{ isSending ? '发送中...' : '发送' }}
            </button>
            <button
              type="button"
              class="secondary-btn"
              :class="{ 'save-dirty': isDirty }"
              data-testid="api-save-btn"
              :disabled="isSaving || isLoadingConfig"
              @click="saveConfig"
            >
              {{ isSaving ? '保存中...' : isDirty ? '保存 ●' : '保存' }}
            </button>
          </div>

          <div v-if="isLoadingConfig" class="empty-state">正在加载配置...</div>

          <template v-else>
            <!-- 子 Tab 行 -->
            <div class="tablist" role="tablist" aria-label="请求配置">
              <button
                v-for="tab in SUB_TABS"
                :key="tab.id"
                type="button"
                role="tab"
                :aria-selected="activeSubTab === tab.id ? 'true' : 'false'"
                :class="['tab', { active: activeSubTab === tab.id }]"
                :data-testid="`subtab-${tab.id}`"
                @click="switchSubTab(tab.id)"
              >
                {{ tab.label }}
              </button>
            </div>

            <!-- Params -->
            <section v-if="activeSubTab === SUB_TAB_PARAMS" data-testid="panel-params">
              <table class="data-table" data-testid="params-table">
                <thead>
                  <tr>
                    <th scope="col">参数名</th>
                    <th scope="col">参数值</th>
                    <th scope="col">说明</th>
                    <th scope="col" class="col-action"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in config.params" :key="i">
                    <td><input v-model="row.name" type="text" placeholder="参数名" /></td>
                    <td><input v-model="row.value" type="text" placeholder="参数值" /></td>
                    <td><input v-model="row.description" type="text" placeholder="说明（可选）" /></td>
                    <td class="col-action">
                      <button type="button" class="icon-btn danger" :data-testid="`param-remove-${i}`" @click="removeRow(config.params, i)">×</button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <button type="button" class="link-btn" data-testid="param-add" @click="addRow(config.params)">+ 添加参数</button>
            </section>

            <!-- Body -->
            <section v-else-if="activeSubTab === SUB_TAB_BODY" data-testid="panel-body">
              <div class="body-type-group">
                <button
                  v-for="bt in BODY_TYPES"
                  :key="bt.value"
                  type="button"
                  :class="['body-type-btn', { active: config.body_type === bt.value }]"
                  :data-testid="`body-type-${bt.value}`"
                  @click="setBodyType(bt.value)"
                >
                  {{ bt.label }}
                </button>
              </div>

              <div v-if="config.body_type === 'none'" class="empty-state" data-testid="body-none">
                该请求没有 Body
              </div>

              <textarea
                v-else-if="['json', 'xml', 'text'].includes(config.body_type)"
                v-model="config.body_content"
                class="body-textarea"
                rows="10"
                :placeholder="config.body_type === 'json' ? '{ &quot;key&quot;: &quot;value&quot; }' : '请求体内容'"
                data-testid="body-content"
              ></textarea>

              <template v-else>
                <table class="data-table" data-testid="form-fields-table">
                  <thead>
                    <tr>
                      <th scope="col">字段名</th>
                      <th scope="col">字段值</th>
                      <th scope="col">说明</th>
                      <th scope="col" class="col-action"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, i) in config.form_fields" :key="i">
                      <td><input v-model="row.name" type="text" placeholder="字段名" /></td>
                      <td><input v-model="row.value" type="text" placeholder="字段值" /></td>
                      <td><input v-model="row.description" type="text" placeholder="说明（可选）" /></td>
                      <td class="col-action">
                        <button type="button" class="icon-btn danger" :data-testid="`form-field-remove-${i}`" @click="removeRow(config.form_fields, i)">×</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <button type="button" class="link-btn" data-testid="form-field-add" @click="addRow(config.form_fields)">+ 添加字段</button>
              </template>
            </section>

            <!-- Headers -->
            <section v-else-if="activeSubTab === SUB_TAB_HEADERS" data-testid="panel-headers">
              <table class="data-table" data-testid="headers-table">
                <thead>
                  <tr>
                    <th scope="col">参数名</th>
                    <th scope="col">参数值</th>
                    <th scope="col">说明</th>
                    <th scope="col" class="col-action"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in config.headers" :key="i">
                    <td>
                      <input v-model="row.name" type="text" list="header-name-suggestions" placeholder="Header 名" />
                    </td>
                    <td><input v-model="row.value" type="text" placeholder="Header 值" /></td>
                    <td><input v-model="row.description" type="text" placeholder="说明（可选）" /></td>
                    <td class="col-action">
                      <button type="button" class="icon-btn danger" :data-testid="`header-remove-${i}`" @click="removeRow(config.headers, i)">×</button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <datalist id="header-name-suggestions">
                <option v-for="h in HEADER_SUGGESTIONS" :key="h" :value="h"></option>
              </datalist>
              <button type="button" class="link-btn" data-testid="header-add" @click="addRow(config.headers)">+ 添加参数</button>
            </section>

            <!-- Mock（预期结果校验） -->
            <section v-else-if="activeSubTab === SUB_TAB_MOCK" data-testid="panel-mock">
              <p class="mock-hint">发送请求后将按以下规则校验响应，全部通过则判定接口正常。</p>
              <div class="mock-rules" data-testid="mock-rules">
                <div v-for="(rule, i) in config.expectations" :key="i" class="mock-rule" :data-testid="`mock-rule-${i}`">
                  <select v-model="rule.type" :data-testid="`mock-rule-type-${i}`" aria-label="规则类型">
                    <option v-for="t in EXPECTATION_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
                  </select>

                  <input
                    v-if="rule.type === 'status_code'"
                    v-model="rule.value"
                    type="number"
                    class="mock-status-input"
                    placeholder="200"
                    :data-testid="`mock-rule-value-${i}`"
                    aria-label="期望状态码"
                  />

                  <input
                    v-else-if="rule.type === 'body_contains'"
                    v-model="rule.value"
                    type="text"
                    placeholder="响应体需包含的文本"
                    :data-testid="`mock-rule-value-${i}`"
                    aria-label="包含文本"
                  />

                  <template v-else>
                    <input
                      v-model="rule.path"
                      type="text"
                      class="mock-path-input"
                      placeholder="JSON path，如 data.id"
                      :data-testid="`mock-rule-path-${i}`"
                      aria-label="JSON path"
                    />
                    <select v-model="rule.operator" :data-testid="`mock-rule-operator-${i}`" aria-label="运算符">
                      <option value="exists">exists</option>
                      <option value="eq">eq</option>
                    </select>
                    <input
                      v-if="rule.operator === 'eq'"
                      v-model="rule.value"
                      type="text"
                      placeholder="期望值"
                      :data-testid="`mock-rule-value-${i}`"
                      aria-label="期望值"
                    />
                  </template>

                  <button
                    type="button"
                    class="icon-btn danger"
                    :data-testid="`mock-rule-remove-${i}`"
                    aria-label="删除规则"
                    @click="removeExpectation(i)"
                  >
                    ×
                  </button>
                </div>
              </div>
              <button type="button" class="link-btn" data-testid="mock-add" @click="addExpectation">+ 添加规则</button>
            </section>

            <!-- 发送结果区 -->
            <section v-if="sendResult" class="send-result" data-testid="send-result">
              <div class="send-result-meta">
                <span v-if="sendResult.http_status != null" class="send-meta-item" data-testid="send-status">
                  HTTP {{ sendResult.http_status }}
                </span>
                <span v-if="sendResult.duration_ms != null" class="send-meta-item" data-testid="send-duration">
                  {{ sendResult.duration_ms }} ms
                </span>
                <span
                  class="check-badge"
                  :class="sendResult.check_passed ? 'check-pass' : 'check-fail'"
                  data-testid="send-check-badge"
                >
                  {{ sendResult.check_passed ? '正常' : '异常' }}
                </span>
              </div>

              <div v-if="sendResult.error_message" class="alert error" data-testid="send-error">
                {{ sendResult.error_message }}
              </div>

              <ul v-if="sendResult.assertion_results && sendResult.assertion_results.length" class="assertion-list" data-testid="assertion-results">
                <li
                  v-for="(a, i) in sendResult.assertion_results"
                  :key="i"
                  :class="a.passed ? 'assertion-pass' : 'assertion-fail'"
                  :data-testid="`assertion-${i}`"
                >
                  <span class="assertion-mark">{{ a.passed ? '✓' : '✗' }}</span>
                  <span class="assertion-rule">{{ a.rule }}</span>
                  <span v-if="a.detail" class="assertion-detail">{{ a.detail }}</span>
                </li>
              </ul>

              <template v-if="responsePreview.text">
                <pre class="response-preview" data-testid="response-preview">{{ responsePreview.text }}</pre>
                <p v-if="responsePreview.truncated" class="truncate-hint" data-testid="response-truncated">
                  响应体过长，已截断展示前 {{ RESPONSE_PREVIEW_LIMIT }} 字符
                </p>
              </template>
            </section>

            <!-- 最近发送历史 -->
            <section v-if="runs.length" class="runs-section" data-testid="runs-list">
              <h4>最近发送记录</h4>
              <table class="data-table">
                <thead>
                  <tr>
                    <th scope="col">时间</th>
                    <th scope="col">HTTP 状态</th>
                    <th scope="col">耗时</th>
                    <th scope="col">校验</th>
                    <th scope="col">错误</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="run in runs" :key="run.id" :data-testid="`run-${run.id}`">
                    <td>{{ run.created_at }}</td>
                    <td>{{ run.http_status ?? '-' }}</td>
                    <td>{{ run.duration_ms != null ? `${run.duration_ms} ms` : '-' }}</td>
                    <td>
                      <span class="check-badge" :class="run.check_passed ? 'check-pass' : 'check-fail'">
                        {{ run.check_passed ? '正常' : '异常' }}
                      </span>
                    </td>
                    <td class="run-error">{{ run.error_message || '' }}</td>
                  </tr>
                </tbody>
              </table>
            </section>
          </template>
        </template>
      </main>
    </div>
  </section>
</template>

<style scoped>
.api-config-manager {
  display: flex;
  flex-direction: column;
  min-height: 480px;
  height: 100%;
}

.acm-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  grid-template-rows: 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
  height: 100%;
}

.acm-sidebar,
.acm-detail {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 14px;
  height: 100%;
  min-height: 0;
}

.acm-sidebar {
  display: flex;
  flex-direction: column;
}

.acm-detail {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.acm-toolbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.acm-search {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  color: #111827;
}

.acm-search:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.acm-toolbar-actions {
  display: flex;
  gap: 8px;
}

.acm-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #111827;
}

.tree-node:hover {
  background: #f3f4f6;
}

.tree-node.active {
  background: #eff6ff;
  color: #1e40af;
}

.folder-arrow {
  width: 14px;
  color: #6b7280;
  flex-shrink: 0;
}

.folder-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  color: #f59e0b;
}

.method-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
}

.method-post {
  background: #fef3c7;
  color: #b45309;
}

.method-put {
  background: #dbeafe;
  color: #1e40af;
}

.node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rename-input {
  flex: 1;
  min-width: 0;
  border: 1px solid #2563eb;
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 13px;
}

.node-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  flex-shrink: 0;
}

.tree-node:hover .node-actions,
.tree-node:focus-within .node-actions {
  opacity: 1;
}

.icon-btn {
  background: none;
  border: 0;
  color: #6b7280;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 4px;
  line-height: 1;
}

.icon-btn:hover {
  background: #e5e7eb;
  color: #111827;
}

.icon-btn.danger:hover {
  background: #fee2e2;
  color: #dc2626;
}

.detail-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 16px;
}

.request-line {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.method-select {
  width: 96px;
  flex-shrink: 0;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  background: #ffffff;
}

.url-input {
  flex: 1;
  min-width: 0;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  color: #111827;
}

.url-input:focus,
.method-select:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.tablist {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 14px;
}

.tab {
  background: transparent;
  border: 0;
  padding: 8px 12px;
  border-radius: 8px 8px 0 0;
  color: #4b5563;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}

.tab.active {
  color: #2563eb;
  border-bottom: 2px solid #2563eb;
  background: #eff6ff;
}

.tab:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
  font-size: 13px;
  color: #111827;
}

.data-table th {
  background: #f9fafb;
  color: #374151;
  font-weight: 600;
}

.data-table input {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  color: #111827;
}

.data-table input:focus {
  outline: none;
  border-color: #2563eb;
}

.col-action {
  width: 40px;
  text-align: center;
}

.link-btn {
  background: none;
  border: 0;
  color: #2563eb;
  font-size: 13px;
  cursor: pointer;
  padding: 8px 4px;
}

.link-btn:hover {
  text-decoration: underline;
}

.body-type-group {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.body-type-btn {
  border: 1px solid #d1d5db;
  background: #ffffff;
  color: #4b5563;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
}

.body-type-btn.active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #2563eb;
  font-weight: 600;
}

.body-textarea {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 10px;
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #111827;
  resize: vertical;
}

.body-textarea:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.mock-hint {
  margin: 0 0 10px;
  color: #6b7280;
  font-size: 12px;
}

.mock-rules {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mock-rule {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mock-rule select,
.mock-rule input {
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  color: #111827;
}

.mock-rule input {
  flex: 1;
  min-width: 0;
}

.mock-status-input {
  max-width: 120px;
}

.mock-path-input {
  max-width: 220px;
}

.send-result {
  margin-top: 18px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 14px;
}

.send-result-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.send-meta-item {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.check-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.check-pass {
  color: #047857;
  background: #d1fae5;
}

.check-fail {
  color: #b91c1c;
  background: #fee2e2;
}

.assertion-list {
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.assertion-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.assertion-pass {
  color: #047857;
}

.assertion-fail {
  color: #b91c1c;
}

.assertion-mark {
  font-weight: 700;
}

.assertion-rule {
  font-weight: 600;
}

.assertion-detail {
  color: #6b7280;
  font-size: 12px;
}

.response-preview {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.truncate-hint {
  margin: 6px 0 0;
  color: #b45309;
  font-size: 12px;
}

.runs-section {
  margin-top: 18px;
}

.runs-section h4 {
  margin: 0 0 8px;
  color: #111827;
  font-size: 14px;
}

.run-error {
  color: #b91c1c;
}

.alert {
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
  font-size: 13px;
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
  font-size: 13px;
}

.primary-btn,
.secondary-btn {
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
}

.primary-btn {
  color: #ffffff;
  background: #2563eb;
}

.primary-btn:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

.secondary-btn {
  color: #1f2937;
  background: #e5e7eb;
}

.secondary-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.secondary-btn.save-dirty {
  background: #fef3c7;
  color: #b45309;
}

@media (max-width: 900px) {
  .acm-layout {
    grid-template-columns: 1fr;
  }
  .request-line {
    flex-wrap: wrap;
  }
}
</style>
