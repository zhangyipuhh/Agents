<script setup>
/**
 * InspectionScriptEditorPanel - 巡检脚本库右侧编辑面板（2026-08-04 新增；2026-09-16 重构）
 *
 * 接收 `scriptId` prop；scriptId 为 null 时显示「请选择左侧节点查看详情」。
 * 非空时并行拉详情 + 段列表，渲染可编辑表单：
 *   - 组字段（display_name / platform / version / inspection_parser）独立「保存组字段」按钮；
 *   - 段列表（按 sort_order 升序）独立「保存分段」按钮，每段独立 CRUD；
 *   - 字段规则（组级共享 inspection_fields JSONB）保留为单一表格，与组字段同 PUT 提交；
 *   - legacy `inspection_script` 字段保留只读折叠区（运维可看完整合并脚本，不再编辑）。
 *
 * 保存成功后 emit 'saved'，父组件用于更新列表缓存或显示成功提示。
 *
 * 2026-09-16 拆分边界（D1）：
 *   - 脚本正文：按段拆分 → 每段独立 textarea + enabled / sort_order / display_name 编辑；
 *   - 字段规则：保留为单一表格（组级共享，不分段）；
 *   - legacy inspection_script：折叠区只读显示拼接文本，不发送 PUT。
 */
import { computed, reactive, ref, watch } from 'vue'
import {
  fetchInspectionScriptDetail,
  fetchInspectionScriptSegments,
  createInspectionScriptSegment,
  updateInspectionScriptSegment,
  deleteInspectionScriptSegment,
  updateInspectionScript,
} from '../utils/api.js'

const props = defineProps({
  scriptId: { type: [Number, null], default: null },
})
const emit = defineEmits(['saved'])

const detail = ref(null)
const isLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const segmentSaveMessage = ref('')

const form = reactive({
  display_name: '',
  platform: 'linux',
  version: '',
  inspection_parser: 'json',
  inspection_fields: [],
})

const segments = ref([])
const loadedSegments = ref([]) // 用于 dirty 检测；与 segments[i] 对比
const segmentErrors = ref({}) // index -> error message

const isSavingGroup = ref(false)
const isSavingSegments = ref(false)

const platformOptions = ['linux', 'windows']
const parserOptions = ['json', 'kv', 'csv', 'raw']
const directionOptions = ['high', 'low', 'ignore']

const SEGMENT_KEY_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/

const isFormValid = computed(() => {
  return Boolean(form.display_name && form.display_name.trim())
})

// legacy inspection_script 折叠区派生:按 sort_order 拼接的完整合并脚本(只读)
const inspectionScriptCombined = computed(() => {
  const enabledSegs = (segments.value || [])
    .filter((s) => s.enabled !== false && s.script && s.script.trim())
    .slice()
    .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
  if (!enabledSegs.length) return ''
  return enabledSegs
    .map((s) => `# --- segment ${s.segment_key} ---\n${s.script || ''}`)
    .join('\n\n')
})

watch(
  () => props.scriptId,
  async (newId) => {
    errorMessage.value = ''
    successMessage.value = ''
    segmentSaveMessage.value = ''
    segmentErrors.value = {}
    detail.value = null
    segments.value = []
    loadedSegments.value = []
    if (newId == null) return
    isLoading.value = true
    try {
      const [d, segs] = await Promise.all([
        fetchInspectionScriptDetail(newId),
        fetchInspectionScriptSegments(newId),
      ])
      detail.value = d
      form.display_name = d.display_name || ''
      form.platform = d.platform || 'linux'
      form.version = d.version || ''
      form.inspection_parser = d.inspection_parser || 'json'
      form.inspection_fields = Array.isArray(d.inspection_fields)
        ? d.inspection_fields.map((f) => ({ ...f }))
        : []
      const segList = Array.isArray(segs) ? segs.slice() : []
      segments.value = segList
      loadedSegments.value = JSON.parse(JSON.stringify(segList))
    } catch (err) {
      errorMessage.value = err?.message || '加载脚本详情失败'
    } finally {
      isLoading.value = false
    }
  },
  { immediate: true }
)

function addField() {
  form.inspection_fields.push({
    key: '',
    name_zh: '',
    unit: '',
    direction: 'high',
    warn: null,
    crit: null,
    ssd_warn: null,
    ssd_crit: null,
  })
}
function removeField(idx) {
  form.inspection_fields.splice(idx, 1)
}

/** 比对两个段(忽略 id / script_id / 时间戳),返回 dirty bool。 */
function isSegmentDirty(a, b) {
  if (!a || !b) return a !== b
  const keys = ['segment_key', 'display_name', 'sort_order', 'script', 'enabled']
  for (const k of keys) {
    const av = a[k]
    const bv = b[k]
    if (k === 'enabled') {
      // bool 严格比较
      if (Boolean(av) !== Boolean(bv)) return true
    } else if (String(av ?? '') !== String(bv ?? '')) {
      return true
    }
  }
  return false
}

async function onSaveGroup() {
  if (!isFormValid.value) {
    errorMessage.value = '展示名称不能为空'
    return
  }
  if (props.scriptId == null) return
  isSavingGroup.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const payload = {
      display_name: form.display_name.trim(),
      platform: form.platform,
      version: form.version || '',
      inspection_parser: form.inspection_parser,
      inspection_fields: form.inspection_fields.map((f) => ({
        key: (f.key || '').trim(),
        name_zh: (f.name_zh || '').trim(),
        unit: f.unit || '',
        direction: f.direction || 'high',
        warn: f.warn == null || f.warn === '' ? null : Number(f.warn),
        crit: f.crit == null || f.crit === '' ? null : Number(f.crit),
        ssd_warn: f.ssd_warn == null || f.ssd_warn === '' ? null : Number(f.ssd_warn),
        ssd_crit: f.ssd_crit == null || f.ssd_crit === '' ? null : Number(f.ssd_crit),
      })),
    }
    // 2026-09-16 D4:不发送 inspection_script / segments 字段(后端 contract 接受但前端主动不发)
    const updated = await updateInspectionScript(props.scriptId, payload)
    detail.value = updated
    form.display_name = updated.display_name || ''
    form.platform = updated.platform || 'linux'
    form.version = updated.version || ''
    form.inspection_parser = updated.inspection_parser || 'json'
    form.inspection_fields = Array.isArray(updated.inspection_fields)
      ? updated.inspection_fields.map((f) => ({ ...f }))
      : []
    successMessage.value = '保存成功'
    emit('saved', updated)
  } catch (err) {
    // 错误脱敏:仅显示通用文案,不回显后端 detail
    errorMessage.value = '保存失败，请稍后重试'
  } finally {
    isSavingGroup.value = false
  }
}

function moveSegment(idx, delta) {
  const next = idx + delta
  if (next < 0 || next >= segments.value.length) return
  const arr = segments.value
  const tmp = arr[idx]
  arr[idx] = arr[next]
  arr[next] = tmp
  // 同步 sort_order(同步持久化后续 PUT 时使用)
  arr.forEach((s, i) => { s.sort_order = i * 10 })
}

function onAddSegment() {
  if (typeof window === 'undefined') return
  const key = window.prompt('请输入 segment_key（小写字母数字 + 下划线/短横线,1-64 字符,必须以字母数字开头）')
  if (!key) return
  if (!SEGMENT_KEY_RE.test(key)) {
    errorMessage.value = 'segment_key 不合法:必须匹配 ^[a-z0-9][a-z0-9_-]{0,63}$'
    return
  }
  if (segments.value.some((s) => s.segment_key === key)) {
    errorMessage.value = `segment_key「${key}」已存在`
    return
  }
  // 本地乐观新增;保存时再 POST
  const draft = {
    script_id: props.scriptId,
    segment_key: key,
    display_name: '',
    sort_order: (segments.value.length || 0) * 10,
    script: '',
    enabled: true,
    _localNew: true, // 标记新建未持久化
  }
  segments.value.push(draft)
  loadedSegments.value.push(JSON.parse(JSON.stringify(draft)))
}

async function onDeleteSegment(idx) {
  if (typeof window === 'undefined') return
  const seg = segments.value[idx]
  if (!seg) return
  const label = seg.segment_key || `分段 ${idx + 1}`
  const confirmed = window.confirm(`确定删除巡检分段「${label}」吗？删除后无法恢复。`)
  if (!confirmed) return
  if (seg._localNew) {
    // 尚未持久化,本地移除即可
    segments.value.splice(idx, 1)
    loadedSegments.value.splice(idx, 1)
    return
  }
  if (seg.id == null) {
    errorMessage.value = '分段缺少 id,无法删除'
    return
  }
  try {
    await deleteInspectionScriptSegment(props.scriptId, seg.id)
    segments.value.splice(idx, 1)
    loadedSegments.value.splice(idx, 1)
    delete segmentErrors.value[idx]
  } catch (err) {
    errorMessage.value = err?.message || '删除分段失败'
  }
}

async function onSaveSegments() {
  if (props.scriptId == null) return
  isSavingSegments.value = true
  segmentSaveMessage.value = ''
  segmentErrors.value = {}
  try {
    // 1) 新增段(segment._localNew && !id) → POST
    // 2) 现有段且与 loadedSegments 不一致 → PUT(id 已知)
    // 3) 未变化段 → 跳过
    const tasks = []
    const newSegments = []
    segments.value.forEach((seg, idx) => {
      const loaded = loadedSegments.value[idx]
      if (seg._localNew && seg.id == null) {
        tasks.push({
          kind: 'create',
          idx,
          payload: {
            segment_key: seg.segment_key,
            display_name: seg.display_name || '',
            sort_order: Number(seg.sort_order || 0),
            script: seg.script || '',
            enabled: seg.enabled !== false,
          },
        })
      } else if (seg.id != null && isSegmentDirty(seg, loaded)) {
        tasks.push({
          kind: 'update',
          idx,
          segmentId: seg.id,
          payload: {
            segment_key: seg.segment_key,
            display_name: seg.display_name || '',
            sort_order: Number(seg.sort_order || 0),
            script: seg.script || '',
            enabled: seg.enabled !== false,
          },
        })
      }
    })

    if (!tasks.length) {
      segmentSaveMessage.value = '没有需要保存的分段变更'
      return
    }

    const results = await Promise.allSettled(tasks.map(async (t) => {
      if (t.kind === 'create') {
        const created = await createInspectionScriptSegment(props.scriptId, t.payload)
        newSegments.push({ idx: t.idx, record: created })
      } else {
        const updated = await updateInspectionScriptSegment(props.scriptId, t.segmentId, t.payload)
        newSegments.push({ idx: t.idx, record: updated })
      }
    }))

    let failed = 0
    results.forEach((r, i) => {
      const t = tasks[i]
      if (r.status === 'rejected') {
        failed++
        const msg = r.reason?.message || '保存分段失败'
        segmentErrors.value = { ...segmentErrors.value, [t.idx]: msg }
      }
    })

    // 把服务端回写后的 record 应用到本地(包含 id / created_at / updated_at / 真实 sort_order)
    // 对未变化的段也用新 record 刷新 loadedSegments
    newSegments.forEach(({ idx, record }) => {
      const local = segments.value[idx]
      if (local) {
        segments.value[idx] = { ...local, ...record, _localNew: false }
        loadedSegments.value[idx] = JSON.parse(JSON.stringify(segments.value[idx]))
      }
    })

    if (failed === 0) {
      segmentSaveMessage.value = '分段保存成功'
    } else if (failed < tasks.length) {
      segmentSaveMessage.value = `分段部分保存成功,${failed} 项失败`
    } else {
      segmentSaveMessage.value = '分段保存失败'
    }
  } catch (err) {
    errorMessage.value = err?.message || '保存分段失败'
  } finally {
    isSavingSegments.value = false
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
    <form v-else data-testid="editor-form" class="editor-form" @submit.prevent="onSaveGroup">
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

      <!-- 巡检分段区域(2026-09-16 新增) -->
      <div class="editor-segments">
        <div class="editor-segments-header">
          <h4>巡检分段（共 {{ segments.length }} 段）</h4>
          <div class="editor-segments-actions">
            <button
              type="button"
              class="primary-btn"
              :disabled="isSavingSegments"
              :aria-busy="isSavingSegments ? 'true' : 'false'"
              data-testid="editor-save-segments-btn"
              @click="onSaveSegments"
            >
              <span v-if="isSavingSegments" data-testid="editor-save-segments-loading">保存中...</span>
              <span v-else>保存分段</span>
            </button>
            <button
              type="button"
              class="ghost-btn"
              data-testid="editor-add-segment-btn"
              @click="onAddSegment"
            >新增段</button>
          </div>
        </div>
        <div v-if="!segments.length" class="empty-state" data-testid="editor-segments-empty">
          暂无分段
        </div>
        <ul v-else class="editor-segments-list" data-testid="editor-segments-list">
          <li
            v-for="(seg, idx) in segments"
            :key="seg.id != null ? seg.id : `new-${idx}`"
            class="editor-segment-card"
            :data-testid="`editor-segment-card-${idx}`"
          >
            <details open class="editor-segment-details">
              <summary class="editor-segment-summary">
                <label class="editor-segment-enabled" @click.stop>
                  <input
                    v-model="seg.enabled"
                    type="checkbox"
                    :data-testid="`editor-segment-enabled-${idx}`"
                    :aria-label="`启用分段 ${seg.segment_key}`"
                  />
                  <span class="editor-segment-key">{{ seg.segment_key }}</span>
                </label>
                <span class="editor-segment-controls">
                  <input
                    v-model.number="seg.sort_order"
                    type="number"
                    min="0"
                    class="editor-segment-sortorder"
                    :data-testid="`editor-segment-sortorder-${idx}`"
                    :aria-label="`排序 ${seg.segment_key}`"
                    @click.stop
                  />
                  <input
                    v-model="seg.display_name"
                    type="text"
                    class="editor-segment-display-name"
                    :data-testid="`editor-segment-display-name-${idx}`"
                    :aria-label="`分段 ${seg.segment_key} 展示名`"
                    placeholder="展示名"
                    @click.stop
                  />
                  <button
                    type="button"
                    class="ghost-btn editor-segment-move-up"
                    :disabled="idx === 0"
                    :data-testid="`editor-segment-move-up-${idx}`"
                    :aria-label="`上移分段 ${seg.segment_key}`"
                    @click.stop="moveSegment(idx, -1)"
                  >{{ '▲' }}</button>
                  <button
                    type="button"
                    class="ghost-btn editor-segment-move-down"
                    :disabled="idx === segments.length - 1"
                    :data-testid="`editor-segment-move-down-${idx}`"
                    :aria-label="`下移分段 ${seg.segment_key}`"
                    @click.stop="moveSegment(idx, 1)"
                  >{{ '▼' }}</button>
                  <button
                    type="button"
                    class="ghost-btn danger editor-segment-delete"
                    :data-testid="`editor-segment-delete-${idx}`"
                    :aria-label="`删除分段 ${seg.segment_key}`"
                    @click.stop="onDeleteSegment(idx)"
                  >删除</button>
                </span>
              </summary>
              <textarea
                v-model="seg.script"
                rows="10"
                class="editor-segment-textarea"
                :data-testid="`editor-segment-script-${idx}`"
                :aria-label="`分段 ${seg.segment_key} 脚本正文`"
                placeholder="# 段脚本正文"
              ></textarea>
              <div
                v-if="segmentErrors[idx]"
                class="alert error segment-error"
                :data-testid="`editor-segment-error-${idx}`"
                role="alert"
              >
                {{ segmentErrors[idx] }}
              </div>
            </details>
          </li>
        </ul>
        <div
          v-if="segmentSaveMessage"
          class="alert success"
          data-testid="editor-save-segments-status"
          role="status"
        >
          {{ segmentSaveMessage }}
        </div>
      </div>

      <!-- legacy inspection_script 折叠区(只读,2026-09-16 新增) -->
      <details v-if="inspectionScriptCombined" class="editor-legacy">
        <summary>查看完整合并脚本（只读，按 sort_order 拼接）</summary>
        <pre
          class="editor-legacy-pre"
          data-testid="editor-legacy-pre"
          :aria-label="完整合并脚本预览"
        >{{ inspectionScriptCombined }}</pre>
      </details>

      <!-- 字段规则(组级共享,不分段) -->
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
              <th>SSD 警告</th>
              <th>SSD 严重</th>
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
              <td><input v-model.number="f.ssd_warn" type="number" step="any" aria-label="SSD 警告阈值" /></td>
              <td><input v-model.number="f.ssd_crit" type="number" step="any" aria-label="SSD 严重阈值" /></td>
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
          :disabled="isSavingGroup || !isFormValid"
          :aria-busy="isSavingGroup ? 'true' : 'false'"
          data-testid="editor-save-btn"
        >
          <span v-if="isSavingGroup" data-testid="editor-saving">保存中...</span>
          <span v-else>保存组字段</span>
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
/* 分段(2026-09-16 新增) */
.editor-segments-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.editor-segments-actions {
  display: flex;
  gap: 8px;
}
.editor-segments-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.editor-segment-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fafafa;
}
.editor-segment-details {
  padding: 0;
}
.editor-segment-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  list-style: none;
}
.editor-segment-summary::-webkit-details-marker { display: none; }
.editor-segment-enabled {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  font-size: 13px;
  color: #1f2937;
  flex: 0 0 auto;
}
.editor-segment-key {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  background: #eef2ff;
  padding: 1px 6px;
  border-radius: 4px;
  color: #4338ca;
}
.editor-segment-controls {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  flex: 0 0 auto;
}
.editor-segment-controls input,
.editor-segment-controls button {
  font-size: 12px;
}
.editor-segment-sortorder {
  width: 60px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 2px 4px;
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
}
.editor-segment-display-name {
  width: 140px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 2px 6px;
}
.editor-segment-move-up,
.editor-segment-move-down,
.editor-segment-delete {
  padding: 2px 6px;
}
.editor-segment-textarea {
  width: calc(100% - 16px);
  margin: 8px;
  font-family: ui-monospace, 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  white-space: pre;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 6px 8px;
  min-height: 180px;
  box-sizing: border-box;
}
.segment-error {
  margin: 0 8px 8px;
  font-size: 12px;
}
.editor-legacy {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 12px;
  background: #f9fafb;
}
.editor-legacy summary {
  cursor: pointer;
  font-size: 13px;
  color: #4b5563;
}
.editor-legacy-pre {
  margin: 8px 0 0;
  padding: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  font-family: ui-monospace, 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  overflow-x: auto;
  max-height: 320px;
  overflow-y: auto;
}
/* 字段规则(原状) */
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
.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ghost-btn.danger {
  color: #dc2626;
}
</style>