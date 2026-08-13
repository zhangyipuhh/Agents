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
 * Props:
 *   - time: string  当前时间字符串（由父组件 OpsConsoleApp 1s 定时器驱动）
 *
 * Emits:
 *   - exit  点击 ✕ Close 原生按钮，关闭整个运维控制台
 */
defineProps({
  time: { type: String, default: '' },
})

const emit = defineEmits(['exit'])
</script>

<template>
  <div class="menubar">
    <span class="mi">
      <!-- 运维监控图标：监视器 + 心跳脉冲 -->
      <svg width="16" height="16" viewBox="0 0 48 48" style="vertical-align:-3px">
        <rect x="4" y="7" width="40" height="28" rx="4" fill="#003a8c"/>
        <rect x="8" y="11" width="32" height="20" rx="2" fill="#eaf2fd"/>
        <path d="M11 21h6l3-6 4 12 3-6h10" stroke="#1e6add" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="20" y="37" width="8" height="4" fill="#003a8c"/>
        <rect x="14" y="41" width="20" height="3" rx="1.5" fill="#003a8c"/>
      </svg>
    </span>
    <span class="mi menubar-app">智能运维中心</span>
    <!-- 2026-08-13：GNOME 风格全局菜单占位（中文），纯静态展示无点击行为 -->
    <span class="mi menubar-menu-item">文件</span>
    <span class="mi menubar-menu-item">编辑</span>
    <span class="mi menubar-menu-item">视图</span>
    <span class="mi menubar-menu-item">帮助</span>
    <div class="spacer"></div>
    <span class="mi">{{ time }}</span>
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
  </div>
</template>