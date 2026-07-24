<script setup>
/**
 * UserServerManager - 用户服务器配置管理组件（2026-07-24 新增）
 *
 * 左右布局：左侧为「文件夹 / 服务器节点」树（支持搜索、新建文件夹、
 * inline 重命名、删除、展开折叠、导入已有配置），右侧为只读详情面板
 * （folder→空，server→JOIN devops_servers 的 7 字段只读展示）。
 *
 * 后端契约：/api/admin/user-servers（见 utils/api.js 中 fetchUserServerTree 等封装）。
 * 多对多关系：每个用户导入时生成独立 user_server_nodes 行
 * （同 source_devops_server_id），通过 created_by_user_id 区分归属。
 * 共享引用：server 节点不存任何业务字段，详情实时 JOIN devops_servers 读。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  fetchUserServerTree,
  createUserServerNode,
  updateUserServerNode,
  deleteUserServerNode,
  fetchUserServerConfig,
  importDevopsServers,
} from '../utils/api.js'
import ImportServerDialog from './ImportServerDialog.vue'

// 将 API 执行记录时间（ISO 字符串）格式化为 年-月-日 时:分:秒（YYYY-MM-DD HH:mm:ss）。
// 入参为后端返回的 ISO 时间字符串；无法解析时返回原字符串，避免显示空值或抛错。
// 使用本地时区以匹配用户（Asia/Shanghai）的直觉展示。
// @param {string} value ISO 时间字符串
// @returns {string} 格式化时间或原值
function formatRunTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

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

// ---------- 新建菜单 ----------
const toolbarRef = ref(null)
const newMenuOpen = ref(false)

// ---------- 详情状态 ----------
const nodeDetail = ref(null)
const isLoadingDetail = ref(false)
const detailError = ref('')
const detailMessage = ref('')

// ---------- 导入弹窗 ----------
const importDialogOpen = ref(false)

// ---------- 停用预留提示（新建服务器配置） ----------
const newServerDisabled = ref(true) // 该按钮暂未开放（按需求预留）

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
 * 无搜索词时按 expandedIds 展开；有搜索词时强制全部展开。
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
 * 当前选中的节点对象（可能为 folder 或 server）。
 * @returns {Object|null} 节点对象
 */
const selectedNode = computed(
  () => nodes.value.find((n) => n.id === selectedNodeId.value) || null
)

/**
 * 加载节点树，默认展开全部 folder。
 * @returns {Promise<void>} 无返回值
 */
async function loadTree() {
  isLoadingTree.value = true
  treeError.value = ''
  try {
    const data = await fetchUserServerTree()
    nodes.value = Array.isArray(data?.nodes) ? data.nodes : []
    expandedIds.value = new Set(
      nodes.value.filter((n) => n.node_type === 'folder').map((n) => n.id)
    )
  } catch (err) {
    treeError.value = err.message || '加载用户服务器 tree 失败'
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
 * 点击树节点：folder → 选中并切换展开；server → 选中并加载详情。
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
  await loadDetail(node.id)
}

/**
 * 加载 server 节点详情（JOIN devops_servers）。
 * @param {number} nodeId - 节点 ID
 * @returns {Promise<void>} 无返回值
 */
async function loadDetail(nodeId) {
  isLoadingDetail.value = true
  detailError.value = ''
  detailMessage.value = ''
  try {
    nodeDetail.value = await fetchUserServerConfig(nodeId)
  } catch (err) {
    detailError.value = err.message || '加载节点详情失败'
    nodeDetail.value = null
  } finally {
    isLoadingDetail.value = false
  }
}

/**
 * 新建 folder 节点（在选中 folder 下或根）。
 * @returns {Promise<void>} 无返回值
 */
async function createFolder() {
  treeError.value = ''
  treeMessage.value = ''
  let parentId = null
  const sel = selectedNode.value
  if (sel) parentId = sel.node_type === 'folder' ? sel.id : sel.parent_id ?? null
  try {
    const created = await createUserServerNode(parentId, 'folder', '新建文件夹', null)
    nodes.value.push(created)
    if (parentId != null) {
      const next = new Set(expandedIds.value)
      next.add(parentId)
      expandedIds.value = next
    }
    startRename(created)
  } catch (err) {
    treeError.value = err.message || '新建文件夹失败'
  }
}

/**
 * 点击「新建服务器配置」按钮（2026-07-24 第一版停用预留）。
 * 提示「该功能暂未开放」；未来放开时只需去掉拦截并把按钮 disabled 移除。
 * @returns {void}
 */
function onNewServerConfigClick() {
  // 2026-07-24 需求：保留按钮但功能暂未开放
  treeError.value = '该功能暂未开放'
  // 3 秒后清除提示（避免常驻）
  setTimeout(() => {
    if (treeError.value === '该功能暂未开放') treeError.value = ''
  }, 3000)
}

/**
 * 打开「导入已有配置」弹窗。
 * @returns {void}
 */
function openImportDialog() {
  importDialogOpen.value = true
}

/**
 * 处理导入完成：刷新 tree，关闭弹窗，高亮新节点。
 * @param {{imported: number, skipped: number, failed: number, node_ids: number[]}} result - 导入结果
 * @returns {Promise<void>} 无返回值
 */
async function handleImportDone(result) {
  importDialogOpen.value = false
  treeMessage.value = `导入完成：新增 ${result.imported}，跳过 ${result.skipped}，失败 ${result.failed}`
  // 刷新 tree
  await loadTree()
  // 高亮第一个新节点
  if (result.node_ids && result.node_ids.length > 0) {
    selectedNodeId.value = result.node_ids[0]
    const newNode = nodes.value.find((n) => n.id === result.node_ids[0])
    if (newNode) {
      // 展开所有祖先
      const ancestors = []
      let cursor = newNode.parent_id
      while (cursor != null) {
        ancestors.push(cursor)
        const parent = nodes.value.find((n) => n.id === cursor)
        cursor = parent ? parent.parent_id : null
      }
      const next = new Set(expandedIds.value)
      ancestors.forEach((id) => next.add(id))
      expandedIds.value = next
      if (newNode.node_type === 'server') {
        await loadDetail(newNode.id)
      }
    }
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
  nextTick(() => {
    const input = document.querySelector('.usm-rename-input')
    if (input) {
      input.focus()
      input.select()
    }
  })
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
    await updateUserServerNode(id, { name })
    const target = nodes.value.find((n) => n.id === id)
    if (target) target.name = name
    cancelRename()
  } catch (err) {
    treeError.value = err.message || '重命名失败'
  }
}

/**
 * 删除节点（需用户确认）。非空 folder 后端返回 400。
 * @param {Object} node - 目标节点
 * @returns {Promise<void>} 无返回值
 */
async function removeNode(node) {
  if (!confirm(`确认删除「${node.name}」？`)) return
  treeError.value = ''
  treeMessage.value = ''
  try {
    await deleteUserServerNode(node.id)
    nodes.value = nodes.value.filter((n) => n.id !== node.id)
    if (selectedNodeId.value === node.id) {
      selectedNodeId.value = null
      nodeDetail.value = null
    }
    treeMessage.value = '节点已删除'
  } catch (err) {
    treeError.value = err.message || '删除失败'
  }
}

// ---------- 新建菜单开关控制 ----------
function toggleNewMenu() {
  newMenuOpen.value = !newMenuOpen.value
}
function closeNewMenu() {
  newMenuOpen.value = false
}

// 点击 toolbar 外部关闭新建菜单
function handleDocClick(e) {
  if (!newMenuOpen.value) return
  if (toolbarRef.value && !toolbarRef.value.contains(e.target)) {
    closeNewMenu()
  }
}

onMounted(async () => {
  document.addEventListener('click', handleDocClick)
  await loadTree()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocClick)
})

// 监听选中变化，加载详情（folder 节点不请求接口）
watch(selectedNodeId, async (newId) => {
  if (newId == null) {
    nodeDetail.value = null
    return
  }
  const node = nodes.value.find((n) => n.id === newId)
  if (!node) {
    nodeDetail.value = null
    return
  }
  if (node.node_type === 'folder') {
    nodeDetail.value = null
  } else {
    await loadDetail(newId)
  }
})
</script>

<template>
  <div class="usm-layout">
    <!-- 左侧：节点树 -->
    <aside class="usm-sidebar">
      <div
        class="usm-toolbar"
        :class="{ 'menu-open': newMenuOpen }"
        ref="toolbarRef"
      >
        <div class="usm-search-wrapper">
          <svg
            class="usm-search-icon"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9 17a8 8 0 100-16 8 8 0 000 16zM14 14l4 4"
            />
          </svg>
          <input
            v-model="searchKeyword"
            type="text"
            class="usm-search-input"
            placeholder="搜索文件夹 / 服务器"
            aria-label="搜索"
            data-testid="usm-search-input"
          />
        </div>

        <button
          type="button"
          class="usm-new-trigger"
          :class="{ open: newMenuOpen }"
          data-testid="usm-new-trigger"
          aria-label="新建"
          aria-haspopup="true"
          :aria-expanded="newMenuOpen ? 'true' : 'false'"
          @click.stop="toggleNewMenu"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="usm-plus-icon" aria-hidden="true">
            <path
              d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z"
            />
          </svg>
          <span>新建</span>
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            class="usm-caret-icon"
            aria-hidden="true"
          >
            <path d="M5.5 7.5l4.5 4.5 4.5-4.5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>

        <ul
          v-if="newMenuOpen"
          class="usm-new-menu"
          role="menu"
          data-testid="usm-new-menu"
        >
          <li role="none">
            <button
              type="button"
              role="menuitem"
              class="usm-new-menu-item"
              data-testid="usm-new-folder"
              @click="createFolder(); closeNewMenu()"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="usm-menu-icon" aria-hidden="true">
                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
              </svg>
              <span>新建文件夹</span>
            </button>
          </li>
          <li role="none">
            <button
              type="button"
              role="menuitem"
              class="usm-new-menu-item"
              :disabled="newServerDisabled"
              :class="{ disabled: newServerDisabled }"
              :title="newServerDisabled ? '该功能暂未开放' : ''"
              data-testid="usm-new-server"
              @click.stop="onNewServerConfigClick"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="usm-menu-icon" aria-hidden="true">
                <path d="M3 4h14v3H3V4zm0 5h14v7H3V9zm2 2v1h2v-1H5zm4 0v1h2v-1H9z" />
              </svg>
              <span>新建服务器配置</span>
            </button>
          </li>
          <li role="none" class="usm-new-menu-divider"></li>
          <li role="none">
            <button
              type="button"
              role="menuitem"
              class="usm-new-menu-item"
              data-testid="usm-import-existing"
              @click="openImportDialog(); closeNewMenu()"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="usm-menu-icon" aria-hidden="true">
                <path d="M10 3a1 1 0 011 1v6.59l2.3-2.3a1 1 0 011.4 1.42l-4 4a1 1 0 01-1.4 0l-4-4a1 1 0 011.4-1.42L9 10.6V4a1 1 0 011-1zM3 16a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" />
              </svg>
              <span>导入已有配置</span>
            </button>
          </li>
        </ul>
      </div>

      <div
        v-if="treeError"
        class="alert error"
        role="alert"
        data-testid="usm-tree-error"
      >
        {{ treeError }}
      </div>
      <div
        v-if="treeMessage"
        class="alert success"
        role="status"
        data-testid="usm-tree-message"
      >
        {{ treeMessage }}
      </div>

      <div v-if="isLoadingTree" class="empty-state" data-testid="usm-tree-loading">
        正在加载...
      </div>
      <div
        v-else-if="!nodes.length"
        class="empty-state"
        data-testid="usm-tree-empty"
      >
        暂无节点，点击右上角「+ 新建」开始
      </div>

      <ul
        v-else
        class="usm-tree"
        role="tree"
        data-testid="usm-tree"
      >
        <li
          v-for="item in visibleNodes"
          :key="item.node.id"
          class="usm-tree-item"
          :class="{
            selected: selectedNodeId === item.node.id,
            'is-folder': item.node.node_type === 'folder',
            'is-server': item.node.node_type === 'server'
          }"
          :style="{ paddingLeft: `${8 + item.depth * 16}px` }"
          :data-testid="`usm-node-${item.node.id}`"
          role="treeitem"
          :aria-selected="selectedNodeId === item.node.id ? 'true' : 'false'"
        >
          <div
            class="usm-tree-row"
            tabindex="0"
            @click="onNodeClick(item.node)"
            @keydown.enter="onNodeClick(item.node)"
          >
            <template v-if="item.node.node_type === 'folder'">
              <span class="usm-folder-arrow">
                {{ expandedIds.has(item.node.id) || searchKeyword ? '▾' : '▸' }}
              </span>
              <svg class="usm-folder-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
              </svg>
            </template>
            <template v-else>
              <span class="usm-folder-arrow usm-spacer"></span>
              <svg class="usm-server-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M3 4h14v3H3V4zm0 5h14v7H3V9zm2 2v1h2v-1H5zm4 0v1h2v-1H9z" />
              </svg>
            </template>
            <input
              v-if="renamingId === item.node.id"
              v-model="renamingValue"
              class="usm-rename-input"
              type="text"
              @click.stop
              @keydown.enter="submitRename"
              @keydown.esc="cancelRename"
              @blur="submitRename"
            />
            <span v-else class="usm-node-name" :title="item.node.name">
              {{ item.node.name }}
            </span>
            <span class="usm-node-actions">
              <button
                type="button"
                class="icon-btn"
                :aria-label="`重命名 ${item.node.name}`"
                :data-testid="`usm-rename-${item.node.id}`"
                @click.stop="startRename(item.node)"
              >
                ✎
              </button>
              <button
                type="button"
                class="icon-btn danger"
                :aria-label="`删除 ${item.node.name}`"
                :data-testid="`usm-delete-${item.node.id}`"
                @click.stop="removeNode(item.node)"
              >
                ×
              </button>
            </span>
          </div>
        </li>
      </ul>
    </aside>

    <!-- 右侧：详情面板（只读） -->
    <main class="usm-detail">
      <div
        v-if="!selectedNode"
        class="empty-state detail-empty"
        data-testid="usm-detail-empty"
      >
        请选择左侧节点查看详情
      </div>
      <div
        v-else-if="selectedNode.node_type === 'folder'"
        class="usm-folder-detail"
        data-testid="usm-folder-detail"
      >
        <h3>文件夹</h3>
        <p class="usm-folder-name">{{ selectedNode.name }}</p>
        <p class="usm-folder-hint">
          文件夹用于组织服务器节点，无业务字段。
        </p>
      </div>
      <div
        v-else
        class="usm-server-detail"
        data-testid="usm-server-detail"
      >
        <div
          v-if="detailError"
          class="alert error"
          role="alert"
          data-testid="usm-detail-error"
        >
          {{ detailError }}
        </div>
        <div v-if="isLoadingDetail" class="empty-state" data-testid="usm-detail-loading">
          正在加载...
        </div>
        <template v-else-if="nodeDetail">
          <h3>服务器</h3>
          <dl class="usm-detail-list">
            <dt>业务名</dt>
            <dd>{{ nodeDetail.business_name || selectedNode.name }}</dd>

            <dt>系统类型</dt>
            <dd>
              <span class="usm-tag">{{ nodeDetail.server_type || 'linux' }}</span>
            </dd>

            <dt>最近同步</dt>
            <dd>{{ formatRunTime(nodeDetail.devops_updated_at) }}</dd>

            <dt>白名单</dt>
            <dd>
              <span v-if="!nodeDetail.whitelist || nodeDetail.whitelist.length === 0" class="muted">（无）</span>
              <ul v-else class="usm-whitelist">
                <li v-for="(cmd, idx) in nodeDetail.whitelist" :key="idx">{{ cmd }}</li>
              </ul>
            </dd>

            <dt>解析器</dt>
            <dd>
              <span class="usm-tag">{{ nodeDetail.inspection_parser || 'json' }}</span>
            </dd>

            <dt>巡检脚本</dt>
            <dd>
              <pre v-if="nodeDetail.inspection_script" class="usm-script">{{ nodeDetail.inspection_script }}</pre>
              <span v-else class="muted">（未配置）</span>
            </dd>

            <dt v-if="nodeDetail.inspection_fields && nodeDetail.inspection_fields.length">巡检字段</dt>
            <dd v-if="nodeDetail.inspection_fields && nodeDetail.inspection_fields.length">
              <table class="usm-fields-table" data-testid="usm-fields-table">
                <thead>
                  <tr>
                    <th>key</th>
                    <th>中文名</th>
                    <th>单位</th>
                    <th>方向</th>
                    <th>warn</th>
                    <th>crit</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(f, idx) in nodeDetail.inspection_fields" :key="idx">
                    <td>{{ f.key }}</td>
                    <td>{{ f.name_zh || '' }}</td>
                    <td>{{ f.unit || '' }}</td>
                    <td>{{ f.direction || '' }}</td>
                    <td>{{ f.warn ?? '' }}</td>
                    <td>{{ f.crit ?? '' }}</td>
                  </tr>
                </tbody>
              </table>
            </dd>
          </dl>
          <p class="usm-readonly-hint">只读视图，修改请前往「服务器扫描入库」。</p>
        </template>
      </div>
    </main>

    <!-- 导入弹窗 -->
    <ImportServerDialog
      v-if="importDialogOpen"
      :parent-id="selectedNode && selectedNode.node_type === 'folder' ? selectedNode.id : null"
      @close="importDialogOpen = false"
      @done="handleImportDone"
    />
  </div>
</template>

<style scoped>
.usm-layout {
  display: flex;
  height: 100%;
  min-height: 480px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}
.usm-sidebar {
  width: 320px;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  background: #fafbfc;
  overflow: hidden;
}
.usm-toolbar {
  position: relative;
  padding: 8px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  display: flex;
  align-items: center;
  gap: 6px;
}
.usm-search-wrapper {
  position: relative;
  flex: 1;
  min-width: 0;
}
.usm-search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: #6b7280;
}
.usm-search-input {
  width: 100%;
  padding: 6px 8px 6px 28px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.usm-search-input:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}
.usm-new-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.usm-new-trigger:hover {
  background: #1d4ed8;
}
.usm-new-trigger.open {
  background: #1d4ed8;
}
.usm-plus-icon,
.usm-caret-icon {
  width: 14px;
  height: 14px;
}
.usm-new-menu {
  position: absolute;
  top: 100%;
  right: 8px;
  margin-top: 4px;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  min-width: 180px;
  list-style: none;
  padding: 4px 0;
  margin: 4px 0 0 0;
  z-index: 10;
}
.usm-new-menu li {
  list-style: none;
}
.usm-new-menu-divider {
  height: 1px;
  background: #e5e7eb;
  margin: 4px 0;
}
.usm-new-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: none;
  border: none;
  text-align: left;
  font-size: 13px;
  cursor: pointer;
  color: #111827;
}
.usm-new-menu-item:hover:not(.disabled) {
  background: #f3f4f6;
}
.usm-new-menu-item.disabled {
  cursor: not-allowed;
  color: #9ca3af;
}
.usm-menu-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.usm-tree {
  flex: 1;
  overflow-y: auto;
  list-style: none;
  padding: 0;
  margin: 0;
}
.usm-tree-item {
  list-style: none;
}
.usm-tree-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
}
.usm-tree-row:hover {
  background: #eef2ff;
}
.usm-tree-item.selected > .usm-tree-row {
  background: #dbeafe;
}
.usm-folder-arrow {
  width: 12px;
  display: inline-block;
  color: #6b7280;
  font-size: 10px;
  flex-shrink: 0;
}
.usm-spacer {
  visibility: hidden;
}
.usm-folder-icon,
.usm-server-icon {
  width: 14px;
  height: 14px;
  color: #4b5563;
  flex-shrink: 0;
}
.usm-server-icon {
  color: #2563eb;
}
.usm-rename-input {
  flex: 1;
  min-width: 0;
  padding: 2px 4px;
  border: 1px solid #2563eb;
  border-radius: 2px;
  font-size: 13px;
  outline: none;
}
.usm-node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.usm-node-actions {
  display: none;
  gap: 2px;
}
.usm-tree-item:hover .usm-node-actions {
  display: inline-flex;
}
.icon-btn {
  background: none;
  border: none;
  font-size: 12px;
  color: #4b5563;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 2px;
}
.icon-btn:hover {
  background: #e5e7eb;
}
.icon-btn.danger {
  color: #dc2626;
}
.usm-detail {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
}
.usm-folder-detail h3,
.usm-server-detail h3 {
  margin-top: 0;
  font-size: 16px;
  color: #111827;
}
.usm-folder-name {
  font-size: 14px;
  color: #1f2937;
}
.usm-folder-hint,
.usm-readonly-hint {
  font-size: 12px;
  color: #6b7280;
  margin-top: 8px;
}
.usm-detail-list {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px 16px;
  margin: 0;
}
.usm-detail-list dt {
  color: #6b7280;
  font-size: 13px;
  font-weight: 500;
}
.usm-detail-list dd {
  margin: 0;
  color: #111827;
  font-size: 13px;
  word-break: break-word;
}
.usm-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #eef2ff;
  color: #1e3a8a;
  border-radius: 3px;
  font-size: 12px;
}
.usm-whitelist {
  list-style: none;
  padding: 0;
  margin: 0;
}
.usm-whitelist li {
  padding: 2px 0;
  font-family: monospace;
  font-size: 12px;
  color: #1f2937;
}
.usm-script {
  background: #1f2937;
  color: #f9fafb;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}
.usm-fields-table {
  border-collapse: collapse;
  font-size: 12px;
  width: 100%;
}
.usm-fields-table th,
.usm-fields-table td {
  border: 1px solid #e5e7eb;
  padding: 4px 8px;
  text-align: left;
}
.usm-fields-table th {
  background: #f9fafb;
  font-weight: 500;
  color: #4b5563;
}
.muted {
  color: #9ca3af;
  font-style: italic;
}
.alert {
  padding: 6px 10px;
  margin: 6px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.alert.error {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}
.alert.success {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.empty-state {
  padding: 24px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}
.detail-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: auto;
}
</style>
