<script setup>
/**
 * InspectionScriptEditorPanel - 巡检脚本库右侧编辑面板（2026-08-04 新增）
 *
 * 接收 `scriptId` prop；scriptId 为 null 时显示「请选择左侧节点查看详情」。
 * 非空时调 GET /api/admin/inspection-scripts/{id} 拉详情，渲染可编辑表单
 * （display_name / platform / version / inspection_parser / inspection_script
 *  / inspection_fields 字段规则表）。点「保存」调 PUT，失败时显示脱敏提示。
 *
 * 保存成功后 emit 'saved'，父组件用于更新列表缓存或显示成功提示。
 */
import { computed, ref, watch } from 'vue'
import {
  fetchInspectionScriptDetail,
  updateInspectionScript,
} from '../utils/api.js'

const props = defineProps({
  scriptId: { type: [Number, null], default: null },
})
const emit = defineEmits(['saved'])

const detail = ref(null)
const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const form = ref({
  display_name: '',
  platform: 'linux',
  version: '',
  inspection_parser: 'json',
  inspection_script: '',
  inspection_fields: [],
})

const platformOptions = ['linux', 'windows']
const parserOptions = ['json', 'kv', 'csv', 'raw']
const directionOptions = ['high', 'low', 'ignore']

const isFormValid = computed(() => {
  return Boolean(form.value.display_name && form.value.display_name.trim())
})

watch(
  () => props.scriptId,
  async (newId) => {
    errorMessage.value = ''
    successMessage.value = ''
    detail.value = null
    if (newId == null) return
    isLoading.value = true
    try {
      const d = await fetchInspectionScriptDetail(newId)
      detail.value = d
      form.value = {
        display_name: d.display_name || '',
        platform: d.platform || 'linux',
        version: d.version || '',
        inspection_parser: d.inspection_parser || 'json',
        inspection_script: d.inspection_script || '',
        inspection_fields: Array.isArray(d.inspection_fields)
          ? d.inspection_fields.map((f) => ({ ...f }))
          : [],
      }
    } catch (err) {
      errorMessage.value = err?.message || '加载脚本详情失败'
    } finally {
      isLoading.value = false
    }
  },
  { immediate: true }
)

function addField() {
  form.value.inspection_fields.push({
    key: '',
    name_zh: '',
    unit: '',
    direction: 'high',
    warn: null,
    crit: null,
  })
}
function removeField(idx) {
  form.value.inspection_fields.splice(idx, 1)
}

async function onSave() {
  if (!isFormValid.value) {
    errorMessage.value = '展示名称不能为空'
    return
  }
  isSaving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const payload = {
      display_name: form.value.display_name.trim(),
      platform: form.value.platform,
      version: form.value.version || '',
      inspection_parser: form.value.inspection_parser,
      inspection_script: form.value.inspection_script || null,
      inspection_fields: form.value.inspection_fields.map((f) => ({
        key: (f.key || '').trim(),
        name_zh: (f.name_zh || '').trim(),
        unit: f.unit || '',
        direction: f.direction || 'high',
        warn: f.warn == null || f.warn === '' ? null : Number(f.warn),
        crit: f.crit == null || f.crit === '' ? null : Number(f.crit),
      })),
    }
    const updated = await updateInspectionScript(props.scriptId, payload)
    detail.value = updated
    form.value = {
      display_name: updated.display_name || '',
      platform: updated.platform || 'linux',
      version: updated.version || '',
      inspection_parser: updated.inspection_parser || 'json',
      inspection_script: updated.inspection_script || '',
      inspection_fields: Array.isArray(updated.inspection_fields)
        ? updated.inspection_fields.map((f) => ({ ...f }))
        : [],
    }
    successMessage.value = '保存成功'
    emit('saved', updated)
  } catch (err) {
    // 错误脱敏：仅显示通用文案，不回显后端 detail
    errorMessage.value = '保存失败，请稍后重试'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="editor-panel">
    <div v-if="props.scriptId == null" class="empty-state" data-testid="editor-empty">
      请选择左侧节点查看详情
    </div>
    <div v-else-if="isLoading" class="empty-state" data-testid="editor-loading">
      正在加载脚本...
    </div>
    <div v-else-if="errorMessage && !detail" class="alert error" data-testid="editor-error" role="alert">
      {{ errorMessage }}
    </div>
    <form v-else data-testid="editor-form" class="editor-form" @submit.prevent="onSave">
      <div class="editor-grid">
        <label class="editor-field">
          <span>展示名称</span>
          <input
            v-model="form.display_name"
            type="text"
            required
            data-testid="editor-display-name"
            aria-label="展示名称"
          />
        </label>
        <label class="editor-field">
          <span>平台</span>
          <select v-model="form.platform" data-testid="editor-platform" aria-label="平台">
            <option v-for="opt in platformOptions" :key="opt" :value="opt">{{ opt }}</option>
          </select>
        </label>
        <label class="editor-field">
          <span>版本</span>
          <input
            v-model="form.version"
            type="text"
            data-testid="editor-version"
            aria-label="版本"
          />
        </label>
        <label class="editor-field">
          <span>解析器</span>
          <select
            v-model="form.inspection_parser"
            data-testid="editor-parser"
            aria-label="解析器"
          >
            <option v-for="opt in parserOptions" :key="opt" :value="opt">{{ opt }}</option>
          </select>
        </label>
      </div>
      <label class="editor-field">
        <span>脚本正文</span>
        <textarea
          v-model="form.inspection_script"
          rows="10"
          class="editor-textarea"
          data-testid="editor-script"
          aria-label="脚本正文"
        ></textarea>
      </label>
      <div class="editor-fields">
        <div class="editor-fields-header">
          <h4>字段规则</h4>
          <button
            type="button"
            class="primary-btn"
            data-testid="editor-add-field-btn"
            @click="addField"
          >新增字段</button>
        </div>
        <div v-if="!form.inspection_fields.length" class="empty-state">
          暂无字段规则
        </div>
        <table v-else class="editor-fields-table">
          <thead>
            <tr>
              <th>字段 key</th>
              <th>中文名</th>
              <th>单位</th>
              <th>方向</th>
              <th>警告</th>
              <th>严重</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(f, idx) in form.inspection_fields"
              :key="idx"
              data-testid="editor-field-row"
            >
              <td><input v-model="f.key" type="text" aria-label="字段 key" /></td>
              <td><input v-model="f.name_zh" type="text" aria-label="中文名" /></td>
              <td><input v-model="f.unit" type="text" aria-label="单位" /></td>
              <td>
                <select v-model="f.direction" aria-label="方向">
                  <option v-for="opt in directionOptions" :key="opt" :value="opt">{{ opt }}</option>
                </select>
              </td>
              <td><input v-model.number="f.warn" type="number" step="any" aria-label="警告阈值" /></td>
              <td><input v-model.number="f.crit" type="number" step="any" aria-label="严重阈值" /></td>
              <td>
                <button
                  type="button"
                  class="ghost-btn"
                  data-testid="editor-remove-field-btn"
                  aria-label="删除字段"
                  @click="removeField(idx)"
                >删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="errorMessage" class="alert error" data-testid="editor-error" role="alert">
        {{ errorMessage }}
      </div>
      <div v-if="successMessage" class="alert success" data-testid="editor-success" role="status">
        {{ successMessage }}
      </div>
      <div class="editor-actions">
        <button
          type="submit"
          class="primary-btn"
          :disabled="isSaving || !isFormValid"
          :aria-busy="isSaving ? 'true' : 'false'"
          data-testid="editor-save-btn"
        >
          <span v-if="isSaving" data-testid="editor-saving">保存中...</span>
          <span v-else>保存</span>
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.editor-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  box-sizing: border-box;
}
.editor-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.editor-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.editor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #374151;
}
.editor-field input,
.editor-field select,
.editor-textarea {
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 14px;
  font-family: inherit;
  background: #fff;
}
.editor-textarea {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  white-space: pre;
  min-height: 200px;
}
.editor-fields-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.editor-fields-table {
  width: 100%;
  border-collapse: collapse;
}
.editor-fields-table th,
.editor-fields-table td {
  border: 1px solid #e5e7eb;
  padding: 6px;
  font-size: 13px;
  text-align: left;
}
.editor-fields-table input,
.editor-fields-table select {
  width: 100%;
}
.editor-actions {
  display: flex;
  justify-content: flex-end;
}
.empty-state {
  padding: 24px;
  color: #6b7280;
  text-align: center;
}
.alert.error {
  color: #b91c1c;
}
.alert.success {
  color: #047857;
}
.primary-btn {
  background: #4f46e5;
  color: #fff;
  border: 0;
  border-radius: 6px;
  padding: 6px 14px;
  cursor: pointer;
}
.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ghost-btn {
  background: #fff;
  border: 1px solid #d1d5db;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
}
</style>
