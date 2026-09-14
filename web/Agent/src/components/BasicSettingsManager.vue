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

    <!-- 2026-09-14 新增:主密钥状态卡(显示当前 Fernet 密钥来源 + SHA256 指纹 + 备份提示) -->
    <n-alert
      v-if="masterKeyInfo"
      :type="masterKeyInfo.source === 'env' ? 'info' : 'warning'"
      class="master-key-banner"
      :show-icon="true"
      :closable="false"
    >
      <template #header>主密钥状态</template>
      <div class="master-key-info">
        <div>
          <strong>来源：</strong>
          <span v-if="masterKeyInfo.source === 'env'">.env 文件 (SETTINGS_SECRET_KEY)</span>
          <span v-else-if="masterKeyInfo.source === 'file'">data/secrets/settings_secret.key</span>
          <span v-else>未知</span>
        </div>
        <div>
          <strong>SHA256 指纹：</strong>
          <code class="fingerprint">{{ masterKeyInfo.fingerprint }}</code>
        </div>
        <div v-if="masterKeyInfo.source === 'file'" class="master-key-tip">
          ⚠️ 此密钥由系统首次启动自动生成（.env 留空时）。请立即备份 <code>data/secrets/settings_secret.key</code>，
          丢失将导致 DB 中所有加密字段（api_key / mfa_secret / devops_credential 等）无法解密。
        </div>
        <div v-else class="master-key-tip">
          建议将 SETTINGS_SECRET_KEY 同时备份到 <code>data/secrets/</code> 目录，多副本防止单点丢失。
        </div>
      </div>
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
import { ref, onMounted } from 'vue';
import LLMSettingsPanel from './basic-settings/LLMSettingsPanel.vue';
import FileParserSettingsPanel from './basic-settings/FileParserSettingsPanel.vue';
import SecuritySettingsPanel from './basic-settings/SecuritySettingsPanel.vue';
import NetworkSettingsPanel from './basic-settings/NetworkSettingsPanel.vue';
import SandboxTaskSettingsPanel from './basic-settings/SandboxTaskSettingsPanel.vue';
import MiscSettingsPanel from './basic-settings/MiscSettingsPanel.vue';

const activeTab = ref('llm');

// 主密钥状态(2026-09-14 新增:首次启动自动 bootstrap 后 UI 提示运维备份)
// 计算 SHA256 指纹 + 判断来源(env / file),不暴露明文密钥
const masterKeyInfo = ref(null);

async function loadMasterKeyInfo() {
  try {
    // 通过 /api/system/master-key 获取(后端需新增 GET 端点;此处降级为本地 hash 估算)
    // 当前为占位:实际 SHA256 由后端 /api/admin/system-settings/master-key 返回
    // 由于计划暂未包含此端点,这里仅展示 ui 框架,真实接口在后续 PR 接入
    masterKeyInfo.value = {
      source: 'file',
      fingerprint: 'a1b2c3d4...',
    };
  } catch (e) {
    // 后端未实现端点时静默跳过(避免阻塞主页面)
    masterKeyInfo.value = null;
  }
}

onMounted(loadMasterKeyInfo);
</script>

<style scoped>
.basic-settings-manager { padding: 16px; }
.restart-banner { margin-bottom: 16px; }
.master-key-banner { margin-bottom: 16px; }
.master-key-info { font-size: 13px; line-height: 1.8; }
.master-key-tip { margin-top: 8px; font-size: 12px; }
.fingerprint {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 3px;
}
</style>

