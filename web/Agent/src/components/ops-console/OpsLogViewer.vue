<script setup>
/**
 * 运维控制台 - 日志内容查看窗口组件（终端风格）
 *
 * 2026-08-05 从 `运维界面/app/src/components/LogViewer.vue` 整段迁移。
 *
 * 2026-08-13 调整为 GNOME 风格：
 *   1) 标题栏 mac 红/绿交通灯 → 右侧 max + close 两按钮（原生 <button> + SVG）；
 *   2) 原生 button 自动支持 Enter/Space 键盘可达，无需手动 keydown 处理；
 *   3) 本轮不实现 minimize。close / max 事件契约不变。
 *
 * Props:
 *   - win: { x, y, z, max }              窗口位置/层级/最大化状态
 *   - file: { name, content: Array<{t, lv, msg}> }  日志文件（name + 已解析的日志行）
 *
 * Emits:
 *   - close / max / front / drag  窗口控制（max/close 由原生 button 触发，事件契约不变）
 */
defineProps({
  win: { type: Object, required: true },
  file: { type: Object, required: true },   // { name, content: [{t, lv, msg}] }
})

const emit = defineEmits(['close', 'max', 'front', 'drag'])
</script>

<template>
  <div class="win win-logview" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">{{ file.name }}</span>
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
    <div class="logview-body">
      <div v-for="(line, i) in file.content" :key="i" class="ll">
        <span class="t">[{{ line.t }}]</span> <span :class="line.lv">{{ line.lv }}</span> {{ line.msg }}
      </div>
    </div>
  </div>
</template>
