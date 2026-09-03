<!--
  帮助页顶部品牌栏
  - 仿 LangChain 中文文档站布局
  - 左侧：品牌 Logo + 「帮助中心」标题
  - 右侧：主题切换 + 语言切换占位按钮（暂未实现）
  - 通过 emit('close') 让父组件支持关闭按钮回调
-->
<template>
  <header class="help-topbar">
    <div class="help-topbar-brand">
      <span class="help-logo" aria-hidden="true">📘</span>
      <span class="help-brand-text">帮助中心</span>
    </div>
    <nav class="help-topbar-nav" aria-label="主导航">
      <span class="help-topbar-tab help-topbar-tab--active">帮助</span>
    </nav>
    <div class="help-topbar-right">
      <button
        type="button"
        class="help-topbar-btn"
        title="主题切换（暂未开放）"
        aria-label="主题切换"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
          <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/>
        </svg>
      </button>
      <button
        type="button"
        class="help-topbar-btn"
        title="语言切换（暂未开放）"
        aria-label="语言切换"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.082 6.082 0 011.912-2.658C6.272 5.12 6.317 5 6.42 5c.07 0 .13.046.181.108.165.225.51.875.694 1.567-.247.118-.487.255-.717.42-.196-.234-.476-.59-.79-.834-.107-.082-.221-.157-.336-.228zm5.668 0c.13-.118.255-.246.358-.39.21-.297.395-.625.55-.969.297.133.585.314.835.572.244.249.42.547.546.857.13.319.21.661.232 1.014.013.158.014.316-.005.474a5.64 5.64 0 00-.526-.32c-.36-.193-.757-.336-1.184-.418-.142-.029-.288-.05-.435-.06-.252-.014-.5-.024-.749-.024-.385 0-.713.052-1.011.135a4.354 4.354 0 00-.523.193l-.084.5zM10 7.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm-5.5 3a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm11 0a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" clip-rule="evenodd"/>
        </svg>
      </button>
      <button
        v-if="showClose"
        type="button"
        class="help-topbar-btn help-topbar-close"
        title="关闭帮助页面"
        aria-label="关闭"
        @click="handleClose"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
        </svg>
      </button>
    </div>
  </header>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

defineProps({
  // 是否显示关闭按钮（被脚本打开的新 Tab 显示）
  showClose: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

/**
 * 处理关闭按钮点击
 * @returns {void}
 */
function handleClose() {
  emit('close')
}
</script>