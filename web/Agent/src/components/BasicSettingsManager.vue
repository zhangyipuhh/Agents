<!--
  BasicSettingsManager.vue
  基本设置主容器(2026-09-14 新增)
  6 孙 Tab: LLM 模型 / 文件解析 / 安全认证 / 网络与集成 / 沙箱与任务 / 其他
-->
<template>
  <div class="basic-settings-manager">
    <n-alert type="warning" class="restart-banner" closable>
      本页配置修改后需重启服务生效
    </n-alert>
    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="llm" tab="LLM 模型">
        <LLMSettingsPanel />
      </n-tab-pane>
      <n-tab-pane name="file-parser" tab="文件解析">
        <FileParserSettingsPanel />
      </n-tab-pane>
      <n-tab-pane name="security" tab="安全认证">
        <SecuritySettingsPanel />
      </n-tab-pane>
      <n-tab-pane name="network" tab="网络与集成">
        <NetworkSettingsPanel />
      </n-tab-pane>
      <n-tab-pane name="sandbox-task" tab="沙箱与任务">
        <SandboxTaskSettingsPanel />
      </n-tab-pane>
      <n-tab-pane name="misc" tab="其他">
        <MiscSettingsPanel />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import LLMSettingsPanel from './basic-settings/LLMSettingsPanel.vue';
import FileParserSettingsPanel from './basic-settings/FileParserSettingsPanel.vue';
import SecuritySettingsPanel from './basic-settings/SecuritySettingsPanel.vue';
import NetworkSettingsPanel from './basic-settings/NetworkSettingsPanel.vue';
import SandboxTaskSettingsPanel from './basic-settings/SandboxTaskSettingsPanel.vue';
import MiscSettingsPanel from './basic-settings/MiscSettingsPanel.vue';

const activeTab = ref('llm');
</script>

<style scoped>
.basic-settings-manager { padding: 16px; }
.restart-banner { margin-bottom: 16px; }
</style>
