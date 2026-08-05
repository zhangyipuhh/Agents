<script setup>
/**
 * 运维控制台 - 顶部菜单栏组件
 *
 * 2026-08-05 从 `运维界面/app/src/components/MenuBar.vue` 整段迁移。
 * 展示运维监控图标（监视器 + 心跳脉冲 SVG）+ 标题「智能运维中心」+ 当前时间。
 *
 * Props:
 *   - time: string  当前时间字符串（由父组件 OpsConsoleApp 1s 定时器驱动）
 */
defineProps({
  time: { type: String, default: '' },
})
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
    <span class="mi bold">智能运维中心</span>
    <div class="spacer"></div>
    <span class="mi">{{ time }}</span>
  </div>
</template>
