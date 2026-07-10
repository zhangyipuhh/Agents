<script setup>
/**
 * TaskSchedulerManager - 智能体定时任务管理组件（admin）
 *
 * 提供定时任务列表、任务表单、启停、立即运行和执行历史查看能力。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import {
  fetchAdminAgentList,
  fetchTaskSchedules,
  createTaskSchedule,
  updateTaskSchedule,
  deleteTaskSchedule,
  setTaskScheduleEnabled,
  triggerTaskSchedule,
  fetchTaskRuns,
} from '../utils/api.js'

const schedules = ref([])
const agents = ref([])
const runs = ref([])
const selectedSchedule = ref(null)
const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const isCreating = ref(false)
const contextJson = ref('{}')

const form = reactive({
  name: '',
  description: '',
  agent_name: '',
  prompt: '',
  cron_expression: '0 9 * * *',
  timezone: 'Asia/Shanghai',
  enabled: true,
  context_overrides: {},
  max_concurrent_runs: 1,
})

const enabledAgents = computed(() => agents.value.filter((agent) => agent.enabled !== false))

/**
 * 初始化数据。
 * @returns {Promise<void>} 无返回值
 */
async function loadInitialData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [taskRows, agentRows] = await Promise.all([
      fetchTaskSchedules(),
      fetchAdminAgentList(),
    ])
    schedules.value = taskRows || []
    agents.value = agentRows || []
    if (schedules.value.length > 0) {
      await selectSchedule(schedules.value[0])
    } else {
      startCreate()
    }
  } catch (error) {
    errorMessage.value = error.message || '加载定时任务失败'
  } finally {
    isLoading.value = false
  }
}

/**
 * 选中已有任务并加载执行历史。
 * @param {Object} schedule - 定时任务记录
 * @returns {Promise<void>} 无返回值
 */
async function selectSchedule(schedule) {
  selectedSchedule.value = schedule
  isCreating.value = false
  fillForm(schedule)
  await loadRuns(schedule.id)
}

/**
 * 加载执行历史。
 * @param {number} scheduleId - 定时任务 ID
 * @returns {Promise<void>} 无返回值
 */
async function loadRuns(scheduleId) {
  if (!scheduleId) {
    runs.value = []
    return
  }
  try {
    runs.value = await fetchTaskRuns(scheduleId, 50)
  } catch (error) {
    errorMessage.value = error.message || '加载执行历史失败'
  }
}

/**
 * 将任务记录填充到表单。
 * @param {Object} schedule - 定时任务记录
 */
function fillForm(schedule) {
  form.name = schedule.name || ''
  form.description = schedule.description || ''
  form.agent_name = schedule.agent_name || enabledAgents.value[0]?.name || ''
  form.prompt = schedule.prompt || ''
  form.cron_expression = schedule.cron_expression || '0 9 * * *'
  form.timezone = schedule.timezone || 'Asia/Shanghai'
  form.enabled = schedule.enabled !== false
  form.context_overrides = schedule.context_overrides || {}
  form.max_concurrent_runs = schedule.max_concurrent_runs || 1
  contextJson.value = JSON.stringify(form.context_overrides, null, 2)
}

/**
 * 开始创建新任务。
 */
function startCreate() {
  selectedSchedule.value = null
  isCreating.value = true
  runs.value = []
  form.name = ''
  form.description = ''
  form.agent_name = enabledAgents.value[0]?.name || ''
  form.prompt = ''
  form.cron_expression = '0 9 * * *'
  form.timezone = 'Asia/Shanghai'
  form.enabled = true
  form.context_overrides = {}
  form.max_concurrent_runs = 1
  contextJson.value = '{}'
  errorMessage.value = ''
  successMessage.value = ''
}

/**
 * 构造提交 payload。
 * @returns {Object} 后端请求体
 * @throws {Error} context_overrides JSON 非法时抛出
 */
function buildPayload() {
  let contextOverrides = {}
  try {
    contextOverrides = contextJson.value.trim() ? JSON.parse(contextJson.value) : {}
  } catch {
    throw new Error('上下文 JSON 格式不正确')
  }
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    agent_name: form.agent_name,
    prompt: form.prompt.trim(),
    cron_expression: form.cron_expression.trim(),
    timezone: form.timezone.trim() || 'Asia/Shanghai',
    enabled: form.enabled,
    context_overrides: contextOverrides,
    max_concurrent_runs: Number(form.max_concurrent_runs) || 1,
  }
}

/**
 * 保存任务。
 * @returns {Promise<void>} 无返回值
 */
async function saveTask() {
  isSaving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const payload = buildPayload()
    if (isCreating.value) {
      const created = await createTaskSchedule(payload)
      successMessage.value = '任务已创建'
      await loadInitialData()
      const match = schedules.value.find((item) => item.id === created.id)
      if (match) await selectSchedule(match)
    } else if (selectedSchedule.value) {
      const updated = await updateTaskSchedule(selectedSchedule.value.id, payload)
      successMessage.value = '任务已保存'
      await refreshSchedules(updated.id)
    }
  } catch (error) {
    errorMessage.value = error.message || '保存任务失败'
  } finally {
    isSaving.value = false
  }
}

/**
 * 刷新任务列表并保持选中项。
 * @param {number} selectedId - 选中任务 ID
 * @returns {Promise<void>} 无返回值
 */
async function refreshSchedules(selectedId = selectedSchedule.value?.id) {
  schedules.value = await fetchTaskSchedules()
  const next = schedules.value.find((item) => item.id === selectedId) || schedules.value[0]
  if (next) await selectSchedule(next)
}

/**
 * 启用或停用当前任务。
 * @returns {Promise<void>} 无返回值
 */
async function toggleTask() {
  if (!selectedSchedule.value) return
  errorMessage.value = ''
  try {
    const updated = await setTaskScheduleEnabled(selectedSchedule.value.id, !selectedSchedule.value.enabled)
    successMessage.value = updated.enabled ? '任务已启用' : '任务已停用'
    await refreshSchedules(updated.id)
  } catch (error) {
    errorMessage.value = error.message || '更新启用状态失败'
  }
}

/**
 * 立即运行当前任务。
 * @returns {Promise<void>} 无返回值
 */
async function runNow() {
  if (!selectedSchedule.value) return
  errorMessage.value = ''
  try {
    await triggerTaskSchedule(selectedSchedule.value.id)
    successMessage.value = '任务已提交运行'
    await loadRuns(selectedSchedule.value.id)
  } catch (error) {
    errorMessage.value = error.message || '立即运行失败'
  }
}

/**
 * 删除当前任务。
 * @returns {Promise<void>} 无返回值
 */
async function removeTask() {
  if (!selectedSchedule.value) return
  if (!window.confirm(`确认删除任务「${selectedSchedule.value.name}」？`)) return
  errorMessage.value = ''
  try {
    await deleteTaskSchedule(selectedSchedule.value.id)
    successMessage.value = '任务已删除'
    await refreshSchedules(null)
    if (!schedules.value.length) startCreate()
  } catch (error) {
    errorMessage.value = error.message || '删除任务失败'
  }
}

onMounted(loadInitialData)
</script>

<template>
  <section class="task-scheduler-manager">
    <aside class="task-sidebar">
      <div class="panel-header">
        <div>
          <h3>定时任务</h3>
          <p>按计划触发已配置智能体</p>
        </div>
        <button class="primary-btn" type="button" @click="startCreate">新增任务</button>
      </div>

      <div v-if="isLoading" class="empty-state">正在加载...</div>
      <div v-else-if="!schedules.length" class="empty-state">暂无定时任务</div>
      <button
        v-for="schedule in schedules"
        :key="schedule.id"
        class="task-item"
        :class="{ active: selectedSchedule && selectedSchedule.id === schedule.id }"
        type="button"
        @click="selectSchedule(schedule)"
      >
        <span class="task-name">{{ schedule.name }}</span>
        <span class="task-agent">{{ schedule.agent_name }}</span>
        <span class="task-cron">{{ schedule.cron_expression }}</span>
        <span class="task-status" :class="schedule.enabled ? 'enabled' : 'disabled'">
          {{ schedule.enabled ? '已启用' : '已停用' }}
        </span>
      </button>
    </aside>

    <main class="task-detail">
      <div v-if="errorMessage" class="alert error">{{ errorMessage }}</div>
      <div v-if="successMessage" class="alert success">{{ successMessage }}</div>

      <header class="detail-header">
        <div>
          <h3>{{ isCreating ? '新增定时任务' : '编辑定时任务' }}</h3>
          <p>每次触发都会创建新的会话记录，停机期间错过的触发不会补跑。</p>
        </div>
        <div class="actions" v-if="!isCreating && selectedSchedule">
          <button type="button" class="secondary-btn" @click="toggleTask">
            {{ selectedSchedule.enabled ? '停用任务' : '启用任务' }}
          </button>
          <button type="button" class="secondary-btn" @click="runNow">立即运行</button>
          <button type="button" class="danger-btn" @click="removeTask">删除任务</button>
        </div>
      </header>

      <form class="task-form" @submit.prevent="saveTask">
        <label class="form-field">
          <span>任务名称 *</span>
          <input v-model="form.name" type="text" placeholder="例如：每日巡检" />
        </label>
        <label class="form-field">
          <span>Cron 表达式 *</span>
          <input v-model="form.cron_expression" type="text" placeholder="0 9 * * *" />
        </label>
        <label class="form-field">
          <span>目标智能体 *</span>
          <select v-model="form.agent_name">
            <option v-for="agent in enabledAgents" :key="agent.name" :value="agent.name">
              {{ agent.display_name || agent.name }}（{{ agent.name }}）
            </option>
          </select>
        </label>
        <label class="form-field">
          <span>时区</span>
          <input v-model="form.timezone" type="text" placeholder="Asia/Shanghai" />
        </label>
        <label class="form-field full">
          <span>任务提示词 *</span>
          <textarea v-model="form.prompt" rows="5" placeholder="描述定时触发时需要智能体完成的任务"></textarea>
        </label>
        <label class="form-field full">
          <span>描述</span>
          <input v-model="form.description" type="text" placeholder="可选：说明该任务的用途" />
        </label>
        <label class="form-field full">
          <span>context_overrides JSON</span>
          <textarea v-model="contextJson" rows="4" placeholder='{}'></textarea>
        </label>
        <label class="inline-field">
          <input v-model="form.enabled" type="checkbox" />
          <span>保存后启用任务</span>
        </label>
        <div class="form-actions">
          <button class="primary-btn" type="submit" :disabled="isSaving">
            {{ isSaving ? '保存中...' : '保存任务' }}
          </button>
        </div>
      </form>

      <section class="run-history" v-if="!isCreating">
        <h4>执行历史</h4>
        <div v-if="!runs.length" class="empty-state">暂无执行记录</div>
        <div v-for="run in runs" :key="run.id" class="run-item">
          <div class="run-main">
            <strong>{{ run.status }}</strong>
            <span>{{ run.trigger_type }}</span>
            <span>{{ run.created_at || run.started_at }}</span>
          </div>
          <p v-if="run.output_text">{{ run.output_text }}</p>
          <p v-if="run.error_message" class="run-error">{{ run.error_message }}</p>
        </div>
      </section>
    </main>
  </section>
</template>

<style scoped>
.task-scheduler-manager {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 20px;
  min-height: 560px;
}

.task-sidebar,
.task-detail {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 18px;
}

.panel-header,
.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.panel-header h3,
.detail-header h3 {
  margin: 0;
  color: #111827;
  font-size: 18px;
}

.panel-header p,
.detail-header p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.task-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  padding: 12px;
  margin-bottom: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  text-align: left;
}

.task-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.task-name {
  color: #111827;
  font-weight: 600;
}

.task-agent,
.task-cron {
  color: #4b5563;
  font-size: 12px;
}

.task-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}

.task-status.enabled {
  color: #047857;
  background: #d1fae5;
}

.task-status.disabled {
  color: #6b7280;
  background: #f3f4f6;
}

.task-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-field,
.inline-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #374151;
  font-size: 13px;
}

.inline-field {
  flex-direction: row;
  align-items: center;
}

.form-field.full,
.form-actions {
  grid-column: 1 / -1;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 14px;
  color: #111827;
  background: #ffffff;
}

textarea {
  resize: vertical;
}

.actions,
.form-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.primary-btn,
.secondary-btn,
.danger-btn {
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-weight: 600;
}

.primary-btn {
  color: #ffffff;
  background: #2563eb;
}

.secondary-btn {
  color: #1f2937;
  background: #e5e7eb;
}

.danger-btn {
  color: #ffffff;
  background: #dc2626;
}

.alert {
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
}

.alert.error {
  color: #991b1b;
  background: #fee2e2;
}

.alert.success {
  color: #065f46;
  background: #d1fae5;
}

.empty-state {
  color: #6b7280;
  padding: 16px;
  text-align: center;
}

.run-history {
  margin-top: 22px;
}

.run-history h4 {
  margin: 0 0 12px;
  color: #111827;
}

.run-item {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: #f9fafb;
}

.run-main {
  display: flex;
  gap: 12px;
  color: #374151;
  font-size: 13px;
}

.run-item p {
  margin: 6px 0 0;
  color: #374151;
}

.run-error {
  color: #b91c1c !important;
}

@media (max-width: 900px) {
  .task-scheduler-manager {
    grid-template-columns: 1fr;
  }
}
</style>
