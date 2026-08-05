<script setup>
/**
 * 运维控制台 - 服务器管理窗口组件（访达图标视图 + 检索）
 *
 * 2026-08-05 从 `运维界面/app/src/components/ServerWindow.vue` 整段迁移。
 *
 * Props:
 *   - win: { x, y, z, max }    窗口位置/层级/最大化状态
 *   - servers: Array<ServerItem>  已过滤的服务器列表
 *   - searchKey: string         搜索关键词（双向绑定）
 *   - selectedId: number|null   当前选中的服务器 ID（用于高亮）
 *
 * Emits:
 *   - update:searchKey  v-model 搜索关键词
 *   - open-detail       点击服务器图标，打开详情窗口
 *   - close / max / front / drag  窗口控制
 */
import { computed } from 'vue'
import OpsServerIcon from './OpsServerIcon.vue'

const props = defineProps({
  win: { type: Object, required: true },
  servers: { type: Array, required: true },
  searchKey: { type: String, default: '' },
  selectedId: { type: Number, default: null },
})

const emit = defineEmits(['update:searchKey', 'open-detail', 'close', 'max', 'front', 'drag'])

/** 异常服务器数量（驱动 statusbar 显示） */
const errCount = computed(() => props.servers.filter(s => s.status === 'err').length)
</script>

<template>
  <div class="win win-servers" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <div class="traffic">
        <span class="r" @click.stop="emit('close')"></span><span class="g" @click.stop="emit('max')"></span>
      </div>
      <span class="win-title">服务器管理</span>
      <div class="srv-toolbar">
        <div class="search-box" @mousedown.stop>
          <svg viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2.4" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><line x1="15.5" y1="15.5" x2="21" y2="21"/></svg>
          <input :value="searchKey" @input="emit('update:searchKey', $event.target.value)" placeholder="搜索服务器名称 / IP" />
        </div>
      </div>
    </div>
    <div class="srv-grid">
      <div v-for="srv in servers" :key="srv.id" class="srv-item"
           :class="{ selected: selectedId === srv.id }"
           @click="emit('open-detail', srv)">
        <div class="icon-wrap">
          <OpsServerIcon :status="srv.status" :size="46" />
        </div>
        <span class="nm">{{ srv.name }}</span>
      </div>
      <div v-if="!servers.length" class="no-result">未找到与「{{ searchKey }}」匹配的服务器</div>
    </div>
    <div class="statusbar">{{ servers.length }} 台服务器，{{ errCount }} 台异常</div>
  </div>
</template>
