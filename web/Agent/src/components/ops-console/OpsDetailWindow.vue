<script setup>
/**
 * 运维控制台 - 服务器详情窗口组件（含智能检测）
 *
 * 2026-08-05 从 `运维界面/app/src/components/DetailWindow.vue` 整段迁移。
 * 暴露 `runDetect()` 方法，供父组件 OpsConsoleApp 通过 ref 调用（一键智能检测）。
 *
 * Props:
 *   - win: { x, y, z, max }    窗口位置/层级/最大化状态
 *   - server: ServerItem       当前展示详情的服务器
 *
 * Emits:
 *   - close / max / front / drag  窗口控制
 *
 * Expose:
 *   - runDetect(): void  触发智能检测动画（依次输出 6 步诊断日志）
 */
import { ref, computed, watch } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'

const props = defineProps({
  win: { type: Object, required: true },
  server: { type: Object, required: true },
})

const emit = defineEmits(['close', 'max', 'front', 'drag'])

const detecting = ref(false)
const detectLogs = ref([])
let timers = []

/** 指标卡列表（CPU/内存/磁盘），值 ≥75 标红，否则绿 */
const metricList = computed(() => {
  const s = props.server
  const c = v => (v >= 75 ? '#ff453a' : '#1d9a40')
  return [
    { label: 'CPU 使用率', value: s.cpu, pct: s.cpu, color: c(s.cpu) },
    { label: '内存占用', value: s.mem, pct: s.mem, color: c(s.mem) },
    { label: '存储使用', value: s.disk, pct: s.disk, color: c(s.disk) },
  ]
})

/** 重置检测状态（清 timers + 清日志 + 标记未在检测） */
function resetDetect() {
  timers.forEach(clearTimeout)
  timers = []
  detectLogs.value = []
  detecting.value = false
}

/**
 * 触发智能检测动画
 * - 重复点击短路：detecting=true 时直接返回
 * - 按 server 状态（ok/err）生成 6 步诊断文本 + 综合评分
 * - 每条 log 按时延依次 push（200ms / 700ms / ... / 3900ms）
 * - 检测结束后 ~200ms 标记 detecting=false
 * @returns {void}
 */
function runDetect() {
  if (detecting.value) return
  const s = props.server
  resetDetect()
  detecting.value = true
  const bad = s.status === 'err'
  const lines = [
    { text: '$ ops-ai diagnose --target ' + s.ip, type: 'info', delay: 200 },
    { text: '[1/6] 采集主机指标 ............ 完成 (CPU ' + s.cpu + '% / MEM ' + s.mem + '% / DISK ' + s.disk + '%)', type: '', delay: 700 },
    { text: '[2/6] 检测系统进程健康度 ...... ' + (s.cpu >= 75 ? '异常：3 个进程 CPU 占用过高' : '正常'), type: s.cpu >= 75 ? 'err' : 'ok', delay: 1200 },
    { text: '[3/6] 检测内存泄漏风险 ........ ' + (s.mem >= 75 ? '警告：内存占用超阈值 75%，建议扩容或重启服务' : '正常'), type: s.mem >= 75 ? 'warn' : 'ok', delay: 1700 },
    { text: '[4/6] 检测磁盘 SMART 状态 ..... ' + (s.disk >= 75 ? '警告：磁盘使用率 ' + s.disk + '%，建议清理日志归档' : '正常'), type: s.disk >= 75 ? 'warn' : 'ok', delay: 2200 },
    { text: '[5/6] 检测网络连通性 .......... 正常 (延迟 0.8ms，丢包 0%)', type: 'ok', delay: 2700 },
    { text: '[6/6] AI 根因分析 ............. ' + (bad ? '判定：数据库慢查询堆积 + 缓存穿透，建议优化索引并限流扩容' : '未发现异常，系统运行良好'), type: bad ? 'err' : 'ok', delay: 3300 },
    { text: '✔ 诊断完成，综合评分 ' + (bad ? '58' : '97') + ' / 100', type: 'info', delay: 3900 },
  ]
  lines.forEach(l => timers.push(setTimeout(() => detectLogs.value.push(l), l.delay)))
  timers.push(setTimeout(() => { detecting.value = false }, 4100))
}

/** 磁盘使用率配色（≥85 红 / ≥70 黄 / 否则蓝） */
function diskColor(used) {
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
          <h3>{{ server.name }}<span class="badge" :class="server.status">{{ server.status === 'ok' ? '运行正常' : '指标异常' }}</span></h3>
          <div class="sub">{{ server.ip }} · {{ server.os }}</div>
        </div>
      </div>

      <div class="metrics">
        <div class="metric" v-for="m in metricList" :key="m.label">
          <div class="m-label">{{ m.label }}</div>
          <div class="m-value" :style="{ color: m.color }">{{ m.value }}<small style="font-size:12px;color:#999"> %</small></div>
          <div class="bar"><i :style="{ width: m.pct + '%', background: m.color }"></i></div>
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
            <circle cx="51" cy="41" r="2.5" :fill="d.used >= 85 ? '#ff453a' : '#30d158'"/>
            <defs><linearGradient id="dsk" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#dfe5ec"/><stop offset="1" stop-color="#b8c2ce"/></linearGradient></defs>
          </svg>
          <div class="disk-info">
            <div class="disk-name">
              <span>{{ d.name }}</span>
              <span class="du">已用 <b>{{ d.used }}%</b> · 共 {{ d.total }}</span>
            </div>
            <div class="bar"><i :style="{ width: d.used + '%', background: diskColor(d.used) }"></i></div>
          </div>
        </div>
      </div>

      <button class="gov-btn" @click="runDetect" :disabled="detecting">
        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><line x1="15.5" y1="15.5" x2="21" y2="21"/><path d="M10.5 7.5v3l2 2" stroke-width="1.6"/></svg>
        {{ detecting ? '智能检测中…' : '智能检测' }}
      </button>

      <div v-if="detectLogs.length" class="detect-panel">
        <div v-for="(log, i) in detectLogs" :key="i" class="line" :class="log.type" :style="{ animationDelay: (i * 0.05) + 's' }">{{ log.text }}</div>
        <span v-if="detecting" class="cursor"></span>
      </div>
    </div>
  </div>
</template>
