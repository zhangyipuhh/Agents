<script>
/**
 * 模块导出（纯函数，供 OpsInspectionLogWindow 等复用，与 <script setup> 共存）。
 * 2026-08-17 抽出：原 <script setup> 内的纯函数搬到这里暴露具名 export，
 * 与 OpsServerWindow.vue 同款模式，便于其他组件直接 import 复用。
 * 单一 <script> 块允许包含多个 export function（Vue 3 SFC 约束：
 * 每个 *.vue 文件最多 1 个 <script> 块 + 可选 1 个 <script setup>）。
 */

/**
 * 模块级纯函数：按真实物理磁盘字段把扁平磁盘记录归组。
 *
 * 宿主磁盘和 `disk_index` 是 Linux/Windows 巡检脚本显式输出的设备关系；
 * 对旧 Windows 快照仍兼容解析 `0 C: D:[SSD]` 实例名。未知归属的记录按
 * mount/name 独立成组，避免把不同物理盘臆测合并。
 *
 * @param {Array} disks 扁平磁盘记录数组
 * @returns {Array<{key:string, hostDisk:string, diskIndex:number|null, records:Array}>}
 *          排序后的物理磁盘组；组内保留原始记录顺序
 */
export function groupDisksByPhysicalDisk(disks) {
  if (!Array.isArray(disks) || disks.length === 0) return []

  const groups = new Map()
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
  const legacyWindowsDriveToDisk = new Map()

  // 兼容历史 Windows WMI mount 文案：先建立盘符到物理盘编号的映射。
  // 例如 `0 C: D:[SSD]` 会把 C:、D: 都映射到磁盘 0。
  for (const item of disks) {
    if (!item || typeof item !== 'object') continue
    const mount = typeof item.mount === 'string' ? item.mount.trim() : ''
    const match = mount.match(/^(\d+)\s+(.+?)(?:\[[^\]]*\])?$/)
    if (!match) continue
    const diskIndex = Number(match[1])
    if (!Number.isInteger(diskIndex) || diskIndex < 0) continue
    const rest = match[2]
    for (const part of rest.split(/\s+/)) {
      const drive = part.match(/^([A-Za-z]:)/)
      if (drive) legacyWindowsDriveToDisk.set(drive[1].toUpperCase(), diskIndex)
    }
  }

  for (const d of disks) {
    if (!d || typeof d !== 'object') continue

    const mount = typeof d.mount === 'string' ? d.mount.trim() : ''
    const rawHost = typeof d.hostDisk === 'string' ? d.hostDisk.trim() : ''
    const rawIndex = Number.isFinite(d.diskIndex) ? d.diskIndex : null
    const drive = mount.match(/^([A-Za-z]:)/)
    const fallbackIndex = drive ? legacyWindowsDriveToDisk.get(drive[1].toUpperCase()) : null
    const legacyIndexMatch = mount.match(/^(\d+)\s+/)
    const legacyIndex = legacyIndexMatch ? Number(legacyIndexMatch[1]) : fallbackIndex
    const diskIndex = rawIndex != null ? rawIndex : legacyIndex
    const hostDisk = rawHost || (diskIndex != null ? `PHYSICALDRIVE${diskIndex}` : '')

    // 分区记录与整盘 IO 记录都必须使用同一个 disk_index；不能因
    // host_disk 字段存在而拆成两个组。没有真实设备关系时按显示标识独立成组。
    const key = diskIndex != null
      ? `disk:${diskIndex}`
      : hostDisk
        ? `host:${hostDisk}`
        : `legacy:${mount || (typeof d.name === 'string' ? d.name.trim() : '') || '-'}`

    if (!groups.has(key)) {
      groups.set(key, {
        key,
        hostDisk,
        diskIndex,
        records: [],
      })
    }
    const group = groups.get(key)
    if (group.diskIndex == null && diskIndex != null) group.diskIndex = diskIndex
    group.records.push(d)
  }

  // 不在纯函数中修改输入数组，保持调用方传入记录的原始顺序。

  return Array.from(groups.values()).sort((a, b) => {
    if (a.diskIndex != null && b.diskIndex != null) return a.diskIndex - b.diskIndex
    if (a.diskIndex != null) return -1
    if (b.diskIndex != null) return 1
    return collator.compare(a.hostDisk || a.key, b.hostDisk || b.key)
  })
}

/** 百分比展示：null/undefined 返回 '-'，其他值保留原数值。 */
export function fmtPct(v) {
  if (v == null) return '-'
  return `${v}%`
}

/** 毫秒展示：null/undefined 返回 '-'，其他值追加 ms。 */
export function fmtMs(v) {
  if (v == null) return '-'
  return `${v}ms`
}

/** 字符串展示：空值或纯空白降级为 '-'，其余 trim。 */
export function fmtStr(v) {
  if (typeof v !== 'string') return '-'
  const trimmed = v.trim()
  return trimmed || '-'
}

/**
 * OS 关键指标 warn 阈值（对齐 data/devops/inspection_scripts.yaml::inspection_fields）：
 * cpu_iowait_pct warn=20 / swap_used_pct warn=30 / inode_used_pct warn=80。
 */
export const IOWAIT_WARN = 20
export const SWAP_WARN = 30
export const INODE_WARN = 80

/**
 * 按 warn 阈值取色（与 metricColor/loadColor 同色系）：
 * null / 非数字 → 灰；≥ warn → 红；否则 → 绿。
 *
 * @param {number|null|undefined} v 指标值
 * @param {number} warn 告警阈值（达到即标红）
 * @returns {string} 颜色十六进制字符串
 */
export function warnColor(v, warn) {
  if (typeof v !== 'number' || Number.isNaN(v)) return '#9aa3af'
  return v >= warn ? '#ff453a' : '#1d9a40'
}

/**
 * 兼容历史字段名 ioAwaitMs / ioawaitMs 读取 IO 等待值（ms）。
 *
 * @param {object|null|undefined} record 磁盘记录
 * @returns {number|null} IO 等待值（ms）；无值返回 null
 */
export function ioAwaitValue(record) {
  if (!record || typeof record !== 'object') return null
  if (record.ioAwaitMs != null) return record.ioAwaitMs
  if (record.ioawaitMs != null) return record.ioawaitMs
  return null
}

/**
 * 生成磁盘节点标题：显示用户可读的"磁盘 N"，并保留 host_disk 设备信息。
 *
 * @param {{diskIndex?: number|null, hostDisk?: string, records?: Array}} group 物理磁盘组
 * @returns {string} 磁盘节点标题
 */
export function diskGroupLabel(group) {
  if (!group) return '未识别磁盘'
  if (group.diskIndex != null) return `磁盘 ${group.diskIndex}`
  if (group.hostDisk) return group.hostDisk
  const diskRecord = group.records && group.records.find(record => record && (record.ioUtilPct != null || ioAwaitValue(record) != null))
  if (diskRecord && typeof diskRecord.mount === 'string' && diskRecord.mount) return diskRecord.mount
  return '未识别磁盘'
}

/**
 * 分区卡片 LED 三态：使用率达到 80 为红，有值为绿，缺失为灰。
 *
 * @param {{used?: number|null}} d 分区使用率记录
 * @returns {'ok'|'err'|'unknown'} 分区状态
 */
export function partitionCardStatus(d) {
  if (d == null || d.used == null) return 'unknown'
  return d.used >= 80 ? 'err' : 'ok'
}

/** 物理磁盘头状态只读取整盘 IO 指标，不受分区使用率值影响。 */
export function diskHeadStatus(group) {
  if (!group || !Array.isArray(group.records)) return 'unknown'
  const values = group.records.flatMap(r => [r && r.ioUtilPct, ioAwaitValue(r)]).filter(v => v != null)
  if (values.length === 0) return 'unknown'
  return values.some(v => v >= 80) ? 'err' : 'ok'
}

/** 整盘排队指标：同组多分区时显示最严重的 IO 等待值。 */
export function peakIoAwait(group) {
  if (!group || !Array.isArray(group.records)) return null
  const values = group.records.map(r => ioAwaitValue(r)).filter(v => v != null)
  return values.length ? Math.max(...values) : null
}

/** 整盘 IO 利用率：同组多分区时显示最严重的 IO 利用率值。 */
export function peakIoUtil(group) {
  if (!group || !Array.isArray(group.records)) return null
  const values = group.records.map(r => r && r.ioUtilPct).filter(v => v != null)
  return values.length ? Math.max(...values) : null
}

/** 巡检状态 → 中文展示。 */
export function statusLabel(s) {
  if (s === 'pass') return '通过'
  if (s === 'warn') return '告警'
  if (s === 'crit') return '严重'
  if (s === 'skipped') return '跳过'
  if (s === 'unassessed') return '未评估'
  return '-'
}

/** 毫秒数 → 友好耗时字符串（如 1234 → "1.23s"；125 → "125ms"）。 */
export function formatDuration(ms) {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}
</script>

<script setup>
/**
 * 运维控制台 - 服务器详情窗口组件（只读卡片 + 物理磁盘分组）
 *
 * Props:
 *   - win: { x, y, z, max } 窗口位置/层级/最大化状态
 *   - server: ServerItem     当前展示详情的服务器；2026-08-16 改造后必含
 *                            serverType / iowait / swap / inode 字段，
 *                            旧版 os / cpuModel / uptime 已下线。
 *
 * Emits:
 *   - close / max / front / drag 窗口控制
 */
import { computed } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'
import {
  metricColor,
  loadColor,
  formatCollectedAt,
  isLinuxType,
  fmtNum,
} from './OpsServerWindow.vue'

const props = defineProps({
  win: { type: Object, required: true },
  server: { type: Object, required: true },
})

const emit = defineEmits(['close', 'max', 'front', 'drag'])

const hasDisks = computed(() => Array.isArray(props.server.disks) && props.server.disks.length > 0)

/** 按真实 host_disk/disk_index 归组后的物理磁盘列表。 */
const diskGroups = computed(() => groupDisksByPhysicalDisk(props.server.disks))
</script>

<template>
  <div class="win win-detail" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">{{ server.name }} — 服务器详情</span>
      <div class="win-controls">
        <button type="button" class="win-control win-control--max" aria-label="最大化" title="最大化" @click.stop="emit('max')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="1.5"/></svg>
        </button>
        <button type="button" class="win-control win-control--close" aria-label="关闭" title="关闭" @click.stop="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
        </button>
      </div>
    </div>

    <div class="win-body detail-body">
      <div class="srv-head">
        <div class="big-icon"><OpsServerIcon :status="server.status" :size="36" /></div>
        <div>
          <h3>{{ server.name }}<span class="badge" :class="server.status">{{ server.status === 'ok' ? '运行正常' : server.status === 'err' ? '指标异常' : '未采集' }}</span></h3>
          <div class="sub" :title="server.collectedAt || ''">最新检测时间:{{ formatCollectedAt(server.collectedAt) }}</div>
        </div>
      </div>

      <div class="detail-metric-bar">
        <div class="dm-item"><span class="dm-label">CPU 使用率</span><span class="dm-value" :style="{ color: metricColor(server.cpu) }">{{ fmtPct(server.cpu) }}</span></div>
        <div class="dm-item"><span class="dm-label">内存占用</span><span class="dm-value" :style="{ color: metricColor(server.mem) }">{{ fmtPct(server.mem) }}</span></div>
        <div class="dm-item"><span class="dm-label">存储使用</span><span class="dm-value" :style="{ color: metricColor(server.disk) }">{{ fmtPct(server.disk) }}</span></div>
        <div v-if="isLinuxType(server.serverType)" class="dm-item"><span class="dm-label">服务器负载</span><span class="dm-value" :style="{ color: loadColor(server.load) }">{{ fmtNum(server.load) }}</span></div>
      </div>

      <div class="kv">
        <div><span class="k">操作系统</span><span>{{ fmtStr(server.serverType) }}</span></div>
        <div><span class="k">CPU IOWait</span><span :style="{ color: warnColor(server.iowait, IOWAIT_WARN) }">{{ fmtPct(server.iowait) }}</span></div>
        <div><span class="k">Swap 使用率</span><span :style="{ color: warnColor(server.swap, SWAP_WARN) }">{{ fmtPct(server.swap) }}</span></div>
        <div><span class="k">Inode 使用率</span><span :style="{ color: warnColor(server.inode, INODE_WARN) }">{{ fmtPct(server.inode) }}</span></div>
      </div>

      <div class="disk-section">
        <div class="disk-title">磁盘</div>
        <div v-if="hasDisks" class="disk-groups">
          <div v-for="group in diskGroups" :key="group.key" class="disk-group">
            <div class="disk-group-head">
              <OpsServerIcon :status="diskHeadStatus(group)" :size="22" />
              <span class="dgh-name">{{ diskGroupLabel(group) }}</span>
              <span v-if="group.diskIndex != null" class="dgh-index">#{{ group.diskIndex }}</span>
              <span v-if="group.hostDisk" class="dgh-device">{{ group.hostDisk }}</span>
              <div class="dgh-metrics">
                <div class="dg-m"><span class="dg-m-label">排队</span><span class="dg-m-value" :style="{ color: metricColor(peakIoAwait(group)) }">{{ fmtMs(peakIoAwait(group)) }}</span></div>
                <div class="dg-m"><span class="dg-m-label">IO 利用率</span><span class="dg-m-value" :style="{ color: metricColor(peakIoUtil(group)) }">{{ fmtPct(peakIoUtil(group)) }}</span></div>
              </div>
            </div>
            <div class="disk-group-partitions">
              <!-- 分区卡只渲染分区记录 (partition 非空); IO 整盘记录 (partition="") 只在磁盘头聚合。-->
              <div v-for="d in group.records.filter(record => typeof record.partition === 'string' && record.partition)" :key="(d.partition || d.mount || d.name) + '|' + (d.used ?? 'null')" class="disk-pcard">
                <div class="dcp-header">
                  <OpsServerIcon :status="partitionCardStatus(d)" :size="14" />
                  <span class="dcp-name">{{ d.mount || d.partition || d.name || '-' }}</span>
                </div>
                <div class="dg-m">
                  <span class="dg-m-label">使用率</span>
                  <span class="dg-m-value" :style="{ color: metricColor(d.used) }">{{ fmtPct(d.used) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="disk-empty">无磁盘数据</div>
      </div>
    </div>
  </div>
</template>
