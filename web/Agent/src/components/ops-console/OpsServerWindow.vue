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
          <div class="srv-metric">
            <span class="srv-metric-label">存储</span>
            <span class="srv-metric-disk">{{ displayDiskOf(srv)?.name || '-' }}</span>
            <span class="srv-metric-value" :style="{ color: metricColor(displayDiskOf(srv)?.used) }">{{ fmtPct(displayDiskOf(srv)?.used) }}</span>
          </div>
        </div>
      </div>
      <div v-if="!servers.length" class="no-result">未找到与「{{ searchKey }}」匹配的服务器</div>
    </div>

    <div class="statusbar">{{ servers.length }} 台服务器，{{ errCount }} 台异常</div>
  </div>
</template>