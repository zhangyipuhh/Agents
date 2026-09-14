<template>
  <div class="network-settings-panel" data-testid="network-settings-panel">
    <GroupFormSection
      group-key="cors"
      label="CORS 跨域"
      description="跨域 origin 白名单(等保三级要求默认拒绝)"
      :fields="corsFields"
    />
    <GroupFormSection
      group-key="portal_auth"
      label="Portal 子 Token"
      description="Portal refresh token TTL 配置"
      :fields="portalFields"
    />
    <GroupFormSection
      group-key="third_party_executor"
      label="第三方执行器"
      description="第三方 SSH 命令执行器端点配置(RSA-OAEP + AES-256-GCM 加密)"
      :fields="executorFields"
    />
  </div>
</template>

<script setup>
// 网络与集成 Tab(2026-09-14 新增,渲染修复)
// 3 个 section:CORS / Portal Token / 第三方执行器
import GroupFormSection from './GroupFormSection.vue';

const corsFields = [
  { name: 'allowed_origins', label: '允许的 Origin', type: 'json', multiline: true, placeholder: '["https://app.example.com"]', description: 'JSON 数组格式,空 = 拒绝所有跨域;新跨域需求只允许通过此字段加白' },
  { name: 'allow_credentials', label: '允许携带凭据', type: 'bool', description: '是否允许 Cookie / Authorization 跨域传递;开启时 origins 不能为 *' },
];

const portalFields = [
  { name: 'portal_refresh_token_ttl_seconds', label: 'Portal Token TTL(秒)', type: 'int', description: 'Portal 子 refresh token 有效期;过期需重新签发' },
];

const executorFields = [
  { name: 'endpoints_json', label: '端点 JSON', type: 'json', multiline: true, placeholder: '[{"name":"primary","endpoint":"https://...","url":"ssh://...","public_key_pem":"-----BEGIN PUBLIC KEY-----\\n...","allow_insecure":false}]', description: '端点 JSON 配置(name/endpoint/url/public_key_pem/allow_insecure);公开密钥 PEM 必填' },
  { name: 'default_endpoint', label: '默认端点名', type: 'str', description: '端点列表中作为 fallback 的 name' },
  { name: 'allow_insecure', label: '允许 http:// 端点', type: 'bool', description: '生产环境务必关闭;仅内网调试可临时开启' },
];
</script>