<script setup>
/**
 * 运维控制台 - 服务器管理窗口组件（访达图标视图 + 检索）
 *
 * 2026-08-05 从 `运维界面/app/src/components/ServerWindow.vue` 整段迁移。
 *
 * 2026-08-13 调整为 GNOME 风格：
 *   1) 标题栏 mac 红/绿交通灯 → 右侧 max + close 两按钮（原生 <button> + SVG）；
 *   2) 原生 button 自动支持 Enter/Space 键盘可达，无需手动 keydown 处理；
 *   3) 本轮不实现 minimize（涉及最小化栈与状态保留，单独 PR 落地）。
 *   close / max 事件契约不变（仍 emit 'close' / 'max'，父组件复用既有逻辑）。
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
 *   - close / max / front / drag  窗口控制（max/close 由原生 button 触发，事件契约不变）
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
      <span class="win-title">服务器管理</span>
      <div class="srv-toolbar">
        <div class="search-box" @mousedown.stop>
          <svg viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2.4" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><line x1="15.5" y1="15.5" x2="21" y2="21"/></svg>
          <input :value="searchKey" @input="emit('update:searchKey', $event.target.value)" placeholder="搜索服务器名称 / IP" />
        </div>
      </div>
      <!-- 2026-08-13 GNOME 风格：右侧两按钮 max + close（左→右），原生 button + SVG -->
      <div class="win-controls">
        <button type="button" class="win-control win-control--max"
                aria-label="最大化" title="最大化"
                @click.stop="emit('max')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="5" y="5" width="14" height="14" rx="1.5"/>
          </svg>
        </button>
        <button type="button" class="win-control win-control--close"
                aria-label="关闭" title="关闭"
                @click.stop="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <line x1="6" y1="6" x2="18" y2="18"/>
            <line x1="18" y1="6" x2="6" y2="18"/>
          </svg>
        </button>
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
