<script setup>
/**
 * 运维控制台 - 日志文件夹管理窗口组件（访达风格：左侧文件夹 + 右侧文件列表）
 *
 * 2026-08-05 从 `运维界面/app/src/components/LogManager.vue` 整段迁移。
 *
 * 2026-08-13 调整为 GNOME 风格：
 *   1) 标题栏 mac 红/绿交通灯 → 右侧 max + close 两按钮（原生 <button> + SVG）；
 *   2) 原生 button 自动支持 Enter/Space 键盘可达，无需手动 keydown 处理；
 *   3) 本轮不实现 minimize。close / max 事件契约不变。
 *
 * Props:
 *   - win: { x, y, z, max }    窗口位置/层级/最大化状态
 *   - folders: Array<LogFolder>  全部日志文件夹
 *   - activeFolder: number       当前选中文件夹下标（双向绑定）
 *   - selectedLog: string        当前选中的日志文件名（高亮）
 *
 * Emits:
 *   - update:activeFolder  v-model 切换文件夹
 *   - open-log             点击日志文件，向父组件派发
 *   - close / max / front / drag  窗口控制（max/close 由原生 button 触发，事件契约不变）
 */
import { computed } from 'vue'

const props = defineProps({
  win: { type: Object, required: true },
  folders: { type: Array, required: true },
  activeFolder: { type: Number, default: 0 },
  selectedLog: { type: String, default: '' },
})

const emit = defineEmits(['update:activeFolder', 'open-log', 'close', 'max', 'front', 'drag'])

/** 当前文件夹下的文件列表（防御性读取） */
const currentFiles = computed(() =>
  props.folders[props.activeFolder] ? props.folders[props.activeFolder].files : []
)
</script>

<template>
  <div class="win win-logs" :class="{ maximized: win.max }"
       :style="{ left: win.x + 'px', top: win.y + 'px', zIndex: win.z }"
       @mousedown="emit('front')">
    <div class="win-bar" @mousedown="emit('drag', $event)">
      <span class="win-title">日志管理</span>
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
    <div class="logs-main">
      <div class="logs-side">
        <div class="side-title">日志文件夹</div>
        <div v-for="(folder, fi) in folders" :key="folder.name" class="side-item"
             :class="{ active: fi === activeFolder }" @click="emit('update:activeFolder', fi)">
          <svg viewBox="0 0 48 48"><path d="M4 12a4 4 0 014-4h10l4 5h18a4 4 0 014 4v21a4 4 0 01-4 4H8a4 4 0 01-4-4z" fill="#3d84e8"/><path d="M4 17h40v21a4 4 0 01-4 4H8a4 4 0 01-4-4z" fill="#7db2f2"/></svg>
          {{ folder.name }}
          <span class="cnt">{{ folder.files.length }}</span>
        </div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;min-width:0">
        <div class="list-head"><span class="fn">名称</span><span class="fs">大小</span><span class="ft">修改时间</span></div>
        <div class="logs-list">
          <div v-for="f in currentFiles" :key="f.name" class="log-row"
               :class="{ selected: selectedLog === f.name }" @click="emit('open-log', f)">
            <svg viewBox="0 0 48 48"><path d="M12 4h16l10 10v28a2 2 0 01-2 2H12a2 2 0 01-2-2V6a2 2 0 012-2z" fill="#f5f8fd" stroke="#b9cbe8"/><path d="M28 4v10h10" fill="#dbe7f8"/><rect x="15" y="22" width="18" height="2.5" rx="1.2" fill="#8aa6cf"/><rect x="15" y="28" width="18" height="2.5" rx="1.2" fill="#8aa6cf"/><rect x="15" y="34" width="12" height="2.5" rx="1.2" fill="#8aa6cf"/></svg>
            <span class="fn">{{ f.name }}</span>
            <span class="fs">{{ f.size }}</span>
            <span class="ft">{{ f.time }}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="statusbar">{{ currentFiles.length }} 个日志文件，单击可查看内容</div>
  </div>
</template>
