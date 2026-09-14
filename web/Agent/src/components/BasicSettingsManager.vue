<!--
  BasicSettingsManager.vue
  基本设置主容器(2026-09-14 新增,2026-09-14 渲染修复)
  6 孙 Tab: LLM 模型 / 文件解析 / 安全认证 / 网络与集成 / 沙箱与任务 / 其他
  视觉风格与 EmailSettingsManager / FeishuSettingsManager 同款
  (复用 .tablist / .tab / .alert / .settings-section 等 token,零 naive-ui 依赖)
-->
<template>
  <section class="basic-settings-manager" data-testid="basic-settings-manager">
    <div class="alert warning" role="alert" data-testid="restart-banner">
      本页配置修改后需重启服务生效
    </div>

    <div class="tablist" role="tablist" aria-label="基本设置导航">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        role="tab"
        :id="`basic-tab-${tab.id}`"
        :aria-controls="`basic-panel-${tab.id}`"
        :aria-selected="activeTab === tab.id ? 'true' : 'false'"
        :tabindex="activeTab === tab.id ? 0 : -1"
        :class="['tab', { active: activeTab === tab.id }]"
        :data-testid="`basic-tab-${tab.id}`"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <section
      v-show="activeTab === 'llm'"
      :id="`basic-panel-llm`"
      role="tabpanel"
      aria-labelledby="basic-tab-llm"
      data-testid="basic-panel-llm"
    >
      <LLMSettingsPanel />
    </section>

    <section
      v-show="activeTab === 'file-parser'"
      :id="`basic-panel-file-parser`"
      role="tabpanel"
      aria-labelledby="basic-tab-file-parser"
      data-testid="basic-panel-file-parser"
    >
      <FileParserSettingsPanel />
    </section>

    <section
      v-show="activeTab === 'security'"
      :id="`basic-panel-security`"
      role="tabpanel"
      aria-labelledby="basic-tab-security"
      data-testid="basic-panel-security"
    >
      <SecuritySettingsPanel />
    </section>

    <section
      v-show="activeTab === 'network'"
      :id="`basic-panel-network`"
      role="tabpanel"
      aria-labelledby="basic-tab-network"
      data-testid="basic-panel-network"
    >
      <NetworkSettingsPanel />
    </section>

    <section
      v-show="activeTab === 'sandbox-task'"
      :id="`basic-panel-sandbox-task`"
      role="tabpanel"
      aria-labelledby="basic-tab-sandbox-task"
      data-testid="basic-panel-sandbox-task"
    >
      <SandboxTaskSettingsPanel />
    </section>

    <section
      v-show="activeTab === 'misc'"
      :id="`basic-panel-misc`"
      role="tabpanel"
      aria-labelledby="basic-tab-misc"
      data-testid="basic-panel-misc"
    >
      <MiscSettingsPanel />
    </section>
  </section>
</template>

<script setup>
/**
 * BasicSettingsManager - 基本设置主容器(2026-09-14 新增)
 *
 * 6 孙 Tab:
 * - llm         LLM 模型(主模型 / 视觉模型 / MCP Sampling / 合同 LLM)
 * - file-parser 文件解析
 * - security    安全认证(认证 Cookie / 默认管理员 / 闲置超时 / MFA / 注册审批 / 会话并发)
 * - network     网络与集成(CORS / Portal Token / 第三方执行器)
 * - sandbox-task 沙箱与任务(沙箱 / 任务调度)
 * - misc        其他(Word 输出 / 演示模式 / MapAgent MCP 标签 / Skills / DevOps 凭据 / 系统开关)
 *
 * 视觉风格:复用 EmailSettingsManager / FeishuSettingsManager 的 tablist + section + form-grid token。
 *
 * 安全设计:
 * - 主密钥状态卡 2026-09-14 渲染修复时删除(假数据 + 半暴露密钥派生信息三重理由)。
 *   如未来需要,新增后端 GET 端点 + 单独评审信息暴露风险后另起 PR。
 */
import { ref } from 'vue';
import LLMSettingsPanel from './basic-settings/LLMSettingsPanel.vue';
import FileParserSettingsPanel from './basic-settings/FileParserSettingsPanel.vue';
import SecuritySettingsPanel from './basic-settings/SecuritySettingsPanel.vue';
import NetworkSettingsPanel from './basic-settings/NetworkSettingsPanel.vue';
import SandboxTaskSettingsPanel from './basic-settings/SandboxTaskSettingsPanel.vue';
import MiscSettingsPanel from './basic-settings/MiscSettingsPanel.vue';

const tabs = [
  { id: 'llm', label: 'LLM 模型' },
  { id: 'file-parser', label: '文件解析' },
  { id: 'security', label: '安全认证' },
  { id: 'network', label: '网络与集成' },
  { id: 'sandbox-task', label: '沙箱与任务' },
  { id: 'misc', label: '其他' },
];

const activeTab = ref('llm');
</script>

<style scoped>
/* 2026-09-14 渲染修复:与 EmailSettingsManager / FeishuSettingsManager 视觉 token 对齐
   (白底卡 + tablist + 蓝色 #2563eb 下划线 + 自滚动)
   不再依赖 naive-ui。*/
.basic-settings-manager {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.tablist {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
  padding-bottom: 0;
  flex-wrap: wrap;
}

.tab {
  border: 0;
  background: transparent;
  padding: 10px 14px;
  cursor: pointer;
  color: #4b5563;
  font-size: 14px;
  border-bottom: 2px solid transparent;
  transition: color 120ms ease, border-color 120ms ease;
}

.tab:hover {
  color: #1f2937;
}

.tab.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
  font-weight: 600;
}

.basic-settings-manager > section[role="tabpanel"] {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
</style>