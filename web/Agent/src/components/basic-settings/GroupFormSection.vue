<!--
  GroupFormSection.vue
  通用单组表单 section 组件(2026-09-14 新增)
  fields: [{name, label, type, sensitive, placeholder, multiline}]
-->
<template>
  <div class="group-form-section" data-testid="group-form-section">
    <n-card :title="label" size="small" class="group-card">
      <template #header-extra>
        <n-button size="tiny" quaternary @click="handleReset" :loading="resetting">
          重置默认
        </n-button>
      </template>
      <n-form :label-width="180" label-placement="left">
        <n-form-item
          v-for="field in fields"
          :key="field.name"
          :label="field.label"
        >
          <!-- 敏感字段 -->
          <n-input
            v-if="field.sensitive"
            v-model:value="formData[field.name]"
            type="password"
            show-password-on="click"
            :placeholder="field.placeholder || '留空保持不变'"
            clearable
          />
          <!-- 布尔 -->
          <n-switch
            v-else-if="field.type === 'bool'"
            v-model:value="formData[field.name]"
          />
          <!-- 数字 -->
          <n-input-number
            v-else-if="field.type === 'int' || field.type === 'float'"
            v-model:value="formData[field.name]"
            :precision="field.type === 'float' ? 2 : 0"
          />
          <!-- JSON 数组 -->
          <n-input
            v-else-if="field.type === 'json'"
            v-model:value="formData[field.name]"
            type="textarea"
            :rows="3"
            placeholder='JSON 格式，如 ["a", "b"]'
          />
          <!-- 文本 -->
          <n-input
            v-else
            v-model:value="formData[field.name]"
            :type="field.multiline ? 'textarea' : 'text'"
            :rows="field.multiline ? 3 : undefined"
          />
        </n-form-item>
      </n-form>
      <div class="group-actions">
        <n-button type="primary" size="small" @click="handleSave" :loading="saving">
          保存
        </n-button>
        <span v-if="updatedAt" class="updated-at">
          最后更新: {{ updatedAt }} by {{ updatedBy }}
        </span>
      </div>
    </n-card>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue';
import { fetchSystemSettingsGroup, updateSystemSettingsGroup, resetSystemSettingsGroup } from '../../utils/api';

const props = defineProps({
  groupKey: { type: String, required: true },
  label: { type: String, required: true },
  fields: { type: Array, required: true },
});

// naive-ui 组件通过全局注册,运行时由 plugin-vue / app.use(naive-ui) 提供
// 在测试环境 stub 后,n-card / n-button 等会被全局 stub 替代
const message = ref({ success: () => {}, error: () => {}, warning: () => {}, info: () => {} });
const formData = ref({});
const saving = ref(false);
const resetting = ref(false);
const updatedAt = ref(null);
const updatedBy = ref(null);

async function load() {
  try {
    const data = await fetchSystemSettingsGroup(props.groupKey);
    formData.value = { ...(data.config || {}) };
    updatedAt.value = data.updated_at;
    updatedBy.value = data.updated_by;
  } catch (e) {
    message.error(e.message || '加载配置组失败');
  }
}

async function handleSave() {
  saving.value = true;
  try {
    // 敏感字段空串 → 删除(后端保持原值)
    const payload = {};
    for (const field of props.fields) {
      const v = formData.value[field.name];
      if (field.sensitive && (v === '' || v == null)) continue;
      if (field.type === 'json' && typeof v === 'string') {
        try { payload[field.name] = JSON.parse(v); } catch { payload[field.name] = v; }
      } else {
        payload[field.name] = v;
      }
    }
    const data = await updateSystemSettingsGroup(props.groupKey, payload);
    formData.value = { ...(data.config || {}) };
    updatedAt.value = data.updated_at;
    updatedBy.value = data.updated_by;
    message.success('保存成功，需重启服务生效');
  } catch (e) {
    message.error(e.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

async function handleReset() {
  if (!confirm(`确认重置「${props.label}」为默认值?`)) return;
  resetting.value = true;
  try {
    const data = await resetSystemSettingsGroup(props.groupKey);
    formData.value = { ...(data.config || {}) };
    message.success('已重置为默认值，需重启服务生效');
  } catch (e) {
    message.error(e.message || '重置失败');
  } finally {
    resetting.value = false;
  }
}

onMounted(load);
watch(() => props.groupKey, load);
</script>

<style scoped>
.group-form-section { margin-bottom: 16px; }
.group-card :deep(.n-card-header) { padding: 12px 16px; }
.group-actions { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.updated-at { font-size: 12px; color: #999; }
</style>
