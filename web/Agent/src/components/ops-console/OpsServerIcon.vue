<script setup>
/**
 * 运维控制台 - 服务器图标组件（深色机架样式 + 红/绿/灰指示灯）
 *
 * 2026-08-05 从 `运维界面/app/src/components/ServerIcon.vue` 整段迁移；
 * 2026-08-05 新增 ``unknown`` 灰色态（从未采集 / 无快照 / 采集跳过）。
 * 被 OpsServerWindow / OpsDetailWindow 共用。
 *
 * Props:
 *   - status: 'ok' | 'err' | 'unknown'  状态（驱动右上角 LED 灯颜色 + 机架指示灯颜色）
 *   - size: number          SVG 边长（px）
 *   - led: boolean          是否显示右上角状态灯（默认 true；DetailWindow 用大图标时为 true）
 */
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'ok' },   // ok=绿灯 err=红灯 unknown=灰灯
  size: { type: Number, default: 46 },
  led: { type: Boolean, default: true },     // 是否显示右上角状态灯
})

/** LED 灯颜色（由状态驱动）。unknown 用中灰色，未采集数据的语义 */
const ledColor = computed(() => {
  if (props.status === 'ok') return '#30d158'
  if (props.status === 'err') return '#ff453a'
  return '#9aa3af'   // unknown → 灰
})

/** 右上角 LED 灯的 CSS class（green / red / gray） */
const ledClass = computed(() => {
  if (props.status === 'ok') return 'green'
  if (props.status === 'err') return 'red'
  return 'gray'
})
</script>

<template>
  <span style="position:relative;display:inline-flex">
    <span v-if="led" class="led" :class="ledClass"></span>
    <svg :width="size" :height="size" viewBox="0 0 64 64" fill="none">
      <rect x="10" y="16" width="44" height="13" rx="2.5" fill="#9aa3af" stroke="#c9d1dc"/>
      <rect x="10" y="33" width="44" height="13" rx="2.5" fill="#8a939f" stroke="#c9d1dc"/>
      <circle cx="17" cy="22.5" r="2" :fill="ledColor"/>
      <circle cx="17" cy="39.5" r="2" :fill="ledColor"/>
      <rect x="24" y="20.5" width="24" height="4" rx="2" fill="rgba(255,255,255,.55)"/>
      <rect x="24" y="37.5" width="24" height="4" rx="2" fill="rgba(255,255,255,.55)"/>
    </svg>
  </span>
</template>

<style scoped>
.led.gray { background: #9aa3af; box-shadow: 0 0 4px rgba(154,163,175,.6); }
</style>
