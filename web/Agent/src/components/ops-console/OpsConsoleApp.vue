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
 * 2026-08-13 GNOME 风格化：
 *       1) 顶部菜单栏 OpsMenuBar 改为 GNOME top bar（实色 + 中文全局菜单占位
 *          + 右侧 ✕ Close 原生 button 替代原 mac 三色交通灯，emit('exit') 不变）；
 *       2) 4 个窗口标题栏 mac 红/绿交通灯 → 右侧 max + close 两按钮（原生 button
 *          + SVG），close / max 事件契约不变；
 *       3) 底部 Dock 改造为底部 taskbar（政务蓝实色 36px 整宽，三图标入口）；
 *       4) 本轮不实现 minimize（涉及最小化栈与状态保留，单独 PR 落地）；
 *       5) 业务逻辑零改动（runDetect / loadLatest / detectAll / mapSnapshotToServer
 *          / startDrag 等未触动）。
 *
 * 2026-08-14 菜单栏重构（用户需求）：
 *       1) 删除底部 taskbar（OpsDockBar 组件 + 模板引用 + .taskbar-* 样式全删）；
 *       2) OpsMenuBar 顶部菜单栏新增「服务器管理 / 日志管理」两按钮，中部水平居中，
 *          顶部菜单栏 emit('open', 'servers'|'logs') → 本组件透传给 openWin；
 *       3) 彻底删除「一键智能检测」入口及 detectAll / detailRef / nextTick 链路
 *          （死代码清理，避免后续误用）；
 *       4) .win.maximized 高度回 calc(100vh - 28px)（不再避让底部 36px taskbar）。
 *
 * 状态机：
 *   - currentTime: string                  顶部菜单栏时间（1s 定时器）
 *   - searchKey: string                    服务器搜索关键词（v-model 双向）
 *   - zTop: number                         全局 z 序计数器
 *   - wins: { servers, detail, logs, logview, inspectionLog } 各窗口的开关/位置/层级/最大化
 *   - detailServer: ServerItem | null      当前展示详情的服务器
 *   - inspectionLogServer: ServerItem      当前打开采集记录窗口的服务器（2026-08-17 新增）
 *   - inspectionLogRecords: HistoryRecord[] 该服务器的历史采集记录数组（2026-08-17 新增）
 *   - inspectionLogLoading: boolean        是否正在拉取采集记录（2026-08-17 新增）
 *   - detectServer: ServerItem | null      当前智能检测窗口的服务器（2026-08-17 新增）
 *   - activeFolder: number                 当前日志文件夹下标
 *   - logFolders: Array<LogFolder>         日志文件夹列表（2026-08-12 起由
 *                                          ``GET /api/admin/log-folders`` 填充；
 *                                          接口未落地前保持空数组，前端不再持有
 *                                          mock 数据，详见 __tests__/fixtures/）
 *   - logFile: { name, content } | null    当前查看的日志文件
 *
 * 行为：
 *   - 1s 定时器刷新时间显示
 *   - 4 个窗口可独立 open/close/max/front/drag
 *   - 服务图标点击 → openDetail
 *   - 日志文件点击 → openLog（生成 14 行样例日志）
 */
import { ref, computed, onMounted } from 'vue'
import OpsMenuBar from './OpsMenuBar.vue'
import OpsServerWindow from './OpsServerWindow.vue'
import OpsDetailWindow from './OpsDetailWindow.vue'
import OpsLogManager from './OpsLogManager.vue'
import OpsLogViewer from './OpsLogViewer.vue'
import OpsInspectionLogWindow from './OpsInspectionLogWindow.vue'
import OpsDetectChatWindow from './OpsDetectChatWindow.vue'
import {
  fetchServerInspectionLatest,
  fetchServerInspectionRecords,
  validateToken,
} from '../../utils/api.js'

const currentTime = ref('')
const searchKey = ref('')
const zTop = ref(10)
const wins = ref({
  servers:       { open: true,  max: true,  x: 90,  y: 60,  z: 3 },
  detail:        { open: true,  max: false, x: 300, y: 120, z: 2 },
  logs:          { open: false, max: false, x: 160, y: 80,  z: 1 },
  logview:       { open: true,  max: false, x: 380, y: 140, z: 1 },
  inspectionLog: { open: false, max: false, x: 220, y: 100, z: 1 },
  detect:        { open: false, max: false, x: 260, y: 110, z: 1 },
})
const detailServer = ref(null)
// 2026-08-17 新增：采集记录窗口状态
const inspectionLogServer = ref(null)
const inspectionLogRecords = ref([])
const inspectionLogLoading = ref(false)
// 2026-08-17 新增：智能检测窗口状态
const detectServer = ref(null)
const activeFolder = ref(0)
// 2026-08-12：logFolders 由后端 /api/admin/log-folders 提供（待落地）；
// 此前由 ``../../data/ops-console/mockData.js`` 兜底，2026-08-12 起移除
// 前端 mock，接口未落地期间保持空数组（日志管理窗口打开后显示空态）。
const logFolders = ref([])
const logFile = ref(null)

// 2026-08-09：新增「关闭整个运维控制台」事件，透传到父组件 OpsConsoleWorkspace。
// 触发源：OpsMenuBar 顶部菜单栏右侧 ✕ Close 原生 button（GNOME 风格）。
const emit = defineEmits(['exit'])

// 2026-08-05：servers 由后端 /api/admin/server-inspection/latest 提供
// （按当前用户 OwnershipScope 过滤），不再用 mockData。
const servers = ref([])
const serversLoadError = ref('')

/**
 * 后端快照行 → 前端 ServerItem 映射。
 *
 * 契约要点：
 *   - ``os`` / ``cpuModel`` / ``uptime`` / ``memTotal`` / ``diskTotal`` / ``netIn``
 *     已移除（2026-08-16：详情页不再消费；「操作系统」改展示 server_type 原值
 *     linux/windows；DB parsed_values 当前也不含 os/cpu_model/uptime_hours）；
 *   - ``iowait`` / ``swap`` / ``inode`` 取自 parsed_values 的 cpu_iowait_pct /
 *     swap_used_pct / inode_used_pct（linux/windows 双平台均采集，缺失 → null）；
 *   - ``load`` 为 linux 1 分钟平均负载原始数值（非百分比），windows → null；
 *   - ``disks`` 由 ``parsed_values.disks`` 映射（mount → name，disk_used_pct → used）；
 *   - ``ip`` 不返（遵循脱敏约定）→ ``-``。
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
    // 2026-08-17：透传 business_name（智能检测 chat override 契约：
    // query_inspection_records 按 business_name 精确反查 server_id，
    // 与卡片显示名 node_name 可能不同，二者必须分别保留）。
    businessName: item.business_name || '',
    ip: '-',                // 不返 ip（运维脱敏约定）
    serverType: item.server_type || '',   // linux/windows，详情页「操作系统」+ 卡片「负载」判定
    status: item.status || 'unknown',
    cpu: item.metrics?.cpu ?? null,
    mem: item.metrics?.mem ?? null,
    disk: item.metrics?.disk ?? null,
    load: item.metrics?.load ?? null,      // linux 1 分钟负载（原始数值，非百分比）；windows/null
    // 2026-08-16：OS 关键指标（对齐 inspection_scripts.yaml linux-bash / windows-ps-5.1，
    // windows 下 iowait 为中断/DPC 占比、swap 为页面文件、inode 为 MFT 使用率）
    iowait: pv.cpu_iowait_pct ?? null,
    swap: pv.swap_used_pct ?? null,
    inode: pv.inode_used_pct ?? null,
    disks: disks.map(d => ({
      // 2026-08-16: 透传 mount（区分"系统盘 mount"/"设备名 mount"）+ IO 字段，
      // 供 OpsServerWindow 卡片异常盘符智能选择。name 仍沿用 mount 兼容旧 UI。
      name: d.mount || '-',
      mount: d.mount || '',
      used: d.disk_used_pct ?? null,
      ioUtilPct: d.io_util_pct ?? null,
      ioAwaitMs: d.io_await_ms ?? null,
      diskType: d.disk_type || '',
      // 2026-08-16: 物理盘分组字段（Linux lsblk PKNAME / Windows Win32_DiskDrive 解析）。
      // 缺失时留空串, 前端按 mount 兜底分组（不跨 mount 猜盘）。
      hostDisk: d.host_disk || '',
      diskIndex: typeof d.disk_index === 'number' ? d.disk_index : null,
      partition: d.partition || '',
      total: '-',
    })),
    // 2026-08-16：透传后端每字段评估结果（由 inspection_scripts.yaml warn/crit
    // 评估后的 pass/warn/crit/unassessed 状态数组），供卡片异常盘符判定。
    fieldResults: Array.isArray(item.field_results) ? item.field_results : [],
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

/**
 * 打开采集记录窗口（OpsInspectionLogWindow）。
 *
 * 流程：
 *   1. 写入 inspectionLogServer，立即打开窗口（不带数据，避免空窗白屏等待）；
 *   2. bringFront 置顶；
 *   3. 异步拉取 server_inspection_records（limit=100），失败时回空列表（窗口内
 *      显示「暂无采集记录」空态）。
 *
 * @param {ServerItem} srv 当前服务器卡片对象
 * @returns {void}
 */
async function openInspectionLog(srv) {
  if (!srv || srv.id == null) return
  inspectionLogServer.value = srv
  inspectionLogRecords.value = []
  wins.value.inspectionLog.open = true
  bringFront('inspectionLog')
  inspectionLogLoading.value = true
  try {
    const resp = await fetchServerInspectionRecords(srv.id, { limit: 100 })
    inspectionLogRecords.value = Array.isArray(resp && resp.items) ? resp.items : []
  } catch (err) {
    console.warn('[OpsConsoleApp] openInspectionLog 拉取采集记录失败:', err && err.message)
    inspectionLogRecords.value = []
  } finally {
    inspectionLogLoading.value = false
  }
}

/** 关闭采集记录窗口并清空状态。 */
function closeInspectionLog() {
  wins.value.inspectionLog.open = false
  inspectionLogServer.value = null
  inspectionLogRecords.value = []
  inspectionLogLoading.value = false
}

/**
 * 打开智能检测聊天窗口（OpsDetectChatWindow）。
 *
 * 流程：写入 detectServer → 打开窗口 → bringFront 置顶。
 * 窗口 onMounted 自动发起一次 SSE 流式检测（agent=project，
 * context_overrides.referenced_servers 注入 business_name）。
 *
 * @param {ServerItem} srv 当前服务器卡片对象
 * @returns {void}
 */
function onOpenDetect(srv) {
  if (!srv || srv.id == null) return
  detectServer.value = srv
  wins.value.detect.open = true
  bringFront('detect')
}

/** 关闭智能检测窗口并清空状态。 */
function closeDetect() {
  wins.value.detect.open = false
  detectServer.value = null
}

/** 打开日志查看窗口（生成 14 行样例日志内容） */
function openLog(f) {
  logFile.value = { ...f, content: genLogContent(f.name) }
  wins.value.logview.open = true
  bringFront('logview')
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
  <!-- 2026-08-14：OpsMenuBar emit('open', 'servers'|'logs') → 透传给 openWin。
       OpsDockBar 已彻底删除，原任务栏两入口上移至此。 -->
  <OpsMenuBar :time="currentTime" @open="openWin" @exit="emit('exit')" />

  <OpsServerWindow v-if="wins.servers.open"
    :win="wins.servers" :servers="filteredServers"
    v-model:search-key="searchKey"
    :selected-id="detailServer ? detailServer.id : null"
    @open-detail="openDetail"
    @open-log="openInspectionLog"
    @open-detect="onOpenDetect"
    @close="closeWin('servers')"
    @max="toggleMax('servers')"
    @front="bringFront('servers')"
    @drag="startDrag($event, 'servers')" />

  <OpsDetailWindow v-if="detailServer && wins.detail.open"
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

  <!-- 2026-08-17 新增：采集记录窗口（数据源 server_inspection_records）-->
  <OpsInspectionLogWindow v-if="inspectionLogServer && wins.inspectionLog.open"
    :win="wins.inspectionLog"
    :server="inspectionLogServer"
    :records="inspectionLogRecords"
    :loading="inspectionLogLoading"
    @close="closeInspectionLog"
    @max="toggleMax('inspectionLog')"
    @front="bringFront('inspectionLog')"
    @drag="startDrag($event, 'inspectionLog')" />

  <!-- 2026-08-17 新增：智能检测聊天窗口（/api/agent/chat SSE，agent=project）-->
  <OpsDetectChatWindow v-if="detectServer && wins.detect.open"
    :win="wins.detect"
    :server="detectServer"
    @close="closeDetect"
    @front="bringFront('detect')"
    @drag="startDrag($event, 'detect')" />

  </div>
</template>
