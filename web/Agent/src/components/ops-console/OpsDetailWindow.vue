<script setup>
/**
 * 运维控制台 - 服务器详情窗口组件（含智能检测）
 *
 * 2026-08-05 从 `运维界面/app/src/components/DetailWindow.vue` 整段迁移。
 * 2026-08-05 改造：``runDetect`` 改为调 ``POST /api/admin/server-inspection/collect``
 * 触发真实采集+落库，面板输出真实判定明细（替代原 6 步假动画）。
 *
 * Props:
 *   - win: { x, y, z, max }    窗口位置/层级/最大化状态
 *   - server: ServerItem       当前展示详情的服务器
 *
 * Emits:
 *   - close / max / front / drag  窗口控制
 *   - collected                采集完成事件，父组件可刷新列表
 *
 * Expose:
 *   - runDetect(): Promise<void>  触发真实采集
 */
import { ref, computed, watch } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'
import { collectServerInspection } from '../../utils/api.js'

const props = defineProps({
  win: { type: Object, required: true },
  server: { type: Object, required: true },
})

const emit = defineEmits(['close', 'max', 'front', 'drag', 'collected'])

const detecting = ref(false)
const detectLogs = ref([])

/** 指标卡列表（CPU/内存/磁盘），值 ≥75 标红，否则绿；null/'-' 显示占位 */
const metricList = computed(() => {
  const s = props.server
  const c = v => {
    if (v == null) return '#9aa3af'                  // 未采集
    if (v >= 75) return '#ff453a'
    return '#1d9a40'
  }
  return [
    { label: 'CPU 使用率', value: s.cpu, pct: s.cpu, color: c(s.cpu) },
    { label: '内存占用', value: s.mem, pct: s.mem, color: c(s.mem) },
    { label: '存储使用', value: s.disk, pct: s.disk, color: c(s.disk) },
  ]
})

/** 重置检测状态（清日志 + 标记未在检测） */
function resetDetect() {
  detectLogs.value = []
  detecting.value = false
}

/**
 * 触发真实采集（智能检测）：
 * - 调 ``POST /collect`` 对当前 server 立即重新采集+落库；
 * - 完成后把逐字段判定（field_results）以行式输出；
 * - 失败仅在面板显示一行错误，不抛异常。
 *
 * @returns {Promise<void>}
 */
async function runDetect() {
  if (detecting.value) return
  const s = props.server
  resetDetect()
  detecting.value = true
  detectLogs.value.push({
    text: `$ ops-ai collect --target server_id=${s.id} ${s.name}`,
    type: 'info',
  })
  try {
    const resp = await collectServerInspection([s.id])
    detectLogs.value.push({
      text: `✔ 采集完成，落库 ${resp.collected} 条`,
      type: 'ok',
    })
    const item = (resp.items || [])[0]
    if (!item) {
      detectLogs.value.push({ text: '⚠ 本次未产生采集明细', type: 'warn' })
    } else {
      detectLogs.value.push({
        text: `状态: ${item.success ? 'OK' : 'FAIL'}  exit=${item.success === false ? '-' : 0} `
            + `inspection=${item.inspection_status || '-'} `
            + `duration=${item.duration_ms ?? '-'}ms`,
        type: item.success === false ? 'err' : (item.inspection_status === 'crit' ? 'err'
              : item.inspection_status === 'warn' ? 'warn' : 'ok'),
      })
      if (item.error_message) {
        detectLogs.value.push({ text: `错误: ${item.error_message}`, type: 'err' })
      }
      ;(item.field_results || []).forEach((f, i) => {
        const status = f.status || 'unassessed'
        const msg = f.message ? `（${f.message}）` : ''
        const value = f.value != null ? f.value : '无值'
        detectLogs.value.push({
          text: `  field[${i}] ${f.key} ${f.name_zh || ''} = ${value}${f.unit || ''} `
              + `→ ${status.toUpperCase()}${msg}`,
          type: status === 'pass' ? 'ok' : status === 'warn' ? 'warn'
              : (status === 'crit' ? 'err' : ''),
        })
      })
    }
    emit('collected')
  } catch (err) {
    detectLogs.value.push({
      text: `✘ 采集失败: ${(err && err.message) || '未知错误'}`,
      type: 'err',
    })
  } finally {
    detecting.value = false
  }
}

/** 磁盘使用率配色（≥85 红 / ≥70 黄 / 否则蓝）；null → 灰 */
function diskColor(used) {
  if (used == null) return '#9aa3af'
  if (used >= 85) return '#ff453a'
  if (used >= 70) return '#e6a700'
  return '#1e6add'
}

watch(() => props.server.id, resetDetect)

defineExpose({ runDetect })
</script>

<template>
  <div class="win win-detail" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <div class="traffic">
        <span class="r" @click.stop="emit('close')"></span><span class="g" @click.stop="emit('max')"></span>
      </div>
      <span class="win-title">{{ server.name }} — 服务器详情</span>
    </div>
    <div class="win-body detail-body">
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
          <div class="sub">{{ server.ip }} · {{ server.os }}</div>
        </div>
      </div>

      <div class="metrics">
        <div class="metric" v-for="m in metricList" :key="m.label">
          <div class="m-label">{{ m.label }}</div>
          <div class="m-value" :style="{ color: m.color }">
            {{ m.value != null ? m.value : '-' }}<small style="font-size:12px;color:#999"> %</small>
          </div>
          <div class="bar"><i :style="{ width: (m.pct != null ? m.pct : 0) + '%', background: m.color }"></i></div>
        </div>
      </div>

      <div class="kv">
        <div><span class="k">操作系统</span><span>{{ server.os }}</span></div>
        <div><span class="k">CPU 型号</span><span>{{ server.cpuModel }}</span></div>
        <div><span class="k">内存总量</span><span>{{ server.memTotal }}</span></div>
        <div><span class="k">存储总量</span><span>{{ server.diskTotal }}</span></div>
        <div><span class="k">运行时长</span><span>{{ server.uptime }}</span></div>
        <div><span class="k">网络流入</span><span>{{ server.netIn }}</span></div>
      </div>

      <!-- 磁盘列表（macOS 存储样式） -->
      <div class="disk-section">
        <div class="disk-title">磁盘</div>
        <div class="disk-row" v-for="d in server.disks" :key="d.name">
          <!-- macOS 磁盘图标 -->
          <svg viewBox="0 0 64 64" fill="none">
            <rect x="6" y="18" width="52" height="30" rx="6" fill="url(#dsk)" stroke="#aab4c0"/>
            <rect x="6" y="18" width="52" height="14" rx="6" fill="rgba(255,255,255,.35)"/>
            <circle cx="51" cy="41" r="2.5" :fill="d.used != null && d.used >= 85 ? '#ff453a' : '#30d158'"></circle>
            <defs><linearGradient id="dsk" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#dfe5ec"/><stop offset="1" stop-color="#b8c2ce"/></linearGradient></defs>
          </svg>
          <div class="disk-info">
            <div class="disk-name">
              <span>{{ d.name }}</span>
              <span class="du">
                {{ d.used != null ? `已用 ${d.used}%` : '未采集' }}
                · 共 {{ d.total }}
              </span>
            </div>
            <div class="bar"><i :style="{ width: (d.used != null ? d.used : 0) + '%', background: diskColor(d.used) }"></i></div>
          </div>
        </div>
      </div>

      <button class="gov-btn" @click="runDetect" :disabled="detecting">
        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><line x1="15.5" y1="15.5" x2="21" y2="21"/><path d="M10.5 7.5v3l2 2" stroke-width="1.6"/></svg>
        {{ detecting ? '检测中…' : '智能检测' }}
      </button>

      <div v-if="detectLogs.length" class="detect-panel">
        <div v-for="(log, i) in detectLogs" :key="i" class="line" :class="log.type" :style="{ animationDelay: (i * 0.05) + 's' }">{{ log.text }}</div>
      </div>
    </div>
  </div>
</template>
