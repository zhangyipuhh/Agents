<script setup>
/**
 * 运维控制台 - 日志内容查看窗口组件（终端风格）
 *
 * 2026-08-05 从 `运维界面/app/src/components/LogViewer.vue` 整段迁移。
 *
 * Props:
 *   - win: { x, y, z, max }              窗口位置/层级/最大化状态
 *   - file: { name, content: Array<{t, lv, msg}> }  日志文件（name + 已解析的日志行）
 *
 * Emits:
 *   - close / max / front / drag  窗口控制
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
      <div class="traffic">
        <span class="r" @click.stop="emit('close')"></span><span class="g" @click.stop="emit('max')"></span>
      </div>
      <span class="win-title">{{ file.name }}</span>
    </div>
    <div class="logview-body">
      <div v-for="(line, i) in file.content" :key="i" class="ll">
        <span class="t">[{{ line.t }}]</span> <span :class="line.lv">{{ line.lv }}</span> {{ line.msg }}
      </div>
    </div>
  </div>
</template>
