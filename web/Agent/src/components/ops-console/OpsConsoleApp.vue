<script setup>
/**
 * 运维控制台 - 页面组件（窗口管理 / 全局状态）
 *
 * 历史：2026-08-05 从 `运维界面/app/src/App.vue` 整段迁移，最初作为
 *       ``/ops-console.html`` 独立 Vite 入口的根组件挂载到独立 #app。
 * 2026-08-08 改造为等保三级 §二访问控制方案：
 *       1) 取消独立 HTML 入口，改为在主应用 ``App.vue::currentPage === 'ops-console'``
 *          条件渲染的子页面；
 *       2) 复用主应用的 HttpOnly Cookie / ``fetchWithAuth`` 自动注入
 *          ``X-Requested-With`` + 401 refresh 重试链路，鉴权与主应用统一，
 *          不再出现「独立子窗口 Cookie / refresh 失效导致接口拉不到」的反模式；
 *       3) 模板外层新增 ``.ops-console-root`` 包裹，配合 ``ops-console.css``
 *          改造为作用域前缀样式，避免政务蓝 ``* { margin: 0; padding: 0 }``
 *          污染主应用其他页面。
 *
 * 状态机：
 *   - currentTime: string                  顶部菜单栏时间（1s 定时器）
 *   - searchKey: string                    服务器搜索关键词（v-model 双向）
 *   - zTop: number                         全局 z 序计数器
 *   - wins: { servers, detail, logs, logview } 各窗口的开关/位置/层级/最大化
 *   - detailServer: ServerItem | null      当前展示详情的服务器
 *   - activeFolder: number                 当前日志文件夹下标
 *   - logFile: { name, content } | null    当前查看的日志文件
 *   - detailRef: ref to OpsDetailWindow    用于触发 runDetect
 *
 * 行为：
 *   - 1s 定时器刷新时间显示
 *   - 4 个窗口可独立 open/close/max/front/drag
 *   - 服务图标点击 → openDetail
 *   - 日志文件点击 → openLog（生成 14 行样例日志）
 *   - 一键智能检测 → 自动找 err 服务器 + 打开详情 + 触发 runDetect
 */
import { ref, computed, nextTick, onMounted } from 'vue'
import OpsMenuBar from './OpsMenuBar.vue'
import OpsServerWindow from './OpsServerWindow.vue'
import OpsDetailWindow from './OpsDetailWindow.vue'
import OpsLogManager from './OpsLogManager.vue'
import OpsLogViewer from './OpsLogViewer.vue'
import OpsDockBar from './OpsDockBar.vue'
import { logFolders } from '../../data/ops-console/mockData.js'
import { fetchServerInspectionLatest, validateToken } from '../../utils/api.js'

const currentTime = ref('')
const searchKey = ref('')
const zTop = ref(10)
const wins = ref({
  servers: { open: true, max: true,  x: 90,  y: 60,  z: 3 },
  detail:  { open: true, max: false, x: 300, y: 120, z: 2 },
  logs:    { open: false, max: false, x: 160, y: 80,  z: 1 },
  logview: { open: true, max: false, x: 380, y: 140, z: 1 },
})
const detailServer = ref(null)
const activeFolder = ref(0)
const logFile = ref(null)
const detailRef = ref(null)

// 2026-08-09：新增「关闭整个运维控制台」事件，透传到父组件 OpsConsoleWorkspace。
// 触发源：OpsMenuBar 顶部菜单栏右侧红色关闭点（mac 风格）。
const emit = defineEmits(['exit'])

// 2026-08-05：servers 由后端 /api/admin/server-inspection/latest 提供
// （按当前用户 OwnershipScope 过滤），不再用 mockData。
const servers = ref([])
const serversLoadError = ref('')

/**
 * 把后端 ``/latest`` 响应映射为前端 ``ServerItem`` 形状：
 *   - ``id = server_id``，``nodeId = node_id``
 *   - ``name = node_name || business_name``
 *   - ``status`` 直用后端三态（ok / err / unknown）
 *   - ``cpu / mem / disk`` 取 ``metrics``；``null`` → 显示 ``-``
 *   - ``disks`` 由 ``parsed_values.disks`` 映射（mount → name，disk_used_pct → used）
 *   - ``os / cpuModel / memTotal / diskTotal / netIn`` 本期未采集 → ``-``
 *   - ``ip`` 不返（遵循脱敏约定）→ ``-``
 *
 * @param {Object} item 后端返回的快照行
 * @returns {Object} 前端 ServerItem
 */
function mapSnapshotToServer(item) {
  const pv = (item && item.parsed_values) || {}
  const disks = Array.isArray(pv.disks) ? pv.disks : []
  return {
    id: item.server_id,
    nodeId: item.node_id,
    name: item.node_name || item.business_name || '-',
    ip: '-',                // 不返 ip（运维脱敏约定）
    os: '-',                // 本期未采集
    status: item.status || 'unknown',
    cpu: item.metrics?.cpu ?? null,
    mem: item.metrics?.mem ?? null,
    disk: item.metrics?.disk ?? null,
    cpuModel: '-',
    memTotal: '-',
    diskTotal: '-',
    netIn: '-',
    uptime: pv.uptime_hours != null ? `${pv.uptime_hours} 小时` : '-',
    disks: disks.map(d => ({
      name: d.mount || '-',
      used: d.disk_used_pct ?? null,
      total: '-',
    })),
    collectedAt: item.collected_at || null,
    errorMessage: item.error_message || null,
  }
}

/** 异步加载每服务器最新采集快照。失败时 ``serversLoadError`` 记录原因，servers 保持空数组。 */
async function loadLatest() {
  serversLoadError.value = ''
  try {
    const resp = await fetchServerInspectionLatest()
    servers.value = (resp.items || []).map(mapSnapshotToServer)
  } catch (err) {
    serversLoadError.value = (err && err.message) || '加载失败'
    servers.value = []
  }
}

/** 正常运行的服务器数量（驱动 ServerWindow 状态显示） */
const onlineCount = computed(() => servers.value.filter(s => s.status === 'ok').length)
/** 按 searchKey 过滤后的服务器列表（按名称 / IP 不区分大小写匹配） */
const filteredServers = computed(() => {
  const k = searchKey.value.trim().toLowerCase()
  if (!k) return servers.value
  return servers.value.filter(s =>
    (s.name || '').toLowerCase().includes(k) ||
    (s.ip || '').includes(k)
  )
})

/** 1s 定时器：刷新顶部菜单栏时间，格式 "YYYY年MM月DD日 HH:MM:SS" */
function tick() {
  const d = new Date()
  const p = n => String(n).padStart(2, '0')
  currentTime.value = d.getFullYear() + '年' + p(d.getMonth() + 1) + '月' + p(d.getDate()) + '日 '
    + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds())
}

/** 将指定窗口置顶（zTop++ 后写入） */
function bringFront(name) { wins.value[name].z = ++zTop.value }

/** 打开窗口（若已关则打开）并置顶 */
function openWin(name) {
  const w = wins.value[name]
  if (!w.open) w.open = true
  bringFront(name)
}

/** 切换窗口最大化状态，并置顶 */
function toggleMax(name) {
  const w = wins.value[name]
  w.max = !w.max
  bringFront(name)
}

/** 关闭窗口 */
function closeWin(name) { wins.value[name].open = false }

/** 打开服务器详情窗口（同时记录选中态） */
function openDetail(srv) {
  detailServer.value = srv
  wins.value.detail.open = true
  bringFront('detail')
}

/** 打开日志查看窗口（生成 14 行样例日志内容） */
function openLog(f) {
  logFile.value = { ...f, content: genLogContent(f.name) }
  wins.value.logview.open = true
  bringFront('logview')
}

/**
 * 一键智能检测：找第一个 err 状态的服务器（找不到取第一台），
 * 打开服务器窗口 + 打开详情 + 触发详情 runDetect()
 * @returns {void}
 */
function detectAll() {
  const target = servers.find(s => s.status === 'err') || servers[0]
  openWin('servers')
  openDetail(target)
  nextTick(() => { if (detailRef.value) detailRef.value.runDetect() })
}

/**
 * 启动窗口拖拽：mousedown 记录偏移，mousemove 实时更新 x/y，mouseup 清理监听
 * - 最大化时禁止拖拽
 * - 拖拽过程中限制窗口四边边界，防止标题栏被顶部菜单栏压盖或窗口完全滑出可视区域
 * @param {MouseEvent} e 鼠标按下事件
 * @param {string} name 窗口名
 * @returns {void}
 */
function startDrag(e, name) {
  const w = wins.value[name]
  if (w.max) return   // 最大化时禁止拖动

  // 通过标题栏找到对应窗口 DOM，动态获取当前窗口尺寸，避免硬编码各窗口 width/height
  const el = e.currentTarget && e.currentTarget.closest('.win')
  const rect = el ? el.getBoundingClientRect() : { width: 0, height: 0 }
  const vw = document.documentElement.clientWidth
  const vh = document.documentElement.clientHeight

  // 顶部菜单栏高度，窗口顶部不得低于菜单栏底部，确保标题栏始终可见可拖
  const MENU_BAR_HEIGHT = 28
  // 窗口边缘至少保留多少像素可见，方便用户从边缘重新拖回
  const MIN_VISIBLE = 60

  const minX = MIN_VISIBLE - rect.width
  const maxX = vw - MIN_VISIBLE
  const minY = MENU_BAR_HEIGHT
  const maxY = vh - MIN_VISIBLE

  const sx = e.clientX - w.x
  const sy = e.clientY - w.y

  const move = ev => {
    w.x = Math.min(Math.max(ev.clientX - sx, minX), maxX)
    w.y = Math.min(Math.max(ev.clientY - sy, minY), maxY)
  }
  const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

/**
 * 生成样例日志内容（终端风格）
 * - slow-query.log / mysql-error.log / firewall.log 三类走专属模板
 * - 其他文件名走通用模板（14 条循环）
 * @param {string} name 日志文件名
 * @returns {Array<{t: string, lv: string, msg: string}>} 解析后的日志行
 */
function genLogContent(name) {
  const tpl = {
    'slow-query.log': [
      ['17:21:04', 'WARN',  "Slow query (2.34s): SELECT * FROM orders WHERE status='pending' ORDER BY created_at"],
      ['17:22:18', 'WARN',  'Slow query (3.01s): SELECT COUNT(*) FROM user_logs GROUP BY uid'],
      ['17:23:40', 'ERROR', 'Lock wait timeout exceeded; try restarting transaction (thread 88412)'],
      ['17:25:02', 'INFO',  'Query cache hit ratio: 61.4%'],
      ['17:28:55', 'WARN',  'Slow query (4.12s): JOIN on tables orders, items missing index idx_items_oid'],
    ],
    'mysql-error.log': [
      ['09:12:03', 'ERROR', "[Server] Aborted connection 1042 to db: 'ops' user: 'app' (Got timeout reading communication packets)"],
      ['09:12:40', 'WARN',  '[Server] IP 192.168.20.31 could not be resolved: Name or service not known'],
      ['09:14:11', 'INFO',  '[Server] /usr/local/mysql/bin/mysqld: ready for connections. port: 3306'],
    ],
    'firewall.log': [
      ['15:40:02', 'WARN',  'DENY TCP 203.0.113.24:51234 -> 192.168.10.21:22 (flags SYN)'],
      ['15:41:37', 'WARN',  'DENY TCP 198.51.100.9:48211 -> 192.168.10.21:3306 (flags SYN)'],
      ['15:44:19', 'INFO',  'Rule reload completed, 214 rules active'],
    ],
  }
  if (tpl[name]) return tpl[name].map(r => ({ t: r[0], lv: r[1], msg: r[2] }))
  const msgs = [
    ['INFO',  'service heartbeat ok, latency 0.8ms'],
    ['DEBUG', 'gc pause 12ms, heap 61%'],
    ['INFO',  'request 200 GET /api/v1/metrics (3ms)'],
    ['WARN',  'connection pool usage 82%, consider raising max_pool_size'],
    ['INFO',  'request 200 POST /api/v1/deploy (128ms)'],
    ['ERROR', 'upstream timeout after 3000ms: http://192.168.30.41:6379'],
    ['INFO',  'retry succeeded (attempt 2/3)'],
    ['DEBUG', 'cache flush completed, 12410 keys evicted'],
  ]
  const rows = []
  for (let i = 0; i < 14; i++) {
    const m = msgs[i % msgs.length]
    rows.push({ t: '17:' + String(10 + i * 3).padStart(2, '0') + ':' + String((i * 17) % 60).padStart(2, '0'), lv: m[0], msg: m[1] })
  }
  return rows
}

onMounted(async () => {
  tick()
  setInterval(tick, 1000)
  // 2026-08-08 等保三级改造：主动调用 /api/auth/validate 触发 Cookie 鉴权链路，
  // 若主应用 Access Token 过期，服务端会通过 HttpOnly Cookie 自动识别并
  // 走 /api/auth/refresh 轮换（validateToken 内部已封装 401 自动 refresh + 重试）。
  // 这步只解决「父窗口长期挂着、Cookie 已超时」场景的引导问题；常规场景下
  // loadLatest() 的 401 也会触发 fetchWithAuth 内置 refresh 链路。
  try {
    await validateToken()
  } catch (err) {
    console.warn('[OpsConsolePage] 主动引导 validateToken 失败（将由 loadLatest 内置 refresh 兜底）:', err && err.message)
  }
  loadLatest()
})
</script>

<template>
  <!--
    2026-08-08 等保三级改造：外层 .ops-console-root 包裹，
    配合 ops-console.css 改造为作用域前缀样式，避免污染主应用其他页面。
    原独立 HTML 入口（/ops-console.html）的 #app 高度 = 100vh 已迁移到本容器。
  -->
  <div class="ops-console-root">
  <OpsMenuBar :time="currentTime" @exit="emit('exit')" />

  <OpsServerWindow v-if="wins.servers.open"
    :win="wins.servers" :servers="filteredServers"
    v-model:search-key="searchKey"
    :selected-id="detailServer ? detailServer.id : null"
    @open-detail="openDetail"
    @close="closeWin('servers')"
    @max="toggleMax('servers')"
    @front="bringFront('servers')"
    @drag="startDrag($event, 'servers')" />

  <OpsDetailWindow v-if="detailServer && wins.detail.open" ref="detailRef"
    :win="wins.detail" :server="detailServer"
    @close="detailServer = null"
    @max="toggleMax('detail')"
    @front="bringFront('detail')"
    @drag="startDrag($event, 'detail')"
    @collected="loadLatest" />

  <OpsLogManager v-if="wins.logs.open"
    :win="wins.logs" :folders="logFolders"
    v-model:active-folder="activeFolder"
    :selected-log="logFile ? logFile.name : ''"
    @open-log="openLog"
    @close="closeWin('logs')"
    @max="toggleMax('logs')"
    @front="bringFront('logs')"
    @drag="startDrag($event, 'logs')" />

  <OpsLogViewer v-if="logFile && wins.logview.open"
    :win="wins.logview" :file="logFile"
    @close="logFile = null"
    @max="toggleMax('logview')"
    @front="bringFront('logview')"
    @drag="startDrag($event, 'logview')" />

  <OpsDockBar :wins="wins" @open="openWin" @detect-all="detectAll" />
  </div>
</template>
