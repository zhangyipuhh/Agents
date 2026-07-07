<!--
  SectionEditor - 字段表编辑器子组件
  --------------------------------------------------
  用于 AgentManager「配置字段」Tab 下的三组字段表格：
  AgentConfig 字段 / State 扩展字段 / Context 扩展字段。

  从 AgentManager.vue 拆出独立 .vue 文件以解决 scoped CSS 问题：
  原内联 defineComponent + h() render function 不会自动给元素加 data-v-xxx
  scoped 属性，导致样式失效；模板写法由 Vue 编译器自动接管 scoped。

  Date: 2026-06-26
  Author: AI Assistant
-->
<template>
  <section class="section-editor">
    <header class="section-header">
      <div class="section-title-wrap">
        <h4 class="section-title">
          <span class="section-accent-bar"></span>
          {{ title }}
        </h4>
        <p v-if="subtitle" class="section-subtitle">{{ subtitle }}</p>
      </div>
      <div class="section-header-actions">
        <span v-if="fields.length > 0" class="section-count">
          共 {{ fields.length }} 个字段
        </span>
        <button class="btn-add-field" @click="emit('add')">+ 添加字段</button>
      </div>
    </header>

    <table class="fields-table">
      <thead>
        <tr>
          <th>字段名</th>
          <th>类型</th>
          <th>默认值</th>
          <th>来源</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="fields.length === 0">
          <td colspan="5" class="empty-row">
            <div class="empty-row-content">
              <div class="empty-row-icon">∅</div>
              <div class="empty-row-text">暂无字段</div>
              <div class="empty-row-hint">点击上方「添加字段」按钮创建第一个字段</div>
            </div>
          </td>
        </tr>
        <tr
          v-for="f in fields"
          v-else
          :key="f.name"
          :class="{ 'pending-row': f.isPending }"
        >
          <td>
            <code class="field-name-code">{{ f.name }}</code>
            <span v-if="f.isNew" class="badge-new">新增</span>
          </td>
          <td>{{ f.type }}</td>
          <td>{{ formatValue(f.default) }}</td>
          <td>
            <span
              :class="f.isNew ? 'badge-custom' : (isFromTemplate(f.name) ? 'badge-agent-config' : 'badge-custom')"
            >
              {{ f.isNew ? '自定义' : (isFromTemplate(f.name) ? sourceLabel : '自定义') }}
            </span>
          </td>
          <td>
            <button class="btn-danger btn-sm" @click="emit('remove', section, f.name)">
              删除
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
/**
 * SectionEditor 子组件
 *
 * @prop {string} title      - 卡片标题，如 "AgentConfig 字段"
 * @prop {string} subtitle   - 副标题（可选）
 * @prop {Array}  fields     - 字段列表 [{name, type, default, isNew, isPending}]
 * @prop {Array}  templates  - 该 section 的字段模板列表（用于判断「来源」标签）
 * @prop {string} section    - 所属 section key: 'root' / 'state_fields' / 'context_fields'
 * @prop {string} sourceLabel - 来源标签文本，如 'AgentConfig'
 * @emits add - 点击「添加字段」按钮
 * @emits remove(section, fieldName) - 点击某行的「删除」按钮
 */
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  fields: { type: Array, required: true },
  templates: { type: Array, default: () => [] },
  section: { type: String, required: true },
  sourceLabel: { type: String, default: 'AgentConfig' },
})

const emit = defineEmits(['add', 'remove'])

/**
 * 格式化字段默认值显示
 * @param {*} v 字段默认值
 * @returns {string} 渲染字符串
 */
function formatValue(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/**
 * 判断某字段是否来自模板（用于显示「来源」badge）
 * @param {string} fieldName 字段名
 * @returns {boolean}
 */
function isFromTemplate(fieldName) {
  return props.templates.some((t) => t.field_name === fieldName)
}
</script>

<style scoped>
/* 卡片外壳：保留原 section-editor 风格（白底 + 细边 + 阴影 + hover 抬起） */
.section-editor {
  position: relative;
  overflow: hidden;
  margin-bottom: 24px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: 20px 20px 20px 24px; /* 左侧多 4px 留给 accent bar */
  transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}
.section-editor:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
  border-color: var(--color-accent);
}

/* 左侧 4px 装饰条 */
.section-accent-bar {
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  border-radius: var(--radius-md) 0 0 var(--radius-md);
  background-color: var(--color-accent);
  transition: width 0.2s ease;
  flex-shrink: 0;
}
.section-editor:hover .section-accent-bar {
  width: 6px;
}

/* 卡片头：grid 布局强制「标题（含副标题）在左 | 计数+按钮在右」 */
.section-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}
.section-title-wrap {
  min-width: 0;
}
.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 4px; /* 避开左侧 4px accent bar */
}
.section-subtitle {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.5;
  word-break: break-word;
}

/* 卡片头右侧操作区：对齐用户管理 admin-header-actions */
.section-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  white-space: nowrap;
}
.section-count {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* 添加字段按钮：与用户管理 admin-count + 新增用户 同款样式 */
.btn-add-field {
  font-family: inherit;
  font-size: 12px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
  background-color: var(--color-accent);
  color: var(--color-text-inverse);
  font-weight: 500;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.btn-add-field:hover {
  background-color: var(--color-accent-hover);
}

/* 字段表：扁平风格，对齐用户管理 admin-table */
.fields-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background-color: transparent;
}
.fields-table th,
.fields-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}
.fields-table th {
  background-color: var(--color-bg-secondary);
  font-weight: 600;
  color: var(--color-text-primary);
  font-size: 12px;
}
.fields-table tbody tr {
  transition: background-color 0.15s ease;
}
.fields-table tbody tr:nth-child(even) {
  background-color: var(--color-bg-secondary);
}
.fields-table tbody tr:hover {
  background-color: var(--color-bg-hover);
}
.fields-table td code {
  font-family: monospace;
  background-color: var(--color-bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
.fields-table td code.field-name-code {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
  font-weight: 500;
}

/* 未保存变更行高亮 */
.pending-row {
  background-color: #fff7e6;
  border-left: 3px solid #f59e0b;
}

/* 空状态行 */
.empty-row {
  text-align: center;
  color: var(--color-text-muted);
  padding: 40px 24px;
}
.empty-row-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.empty-row-icon {
  font-size: 36px;
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-accent-light);
  color: var(--color-accent);
  border-radius: 50%;
  line-height: 1;
  margin-bottom: 4px;
}
.empty-row-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
}
.empty-row-hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 来源 badge */
.badge-new {
  background-color: #FEF3C7;
  color: #B45309;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  margin-left: 6px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
}
.badge-agent-config,
.badge-custom {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
}
.badge-agent-config {
  background-color: var(--color-accent-light);
  color: var(--color-accent);
}
.badge-custom {
  background-color: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}
</style>
