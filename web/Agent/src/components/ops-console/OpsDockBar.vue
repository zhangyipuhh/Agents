<script setup>
/**
 * 运维控制台 - 底部 Dock 栏组件
 *
 * 2026-08-05 从 `运维界面/app/src/components/DockBar.vue` 整段迁移。
 * 三个图标入口：服务器管理 / 日志管理 / 一键智能检测。
 *
 * Props:
 *   - wins: { servers: { open }, logs: { open } }  窗口开关状态（用于显示运行中圆点）
 *
 * Emits:
 *   - open(name)        点击服务器/日志图标，name='servers'|'logs'，父组件打开对应窗口
 *   - detect-all        点击一键智能检测图标
 */
defineProps({
  wins: { type: Object, required: true },
})

const emit = defineEmits(['open', 'detect-all'])
</script>

<template>
  <div class="dock-wrap">
    <div class="dock">
      <div class="dock-item" @click="emit('open', 'servers')"><span class="tip">服务器管理</span>
        <svg viewBox="0 0 48 48"><rect x="5" y="7" width="38" height="34" rx="6" fill="url(#dg)"/><rect x="11" y="14" width="26" height="8" rx="2" fill="#9aa3af"/><rect x="11" y="26" width="26" height="8" rx="2" fill="#8a939f"/><circle cx="15.5" cy="18" r="1.6" fill="#30d158"/><circle cx="15.5" cy="30" r="1.6" fill="#ff453a"/><defs><linearGradient id="dg" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#2b4a7c"/><stop offset="1" stop-color="#1a3054"/></linearGradient></defs></svg>
        <span v-if="wins.servers.open" class="run-dot"></span>
      </div>
      <div class="dock-item" @click="emit('open', 'logs')"><span class="tip">日志管理</span>
        <svg viewBox="0 0 48 48"><path d="M5 11a4 4 0 014-4h9l4 5h17a4 4 0 014 4v21a4 4 0 01-4 4H9a4 4 0 01-4-4z" fill="#1e6add"/><path d="M5 16h38v21a4 4 0 01-4 4H9a4 4 0 01-4-4z" fill="#3d84e8"/><path d="M9 20h30v17a3 3 0 01-3 3H12a3 3 0 01-3-3z" fill="#7db2f2"/></svg>
        <span v-if="wins.logs.open" class="run-dot"></span>
      </div>
      <div class="dock-sep"></div>
      <div class="dock-item" @click="emit('detect-all')"><span class="tip">一键智能检测</span>
        <svg viewBox="0 0 48 48"><circle cx="20" cy="20" r="11" fill="none" stroke="#1e6add" stroke-width="4"/><line x1="28" y1="28" x2="40" y2="40" stroke="#1e6add" stroke-width="5" stroke-linecap="round"/><path d="M20 14v4l3 3" stroke="#1e6add" stroke-width="2.5" fill="none" stroke-linecap="round"/></svg>
      </div>
    </div>
  </div>
</template>
