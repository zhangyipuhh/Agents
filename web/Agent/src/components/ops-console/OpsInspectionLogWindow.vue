<!--
  运维控制台 - 采集记录窗口（2026-08-17 新增）

  用途：
    - 由 OpsServerWindow 卡片头「日志」按钮触发（emit('open-log', srv)）；
    - 数据源 server_inspection_records（按 server_id 倒序，最新 100 条）；
    - 布局：左 280px 列表 + 右自适应详情（复用 OpsDetailWindow 的指标卡 / kv / 磁盘分组布局）；
    - 列表字段：采集时间、状态徽章、耗时、exit_code、错误摘要。

  设计决策：
    - 复用 OpsDetailWindow 的纯函数 + 渲染模板，但避免嵌套窗口外壳（双重标题栏问题）；
      本组件内部 inline 渲染详情区，逻辑函数从 OpsDetailWindow 具名 import。
    - 数据加载由父级 OpsConsoleApp 调 fetchServerInspectionRecords 完成，本组件只消费
      props（records / loading），组件本身无网络请求，便于测试。
    - 选中态默认指向首条；点击其他条切换；右栏重新渲染对应记录的指标。
-->
<script>
/**
 * record 行（server_inspection_records 一行）→ ServerItem 形状（驱动右栏渲染）。
 *
 * 与 OpsConsoleApp::mapSnapshotToServer 字段对齐：
 *   - parsed_values → metrics / disks / load / iowait / swap / inode；
 *   - field_results 透传；
 *   - collected_at → collectedAt；
 *   - 其他顶层字段（server_id / business_name / server_type）从 baseServer 继承。
 *
 * 输入字段约束：
 *   - record.parsed_values 可能是 dict / list / 其他类型（防御性处理）；
 *   - record.field_results 可能是 list 或其他（list 校验）。
 *
 * @param {object} record  历史采集记录行
 * @param {object} baseServer  当前服务器 ServerItem（提供 serverType / name / id 等基础字段）
 * @returns {object} 渲染右栏用的 ServerItem 形状
 */
export function mapRecordToServer(record, baseServer) {
  if (!record || typeof record !== 'object') {
    return baseServer || {}
  }
  // 安全解析 parsed_values（dict | list | 其他）
  let pv = record.parsed_values
  if (pv && typeof pv === 'string') {
    try { pv = JSON.parse(pv) } catch { pv = null }
  }
  if (!pv || typeof pv !== 'object' || Array.isArray(pv)) {
    pv = {}
  }

  const disks = Array.isArray(pv.disks) ? pv.disks : []
  const fieldResults = Array.isArray(record.field_results)
    ? record.field_results
    : []

  return {
    id: baseServer ? baseServer.id : (record.server_id || null),
    nodeId: baseServer ? baseServer.nodeId : null,
    name: baseServer ? baseServer.name : (record.business_name || '-'),
    ip: '-',
    serverType: baseServer ? baseServer.serverType : '',
    status: record.success === false ? 'err' : (record.inspection_status === 'pass' ? 'ok' : (record.inspection_status === 'warn' || record.inspection_status === 'crit' ? 'err' : 'unknown')),
    cpu: pv.cpu_used_pct ?? (pv.cpu_idle_pct != null ? roundTo2(100 - Number(pv.cpu_idle_pct)) : null),
    mem: pv.mem_used_pct ?? null,
    disk: pickRootDiskPct(disks),
    load: pv.load_1m ?? null,
    iowait: pv.cpu_iowait_pct ?? null,
    swap: pv.swap_used_pct ?? null,
    inode: pv.inode_used_pct ?? null,
    disks: disks.map(d => ({
      name: d && d.mount ? d.mount : '-',
      mount: d && d.mount ? d.mount : '',
      used: d && d.disk_used_pct != null ? d.disk_used_pct : null,
      ioUtilPct: d && d.io_util_pct != null ? d.io_util_pct : null,
      ioAwaitMs: d && d.io_await_ms != null ? d.io_await_ms : null,
      diskType: d && d.disk_type ? d.disk_type : '',
      hostDisk: d && d.host_disk ? d.host_disk : '',
      diskIndex: typeof d?.disk_index === 'number' ? d.disk_index : null,
      partition: d && d.partition ? d.partition : '',
      total: '-',
    })),
    fieldResults,
    collectedAt: record.collected_at || null,
    errorMessage: record.error_message || null,
  }
}

/** 选系统盘占用率（与 server_inspection_record_service._pick_root_disk_pct 对齐）。 */
function pickRootDiskPct(disks) {
  if (!Array.isArray(disks) || disks.length === 0) return null
  // 1) 找 mount 为 '/' 或 Windows C: 系统盘
  for (const d of disks) {
    if (!d || typeof d !== 'object') continue
    const m = String(d.mount || '').trim()
    const isRoot = m === '/' || /^C:\?$/i.test(m) || /^C:$/i.test(m)
    if (isRoot && d.disk_used_pct != null) return Number(d.disk_used_pct)
  }
  // 2) 兜底：第一块可用盘
  for (const d of disks) {
    if (!d || typeof d !== 'object') continue
    if (d.disk_used_pct != null) return Number(d.disk_used_pct)
  }
  return null
}

function roundTo2(v) {
  const n = Number(v)
  return Number.isFinite(n) ? Math.round(n * 100) / 100 : null
}
</script>

<script setup>
/**
 * 运维控制台 - 采集记录窗口组件（左 280 列表 + 右自适应详情）
 *
 * Props:
 *   - win: { x, y, z, max }       窗口位置/层级/最大化
 *   - server: ServerItem          当前服务器（基础字段：name / id / serverType）
 *   - records: Array              历史采集记录数组（按 collected_at DESC）
 *   - loading: boolean            父级是否正在拉数据
 *
 * Emits:
 *   - close / max / front / drag  窗口控制
 */
import { ref, computed, watch } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'
import {
  metricColor,
  loadColor,
  formatCollectedAt,
  isLinuxType,
  fmtNum,
} from './OpsServerWindow.vue'
import {
  fmtPct,
  fmtMs,
  fmtStr,
  warnColor,
  IOWAIT_WARN,
  SWAP_WARN,
  INODE_WARN,
  groupDisksByPhysicalDisk,
  diskGroupLabel,
  diskHeadStatus,
  peakIoAwait,
  peakIoUtil,
  partitionCardStatus,
  statusLabel,
  formatDuration,
} from './OpsDetailWindow.vue'

const props = defineProps({
  win: { type: Object, required: true },
  server: { type: Object, required: true },
  records: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'max', 'front', 'drag'])

/** 当前选中的记录 id（默认指向第一条）。 */
const selectedRecordId = ref(null)

/** 选中态切换。 */
function selectRecord(r) {
  if (!r || r.id == null) return
  selectedRecordId.value = r.id
}

/** 当前选中的 record 行。 */
const selectedRecord = computed(() => {
  if (!Array.isArray(props.records) || props.records.length === 0) return null
  const id = selectedRecordId.value
  if (id != null) {
    const hit = props.records.find(r => r && r.id === id)
    if (hit) return hit
  }
  return props.records[0]
})

/** 选中 record → ServerItem 形状，喂给右栏渲染。 */
const displayServer = computed(() => {
  const rec = selectedRecord.value
  if (!rec) return props.server
  return mapRecordToServer(rec, props.server)
})

/** 当前选中的物理磁盘分组。 */
const diskGroups = computed(() => groupDisksByPhysicalDisk(displayServer.value.disks || []))
const hasDisks = computed(() => Array.isArray(displayServer.value.disks) && displayServer.value.disks.length > 0)

/** records 切换时把选中态重置到第一条（避免停在已删除的 id）。 */
watch(() => props.records, (next) => {
  if (Array.isArray(next) && next.length > 0) {
    const stillExists = next.find(r => r && r.id === selectedRecordId.value)
    selectedRecordId.value = stillExists ? stillExists.id : (next[0].id ?? null)
  } else {
    selectedRecordId.value = null
  }
})
</script>

<template>
  <div class="win win-inspection-log" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">{{ server.name }} — 采集记录</span>
      <div class="win-controls">
        <button type="button" class="win-control win-control--max" aria-label="最大化" title="最大化"
                @click.stop="emit('max')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="5" y="5" width="14" height="14" rx="1.5"/>
          </svg>
        </button>
        <button type="button" class="win-control win-control--close" aria-label="关闭" title="关闭"
                @click.stop="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <line x1="6" y1="6" x2="18" y2="18"/>
            <line x1="18" y1="6" x2="6" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="inslog-body">
      <!-- 左栏：采集记录列表 -->
      <div class="inslog-list">
        <div v-if="loading" class="inslog-empty">加载中…</div>
        <div v-else-if="!records.length" class="inslog-empty">暂无采集记录</div>
        <div v-for="r in records" :key="r.id"
             class="inslog-item" :class="{ active: (selectedRecordId ?? records[0]?.id) === r.id }"
             @click="selectRecord(r)">
          <div class="inslog-row1">
            <span class="inslog-time">{{ formatCollectedAt(r.collected_at) }}</span>
            <span class="inslog-badge" :class="r.inspection_status || 'unassessed'">{{ statusLabel(r.inspection_status) }}</span>
          </div>
          <div class="inslog-row2">
            <span class="inslog-meta">耗时 {{ formatDuration(r.duration_ms) }}</span>
            <span v-if="r.exit_code != null" class="inslog-meta">exit {{ r.exit_code }}</span>
            <span v-if="r.success === false" class="inslog-meta">失败</span>
            <span v-else-if="r.success === true" class="inslog-meta">成功</span>
          </div>
          <div v-if="r.error_message" class="inslog-err" :title="r.error_message">{{ r.error_message }}</div>
        </div>
      </div>

      <!-- 右栏：详情（复用 OpsDetailWindow body 区域同样式，但去掉窗口外壳） -->
      <div class="inslog-detail detail-body">
        <div class="srv-head">
          <div class="big-icon"><OpsServerIcon :status="displayServer.status" :size="36" /></div>
          <div>
            <h3>{{ displayServer.name }}<span class="badge" :class="displayServer.status">{{ displayServer.status === 'ok' ? '运行正常' : displayServer.status === 'err' ? '指标异常' : '未采集' }}</span></h3>
            <div class="sub" :title="displayServer.collectedAt || ''">最新检测时间:{{ formatCollectedAt(displayServer.collectedAt) }}</div>
          </div>
        </div>

        <div class="detail-metric-bar">
          <div class="dm-item"><span class="dm-label">CPU 使用率</span><span class="dm-value" :style="{ color: metricColor(displayServer.cpu) }">{{ fmtPct(displayServer.cpu) }}</span></div>
          <div class="dm-item"><span class="dm-label">内存占用</span><span class="dm-value" :style="{ color: metricColor(displayServer.mem) }">{{ fmtPct(displayServer.mem) }}</span></div>
          <div class="dm-item"><span class="dm-label">存储使用</span><span class="dm-value" :style="{ color: metricColor(displayServer.disk) }">{{ fmtPct(displayServer.disk) }}</span></div>
          <div v-if="isLinuxType(displayServer.serverType)" class="dm-item"><span class="dm-label">服务器负载</span><span class="dm-value" :style="{ color: loadColor(displayServer.load) }">{{ fmtNum(displayServer.load) }}</span></div>
        </div>

        <div class="kv">
          <div><span class="k">操作系统</span><span>{{ fmtStr(displayServer.serverType) }}</span></div>
          <div><span class="k">CPU IOWait</span><span :style="{ color: warnColor(displayServer.iowait, IOWAIT_WARN) }">{{ fmtPct(displayServer.iowait) }}</span></div>
          <div><span class="k">Swap 使用率</span><span :style="{ color: warnColor(displayServer.swap, SWAP_WARN) }">{{ fmtPct(displayServer.swap) }}</span></div>
          <div><span class="k">Inode 使用率</span><span :style="{ color: warnColor(displayServer.inode, INODE_WARN) }">{{ fmtPct(displayServer.inode) }}</span></div>
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
  </div>
</template>
