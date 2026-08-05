<script setup>
/**
 * 运维控制台 - 服务器图标组件（深色机架样式 + 红/绿指示灯）
 *
 * 2026-08-05 从 `运维界面/app/src/components/ServerIcon.vue` 整段迁移。
 * 被 OpsServerWindow / OpsDetailWindow 共用。
 *
 * Props:
 *   - status: 'ok' | 'err'  状态（驱动右上角 LED 灯颜色 + 机架指示灯颜色）
 *   - size: number          SVG 边长（px）
 *   - led: boolean          是否显示右上角状态灯（默认 true；DetailWindow 用大图标时为 true）
 */
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'ok' },   // ok=绿灯 err=红灯
  size: { type: Number, default: 46 },
  led: { type: Boolean, default: true },     // 是否显示右上角状态灯
})

/** LED 灯颜色（由状态驱动） */
const ledColor = computed(() => (props.status === 'ok' ? '#30d158' : '#ff453a'))
</script>

<template>
  <span style="position:relative;display:inline-flex">
    <span v-if="led" class="led" :class="status === 'ok' ? 'green' : 'red'"></span>
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
