<script setup>
/**
 * 运维控制台 - 顶部菜单栏组件（GNOME / Ubuntu top bar 风格）
 *
 * 2026-08-05 从 `运维界面/app/src/components/MenuBar.vue` 整段迁移。
 * 展示运维监控图标（监视器 + 心跳脉冲 SVG）+ 标题「智能运维中心」+ 当前时间。
 *
 * 2026-08-09：右侧加 mac 风格三色关闭点，仅红色 active。
 * 关闭整个运维控制台（emit('exit')）。黄/绿保留占位以备未来最小化/最大化。
 *
 * 2026-08-13 调整为 GNOME 风格：
 *   1) 移除 mac 红/黄/绿交通灯，右侧改为原生 <button> ✕ Close（aria-label
 *      "关闭运维控制台"），事件契约 emit('exit') 不变；
 *   2) 原生 button 自动支持 Enter/Space 键盘可达，无需手动 @keydown 处理；
 *   3) 应用名右侧新增中文全局菜单占位（文件 / 编辑 / 视图 / 帮助），hover 蓝底；
 *   4) 取消「Activities」按钮（政务系统场景突兀 + 无操作易被当 bug）；
 *   5) 本轮不实现 minimize（minimize 涉及最小化栈与状态保留，单独 PR 落地）。
 *
 * 2026-08-14 菜单栏重构（用户需求）：
 *   1) 移除 文件 / 编辑 / 视图 / 帮助 中文全局菜单占位；
 *   2) 新增「服务器管理」「日志管理」两个原生 <button> 入口，
 *      emit('open', 'servers' | 'logs')，由 OpsConsoleApp 透传给 openWin；
 *   3) 两按钮在菜单栏中部水平居中（flex: 1 + justify-content: center），
 *      左侧 = 应用图标 + 应用名，右侧 = 时间 + ✕ Close；
 *   4) 「一键智能检测」入口彻底移除（OpsConsoleApp 的 detectAll / detailRef /
 *      nextTick 链路一并删除，避免死代码）。
 *
 * Props:
 *   - time: string  当前时间字符串（由父组件 OpsConsoleApp 1s 定时器驱动）
 *
 * Emits:
 *   - open(name)  点击「服务器管理 / 日志管理」按钮，name='servers'|'logs'
 *   - exit        点击 ✕ Close 原生按钮，关闭整个运维控制台
 */
defineProps({
  time: { type: String, default: '' },
})

const emit = defineEmits(['open', 'exit'])
</script>

<template>
  <div class="menubar">
    <span class="mi menubar-left">
      <!-- 运维监控图标：监视器 + 心跳脉冲 -->
      <svg width="16" height="16" viewBox="0 0 48 48" style="vertical-align:-3px">
        <rect x="4" y="7" width="40" height="28" rx="4" fill="#003a8c"/>
        <rect x="8" y="11" width="32" height="20" rx="2" fill="#eaf2fd"/>
        <path d="M11 21h6l3-6 4 12 3-6h10" stroke="#1e6add" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="20" y="37" width="8" height="4" fill="#003a8c"/>
        <rect x="14" y="41" width="20" height="3" rx="1.5" fill="#003a8c"/>
      </svg>
      <span class="menubar-app">智能运维中心</span>
    </span>

    <!-- 2026-08-14：中部水平居中两按钮（服务器管理 / 日志管理），由 menubar-center
         自身 flex:1 + justify-content:center 撑开，无需 spacer 干预。 -->
    <span class="menubar-center">
      <button
        type="button"
        class="menubar-nav-btn"
        aria-label="服务器管理"
        title="服务器管理"
        @click="emit('open', 'servers')"
      >
        <svg viewBox="0 0 48 48" aria-hidden="true">
          <rect x="5" y="7" width="38" height="34" rx="6" fill="url(#mb-dg)"/>
          <rect x="11" y="14" width="26" height="8" rx="2" fill="#9aa3af"/>
          <rect x="11" y="26" width="26" height="8" rx="2" fill="#8a939f"/>
          <circle cx="15.5" cy="18" r="1.6" fill="#30d158"/>
          <circle cx="15.5" cy="30" r="1.6" fill="#ff453a"/>
          <defs>
            <linearGradient id="mb-dg" x1="0" y1="0" x2="0" y2="1">
              <stop stop-color="#2b4a7c"/>
              <stop offset="1" stop-color="#1a3054"/>
            </linearGradient>
          </defs>
        </svg>
        <span>服务器管理</span>
      </button>
      <button
        type="button"
        class="menubar-nav-btn"
        aria-label="日志管理"
        title="日志管理"
        @click="emit('open', 'logs')"
      >
        <svg viewBox="0 0 48 48" aria-hidden="true">
          <path d="M5 11a4 4 0 014-4h9l4 5h17a4 4 0 014 4v21a4 4 0 01-4 4H9a4 4 0 01-4-4z" fill="#1e6add"/>
          <path d="M5 16h38v21a4 4 0 01-4 4H9a4 4 0 01-4-4z" fill="#3d84e8"/>
          <path d="M9 20h30v17a3 3 0 01-3 3H12a3 3 0 01-3-3z" fill="#7db2f2"/>
        </svg>
        <span>日志管理</span>
      </button>
    </span>

    <span class="menubar-right">
      <span class="mi menubar-time">{{ time }}</span>
      <!-- 2026-08-13：✕ Close 原生 button（替代 mac 红点），全局唯一关闭入口。
           原生 button 自动支持 Enter/Space 键盘可达（无需手动 keydown 处理）。
           aria-label + title 双标注语义。 -->
      <button
        type="button"
        class="close-all-btn"
        aria-label="关闭运维控制台"
        title="关闭运维控制台"
        @click.stop="emit('exit')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <line x1="6" y1="6" x2="18" y2="18"/>
          <line x1="18" y1="6" x2="6" y2="18"/>
        </svg>
        <span>关闭</span>
      </button>
    </span>
  </div>
</template>
