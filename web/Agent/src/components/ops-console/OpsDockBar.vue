<script setup>
/**
 * 运维控制台 - 底部 taskbar 任务栏组件（GNOME / Ubuntu 风格）
 *
 * 2026-08-05 从 `运维界面/app/src/components/DockBar.vue` 整段迁移。
 * 三个图标入口：服务器管理 / 日志管理 / 一键智能检测。
 *
 * 2026-08-13 调整为 GNOME 风格（替代原 mac 底部 Dock）：
 *   1) 样式从 `position: fixed; bottom: 10px; left: 50%` 居中胶囊
 *      → `position: fixed; bottom: 0; left: 0; right: 0` 整宽政务蓝实色；
 *   2) 高度 36px，三图标水平居中，间距 24px；
 *   3) 模板类名全量重命名 `dock-*` → `taskbar-*`（6 类）；
 *   4) .run-dot 位置由 bottom:-5px 改 top:2px right:2px（taskbar 36px 栏内无底部空间）；
 *   5) 取消 hover 弹跳（translateY(-12px) scale(1.18)）；
 *   6) 不新增 close-all emit（全局关闭入口唯一在 OpsMenuBar ✕ Close）。
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
  <div class="taskbar-wrap">
    <button
      type="button"
      class="taskbar-item"
      aria-label="服务器管理"
      title="服务器管理"
      @click="emit('open', 'servers')"
    >
      <span class="taskbar-tip">服务器管理</span>
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <rect x="5" y="7" width="38" height="34" rx="6" fill="url(#dg)"/>
        <rect x="11" y="14" width="26" height="8" rx="2" fill="#9aa3af"/>
        <rect x="11" y="26" width="26" height="8" rx="2" fill="#8a939f"/>
        <circle cx="15.5" cy="18" r="1.6" fill="#30d158"/>
        <circle cx="15.5" cy="30" r="1.6" fill="#ff453a"/>
        <defs>
          <linearGradient id="dg" x1="0" y1="0" x2="0" y2="1">
            <stop stop-color="#2b4a7c"/>
            <stop offset="1" stop-color="#1a3054"/>
          </linearGradient>
        </defs>
      </svg>
      <span v-if="wins.servers.open" class="taskbar-run-dot"></span>
    </button>
    <button
      type="button"
      class="taskbar-item"
      aria-label="日志管理"
      title="日志管理"
      @click="emit('open', 'logs')"
    >
      <span class="taskbar-tip">日志管理</span>
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M5 11a4 4 0 014-4h9l4 5h17a4 4 0 014 4v21a4 4 0 01-4 4H9a4 4 0 01-4-4z" fill="#1e6add"/>
        <path d="M5 16h38v21a4 4 0 01-4 4H9a4 4 0 01-4-4z" fill="#3d84e8"/>
        <path d="M9 20h30v17a3 3 0 01-3 3H12a3 3 0 01-3-3z" fill="#7db2f2"/>
      </svg>
      <span v-if="wins.logs.open" class="taskbar-run-dot"></span>
    </button>
    <button
      type="button"
      class="taskbar-item"
      aria-label="一键智能检测"
      title="一键智能检测"
      @click="emit('detect-all')"
    >
      <span class="taskbar-tip">一键智能检测</span>
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="20" cy="20" r="11" fill="none" stroke="#ffffff" stroke-width="4"/>
        <line x1="28" y1="28" x2="40" y2="40" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>
        <path d="M20 14v4l3 3" stroke="#ffffff" stroke-width="2.5" fill="none" stroke-linecap="round"/>
      </svg>
    </button>
  </div>
</template>