<script>
/**
 * 模块导出（纯函数，供测试直接调用）。与下方 <script setup> 共存：
 *   - <script> 块允许 ES module exports；
 *   - <script setup> 块使用 defineProps / defineEmits / computed 等编译宏。
 */
export const WARN_PCT = 80

/**
 * 智能挑选展示的磁盘：
 *   1) 使用率 ≥ WARN_PCT 的盘 → 取 used 最大者；
 *   2) 否则挑 Windows 系统盘：mount 匹配 /^[A-Za-z]:/（优先 C:，无则第一块）；
 *   3) 否则挑 Linux 根盘：mount === '/'；
 *   4) 都没有 → 返回 null（卡片显示 '-'）。
 *
 * @param {Array<{name: string, used: number|null}>} disks 磁盘列表
 * @returns {{name: string, used: number|null}|null} 选中的磁盘；null 表示无可用盘
 */
export function pickDisplayDisk(disks) {
  if (!Array.isArray(disks) || disks.length === 0) return null
  // 1) 有使用率 ≥ WARN_PCT 的盘 → 返回其中 used 最大者
  const problem = disks.filter(d => d && typeof d.used === 'number' && d.used >= WARN_PCT)
  if (problem.length) {
    return problem.reduce((best, d) => (best == null || d.used > best.used) ? d : best, null)
  }
  // 2) 都没问题 → Windows 优先选 C:（无 C: 取首块盘符）；Linux 选 mount === '/' 的盘
  const winLike = disks.filter(d => d && typeof d.name === 'string' && /^[A-Za-z]:/.test(d.name))
  if (winLike.length) {
    const c = winLike.find(d => /^C:/i.test(d.name))
    return c || winLike[0]
  }
  const linuxRoot = disks.find(d => d && d.name === '/')
  if (linuxRoot) return linuxRoot
  // 3) 都不匹配 → 退回首块
  return disks[0] || null
}

/**
 * 指标着色：null → 灰色（未采集）；≥ WARN_PCT → 红色（有问题）；否则 → 正常绿
 *
 * @param {number|null} v 百分比数值
 * @returns {string} 颜色字符串
 */
export function metricColor(v) {
  if (v == null) return '#9aa3af'
  if (v >= WARN_PCT) return '#ff453a'
  return '#1d9a40'
}

/**
 * Linux 1 分钟平均负载着色（独立阈值，与 CPU/Mem/Disk 的 80% 阈值不同）：
 *   - null / 非数字 → 灰色（未采集）
 *   - < LOAD_WARN → 绿
 *   - ≥ LOAD_WARN → 红（与 inspection_scripts.yaml 中 warn=4.0 对齐）
 *
 * 阈值 4 来自 ``data/devops/inspection_scripts.yaml`` linux-bash 的
 * ``load_1m`` 字段规则 warn=4.0（crit=8.0）。运维看卡片只需要二态即可。
 *
 * @param {number|null} v 负载数值（保留 2 位小数）
 * @returns {string} 颜色字符串
 */
export const LOAD_WARN = 4
export function loadColor(v) {
  if (v == null) return '#9aa3af'
  if (v >= LOAD_WARN) return '#ff453a'
  return '#1d9a40'
}

/**
 * 非百分比数值格式化（如 load_1m 平均负载）：null/undefined → '-'，其他原样输出。
 * 负载是「1 分钟平均负载」原始数值而非百分比，不能追加 % 后缀。
 *
 * @param {number|null|undefined} v 数值
 * @returns {string} 格式化字符串
 */
export function fmtNum(v) {
  if (v == null) return '-'
  return `${v}`
}

/**
 * 把 ISO 时间格式化为 ``YYYY-MM-DD HH:MM``（本地时区）。
 * - null / undefined / 非字符串 / 解析失败 → ``'-'``（无快照兜底）
 *
 * @param {string|null|undefined} iso ISO 时间字符串（如 ``2026-08-16T00:46:35``）
 * @returns {string} 格式化后的时间字符串；无效输入返回 ``'-'``
 */
export function formatCollectedAt(iso) {
  if (typeof iso !== 'string' || !iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}`
}

/**
 * 判定是否显示「负载」指标项。仅 ``serverType === 'linux'``（不区分大小写）
 * 返回 true；其他（windows / 空串 / 未知）一律 false —— 白名单策略避免未来
 * 引入新 platform 时误显示。
 *
 * @param {string|undefined|null} serverType 后端返回的平台类型
 * @returns {boolean} 是否渲染负载项
 */
export function isLinuxType(serverType) {
  return typeof serverType === 'string' && serverType.toLowerCase() === 'linux'
}

/**
 * 磁盘指标 key 集合（来自 inspection_scripts.yaml 中 disk_used_pct /
 * io_util_pct / io_await_ms 三条规则的 key）。
 */
const DISK_METRIC_KEYS = ['disk_used_pct', 'io_util_pct', 'io_await_ms']

/**
 * 状态严重度（数值越大越严重），用于按 mount 分组后取最严重项 + 整体排序。
 */
const STATUS_SEVERITY = { pass: 0, unassessed: 1, warn: 2, crit: 3 }

/**
 * 从后端 ``field_results`` 中按 mount 聚合「异常」磁盘项：
 *   - 只看 ``key ∈ {disk_used_pct, io_util_pct, io_await_ms}``;
 *   - 只收 ``status ∈ {warn, crit}``（pass/unassessed 跳过）;
 *   - 同一 mount 多条异常 → 合并到 ``items`` 数组；
 *   - 整体排序：crit 优先，warn 次之；同状态按 mount 名升序。
 *
 * mount 提取优先级（与后端 ``_expand_disks_array`` 一致）：
 *   1) ``field_result.message`` 形如 ``"磁盘 /data"`` → 取 ``/data``；
 *   2) 兜底 ``disks[]`` 中 mount 与 key 匹配的项；
 *   3) 仍无 mount → 退回空串（聚合用 '__anon__' 占位）。
 *
 * @param {Array} fieldResults 后端 ``ServerInspectionRecordService._row_to_view``
 *                              返回的 ``field_results`` 数组
 * @param {Array} disks         后端 ``parsed_values.disks`` 原始数组（用于兜底 mount 提取）
 * @returns {Array<{mount:string, status:'warn'|'crit', items:Array}>}
 *          按状态降序排好的异常盘符列表；无异常返回 ``[]``
 */
export function pickAnomalyDisks(fieldResults, disks) {
  if (!Array.isArray(fieldResults) || fieldResults.length === 0) return []

  const buckets = new Map()  // mount → {mount, status, items}

  // 预先建 mount → disk 索引，方便兜底
  const mountToDisk = new Map()
  if (Array.isArray(disks)) {
    for (const d of disks) {
      if (d && typeof d.mount === 'string' && d.mount) {
        mountToDisk.set(d.mount, d)
      }
    }
  }

  for (const fr of fieldResults) {
    if (!fr || typeof fr !== 'object') continue
    const key = fr.key
    if (!DISK_METRIC_KEYS.includes(key)) continue
    const status = fr.status
    if (status !== 'warn' && status !== 'crit') continue

    // 1) 优先从 message 解析 mount（后端约定："磁盘 {mount}"）
    let mount = ''
    const msg = typeof fr.message === 'string' ? fr.message : ''
    if (msg.startsWith('磁盘 ')) {
      mount = msg.slice(3).trim()
    }
    // 2) 兜底：disks[] 里 mount 在 message 里未匹配时，跳过
    //    （保证前端不臆造 mount，避免误把 `/data` 与 `sda[HDD]` 混到一起）
    if (!mount) {
      // 第三层兜底：取对应 disks[] 中含该 key 的首项
      for (const [, d] of mountToDisk) {
        if (d && (d[key] !== undefined && d[key] !== null)) {
          mount = d.mount
          break
        }
      }
    }
    const bucketKey = mount || '__anon__'

    let bucket = buckets.get(bucketKey)
    if (!bucket) {
      bucket = { mount, status, items: [] }
      buckets.set(bucketKey, bucket)
    }
    // 升级桶状态（crit > warn）
    if ((STATUS_SEVERITY[status] || 0) > (STATUS_SEVERITY[bucket.status] || 0)) {
      bucket.status = status
    }
    bucket.items.push({
      key,
      name_zh: fr.name_zh || key,
      unit: fr.unit || '',
      value: fr.value ?? null,
      status,
    })
  }

  // 排序：crit 优先，warn 次之；同状态按 mount 升序
  return Array.from(buckets.values()).sort((a, b) => {
    const sd = (STATUS_SEVERITY[b.status] || 0) - (STATUS_SEVERITY[a.status] || 0)
    if (sd !== 0) return sd
    return (a.mount || '').localeCompare(b.mount || '')
  })
}

/**
 * 异常项 → 紧凑展示文本（用于卡片存储行的异常概要）。
 *   - 单位 ``%`` → ``<name> <value>%``（如 "使用 92%"）
 *   - 单位 ``ms`` → ``<name> <value>ms``（如 "等待 150ms"）
 *   - 其他单位 → ``<name> <value><unit>``
 *   - name 简写：磁盘使用率 → "使用"；磁盘 IO 利用率 → "IO"；磁盘 IO 平均等待 → "等待"
 *
 * @param {{key:string, name_zh:string, unit:string, value:any}} item
 * @returns {string} 紧凑展示文本
 */
export function formatAnomalyItem(item) {
  if (!item || item.value == null) return ''
  const v = item.value
  const NAME_MAP = {
    disk_used_pct: '使用',
    io_util_pct: 'IO',
    io_await_ms: '等待',
  }
  const short = NAME_MAP[item.key] || item.name_zh || item.key
  if (item.unit === '%') return `${short} ${v}%`
  if (item.unit === 'ms') return `${short} ${v}ms`
  return `${short} ${v}${item.unit || ''}`
}
</script>

<script setup>
/**
 * 运维控制台 - 服务器管理窗口组件（卡片式 2 列 + 红绿灯 + 指标预览）
 *
 * 2026-08-14 改造（卡片化）：
 *   1) 列表由图标视图（110px 方格）改为两列横向长方形卡片；
 *   2) 卡片头部保留红绿灯 LED + 服务器名称（紧凑），下方单行指标
 *      （CPU / 内存 / 存储，竖线分隔）即时反馈巡检结果；
 *   3) 阈值口径与 ``data/devops/inspection_scripts.yaml`` 的 warn 字段对齐
 *      （CPU 80 / 内存 80 / 磁盘 80），超标红色（#ff453a），未采集灰色；
 *   4) 存储行按 disks 列表智能选择：有使用率 ≥ 80 的盘 → 取最高的那块；
 *      否则 Windows 取 C: 盘符盘（无 C: 取首块盘符），Linux 取 mount === '/'；
 *      找不到 → 显示 '-'；
 *   5) 单击卡片仍 emit('open-detail', srv) 打开 OpsDetailWindow，详情页契约不变。
 *
 * Props:
 *   - win: { x, y, z, max }    窗口位置/层级/最大化状态
 *   - servers: Array<ServerItem>  已过滤的服务器列表
 *   - searchKey: string         搜索关键词（双向绑定）
 *   - selectedId: number|null   当前选中的服务器 ID（用于高亮）
 *
 * Emits:
 *   - update:searchKey  v-model 搜索关键词
 *   - open-detail       点击服务器卡片，打开详情窗口
 *   - close / max / front / drag  窗口控制
 */
import { computed } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'

const props = defineProps({
  win: { type: Object, required: true },
  servers: { type: Array, required: true },
  searchKey: { type: String, default: '' },
  selectedId: { type: Number, default: null },
})

const emit = defineEmits(['update:searchKey', 'open-detail', 'close', 'max', 'front', 'drag'])

/** 异常服务器数量（驱动 statusbar 显示） */
const errCount = computed(() => props.servers.filter(s => s.status === 'err').length)

/** 卡片使用的磁盘视图（具名函数，便于模板复用） */
function displayDiskOf(srv) {
  return pickDisplayDisk(srv.disks)
}

/**
 * 每张卡片的异常盘符列表（基于后端 ``field_results`` 聚合）。
 * 缓存到 Map 避免模板中 ``v-for`` 重复调 ``pickAnomalyDisks``。
 *
 * 行为：
 *   - ``srv.fieldResults`` 非空 → 按 mount 聚合异常项；
 *   - 空 → 返回空数组（让模板退化到 ``displayDiskOf`` 老逻辑分支）;
 *
 * @type {ComputedRef<Map<string, Array>>} key = String(srv.id)
 */
const anomaliesById = computed(() => {
  const m = new Map()
  for (const srv of props.servers) {
    const frs = Array.isArray(srv.fieldResults) ? srv.fieldResults : []
    m.set(String(srv.id), frs.length === 0 ? [] : pickAnomalyDisks(frs, srv.disks))
  }
  return m
})

/** 模板 helper：按 server id 取异常列表 */
function anomaliesOf(srv) {
  return anomaliesById.value.get(String(srv.id)) || []
}

/** 把百分比格式化为字符串（null → '-'） */
function fmtPct(v) {
  if (v == null) return '-'
  return `${v}%`
}
</script>

<template>
  <div class="win win-servers" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">服务器管理</span>
      <div class="srv-toolbar">
        <div class="search-box" @mousedown.stop>
          <svg viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2.4" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><line x1="15.5" y1="15.5" x2="21" y2="21"/></svg>
          <input :value="searchKey" @input="emit('update:searchKey', $event.target.value)" placeholder="搜索服务器名称 / IP" />
        </div>
      </div>
      <!-- 2026-08-13 GNOME 风格：右侧两按钮 max + close（左→右），原生 button + SVG -->
      <div class="win-controls">
        <button type="button" class="win-control win-control--max"
                aria-label="最大化" title="最大化"
                @click.stop="emit('max')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="5" y="5" width="14" height="14" rx="1.5"/>
          </svg>
        </button>
        <button type="button" class="win-control win-control--close"
                aria-label="关闭" title="关闭"
                @click.stop="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <line x1="6" y1="6" x2="18" y2="18"/>
            <line x1="18" y1="6" x2="6" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 2026-08-14 卡片式：两列横向长方形，每张含 LED + 标题 + 单行指标（竖线分隔） -->
    <div class="srv-grid">
      <div v-for="srv in servers" :key="srv.id" class="srv-card"
           :class="{ selected: selectedId === srv.id, problem: srv.status === 'err' }"
           @click="emit('open-detail', srv)">
        <div class="srv-card-head">
          <OpsServerIcon :status="srv.status" :size="26" />
          <span class="srv-card-title" :title="srv.name">{{ srv.name }}</span>
          <!-- 2026-08-16 新增：最后检测时间（来自 server_latest_snapshot.collected_at）；
               无快照时显示 '-'。标题 flex:1 自动让位挤压，时间右贴保持省略号不变。
               2026-08-16 追加：「最新检测时间:」前缀标签，让用户一眼看出语义。 -->
          <span class="srv-card-time" :title="srv.collectedAt || ''">最新检测时间:{{ formatCollectedAt(srv.collectedAt) }}</span>
        </div>
        <div class="srv-card-metrics">
          <div class="srv-metric">
            <span class="srv-metric-label">CPU</span>
            <span class="srv-metric-value" :style="{ color: metricColor(srv.cpu) }">{{ fmtPct(srv.cpu) }}</span>
          </div>
          <div class="srv-metric">
            <span class="srv-metric-label">内存</span>
            <span class="srv-metric-value" :style="{ color: metricColor(srv.mem) }">{{ fmtPct(srv.mem) }}</span>
          </div>
          <!-- 2026-08-16 重构：磁盘行基于后端 ``field_results`` 智能选异常盘。
               - 有异常：盘符 + 异常指标概要（IO 92% / 等待 150ms / 使用 95%），
                 盘符与概要统一标红 #ff453a（与 LED 红同系），多个异常盘用逗号分隔；
               - 无异常：显示 '-'（沿用 metricColor(null) 灰）；
               - 兜底：fieldResults 为空（老数据 / 未落库）→ 退化到
                 displayDiskOf 行为（保留 pickDisplayDisk 既有逻辑）。 -->
          <div class="srv-metric srv-metric-storage">
            <span class="srv-metric-label">存储</span>
            <template v-if="anomaliesOf(srv).length">
              <span v-for="(a, idx) in anomaliesOf(srv)" :key="(a.mount || 'anon') + '-' + idx"
                    class="srv-metric-disk srv-metric-disk--problem">
                <span class="srv-metric-disk-name">{{ a.mount || '匿名盘' }}</span>
                <span v-for="(it, j) in a.items" :key="a.mount + '-' + it.key + '-' + j"
                      class="srv-metric-anomaly">
                  · {{ formatAnomalyItem(it) }}
                </span>
              </span>
            </template>
            <template v-else-if="srv.fieldResults && srv.fieldResults.length === 0 && displayDiskOf(srv)">
              <!-- 老数据兜底：fieldResults 为空 + 仍能选盘 → 显示使用率（沿用旧 UI） -->
              <span class="srv-metric-disk">{{ displayDiskOf(srv)?.name || '-' }}</span>
              <span class="srv-metric-value" :style="{ color: metricColor(displayDiskOf(srv)?.used) }">{{ fmtPct(displayDiskOf(srv)?.used) }}</span>
            </template>
            <template v-else>
              <span class="srv-metric-value" :style="{ color: metricColor(null) }">-</span>
            </template>
          </div>
          <!-- 2026-08-16 改造：linux 负载 label 改为「服务器负载」（语义更明确）。
               颜色阈值独立（loadColor: ≥4 红 / <4 绿 / null 灰），与百分比指标阈值 80 解耦。
               数值经 fmtNum 原样输出（load_1m 非百分比，2026-08-16 去 %）。 -->
          <div v-if="isLinuxType(srv.serverType)" class="srv-metric">
            <span class="srv-metric-label">服务器负载</span>
            <span class="srv-metric-value" :style="{ color: loadColor(srv.load) }">{{ fmtNum(srv.load) }}</span>
          </div>
        </div>
      </div>
      <div v-if="!servers.length" class="no-result">未找到与「{{ searchKey }}」匹配的服务器</div>
    </div>

    <div class="statusbar">{{ servers.length }} 台服务器，{{ errCount }} 台异常</div>
  </div>
</template>