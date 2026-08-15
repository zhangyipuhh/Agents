<script setup>
/**
 * 运维控制台 - 服务器详情窗口组件（只读卡片 + 多列磁盘）
 *
 * 2026-08-05 从 `运维界面/app/src/components/DetailWindow.vue` 整段迁移。
 * 2026-08-05 改造：`runDetect` 改为调 `POST /api/admin/server-inspection/collect`
 * 触发真实采集+落库，面板输出真实判定明细（替代原 6 步假动画）。
 *
 * 2026-08-13 调整为 GNOME 风格：
 *   1) 标题栏 mac 红/绿交通灯 → 右侧 max + close 两按钮（原生 <button> + SVG）；
 *   2) 原生 button 自动支持 Enter/Space 键盘可达，无需手动 keydown 处理；
 *   3) 本轮不实现 minimize（涉及最小化栈与状态保留，单独 PR 落地）。
 *
 * 2026-08-16 用户需求改造：
 *   1) 移除「智能检测」按钮 + detect-panel + runDetect 整段逻辑（详情页只读）；
 *   2) 头部 sub 由 `ip · os` 改为「最新检测时间:YYYY-MM-DD HH:MM」绝对时间
 *      （与外层卡片 srv-card-time 文案/格式完全一致，复用 formatCollectedAt）；
 *   3) 顶部 3 个圆角指标卡（含进度条 .bar） → 删除；
 *      改为与外层卡片同款长方形 4 联指标条（.detail-metric-bar）：
 *        CPU 使用率 / 内存占用 / 存储使用 / 服务器负载（仅 linux）；
 *      复用 OpsServerWindow 已具名导出的 metricColor / loadColor / isLinuxType，
 *      不复制阈值口径；删除进度条样式 .bar；
 *   4) kv 表格精简：移除「内存总量 / 存储总量 / 网络流入」3 项；
 *      保留「操作系统 / CPU 型号 / 运行时长」3 项；
 *   5) 磁盘展示由单列行（盘符 + 已用% + 共 + 进度条） → 多列网格（.disk-grid）：
 *        每列：盘符 + 三指标（使用率 / 排队 ms / IO 利用率）；
 *      完全去除磁盘进度条样式；
 *   6) 详情窗口宽度 500 → 460（用户要求「四联的框需要缩小」）。
 *
 * Props:
 *   - win: { x, y, z, max }    窗口位置/层级/最大化状态
 *   - server: ServerItem       当前展示详情的服务器
 *
 * Emits:
 *   - close / max / front / drag  窗口控制（max/close 由原生 button 触发，事件契约不变）
 */
import { computed } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'
import {
  metricColor,
  loadColor,
  formatCollectedAt,
  isLinuxType,
} from './OpsServerWindow.vue'

const props = defineProps({
  win: { type: Object, required: true },
  server: { type: Object, required: true },
})

const emit = defineEmits(['close', 'max', 'front', 'drag'])

/**
 * 数值展示：null/undefined → '-'；其他 → `${v}%`。
 * 与外层卡片 fmtPct 行为一致（卡片 helper 未导出，故本地复制实现）。
 */
function fmtPct(v) {
  if (v == null) return '-'
  return `${v}%`
}

/**
 * 毫秒展示：null/undefined → '-'；其他 → `${v}ms`。
 * 磁盘「排队」专用。
 */
function fmtMs(v) {
  if (v == null) return '-'
  return `${v}ms`
}

/**
 * 字符串展示字段降级：null / undefined / 空串 / 纯空白 → '-'；
 * 其他 → 原字符串 trim。
 *
 * 2026-08-16：详情页 kv 表格「操作系统 / CPU 型号」值由
 * ``OpsConsoleApp.mapSnapshotToServer`` 从 ``parsed_values.os`` /
 * ``parsed_values.cpu_model`` 读取，已做防御性 trim 兜底；
 * 详情页这里再做一次防御是双保险（即使上游不传 '' 也不显示空白）。
 *
 * @param {string|null|undefined} v 原始字符串
 * @returns {string} 清洗后的字符串；空值返回 '-'
 */
function fmtStr(v) {
  if (typeof v !== 'string') return '-'
  const t = v.trim()
  return t ? t : '-'
}

/**
 * 磁盘图标 LED 三态：任一指标超阈（≥80）→ 红；都正常 → 绿；都未采集 → 灰。
 * 与外层卡片 .led 红/绿/gray 同款映射（颜色由 OpsServerIcon 内部 class 决定）。
 */
function diskIconStatus(d) {
  const items = [d && d.used, d && d.ioUtilPct, d && d.ioAwaitMs]
  const hasValue = items.some(v => v != null)
  if (!hasValue) return 'unknown'
  const overThreshold = items.some(v => typeof v === 'number' && v >= 80)
  return overThreshold ? 'err' : 'ok'
}

/** 磁盘 list 是否存在（前端防御） */
const hasDisks = computed(() => Array.isArray(props.server.disks) && props.server.disks.length > 0)
</script>

<template>
  <div class="win win-detail" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">{{ server.name }} — 服务器详情</span>
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

    <div class="win-body detail-body">
      <!-- 头部：大图标 + 名称 + 状态 badge + 最新检测时间（绝对时间） -->
      <div class="srv-head">
        <div class="big-icon">
          <OpsServerIcon :status="server.status" :size="36" />
        </div>
        <div>
          <h3>{{ server.name }}<span class="badge" :class="server.status">{{
            server.status === 'ok' ? '运行正常'
              : server.status === 'err' ? '指标异常'
              : '未采集'
          }}</span></h3>
          <!-- 2026-08-16：头部 sub 由 `ip · os` 改为「最新检测时间:」+ 绝对时间
               （与外层卡片 srv-card-time 文案/格式完全一致）；title 放 ISO 全文 -->
          <div class="sub" :title="server.collectedAt || ''">
            最新检测时间:{{ formatCollectedAt(server.collectedAt) }}
          </div>
        </div>
      </div>

      <!-- 长方形 4 联指标条（与外层卡片同款视觉）：CPU / 内存 / 存储 / 负载（仅 linux）。
           复用 OpsServerWindow 具名导出的 metricColor / loadColor / isLinuxType。 -->
      <div class="detail-metric-bar">
        <div class="dm-item">
          <span class="dm-label">CPU 使用率</span>
          <span class="dm-value" :style="{ color: metricColor(server.cpu) }">{{ fmtPct(server.cpu) }}</span>
        </div>
        <div class="dm-item">
          <span class="dm-label">内存占用</span>
          <span class="dm-value" :style="{ color: metricColor(server.mem) }">{{ fmtPct(server.mem) }}</span>
        </div>
        <div class="dm-item">
          <span class="dm-label">存储使用</span>
          <span class="dm-value" :style="{ color: metricColor(server.disk) }">{{ fmtPct(server.disk) }}</span>
        </div>
        <div v-if="isLinuxType(server.serverType)" class="dm-item">
          <span class="dm-label">服务器负载</span>
          <span class="dm-value" :style="{ color: loadColor(server.load) }">{{ fmtPct(server.load) }}</span>
        </div>
      </div>

      <!-- 精简 kv：保留 OS / CPU 型号 / 运行时长；删除内存/存储总量 / 网络流入。
           2026-08-16：os / cpuModel 通过 fmtStr 做防御性 trim 兜底（空串/空白 → '-'），
           即使上游 mapSnapshotToServer 漏 trim 也能保持显示一致。 -->
      <div class="kv">
        <div><span class="k">操作系统</span><span>{{ fmtStr(server.os) }}</span></div>
        <div><span class="k">CPU 型号</span><span>{{ fmtStr(server.cpuModel) }}</span></div>
        <div><span class="k">运行时长</span><span>{{ server.uptime }}</span></div>
      </div>

      <!-- 磁盘多列网格：每列盘符 + 三指标（使用率/排队/IO利用率），无进度条 -->
      <div class="disk-section">
        <div class="disk-title">磁盘</div>
        <div v-if="hasDisks" class="disk-grid">
          <div v-for="d in server.disks" :key="d.mount || d.name" class="disk-cell">
            <div class="dc-head">
              <OpsServerIcon :status="diskIconStatus(d)" :size="22" />
              <span class="dc-name">{{ d.mount || d.name || '-' }}</span>
            </div>
            <div class="dc-metrics">
              <div class="dc-m">
                <span class="dc-m-label">使用率</span>
                <span class="dc-m-value" :style="{ color: metricColor(d.used) }">{{ fmtPct(d.used) }}</span>
              </div>
              <div class="dc-m">
                <span class="dc-m-label">排队</span>
                <span class="dc-m-value" :style="{ color: metricColor(d.ioAwaitMs) }">{{ fmtMs(d.ioAwaitMs) }}</span>
              </div>
              <div class="dc-m">
                <span class="dc-m-label">IO 利用率</span>
                <span class="dc-m-value" :style="{ color: metricColor(d.ioUtilPct) }">{{ fmtPct(d.ioUtilPct) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="disk-empty">无磁盘数据</div>
      </div>
    </div>
  </div>
</template>