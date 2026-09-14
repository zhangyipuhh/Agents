<template>
  <div>
    <GroupFormSection group-key="auth_cookie" label="认证 Cookie" :fields="cookieFields" />
    <GroupFormSection group-key="auth_bootstrap" label="默认管理员" :fields="bootstrapFields" />
    <GroupFormSection group-key="auth_idle" label="闲置超时" :fields="idleFields" />
    <GroupFormSection group-key="mfa" label="MFA 双因素" :fields="mfaFields" />
    <GroupFormSection group-key="registration_security" label="注册审批" :fields="regFields" />
    <GroupFormSection group-key="session" label="会话并发" :fields="sessionFields" />
  </div>
</template>

<script setup>
import GroupFormSection from './GroupFormSection.vue';

const cookieFields = [
  { name: 'secure', label: 'Secure 标志', type: 'bool' },
  { name: 'samesite', label: 'SameSite', type: 'str', placeholder: 'lax / strict / none' },
  { name: 'access_token_max_age', label: 'Access Token 有效期(秒)', type: 'int' },
  { name: 'refresh_token_max_age', label: 'Refresh Token 有效期(秒)', type: 'int' },
];

const bootstrapFields = [
  { name: 'bootstrap_enabled', label: '启用默认管理员创建', type: 'bool' },
  { name: 'default_admin_username', label: '默认管理员用户名', type: 'str' },
  { name: 'default_admin_password', label: '默认管理员密码', type: 'str', sensitive: true },
  { name: 'max_concurrent_sessions', label: '同账号最大并发', type: 'int' },
];

const idleFields = [
  { name: 'idle_timeout_enabled', label: '启用闲置超时', type: 'bool' },
  { name: 'idle_timeout_seconds', label: '超时(秒)', type: 'int' },
];

const mfaFields = [
  { name: 'issuer', label: 'Issuer', type: 'str' },
  { name: 'secret_key', label: 'Secret Key', type: 'str', sensitive: true },
  { name: 'mfa_required_for_admin', label: '管理员强制 MFA', type: 'bool' },
];

const regFields = [
  { name: 'enabled', label: '启用注册审批', type: 'bool' },
];

const sessionFields = [
  { name: 'agent_chat_max_concurrency', label: '聊天最大并发', type: 'int' },
];
</script>
