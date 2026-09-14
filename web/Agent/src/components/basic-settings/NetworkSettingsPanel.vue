<template>
  <div>
    <GroupFormSection group-key="cors" label="CORS 跨域" :fields="corsFields" />
    <GroupFormSection group-key="portal_auth" label="Portal 子 Token" :fields="portalFields" />
    <GroupFormSection group-key="third_party_executor" label="第三方执行器" :fields="executorFields" />
  </div>
</template>

<script setup>
import GroupFormSection from './GroupFormSection.vue';

const corsFields = [
  { name: 'allowed_origins', label: '允许的 Origin', type: 'json' },
  { name: 'allow_credentials', label: '允许携带凭据', type: 'bool' },
];

const portalFields = [
  { name: 'portal_refresh_token_ttl_seconds', label: 'Portal Token TTL(秒)', type: 'int' },
];

const executorFields = [
  { name: 'endpoints_json', label: '端点 JSON', type: 'json', multiline: true },
  { name: 'default_endpoint', label: '默认端点名', type: 'str' },
  { name: 'allow_insecure', label: '允许 http:// 端点', type: 'bool' },
];
</script>
