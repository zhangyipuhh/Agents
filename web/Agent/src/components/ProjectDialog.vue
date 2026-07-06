<script setup>
/**
 * ProjectDialog 组件（2026-06-30 新增）
 *
 * 双模式弹窗：
 *   - mode='create'：新建空白项目（输入项目名称，隐藏路径字段）
 *   - mode='pick'  ：使用现有文件夹（从项目列表中选）
 *
 * 通过 v-model:visible 控制显隐。
 */
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { createProject, fetchProjectList } from '../utils/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  mode: {
    type: String,
    default: 'create' // 'create' | 'pick'
  },
  projects: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:visible', 'created', 'picked'])

// === create 模式 ===
const projectName = ref('')
const isSubmitting = ref(false)
const createError = ref('')

// === pick 模式 ===
const isLoadingProjects = ref(false)
const internalProjects = ref([])
const pickError = ref('')

const isCreateMode = computed(() => props.mode === 'create')

watch(() => props.visible, (val) => {
  if (val) {
    projectName.value = ''
    createError.value = ''
    pickError.value = ''
    if (props.mode === 'create') {
      nextTick(() => {
        const input = document.getElementById('project-name-input')
        if (input) input.focus()
      })
    } else {
      loadProjectList()
    }
  }
})

async function loadProjectList() {
  isLoadingProjects.value = true
  pickError.value = ''
  try {
    const data = await fetchProjectList()
    internalProjects.value = data.projects || []
  } catch (err) {
    pickError.value = err.message || '加载项目列表失败'
  } finally {
    isLoadingProjects.value = false
  }
}

function closeDialog() {
  emit('update:visible', false)
}

async function handleCreateSubmit() {
  const name = projectName.value.trim()
  if (!name) {
    createError.value = '请输入项目名称'
    return
  }
  if (name.length > 50) {
    createError.value = '项目名称不能超过 50 字符'
    return
  }
  isSubmitting.value = true
  createError.value = ''
  try {
    // 注意：uuid 必须由调用方在 create 之前确定 = 当前 session_id
    // 但本组件不直接知道 session_id，所以把"生成 uuid"的职责放在父组件的 onCreate 事件里
    // 这里只 emit 'created' 让父组件去调 createProject(name, uuid)
    emit('created', { name })
    closeDialog()
  } catch (err) {
    createError.value = err.message || '创建项目失败'
  } finally {
    isSubmitting.value = false
  }
}

function handlePickProject(project) {
  emit('picked', project)
  closeDialog()
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    closeDialog()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="project-dialog-fade">
      <div
        v-if="visible"
        class="project-dialog-overlay"
        @click.self="closeDialog"
      >
        <div class="project-dialog-container" role="dialog" aria-modal="true">
          <div class="project-dialog-header">
            <h3 class="project-dialog-title">
              {{ isCreateMode ? '创建项目' : '选择项目' }}
            </h3>
            <button class="project-dialog-close" @click="closeDialog" aria-label="关闭">
              <svg viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
              </svg>
            </button>
          </div>

          <div class="project-dialog-body">
            <!-- create 模式 -->
            <template v-if="isCreateMode">
              <label class="project-dialog-label" for="project-name-input">
                项目名称 <span class="required">*</span>
              </label>
              <input
                id="project-name-input"
                v-model="projectName"
                type="text"
                class="project-dialog-input"
                placeholder="请输入文件夹名称"
                maxlength="50"
                @keydown.enter="handleCreateSubmit"
              />
              <div v-if="createError" class="project-dialog-error">{{ createError }}</div>
            </template>

            <!-- pick 模式 -->
            <template v-else>
              <div v-if="isLoadingProjects" class="project-dialog-loading">加载中...</div>
              <div v-else-if="pickError" class="project-dialog-error">{{ pickError }}</div>
              <div v-else-if="internalProjects.length === 0" class="project-dialog-empty">
                暂无已创建的项目
              </div>
              <div v-else class="project-dialog-list">
                <div
                  v-for="project in internalProjects"
                  :key="project.id"
                  class="project-dialog-item"
                  @click="handlePickProject(project)"
                >
                  <svg class="item-icon" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                  </svg>
                  <div class="item-content">
                    <div class="item-name">{{ project.name }}</div>
                    <div class="item-meta">UUID: {{ project.uuid.slice(0, 8) }}...</div>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <div class="project-dialog-footer">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button
              v-if="isCreateMode"
              class="btn-confirm"
              :disabled="isSubmitting"
              @click="handleCreateSubmit"
            >
              保存
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.project-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.project-dialog-container {
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 420px;
  max-width: calc(100vw - 32px);
  padding: 0;
  display: flex;
  flex-direction: column;
  font-family: var(--font-family);
}

.project-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--color-border-light);
}

.project-dialog-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.project-dialog-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: var(--transition-colors);
}

.project-dialog-close:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.project-dialog-close svg {
  width: 16px;
  height: 16px;
}

.project-dialog-body {
  padding: 20px 24px;
  min-height: 120px;
}

.project-dialog-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

.required {
  color: var(--color-error);
}

.project-dialog-input {
  width: 100%;
  padding: 10px 12px;
  font-size: var(--font-size-base);
  font-family: inherit;
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: var(--transition-colors), border-color 0.2s ease;
  box-sizing: border-box;
}

.project-dialog-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.project-dialog-error {
  margin-top: 8px;
  font-size: var(--font-size-sm);
  color: var(--color-error);
}

.project-dialog-loading,
.project-dialog-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.project-dialog-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 360px;
  overflow-y: auto;
}

.project-dialog-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors);
}

.project-dialog-item:hover {
  background-color: var(--color-bg-hover);
}

.item-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: var(--color-accent);
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
}

.project-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 24px 20px;
  border-top: 1px solid var(--color-border-light);
}

.btn-cancel,
.btn-confirm {
  font-family: inherit;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: var(--transition-colors);
}

.btn-cancel {
  background-color: var(--color-bg-primary);
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

.btn-cancel:hover {
  background-color: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.btn-confirm {
  background-color: var(--color-accent);
  color: white;
}

.btn-confirm:hover:not(:disabled) {
  background-color: var(--color-accent-hover);
}

.btn-confirm:disabled {
  opacity: var(--opacity-disabled);
  cursor: not-allowed;
}

.project-dialog-fade-enter-active,
.project-dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.project-dialog-fade-enter-active .project-dialog-container,
.project-dialog-fade-leave-active .project-dialog-container {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.project-dialog-fade-enter-from,
.project-dialog-fade-leave-to {
  opacity: 0;
}

.project-dialog-fade-enter-from .project-dialog-container,
.project-dialog-fade-leave-to .project-dialog-container {
  transform: scale(0.96);
  opacity: 0;
}
</style>
