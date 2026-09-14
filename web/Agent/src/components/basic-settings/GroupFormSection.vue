<!--
  GroupFormSection.vue
  通用单组表单 section 组件(2026-09-14 新增,2026-09-14 渲染修复)
  fields: [{name, label, type, sensitive, placeholder, multiline, description, required}]
  视觉风格与 EmailSettingsManager / FeishuSettingsManager 同款
  (复用 .settings-section / .form-group / .form-input / .alert / .primary-btn / .switch 等 token,零 naive-ui 依赖)
-->
<template>
  <section class="group-card" data-testid="group-form-section">
    <header class="group-card-header">
      <div class="group-card-titles">
        <h3 class="group-card-title">
          {{ label }}
          <code class="group-key-chip" :title="`后端 group_key: ${groupKey}`">{{ groupKey }}</code>
        </h3>
        <p v-if="description" class="group-card-desc">{{ description }}</p>
        <p class="group-card-meta">
          配置项 <strong>{{ fields.length }}</strong> 个 · 敏感字段
          <strong>{{ sensitiveCount }}</strong> 个
        </p>
      </div>
      <button
        type="button"
        class="ghost-btn"
        :disabled="resetting || loading"
        data-testid="reset-btn"
        @click="handleReset"
      >
        重置默认
      </button>
    </header>

    <div v-if="loading" class="loading-hint" data-testid="loading-hint">加载中...</div>

    <div v-if="error" class="alert error" role="alert" data-testid="error-alert">{{ error }}</div>
    <div v-if="message" class="alert success" role="alert" data-testid="success-alert">{{ message }}</div>

    <div v-if="!loading" class="form-grid" data-testid="form-grid">
      <div
        v-for="field in fields"
        :key="field.name"
        class="form-group"
        :class="{ 'form-group-full': field.multiline || field.type === 'json' }"
        :data-testid="`form-group-${field.name}`"
      >
        <label class="form-label" :for="`field-${field.name}`">
          <span class="form-label-text">{{ field.label }}</span>
          <span class="field-meta">
            <code class="field-key-chip" :data-testid="`field-key-${field.name}`" :title="`后端字段名: ${field.name}`">{{ field.name }}</code>
            <span class="field-type-chip" :data-testid="`field-type-${field.name}`">{{ fieldTypeLabel(field) }}</span>
            <span v-if="field.required" class="required-mark" aria-label="必填">*</span>
            <span v-if="field.sensitive" class="sensitive-mark" aria-label="敏感字段" title="敏感字段(留空保持原值)">🔒</span>
          </span>
        </label>

        <!-- 敏感字段 -->
        <input
          v-if="field.sensitive"
          :id="`field-${field.name}`"
          type="password"
          class="form-input"
          :placeholder="field.placeholder || '留空保持不变'"
          :value="formData[field.name] || ''"
          :data-testid="`field-input-${field.name}`"
          @input="formData[field.name] = $event.target.value"
        />

        <!-- bool toggle -->
        <label
          v-else-if="field.type === 'bool'"
          class="switch"
          :data-testid="`field-switch-${field.name}`"
        >
          <input
            type="checkbox"
            :checked="!!formData[field.name]"
            @change="formData[field.name] = $event.target.checked"
          />
          <span class="slider"></span>
          <span class="switch-label">{{ formData[field.name] ? '开启' : '关闭' }}</span>
          <span class="current-value" :data-testid="`field-current-${field.name}`">
            当前值: <code>{{ formData[field.name] === undefined ? '∅' : (formData[field.name] ? 'true' : 'false') }}</code>
          </span>
        </label>

        <!-- int / float -->
        <input
          v-else-if="field.type === 'int' || field.type === 'float'"
          :id="`field-${field.name}`"
          type="number"
          class="form-input"
          :step="field.type === 'float' ? '0.01' : '1'"
          :placeholder="field.placeholder || ''"
          :value="formData[field.name] ?? ''"
          :data-testid="`field-input-${field.name}`"
          @input="onNumberInput(field, $event)"
        />

        <!-- json / multiline -->
        <textarea
          v-else-if="field.type === 'json' || field.multiline"
          :id="`field-${field.name}`"
          class="form-input"
          :rows="field.multiline ? 4 : 5"
          :placeholder="textareaPlaceholder(field)"
          :value="formData[field.name] ?? ''"
          :data-testid="`field-input-${field.name}`"
          @input="formData[field.name] = $event.target.value"
        ></textarea>

        <!-- 普通文本 -->
        <input
          v-else
          :id="`field-${field.name}`"
          type="text"
          class="form-input"
          :placeholder="field.placeholder || ''"
          :value="formData[field.name] ?? ''"
          :data-testid="`field-input-${field.name}`"
          @input="formData[field.name] = $event.target.value"
        />

        <p v-if="field.description" class="form-help">{{ field.description }}</p>
      </div>
    </div>

    <div class="group-actions">
      <button
        type="button"
        class="primary-btn"
        :disabled="saving || loading"
        data-testid="save-btn"
        @click="handleSave"
      >
        {{ saving ? '保存中...' : '保存' }}
      </button>
      <span v-if="updatedAt" class="updated-at" data-testid="updated-at">
        最后更新: {{ updatedAt }} by {{ updatedBy }}
      </span>
    </div>
  </section>
</template>

<script setup>
/**
 * GroupFormSection - 单组配置 section(2026-09-14 新增,渲染修复)
 *
 * Props:
 *   groupKey    {string}  registry 中的 group_key(对应后端 /api/admin/system-settings/{groupKey})
 *   label       {string}  卡片标题(显示在 .group-card-title)
 *   fields      {Array}   字段元数据列表 [{name, label, type, sensitive, placeholder, multiline, description, required}]
 *   description {string=} 卡片描述(可选,显示在标题下方)
 *
 * 字段 type:
 *   - 'str' (默认)        普通文本输入
 *   - 'int' / 'float'     数字输入
 *   - 'bool'              toggle 开关
 *   - 'json'              textarea,保存时尝试 JSON.parse
 *   - sensitive:true      密码输入框(留空 = 后端保持原值)
 *
 * 交互契约:
 *   - 加载成功后 formData 用 config 填充
 *   - 保存时:sensitive 字段空串/null 不传 payload(后端保持原值)
 *   - json 字段保存时尝试 JSON.parse,失败时 alert 警告并落原值
 *   - 重置:confirm 弹原生确认 → resetSystemSettingsGroup → 表单恢复默认值
 *   - 错误反馈:alert.error 显示后端 message
 *   - 成功反馈:alert.success「保存成功,需重启服务生效」+ 更新底部「最后更新」时间
 */
import { ref, reactive, watch, onMounted, computed } from 'vue';
import {
  fetchSystemSettingsGroup,
  updateSystemSettingsGroup,
  resetSystemSettingsGroup,
} from '../../utils/api.js';

const props = defineProps({
  groupKey: { type: String, required: true },
  label: { type: String, required: true },
  fields: { type: Array, required: true },
  description: { type: String, default: '' },
});

const formData = reactive({});
const loading = ref(false);
const saving = ref(false);
const resetting = ref(false);
const message = ref('');
const error = ref('');
const updatedAt = ref(null);
const updatedBy = ref(null);

// 计算属性:敏感字段计数 + 字段类型标签
const sensitiveCount = computed(() => props.fields.filter(f => f.sensitive).length);

function fieldTypeLabel(field) {
  if (field.sensitive) return 'secret';
  switch (field.type) {
    case 'bool': return 'bool';
    case 'int': return 'int';
    case 'float': return 'float';
    case 'json': return 'json';
    case 'str':
    default:
      return field.multiline ? 'text' : 'str';
  }
}

function clearAlerts() {
  message.value = '';
  error.value = '';
}

async function load() {
  loading.value = true;
  clearAlerts();
  try {
    const data = await fetchSystemSettingsGroup(props.groupKey);
    // 兼容:config 可能是 undefined 或 string(后端 serialize 偶尔返字符串)
    const cfg = typeof data.config === 'string' ? safeJsonParse(data.config, {}) : (data.config || {});
    // 清空 + 填充
    for (const k of Object.keys(formData)) delete formData[k];
    Object.assign(formData, cfg);
    updatedAt.value = data.updated_at;
    updatedBy.value = data.updated_by;
  } catch (e) {
    error.value = e.message || '加载配置组失败';
  } finally {
    loading.value = false;
  }
}

function safeJsonParse(text, fallback) {
  try { return JSON.parse(text); } catch { return fallback; }
}

const JSON_PLACEHOLDER = 'JSON 格式,如 ["a", "b"]';

function textareaPlaceholder(field) {
  if (field.placeholder) return field.placeholder;
  if (field.type === 'json') return JSON_PLACEHOLDER;
  return '';
}

function onNumberInput(field, event) {
  const raw = event.target.value;
  if (raw === '' || raw == null) {
    formData[field.name] = null;
    return;
  }
  if (field.type === 'int') {
    const n = parseInt(raw, 10);
    formData[field.name] = Number.isNaN(n) ? null : n;
  } else {
    const n = parseFloat(raw);
    formData[field.name] = Number.isNaN(n) ? null : n;
  }
}

async function handleSave() {
  saving.value = true;
  clearAlerts();
  try {
    const payload = {};
    for (const field of props.fields) {
      const v = formData[field.name];
      // 敏感字段空串/null → 不传(后端保持原值)
      if (field.sensitive && (v === '' || v == null)) continue;
      // json 字段尝试解析
      if (field.type === 'json' && typeof v === 'string' && v.trim() !== '') {
        try {
          payload[field.name] = JSON.parse(v);
        } catch {
          error.value = `字段 ${field.label} 不是合法 JSON,已按原值提交`;
          payload[field.name] = v;
        }
      } else {
        payload[field.name] = v;
      }
    }
    const data = await updateSystemSettingsGroup(props.groupKey, payload);
    const cfg = typeof data.config === 'string' ? safeJsonParse(data.config, {}) : (data.config || {});
    for (const k of Object.keys(formData)) delete formData[k];
    Object.assign(formData, cfg);
    updatedAt.value = data.updated_at;
    updatedBy.value = data.updated_by;
    message.value = '保存成功,需重启服务生效';
  } catch (e) {
    error.value = e.message || '保存失败';
  } finally {
    saving.value = false;
  }
}

async function handleReset() {
  if (!window.confirm(`确认重置「${props.label}」为默认值?`)) return;
  resetting.value = true;
  clearAlerts();
  try {
    const data = await resetSystemSettingsGroup(props.groupKey);
    const cfg = typeof data.config === 'string' ? safeJsonParse(data.config, {}) : (data.config || {});
    for (const k of Object.keys(formData)) delete formData[k];
    Object.assign(formData, cfg);
    message.value = '已重置为默认值,需重启服务生效';
  } catch (e) {
    error.value = e.message || '重置失败';
  } finally {
    resetting.value = false;
  }
}

onMounted(load);
watch(() => props.groupKey, load);
</script>

<style scoped>
/* 2026-09-14 渲染修复:复用 .group-card / .form-grid / .alert 等 token,与 EmailSettingsManager 风格一致
   不再依赖 naive-ui。*/
.group-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 14px;
}

.group-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f3f4f6;
}

.group-card-titles { flex: 1; min-width: 0; }

.group-card-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 4px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.group-key-chip {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: #2563eb;
  background: #eff6ff;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 400;
}

.group-card-desc {
  font-size: 12px;
  color: #6b7280;
  margin: 0;
  line-height: 1.5;
}

.group-card-meta {
  font-size: 12px;
  color: #9ca3af;
  margin: 6px 0 0;
  line-height: 1.4;
}

.group-card-meta strong {
  color: #374151;
  font-weight: 600;
}

.ghost-btn {
  background: transparent;
  border: 1px solid #d1d5db;
  color: #4b5563;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}

.ghost-btn:hover:not(:disabled) {
  border-color: #9ca3af;
  color: #1f2937;
}

.ghost-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.loading-hint {
  text-align: center;
  padding: 20px;
  color: #6b7280;
  font-size: 13px;
}

.alert {
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.5;
}

.alert.error {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.alert.success {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.alert.warning {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
}

.form-group { display: flex; flex-direction: column; gap: 6px; min-width: 0; }

.form-group-full { grid-column: 1 / -1; }

.form-label {
  font-size: 13px;
  color: #374151;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.form-label-text {
  font-weight: 500;
  color: #111827;
}

.field-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-left: auto;
}

.field-key-chip {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: #4b5563;
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 400;
  white-space: nowrap;
}

.field-type-chip {
  font-family: 'Courier New', monospace;
  font-size: 10px;
  color: #6b7280;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 400;
  text-transform: lowercase;
  white-space: nowrap;
}

.required-mark { color: #dc2626; font-weight: 700; }

.sensitive-mark {
  font-size: 12px;
  color: #d97706;
  cursor: help;
}

.current-value {
  font-size: 12px;
  color: #6b7280;
  margin-left: 6px;
}

.current-value code {
  font-family: 'Courier New', monospace;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  padding: 1px 6px;
  border-radius: 3px;
  color: #374151;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  background: #ffffff;
  color: #111827;
  box-sizing: border-box;
  font-family: inherit;
  line-height: 1.5;
}

textarea.form-input { resize: vertical; min-height: 80px; font-family: 'Courier New', monospace; }

.form-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.form-input::placeholder { color: #9ca3af; }

.form-help {
  font-size: 12px;
  color: #6b7280;
  margin: 0;
  line-height: 1.4;
}

/* toggle switch (2026-09-14 渲染修复:纯 CSS,无 naive-ui) */
.switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
  height: 24px;
}

.switch input { opacity: 0; width: 0; height: 0; }

.slider {
  position: relative;
  width: 36px;
  height: 20px;
  background: #d1d5db;
  border-radius: 999px;
  transition: background 160ms ease;
}

.slider::before {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: #ffffff;
  border-radius: 50%;
  transition: transform 160ms ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}

.switch input:checked + .slider { background: #2563eb; }
.switch input:checked + .slider::before { transform: translateX(16px); }

.switch-label { font-size: 13px; color: #4b5563; min-width: 32px; }

.group-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}

.primary-btn {
  background: #2563eb;
  color: #ffffff;
  border: 0;
  padding: 8px 18px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.primary-btn:hover:not(:disabled) { background: #1d4ed8; }

.primary-btn:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

.updated-at {
  font-size: 12px;
  color: #9ca3af;
}

@media (max-width: 720px) {
  .form-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>